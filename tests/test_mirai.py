"""MiraiAPI transport is mocked; never sends a paid request or leaks credentials."""
import uuid
import httpx
import pytest
from test_api import client
from app.ai import get_key, save_key, ModelError
from app.db import db, one
from app.mirai import ask_mirai, mirai_report, available_models, MIRAI_BASE


def _config(limit=10000000, ratio=1, model='claude-opus-4.8'):
    save_key('mirai','sk-unit-test-private-token')
    r=client.post('/api/settings',json={'academy_mirai_model':model,
         'academy_mirai_ratio':ratio,'academy_daily_token_limit':limit,'academy_enabled':True})
    assert r.status_code==200
    return r.json()['settings']


def test_key_is_isolated_and_not_returned_in_settings():
    save_key('claude','sk-claude-unit-test')
    cfg=_config()
    assert cfg['mirai_configured'] and cfg['claude_configured']
    assert 'sk-unit-test' not in str(cfg)
    assert 'sk-claude-unit' not in str(cfg)
    assert get_key('mirai')=='sk-unit-test-private-token'


def test_compat_request_and_usage_formula():
    _config(ratio=2.0)
    saved={}
    def handler(request:httpx.Request):
        saved['url']=str(request.url)
        saved['auth']=request.headers.get('authorization')
        saved['payload']=request.content.decode('utf-8')
        return httpx.Response(200,json={'choices':[{'message':{'content':'Bài học từ tài liệu.'}}],
                                        'usage':{'prompt_tokens':100,'completion_tokens':20}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        out=ask_mirai('research','Hướng dẫn','Nghiên cứu sản phẩm',purpose='academy_digest',client=http,max_tokens=200)
    assert out=='Bài học từ tài liệu.'
    assert saved['url']==MIRAI_BASE+'/chat/completions'
    assert saved['auth']=='Bearer sk-unit-test-private-token'
    assert 'claude-opus-4.8' in saved['payload']
    row=one('SELECT * FROM mirai_academy_usage ORDER BY rowid DESC LIMIT 1')
    assert row['quota_used']==(100+20*5)*2
    assert row['status']=='completed'


def test_quota_checked_before_request():
    _config(limit=10000,ratio=100)
    called=[]
    def handler(request):
        called.append(1)
        return httpx.Response(200,json={})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(ModelError,match='quota'):
            ask_mirai('research','System prompt','A'*3000,purpose='academy_digest',client=http,max_tokens=1000)
    assert not called


def test_http_403_does_not_leak_key():
    _config()
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(403,json={'error':'secret'}))) as http:
        with pytest.raises(ModelError) as e:
            ask_mirai('research','system','hello',client=http)
    assert 'sk-unit-test-private' not in str(e.value)
    assert '403' in str(e.value)


def test_timeout_keeps_reservation():
    _config()
    def reject(request): raise httpx.ReadTimeout('request timed out')
    before=mirai_report()['used_quota_today']
    with httpx.Client(transport=httpx.MockTransport(reject)) as http:
        with pytest.raises(ModelError,match='dự trù'):
            ask_mirai('research','System','Content',client=http)
    assert mirai_report()['used_quota_today']>before
    assert one('SELECT status FROM mirai_academy_usage ORDER BY rowid DESC')['status']=='unknown'


def test_models_endpoint_mocked():
    _config()
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={
        'data':[{'id':'claude-opus-4.8'},{'id':'gpt-5.6-luna'}]}))) as http:
        r=available_models(client=http)
    assert r['ok'] and r['models']==['claude-opus-4.8','gpt-5.6-luna']


def test_academy_uses_mirai_key_and_independent_budget():
    _config()
    state=client.get('/api/academy').json()
    assert state['usage']['provider']=='miraiapi.com'
    assert state['usage']['configured'] is True
    assert 'quota_remaining' in state['usage']
    assert client.get('/api/bootstrap').json()['settings']['mirai_configured']
    # No Claude key is required for the academy: it uses a separate credential.
    assert get_key('mirai') and get_key('claude')


def test_paid_api_test_button_uses_small_request_and_returns_receipt():
    from app.mirai import test_mirai_completion
    _config(model='claude-opus-4.8',ratio=1.5)
    sent=[]
    def responder(request):
        sent.append(request)
        import json
        payload=json.loads(request.content)
        assert request.url.path == '/v1/chat/completions'
        assert payload['max_tokens'] == 64
        assert payload['stream'] is False
        assert payload['model'] == 'claude-opus-4.8'
        assert request.headers['authorization'] == 'Bearer sk-unit-test-private-token'
        return httpx.Response(200,json={
            'choices':[{'message':{'content':'OK'}}],
            'usage':{'prompt_tokens':17,'completion_tokens':2}
        })
    with httpx.Client(transport=httpx.MockTransport(responder)) as client_mock:
        receipt=test_mirai_completion(client=client_mock)
    assert len(sent) == 1
    assert receipt['ok'] is True
    assert receipt['reply'] == 'OK'
    assert receipt['quota_used'] == 41  # ceil((17 + 5*2)*1.5)
    assert receipt['quota_status'] == 'actual_usage'
    assert receipt['model'] == 'claude-opus-4.8'
    assert receipt['latency_ms'] >= 0
    assert 'sk-unit-test-private' not in str(receipt)
    last=one('SELECT * FROM mirai_academy_usage ORDER BY rowid DESC LIMIT 1')
    assert last['purpose']=='connection_test'
    assert last['status']=='completed'


def test_paid_test_rejects_invalid_key_without_leaking_credentials():
    from app.mirai import test_mirai_completion
    _config()
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401,json={'error':'bad API key'}))) as mock_client:
        with pytest.raises(ModelError,match='401') as err:
            test_mirai_completion(client=mock_client)
    assert 'sk-unit-test-private' not in str(err.value)


def test_paid_test_no_usage_keeps_reserved_quota():
    from app.mirai import test_mirai_completion
    _config()
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200,json={
        'choices':[{'message':{'content':'OK'}}]
    }))) as mock_client:
        result=test_mirai_completion(client=mock_client)
    assert result['quota_status']=='reserved_unknown_usage'
    assert result['prompt_tokens'] is None
    assert result['quota_used']>0
    row=one('SELECT * FROM mirai_academy_usage ORDER BY rowid DESC LIMIT 1')
    assert row['status']=='unknown'


def test_paid_test_refuses_when_internal_quota_is_exhausted():
    from app.mirai import test_mirai_completion
    _config(limit=10000,ratio=100)
    import httpx
    touched=[]
    def responder(request):
        touched.append(1)
        return httpx.Response(200,json={})
    with httpx.Client(transport=httpx.MockTransport(responder)) as client_mock:
        with pytest.raises(ModelError,match='quota'):
            test_mirai_completion(client=client_mock)
    assert not touched


def test_paid_test_api_route_is_registered_and_returns_safe_error(monkeypatch):
    from app import main
    monkeypatch.setattr(main,'test_mirai_completion',lambda: {
        'ok':True,'provider':'MiraiAPI','model':'claude-opus-4.8','reply':'OK',
        'latency_ms':42,'prompt_tokens':11,'completion_tokens':2,'quota_used':21,
        'quota_status':'actual_usage','note':'Test'} )
    r=client.post('/api/mirai/test-call')
    assert r.status_code == 200
    assert r.json()['reply'] == 'OK'
    assert 'sk-unit-test' not in str(r.json())
    def fail(): raise ModelError('MiraiAPI trả HTTP 429.')
    monkeypatch.setattr(main,'test_mirai_completion',fail)
    error=client.post('/api/mirai/test-call')
    assert error.status_code == 400
    assert '429' in error.json()['detail']
