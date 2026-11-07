"""Regression tests for source-update restart (no network or real backend)."""
from __future__ import annotations
import io
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import launcher
from fastapi.testclient import TestClient
from app.main import app, _submitted, _worker_lock


def test_source_hash_ignores_private_data_and_detects_source_changes(tmp_path):
    (tmp_path / 'app').mkdir()
    (tmp_path / 'web').mkdir()
    (tmp_path / 'web' / 'assets').mkdir()
    (tmp_path / 'data').mkdir()
    (tmp_path / '.git').mkdir()
    (tmp_path / 'requirements.txt').write_text('fastapi', encoding='utf8')
    py = tmp_path / 'app' / 'main.py'
    py.write_text('VERSION = 1', encoding='utf8')
    before = launcher.source_signature(tmp_path)
    (tmp_path / 'data' / 'cookie.txt').write_text('private session', encoding='utf8')
    (tmp_path / '.git' / 'HEAD').write_text('ref: refs/heads/main', encoding='utf8')
    (tmp_path / 'README.md').write_text('new docs only', encoding='utf8')
    assert launcher.source_signature(tmp_path) == before
    py.write_text('VERSION = 2', encoding='utf8')
    assert launcher.source_signature(tmp_path) != before
    changed = launcher.source_signature(tmp_path)
    (tmp_path / 'web' / 'assets' / 'app.js').write_text('const a = 1', encoding='utf8')
    assert launcher.source_signature(tmp_path) != changed


def test_update_health_returns_instance_id_and_supervisor_signal(monkeypatch):
    monkeypatch.setenv('AIFC_SUPERVISED', '1')
    with TestClient(app) as client:
        result = client.get('/api/health')
        assert result.status_code == 200
        body = result.json()
        assert body['instance_id'] and body['version'] == '1.14.0'
        assert body['supervised'] is True
        assert client.get('/api/system/restart-readiness').json()['ready'] is True
        with _worker_lock:
            _submitted.add('test-long-claude-task')
        try:
            busy = client.get('/api/system/restart-readiness').json()
            assert busy['ready'] is False
            assert busy['active_workers'] >= 1
        finally:
            with _worker_lock:
                _submitted.discard('test-long-claude-task')
        assert client.get('/api/system/restart-readiness').json()['ready'] is True


def test_automatic_restart_waits_for_stable_change_and_agent_finish(monkeypatch):
    clock = [0.]
    events = []
    class Process:
        def __init__(self, old=False):
            self.old = old
            self.polls = 0
            self.returncode = 0
            self.stopped = False
        def poll(self):
            self.polls += 1
            if self.stopped or (not self.old and self.polls > 2):
                return 0
            return None
    old = Process(old=True)
    new = Process()
    monkeypatch.setattr(launcher.time, 'sleep', lambda n: clock.__setitem__(0, clock[0]+n))
    monkeypatch.setattr(launcher.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(launcher, 'source_signature', lambda: 'old' if clock[0] < 2 else 'new')
    monkeypatch.setattr(launcher, 'requirements_signature', lambda: 'unchanged')
    monkeypatch.setattr(launcher, 'restart_readiness', lambda port: {'ready': clock[0] >= 14, 'reason': 'AI busy'})
    monkeypatch.setattr(launcher, 'stop_backend', lambda p, timeout_seconds=35: events.append(('stop', round(clock[0]))) or setattr(p, 'stopped', True))
    monkeypatch.setattr(launcher, 'start_backend', lambda port, log: events.append(('start', round(clock[0]))) or new)
    monkeypatch.setattr(launcher, 'wait_healthy', lambda p, port: events.append(('healthy',round(clock[0]))))
    assert launcher.supervise(old, 8765, io.StringIO()) == 0
    assert events.count(('start',14)) == 1
    assert events.index(('stop',14)) < events.index(('start',14))
    assert ('healthy',14) in events


def test_update_windows_script_uses_fast_forward_and_no_force():
    script = (ROOT / 'update_windows.bat').read_text(encoding='utf-8').lower()
    assert 'git pull --ff-only origin main' in script
    assert '--force' not in script and 'reset --hard' not in script.split('git pull')[0]
    assert (ROOT / 'start_windows.bat').exists()
