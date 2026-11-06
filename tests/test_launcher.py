"""Launcher regression tests for startup, port reuse, and offline diagnostics."""
from __future__ import annotations
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import launcher
import diagnose


def test_choose_port_reuses_same_version(monkeypatch):
    monkeypatch.setattr(launcher, 'PORTS', (18765, 18766))
    monkeypatch.setattr(launcher, 'health', lambda port: {'ok': True, 'version': launcher.APP_VERSION} if port == 18765 else None)
    monkeypatch.setattr(launcher, 'port_is_free', lambda port: port == 18766)
    assert launcher.choose_port() == (18765, True)


def test_choose_port_avoids_wrong_app(monkeypatch):
    monkeypatch.setattr(launcher, 'PORTS', (18765, 18766))
    monkeypatch.setattr(launcher, 'health', lambda port: {'ok': True, 'version':'other'} if port==18765 else None)
    monkeypatch.setattr(launcher, 'port_is_free', lambda port: port == 18766)
    assert launcher.choose_port() == (18766, False)


def test_choose_port_reports_no_ports(monkeypatch):
    monkeypatch.setattr(launcher, 'PORTS', (18765,))
    monkeypatch.setattr(launcher, 'health', lambda port: None)
    monkeypatch.setattr(launcher, 'port_is_free', lambda port: False)
    try:
        launcher.choose_port()
    except RuntimeError as exc:
        assert 'cổng' in str(exc)
    else:
        raise AssertionError('Should explain unavailable ports')


def test_offline_diagnostics_never_prints_secret(monkeypatch,tmp_path):
    monkeypatch.setenv('AIFC_DATA_DIR',str(tmp_path))
    monkeypatch.setenv('CLAUDE_API_KEY','dummy_private_key_for_test')
    text=diagnose.diagnostic_text()
    assert 'dummy_private_key_for_test' not in text
    assert 'Python:' in text and 'Quyen ghi du lieu:' in text


def test_main_reuses_existing_without_server(monkeypatch):
    monkeypatch.setattr(launcher,'choose_port',lambda: (18765,True))
    visited=[]
    monkeypatch.setattr(launcher.webbrowser,'open',lambda x: visited.append(x))
    assert launcher.main()==0
    assert visited==['http://127.0.0.1:18765/']
