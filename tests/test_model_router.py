"""Regression tests for Claude-only settings, automatic per-agent routing and costs."""
from __future__ import annotations
import json
import httpx
from pathlib import Path
from app.ai import call_llm, config, ModelError
from app.brains import (
    route_claude_model, DEFAULT_CHEAP, DEFAULT_HARD, ask_claude,
    reserve_budget, budget_settings, spent_report,
)
from app.db import db, one, run
from test_api import client


def test_routine_and_complex_tasks_are_routed_without_an_llm_classifier():
    assert route_claude_model('content','content','Viết hướng dẫn pha trà')[0] == DEFAULT_CHEAP
    assert route_claude_model('analytics','analysis','Tóm tắt số liệu này')[0] == DEFAULT_CHEAP
    assert route_claude_model('compliance','audit','Rủi ro pháp lý từ tuyên bố chữa bệnh')[0] == DEFAULT_HARD
    assert route_claude_model('ceo','ceo','Lập kế hoạch dài',hard=True)[0] == DEFAULT_HARD
    assert route_claude_model('ceo','ceo','x'*6001)[0] == DEFAULT_HARD
    assert route_claude_model('research','research','x'*6001)[0] == DEFAULT_CHEAP


def test_legacy_settings_do_not_override_claude_auto_router():
    # Simulates upgrading a pre-V1.4 local DB without discarding other data.
    run("UPDATE settings SET value='gemini' WHERE key='provider'")
    run("UPDATE settings SET value='claude-opus-5-5' WHERE key='claude_hard_model'")
    run("UPDATE settings SET value='claude-opus-5-5' WHERE key='claude_cheap_model'")
    assert config()['provider']=='claude'
    assert 'claude_hard_model' not in config()
    assert route_claude_model('content','content','Bài đăng bình thường')[0] == DEFAULT_CHEAP
    assert client.post('/api/settings',json={'claude_daily_budget_usd':1.5}).status_code==200
    assert config()['provider']=='claude'


def test_firefox_settings_patch_does_not_reset_claude_settings():
    assert client.post('/api/settings',json={'claude_daily_budget_usd':2.0,
        'claude_agent_daily_budget_usd':0.5,'auto_run_agents':True,
        'claude_cache_enabled':False,'brain_learning_enabled':False}).status_code==200
    assert client.post('/api/settings',json={'firefox_path':'C:\\Portable\\firefox.exe'}).status_code==200
    cfg=config()
    assert cfg['claude_daily_budget_usd']=='2.0'
    assert cfg['claude_agent_daily_budget_usd']=='0.5'
    assert cfg['auto_run_agents']=='1'
    assert cfg['claude_cache_enabled']=='0'
    assert cfg['brain_learning_enabled']=='0'


def test_agent_http_uses_selected_model_and_reports_actual_routing():
    from app.ai import save_key
    save_key('claude','sk-test-auto-router-only')
    assert client.post('/api/settings',json={'claude_daily_budget_usd':2,
        'claude_agent_daily_budget_usd':1,'daily_llm_call_limit':50,
        'claude_cache_enabled':False}).status_code==200
    bodies=[]
    def fake(req):
        assert req.url.path == '/v1/messages'
        b=json.loads(req.content);bodies.append(b)
        return httpx.Response(200,json={'content':[{'type':'text','text':'Kết quả đã hoàn thành.'}],
                'usage':{'input_tokens':123,'output_tokens':24}})
    with httpx.Client(transport=httpx.MockTransport(fake)) as mock:
        cheap=ask_claude('content','Quy tắc hệ thống','Viết bài giới thiệu trà',client=mock)
        hard=ask_claude('strategy','Quy tắc hệ thống','Xử lý rủi ro pháp lý',client=mock)
    assert cheap == hard == 'Kết quả đã hoàn thành.'
    assert [b['model'] for b in bodies]==[DEFAULT_CHEAP,DEFAULT_HARD]
    routing=client.get('/api/brains').json()['routing']
    assert routing['mode']=='automatic'
    assert routing['recent'][0]['model']==DEFAULT_HARD
    assert routing['recent'][0]['route_reason']=='complex_keywords'
    assert routing['recent'][1]['model']==DEFAULT_CHEAP


def test_daily_request_count_is_enforced_before_http(monkeypatch):
    assert client.post('/api/settings',json={
        'daily_llm_call_limit':1,'claude_daily_budget_usd':5,
        'claude_agent_daily_budget_usd':2}).status_code==200
    # Count a call already completed today, regardless of budget remaining.
    from app.brains import _vietnam_day_start_utc
    with db() as c:
        c.execute('DELETE FROM claude_usage')
    request_count=0
    def fake(req):
        nonlocal request_count;request_count+=1
        return httpx.Response(200,json={'content':[{'type':'text','text':'Xong.'}],
                'usage':{'input_tokens':30,'output_tokens':10}})
    with httpx.Client(transport=httpx.MockTransport(fake)) as mock:
        assert ask_claude('research','System','Tác vụ A',client=mock)
        try:
            ask_claude('research','System','Tác vụ B',client=mock)
        except ModelError as err:
            assert 'lượt gọi' in str(err).lower()
        else:
            raise AssertionError('must reject before network when daily call limit reached')
    assert request_count==1


def test_claude_check_uses_models_api_not_messages(monkeypatch):
    import httpx as library
    cls=library.Client
    requests=[]
    transport=httpx.MockTransport(lambda request: (requests.append(request) or httpx.Response(200,json={
        'data':[{'id':'claude-haiku-5-5'},{'id':'claude-sonnet-5-5'}]
    })))
    monkeypatch.setattr(library,'Client',lambda **kw:cls(transport=transport,**kw))
    r=client.post('/api/claude/check')
    assert r.status_code==200
    assert r.json()['haiku_available'] and r.json()['sonnet_available']
    assert len(requests)==1 and requests[0].url.path=='/v1/models'


def test_settings_ui_only_shows_claude_key_and_automatic_model():
    js=client.get('/assets/app.js').text
    assert 'Model Gemini' not in js and 'Model Groq' not in js
    assert 'claude_cheap_model' not in js and 'claude_hard_model' not in js
    assert 'Tự chọn model' in js
    assert 'data-action="claude.check"' in js
    assert 'Gemini hoặc Groq' not in js
