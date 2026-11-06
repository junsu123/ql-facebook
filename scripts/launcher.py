"""Windows-friendly launcher with visible diagnostics and safe port recovery.

Runs only on loopback. Reuses an already healthy instance of the same version;
when a different process occupies the preferred port, picks another local port.
No API keys, prompts, or Firefox profile contents are written to logs.
"""
from __future__ import annotations

import json
import os
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
APP_VERSION = '1.5.0'
PORTS = tuple(range(8765, 8776))


def data_dir() -> Path:
    configured = os.environ.get('AIFC_DATA_DIR')
    if configured:
        return Path(configured).expanduser().resolve()
    local = os.environ.get('LOCALAPPDATA')
    return (Path(local) / 'AI-Fanpage-Company' if local else ROOT / 'data').resolve()


def health(port: int) -> dict | None:
    try:
        url = f'http://127.0.0.1:{port}/api/health'
        with urllib.request.urlopen(url, timeout=0.6) as result:
            if result.status != 200:
                return None
            body = json.load(result)
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
    # Reuse the running version to avoid duplicate background workers.
    for port in PORTS:
        existing = health(port)
        if existing and existing.get('version') == APP_VERSION:
            return port, True
    for port in PORTS:
        if port_is_free(port):
            return port, False
    raise RuntimeError('Các cổng 8765–8775 đều bận. Hãy đóng ứng dụng đang dùng cổng hoặc khởi động lại máy.')


def log_folder() -> Path:
    folder = data_dir() / 'logs'
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def main() -> int:
    print('AI Fanpage Company v' + APP_VERSION, flush=True)
    try:
        port, running = choose_port()
        url = f'http://127.0.0.1:{port}/'
        if running:
            print('Phần mềm đang chạy. Đang mở lại giao diện:', url, flush=True)
            webbrowser.open(url)
            return 0
        logs = log_folder()
        log_path = logs / 'startup.log'
        with log_path.open('a', encoding='utf-8', errors='replace') as logfile:
            logfile.write(f'\n=== START {datetime.now().isoformat(timespec="seconds")} | Python {sys.version.split()[0]} | port {port} ===\n')
            logfile.flush()
            proc = subprocess.Popen(
                [sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(port)],
                cwd=str(ROOT), stdin=subprocess.DEVNULL, stdout=logfile, stderr=subprocess.STDOUT,
            )
            try:
                for _ in range(80):
                    if proc.poll() is not None:
                        raise RuntimeError(f'Máy chủ dừng với mã lỗi {proc.returncode}.')
                    if health(port):
                        break
                    time.sleep(0.25)
                else:
                    raise RuntimeError('Máy chủ không phản hồi sau khi khởi động.')
                print('Đã chạy:', url, flush=True)
                print('Nhật ký kỹ thuật:', log_path, flush=True)
                webbrowser.open(url)
                return proc.wait()
            except KeyboardInterrupt:
                proc.terminate()
                try:
                    proc.wait(timeout=7)
                except subprocess.TimeoutExpired:
                    proc.kill()
                return 0
            except Exception:
                if proc.poll() is None:
                    proc.terminate()
                raise
    except Exception as exc:
        print('\n[LOI KHOI DONG]', str(exc), flush=True)
        try:
            print('Xem nhật ký:', log_folder() / 'startup.log', flush=True)
        except OSError:
            pass
        print('Chạy: python scripts\\diagnose.py để kiểm tra Python, Firefox, thư viện và cổng.', flush=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
