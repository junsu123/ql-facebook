"""Installer tests avoid downloading or executing a real installer."""
from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

from app import firefox_installer as fi
from app.main import app
from fastapi.testclient import TestClient


def test_architecture_selection_and_official_download_url():
    assert fi.windows_architecture('AMD64') == 'win64'
    assert fi.windows_architecture('aarch64') == 'win64-aarch64'
    assert fi.windows_architecture('x86') == 'win'
    assert 'os=win64-aarch64' in fi.download_url('win64-aarch64')
    assert 'lang=vi' in fi.download_url('win64')
    with pytest.raises(fi.FirefoxInstallError):
        fi.windows_architecture('unknown-chip')
    with pytest.raises(fi.FirefoxInstallError):
        fi.download_url('macOS')


def test_download_hosts_are_strictly_limited():
    assert fi._trusted_https('https://download.mozilla.org/?product=firefox-latest')
    assert fi._trusted_https('https://download-installer.cdn.mozilla.net/path/Firefox.exe')
    for url in (
        'http://download.mozilla.org/unsafe.exe',
        'https://download.mozilla.org.evil.example/unsafe.exe',
        'https://example.com/installer.exe',
        'https://alice:secret@download.mozilla.org/unsafe.exe',
    ):
        assert not fi._trusted_https(url)


def test_download_checks_executable_magic_and_integrity(monkeypatch, tmp_path):
    data = b'MZ' + bytes(140_000)

    class Response:
        headers = {'Content-Length': str(len(data))}
        def __init__(self): self.pos = 0
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def geturl(self): return 'https://download-installer.cdn.mozilla.net/path/Firefox_Setup.exe'
        def read(self, n):
            part = data[self.pos:self.pos+n]
            self.pos += len(part)
            return part

    class Opener:
        def open(self, request, timeout): return Response()

    monkeypatch.setattr(fi, 'build_opener', lambda _: Opener())
    target = tmp_path / 'installer.exe'
    checksum = fi._fetch_installer(target, 'win64')
    assert target.read_bytes() == data
    assert checksum == hashlib.sha256(data).hexdigest()
    assert not target.with_name('installer.exe.part').exists()


def test_bad_download_never_becomes_executable(monkeypatch, tmp_path):
    class Response:
        headers = {'Content-Length': '120000'}
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def geturl(self): return 'https://download-installer.cdn.mozilla.net/path/installer.exe'
        def read(self, _): return b'<html>Not an installer</html>'
    class Opener:
        def open(self, request, timeout): return Response()
    monkeypatch.setattr(fi, 'build_opener', lambda _: Opener())
    target = tmp_path / 'installer.exe'
    with pytest.raises(fi.FirefoxInstallError):
        fi._fetch_installer(target, 'win')
    assert not target.exists()
    assert not target.with_name('installer.exe.part').exists()


def test_browser_installer_api_is_safe_on_non_windows():
    client = TestClient(app)
    status = client.get('/api/firefox/installer')
    assert status.status_code == 200
    assert 'installed' in status.json()
    assert 'support' in status.json()
    assert 'download_page' in status.json()
    if not status.json()['support']['supported']:
        result = client.post('/api/firefox/installer')
        assert result.status_code == 409
