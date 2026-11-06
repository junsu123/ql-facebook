"""Local Windows launcher and *supervisor* for safe restarts after source updates.

Start this from start_windows.bat.  The parent process supervises Uvicorn,
observes stable changes to app/web/scripts/dependencies, lets running AI jobs
finish, then restarts the server.  It never downloads or executes remote code
on its own.  Use a deliberate `git pull --ff-only` or update_windows.bat.
"""
from __future__ import annotations

import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_VERSION = '1.7.0'
PORTS = tuple(range(8765, 8776))
CHECK_INTERVAL_SECONDS = 2.0
STABLE_FOR_SECONDS = 5.0  # Prevent restarts while git is still writing files.
WATCH_EXTENSIONS = {'.py', '.js', '.css', '.html', '.jpg', '.jpeg', '.png', '.json', '.svg'}


def data_dir() -> Path:
    configured = os.environ.get('AIFC_DATA_DIR')
    if configured:
        return Path(configured).expanduser().resolve()
    local = os.environ.get('LOCALAPPDATA')
    return (Path(local) / 'AI-Fanpage-Company' if local else ROOT / 'data').resolve()


def health(port: int) -> dict | None:
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health', timeout=0.65) as resp:
            if resp.status != 200:
                return None
            body = json.load(resp)
            return body if isinstance(body, dict) and body.get('ok') is True else None
    except (OSError, TimeoutError, ValueError, urllib.error.URLError):
        return None


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(('127.0.0.1', port))
            return True
        except OSError:
            return False


def choose_port() -> tuple[int, bool]:
    for port in PORTS:
        existing = health(port)
        if existing and existing.get('supervised') is True:
            return port, True
        if existing and existing.get('version') == APP_VERSION:
            return port, True
        if existing and 'data_dir' in existing and 'firefox_available' in existing:
            raise RuntimeError(f'Đang chạy AI Fanpage Company bản cũ tại cổng {port}. '
                               'Đóng cửa sổ cũ (Ctrl+C), rồi chạy lại start_windows.bat một lần '
                               'để kích hoạt tự khởi động lại.')
    for port in PORTS:
        if port_is_free(port):
            return port, False
    raise RuntimeError('Các cổng 8765–8775 đều bận. Hãy đóng ứng dụng đang dùng cổng hoặc khởi động lại máy.')


def log_folder() -> Path:
    folder = data_dir() / 'logs'
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def source_signature(root: Path = ROOT) -> str:
    """Fingerprint source changes, not cache, SQLite, browser sessions or logs.

    Hash bytes, not just timestamps: zipped updates may preserve mtimes.  This
    intentionally excludes README and .git contents because they don't affect
    the running application.  Changes made over time are debounced by supervisor.
    """
    files = [root / 'requirements.txt', root / 'start_windows.bat']
    for folder in ('app', 'web', 'scripts'):
        base = root / folder
        if base.is_dir():
            for path in base.rglob('*'):
                if (path.is_file() and path.suffix.lower() in WATCH_EXTENSIONS and
                        '__pycache__' not in path.parts):
                    files.append(path)
    total = hashlib.sha256()
    for path in sorted(set(files)):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix().encode('utf-8')
        total.update(len(rel).to_bytes(4, 'big'))
        total.update(rel)
        # File contents are read in chunks to avoid loading media into memory.
        with path.open('rb') as stream:
            while chunk := stream.read(128 * 1024):
                total.update(chunk)
    return total.hexdigest()


def requirements_signature(root: Path = ROOT) -> str:
    path = root / 'requirements.txt'
    return hashlib.sha256(path.read_bytes() if path.is_file() else b'').hexdigest()


def restart_readiness(port: int) -> dict:
    """Consult *this* server's in-memory worker state before restart."""
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/system/restart-readiness', timeout=1) as resp:
            body = json.load(resp)
            if resp.status == 200 and isinstance(body, dict):
                return body
    except (OSError, ValueError, urllib.error.URLError):
        # The previous app version or a crashed server may not expose this API.
        pass
    return {'ready': True, 'reason': 'Endpoint chưa hỗ trợ hoặc backend không phản hồi.'}


def _timestamp() -> str:
    return datetime.now().isoformat(timespec='seconds')


def _append_log(file, message: str) -> None:
    line = f'[{_timestamp()}] {message}'
    print(line, flush=True)
    file.write(line + '\n')
    file.flush()


def start_backend(port: int, logfile) -> subprocess.Popen:
    windows_flags = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {}
    return subprocess.Popen(
        [sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(port)],
        cwd=str(ROOT), stdin=subprocess.DEVNULL, stdout=logfile, stderr=subprocess.STDOUT,
        env={**os.environ, 'AIFC_SUPERVISED': '1'}, **windows_flags,
    )


def wait_healthy(proc: subprocess.Popen, port: int, timeout_seconds: float = 30) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f'Máy chủ dừng với mã lỗi {proc.returncode}.')
        if health(port):
            return
        time.sleep(0.25)
    raise RuntimeError('Máy chủ không phản hồi sau khi khởi động.')


def stop_backend(proc: subprocess.Popen, timeout_seconds: float = 35) -> None:
    if proc.poll() is not None:
        return
    try:
        if os.name == 'nt':
            # Best-effort console interrupt for the process group. Some Windows
            # configurations cannot deliver this; then use terminate fallback.
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            proc.terminate()  # SIGTERM handled gracefully by Uvicorn on POSIX.
        proc.wait(timeout=timeout_seconds)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        if proc.poll() is None:
            proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def install_changed_requirements(logfile) -> None:
    """Install new dependencies after backend stopped; fail visibly on errors."""
    _append_log(logfile, 'Đang kiểm tra/cài thư viện của bản cập nhật...')
    result = subprocess.run(
        [sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', '-r', str(ROOT / 'requirements.txt')],
        cwd=str(ROOT), stdin=subprocess.DEVNULL, stdout=logfile, stderr=subprocess.STDOUT,
        env={**os.environ, 'AIFC_SUPERVISED': '1'},
        timeout=240, check=False,
    )
    if result.returncode:
        raise RuntimeError(f'Không cài được thư viện của bản mới (mã {result.returncode}). Xem startup.log.')


def supervise(proc: subprocess.Popen, port: int, logfile) -> int:
    """Watch a running server; restart once after each stable source update."""
    fingerprint = source_signature()
    req_fingerprint = requirements_signature()
    pending = None
    pending_at = 0.0
    last_wait_notice = 0.0
    try:
        while True:
            time.sleep(CHECK_INTERVAL_SECONDS)
            if proc.poll() is not None:
                return proc.returncode or 0
            try:
                new_fingerprint = source_signature()
            except OSError as exc:
                _append_log(logfile, f'Đang cập nhật file; kiểm tra lại: {type(exc).__name__}')
                continue
            if new_fingerprint == fingerprint:
                pending = None
                continue
            if pending != new_fingerprint:
                pending = new_fingerprint
                pending_at = time.monotonic()
                _append_log(logfile, 'Đã phát hiện mã nguồn thay đổi. Đang đợi tải/ghi file hoàn tất...')
                continue
            if time.monotonic() - pending_at < STABLE_FOR_SECONDS:
                continue
            readiness = restart_readiness(port)
            if not readiness.get('ready', False):
                if time.monotonic() - last_wait_notice > 25:
                    _append_log(logfile, 'Đợi các tác vụ AI hiện tại hoàn tất trước khi cập nhật: ' + str(readiness.get('reason', 'Đang bận.'))[:180])
                    last_wait_notice = time.monotonic()
                continue
            _append_log(logfile, 'Bắt đầu khởi động lại để áp dụng code mới...')
            stop_backend(proc)
            try:
                next_reqs = requirements_signature()
                if next_reqs != req_fingerprint:
                    install_changed_requirements(logfile)
                    req_fingerprint = next_reqs
                proc = start_backend(port, logfile)
                wait_healthy(proc, port)
            except Exception as exc:
                _append_log(logfile, 'CẬP NHẬT THẤT BẠI: ' + str(exc))
                if 'proc' in locals() and proc.poll() is None:
                    stop_backend(proc)
                raise
            fingerprint = source_signature()  # Use actual code; changes may arrive during startup.
            pending = None
            _append_log(logfile, f'Khởi động lại thành công tại http://127.0.0.1:{port}/. Trình duyệt sẽ tự tải lại.')

    finally:
        stop_backend(proc)


def main() -> int:
    print('AI Fanpage Company v' + APP_VERSION + ' - Auto Restart Supervisor', flush=True)
    try:
        port, running = choose_port()
        url = f'http://127.0.0.1:{port}/'
        if running:
            print('Phần mềm đang chạy. Đang mở lại giao diện:', url, flush=True)
            webbrowser.open(url)
            return 0
        logfile_path = log_folder() / 'startup.log'
        with logfile_path.open('a', encoding='utf-8', errors='replace') as logfile:
            _append_log(logfile, f'=== START | Python {sys.version.split()[0]} | port {port} | supervisor ===')
            proc = start_backend(port, logfile)
            try:
                wait_healthy(proc, port)
                print('Đã chạy:', url, flush=True)
                print('Tự khởi động lại: BẬT khi nguồn code thay đổi và nhiệm vụ AI đã hoàn tất.', flush=True)
                print('Nhật ký kỹ thuật:', logfile_path, flush=True)
                webbrowser.open(url)
                return supervise(proc, port, logfile)
            except KeyboardInterrupt:
                _append_log(logfile, 'Người dùng đã dừng ứng dụng.')
                return 0
            finally:
                stop_backend(proc)
    except Exception as exc:
        print('\n[LOI KHOI DONG / CAP NHAT]', str(exc), flush=True)
        try:
            print('Xem nhật ký:', log_folder() / 'startup.log', flush=True)
        except OSError:
            pass
        print('Chạy: diagnose_windows.bat để kiểm tra lỗi.', flush=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
