"""User-approved Mozilla Firefox installer for the local Windows dashboard.

Downloads the latest stable Windows installer only from Mozilla HTTPS endpoints,
verifies its Windows Authenticode signature, and launches the normal interactive
installer. Never runs an executable from an unverified source.
"""
from __future__ import annotations

import hashlib
import os
import platform
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .db import BASE, log

MOZILLA_DOWNLOAD = 'https://download.mozilla.org/'
MOZILLA_DOWNLOAD_PAGE = 'https://www.firefox.com/vi/firefox/new/'
ALLOWED_HOSTS = frozenset({
    'download.mozilla.org', 'download-installer.cdn.mozilla.net',
    'releases.mozilla.org', 'ftp.mozilla.org', 'archive.mozilla.org',
})
MAX_INSTALLER_BYTES = 250 * 1024 * 1024
INSTALLER_DIR = BASE / 'installers'
_lock = threading.Lock()
_state: dict = {
    'state': 'idle', 'percent': 0, 'downloaded_bytes': 0,
    'total_bytes': None, 'message': '', 'error': '',
    'sha256': '', 'architecture': None,
}


class FirefoxInstallError(Exception):
    pass


def windows_architecture(machine: str) -> str:
    """Map Windows native CPU architecture to Mozilla's platform token."""
    value = machine.strip().lower()
    if value in ('arm64', 'aarch64'):
        return 'win64-aarch64'
    if value in ('amd64', 'x86_64', 'x64'):
        return 'win64'
    if value in ('x86', 'i386', 'i686'):
        return 'win'
    raise FirefoxInstallError(f'Kiến trúc CPU Windows chưa được hỗ trợ: {machine}')


def system_architecture() -> str:
    # PROCESSOR_ARCHITEW6432 shows the native host even from a 32-bit Python.
    machine = (os.environ.get('PROCESSOR_ARCHITEW6432')
               or os.environ.get('PROCESSOR_ARCHITECTURE')
               or platform.machine())
    return windows_architecture(machine)


def install_support() -> dict:
    if os.name != 'nt':
        return {'supported': False, 'reason': 'Chức năng cài tự động chỉ hỗ trợ Windows. Hãy cài Firefox bằng trình quản lý gói của hệ điều hành.', 'architecture': None}
    winver = getattr(sys, 'getwindowsversion', lambda: None)()
    if winver and winver.major < 10:
        return {'supported': False, 'reason': 'Firefox bản mới không hỗ trợ Windows 8.1 trở xuống. Vui lòng xem bản ESR trên trang Mozilla.', 'architecture': None}
    try:
        arch = system_architecture()
    except FirefoxInstallError as exc:
        return {'supported': False, 'reason': str(exc), 'architecture': None}
    return {'supported': True, 'reason': '', 'architecture': arch}


def download_url(architecture: str) -> str:
    if architecture not in ('win', 'win64', 'win64-aarch64'):
        raise FirefoxInstallError('Kiến trúc không hợp lệ.')
    return MOZILLA_DOWNLOAD + '?' + urlencode({'product': 'firefox-latest', 'os': architecture, 'lang': 'vi'})


def _trusted_https(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == 'https' and parsed.hostname in ALLOWED_HOSTS and not parsed.username and not parsed.password


class MozillaOnlyRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _trusted_https(newurl):
            raise FirefoxInstallError('Máy chủ chuyển hướng không thuộc hệ thống tải Firefox của Mozilla.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _change(**kwargs) -> None:
    with _lock:
        _state.update(kwargs)


def status() -> dict:
    from .firefox import executable
    current_exe = executable()
    available = current_exe is not None
    with _lock:
        state = dict(_state)
        if available and state['state'] in ('idle', 'installer_opened', 'checking', 'completed'):
            state['state'] = 'completed'
            state['message'] = 'Firefox đã được tìm thấy trên máy.'
            _state['state'] = 'completed'
    return {
        **state,
        'installed': available,
        'executable': current_exe,
        'support': install_support(),
        'download_page': MOZILLA_DOWNLOAD_PAGE,
    }


def _fetch_installer(target: Path, architecture: str) -> str:
    url = download_url(architecture)
    opener = build_opener(MozillaOnlyRedirects())
    request = Request(url, headers={'User-Agent': 'AI-Fanpage-Company-FirefoxInstaller/1.1'})
    digest = hashlib.sha256()
    written = 0
    partial = target.with_name(target.name + '.part')
    try:
        with opener.open(request, timeout=45) as response:
            final_url = response.geturl()
            if not _trusted_https(final_url):
                raise FirefoxInstallError('Từ chối tải tệp từ địa chỉ không phải Mozilla.')
            declared = response.headers.get('Content-Length')
            total = int(declared) if declared and declared.isdigit() else None
            if total and total > MAX_INSTALLER_BYTES:
                raise FirefoxInstallError('Tệp cài đặt lớn bất thường, đã hủy tải.')
            _change(total_bytes=total)
            with partial.open('wb') as output:
                first = response.read(65536)
                if len(first) < 2 or not first.startswith(b'MZ'):
                    raise FirefoxInstallError('Tệp tải về không phải bộ cài Windows hợp lệ.')
                output.write(first)
                digest.update(first)
                written += len(first)
                while True:
                    block = response.read(256 * 1024)
                    if not block:
                        break
                    written += len(block)
                    if written > MAX_INSTALLER_BYTES:
                        raise FirefoxInstallError('Tệp vượt giới hạn dung lượng cho phép.')
                    output.write(block)
                    digest.update(block)
                    _change(downloaded_bytes=written, percent=min(99, int(written * 100 / total)) if total else None)
        if written < 100_000:
            raise FirefoxInstallError('Tệp tải về quá nhỏ, có thể không phải bộ cài Firefox đầy đủ.')
        if total and written != total:
            raise FirefoxInstallError('Tệp tải về chưa đầy đủ.')
        partial.replace(target)
        return digest.hexdigest()
    finally:
        partial.unlink(missing_ok=True)


def _verify_mozilla_signature(installer: Path) -> None:
    """Require a valid Windows Authenticode signature issued to Mozilla Corporation."""
    if os.name != 'nt':
        raise FirefoxInstallError('Chỉ xác minh và chạy bộ cài trên Windows.')
    quoted = str(installer).replace("'", "''")
    script = (
        f"$s=Get-AuthenticodeSignature -LiteralPath '{quoted}'; "
        "if ($s.Status -eq 'Valid' -and $s.SignerCertificate -and "
        "$s.SignerCertificate.Subject -match '(^|,\\s*)O=Mozilla Corporation(,|$)') "
        "{ Write-Output 'VALID_MOZILLA' } else { exit 7 }"
    )
    try:
        result = subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
            capture_output=True, text=True, timeout=50,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FirefoxInstallError('Không thể kiểm tra chữ ký số Windows. Đã từ chối chạy bộ cài.') from exc
    if result.returncode != 0 or result.stdout.strip() != 'VALID_MOZILLA':
        raise FirefoxInstallError('Chữ ký số của bộ cài không hợp lệ hoặc không thuộc Mozilla Corporation.')


def _install_worker(arch: str) -> None:
    from .firefox import executable
    installer = INSTALLER_DIR / f'Firefox_Setup_{arch}_vi.exe'
    try:
        INSTALLER_DIR.mkdir(parents=True, exist_ok=True)
        _change(state='downloading', message='Đang tải Firefox chính thức từ Mozilla…', error='', percent=0, downloaded_bytes=0, total_bytes=None, sha256='', architecture=arch)
        digest = _fetch_installer(installer, arch)
        _change(state='verifying', percent=100, sha256=digest, message='Đang xác minh chữ ký số Mozilla…')
        _verify_mozilla_signature(installer)
        _change(state='installer_opened', message='Đã mở trình cài Firefox. Hãy làm theo cửa sổ cài đặt và chấp thuận UAC nếu bạn đồng ý.')
        # Windows ShellExecute handles installer manifests / UAC with user consent.
        os.startfile(str(installer))  # type: ignore[attr-defined]
        log('publishing', 'firefox_installer_opened', 'Đã tải và xác minh bộ cài Firefox chính thức; người dùng quyết định cài đặt.')
        # Track installation outcome without accessing credentials or running a silent install.
        for _ in range(120):
            if executable():
                _change(state='completed', message='Firefox đã cài đặt và được phần mềm nhận diện.')
                return
            time.sleep(2)
        _change(state='attention', message='Chưa xác nhận được Firefox sau khi mở bộ cài. Hãy hoàn tất cài đặt rồi bấm Kiểm tra lại.')
    except (FirefoxInstallError, OSError, ValueError) as exc:
        _change(state='error', error=str(exc), message='Không thể cài Firefox tự động. Bạn có thể tải trực tiếp từ Mozilla.')
    except Exception:
        _change(state='error', error='Có lỗi không xác định khi tải/cài Firefox.', message='Đã dừng để bảo vệ máy tính.')
    finally:
        # Keep verified installer available for retry only when needed; never commit it.
        pass


def start_install() -> dict:
    from .firefox import executable
    if executable():
        raise FirefoxInstallError('Máy đã có Firefox. Không cần tải và cài đặt lại.')
    support = install_support()
    if not support['supported']:
        raise FirefoxInstallError(support['reason'])
    with _lock:
        if _state['state'] in ('downloading', 'verifying', 'installer_opened'):
            raise FirefoxInstallError('Quá trình tải/cài Firefox đang diễn ra.')
        _state.update(state='downloading', percent=0, downloaded_bytes=0, total_bytes=None, error='', message='Đang chuẩn bị tải Firefox…', architecture=support['architecture'])
    worker = threading.Thread(target=_install_worker, args=(support['architecture'],), daemon=True, name='aifc-firefox-installer')
    worker.start()
    return status()
