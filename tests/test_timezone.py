"""Windows may not have an IANA tz database; Claude billing must still work."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfoNotFoundError

import app.brains as brains
from app.db import db


def test_vietnam_midnight_has_correct_utc_boundary():
    # 23:59 local on Nov 6, then 00:00 on Nov 7.
    assert brains._vietnam_day_start_utc(datetime(2026,11,6,16,59,tzinfo=timezone.utc)) == '2026-11-05T17:00:00+00:00'
    assert brains._vietnam_day_start_utc(datetime(2026,11,6,17,0,tzinfo=timezone.utc)) == '2026-11-06T17:00:00+00:00'


def test_without_tzdata_budget_still_loads(monkeypatch):
    def no_iana(_key):
        raise ZoneInfoNotFoundError('No time zone found with key Asia/Ho_Chi_Minh')
    monkeypatch.setattr(brains,'ZoneInfo',no_iana)
    assert brains._vietnam_day_start_utc(datetime(2026,11,6,17,0,tzinfo=timezone.utc)) == '2026-11-06T17:00:00+00:00'
    with db() as c:
        assert brains._spent_today(c) >= 0
    overview=brains.agent_brain_overview()
    assert 'cost' in overview and 'agents' in overview


def test_bootstrap_succeeds_without_iana_timezone(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    def no_iana(_key):
        raise ZoneInfoNotFoundError('Missing tzdata')
    monkeypatch.setattr(brains,'ZoneInfo',no_iana)
    with TestClient(app) as client:
        response=client.get('/api/bootstrap')
    assert response.status_code == 200, response.text
    assert 'brain_overview' in response.json()
