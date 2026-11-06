import os
import tempfile
from pathlib import Path

# Isolate the tests from the user's real data, before importing the app.
os.environ['AIFC_DATA_DIR']=tempfile.mkdtemp(prefix='aifc-test-')
from fastapi.testclient import TestClient
from app.main import app

client=TestClient(app)

def test_health_dashboard_empty():
    resp=client.get('/api/health')
    assert resp.status_code==200 and resp.json()['ok']
    data=client.get('/api/bootstrap').json()
    assert data['counts']['pages']==0
    assert len(data['agents'])==9


def test_accounts_pages_memory_and_draft():
    resp=client.post('/api/accounts',json={'label':'Profile Test','auto_open':False})
    assert resp.status_code==200
    acc=resp.json()['account']
    assert Path(acc['profile_path']).is_dir()
    resp=client.post('/api/accounts/'+acc['id']+'/confirm',json={'name':'Marketing Test'})
    assert resp.status_code==200 and resp.json()['confirmed']==1
    page=client.post('/api/pages',json={
        'name':'Fanpage trà thảo mộc thử nghiệm','url':'https://www.facebook.com/my-tea-page',
        'category':'Trà thảo mộc','tone':'Thân thiện','facts':'Trà túi lọc: 30 gói x 3g; pha nước nóng 5-10 phút.',
        'account_id':acc['id']
    }).json()
    assert page['account_id']==acc['id']
    dup=client.post('/api/pages',json={'name':'Duplicate','url':page['url']})
    assert dup.status_code==409
    memory=client.post('/api/pages/'+page['id']+'/memory',json={'note':'Khách quan tâm đến cách pha trà.'})
    assert memory.status_code==200
    draft=client.post('/api/contents',json={
        'page_id':page['id'],'topic':'Hướng dẫn pha trà',
        'body':'Bạn muốn thưởng thức trà túi lọc tại nhà? Hãy dùng nước nóng, ủ 5–10 phút theo hướng dẫn trên bao bì.'
    }).json()
    approved=client.post('/api/contents/'+draft['id']+'/review').json()
    assert approved['status']=='approved'
    schedule=client.post('/api/contents/'+draft['id']+'/schedule',json={'scheduled_at':'2031-11-06T11:00:00+07:00'})
    assert schedule.status_code==200
    assert schedule.json()['status']=='scheduled'
    cancel=client.post('/api/contents/'+draft['id']+'/cancel-schedule')
    assert cancel.status_code==200
    # No implicit claim of Meta posting: only explicit manual confirmation.
    posted=client.post('/api/contents/'+draft['id']+'/complete',json={'confirmed':True,'post_url':''})
    assert posted.status_code==200 and posted.json()['status']=='published_manual'


def test_policy_and_learning():
    page=client.get('/api/bootstrap').json()['pages'][0]
    bad=client.post('/api/contents',json={'page_id':page['id'],'topic':'Bad claim',
      'body':'Đây là thuốc thần dược có thể chữa khỏi mọi bệnh và chắc chắn khỏi 100% ngay.'}).json()
    result=client.post('/api/contents/'+bad['id']+'/review').json()
    assert result['status']=='needs_revision'
    rows=[{'page_id':page['id'],'date':f'2026-11-{i:02d}','views':100*i,'likes':i*2,'comments':i,'shares':i//2} for i in range(1,6)]
    imported=client.post('/api/metrics/import',json={'rows':rows})
    assert imported.status_code==200 and imported.json()['imported']==5
    learned=client.post('/api/pages/'+page['id']+'/learn')
    assert learned.status_code==200 and learned.json()['samples']==5
    assert '5 bản ghi KPI' in learned.json()['note']


def test_ceo_without_model_key_does_not_fabricate_work():
    cfg=client.get('/api/bootstrap').json()['settings']
    # This test assumes no externally provisioned key in test environment.
    if cfg.get('claude_configured'):
        return
    r=client.post('/api/ceo/chat',json={'message':'Giao nhân viên viết kế hoạch 7 ngày cho Fanpage.'})
    assert r.status_code==200
    assert r.json()['mode']=='awaiting_ai_configuration'
    task_id=r.json()['task_ids'][0]
    tasks=client.get('/api/bootstrap').json()['tasks']
    assert next(t for t in tasks if t['id']==task_id)['status']=='queued'


def test_security_and_validation():
    assert client.post('/api/pages',json={'name':'Test bad','url':'https://evil.example/x'}).status_code==400
    assert client.get('/api/bootstrap',headers={'host':'example.com'}).status_code==403
    assert client.post('/api/tasks',json={'agent_id':'malicious','title':'Test task'}).status_code==400

def test_ceo_campaign_batch_and_auto_run_switch():
    page=client.get('/api/bootstrap').json()['pages'][0]
    r=client.post('/api/ceo/campaigns',json={'topic':'Hướng dẫn dùng trà an toàn','max_pages':5})
    assert r.status_code==200
    assert r.json()['queued']>=1
    task=next(t for t in client.get('/api/bootstrap').json()['tasks'] if t['source']=='ceo_campaign')
    assert task['page_id']==page['id']
    cfg=client.get('/api/bootstrap').json()['settings']
    payload={'daily_llm_call_limit':20,'auto_run_agents':False,'firefox_path':''}
    assert client.post('/api/settings',json=payload).status_code==200
    assert client.get('/api/bootstrap').json()['settings']['auto_run_agents']=='0'

# V1.3 independent brains + bounded Claude escalation (all mocked, zero API charges).
def test_brains_independent_memory_and_continuous_local_learning():
    from app.brains import enqueue_learning, learning_tick, relevant_memories
    assert client.get('/api/brains').status_code == 200
    assert len(client.get('/api/brains').json()['agents']) == 9
    enqueue_learning('research','task_completed','Nghiên cứu chủ đề trà túi lọc mùa đông',source_ref='TEST-RESEARCH')
    enqueue_learning('strategy','task_completed','Kế hoạch nội dung từng tuần cho mùa hè',source_ref='TEST-STRATEGY')
    result = client.post('/api/brains/learn-now')
    assert result.status_code == 200 and result.json()['processed'] >= 2
    research = client.get('/api/brains/research/memories').json()['items']
    strategy = client.get('/api/brains/strategy/memories').json()['items']
    assert any('mùa đông' in x['content'] for x in research)
    assert all('mùa đông' not in x['content'] for x in strategy)
    assert relevant_memories('research','trà mùa đông',limit=3)
    assert not relevant_memories('creative','trà mùa đông',limit=3)
    assert all(x['confidence'] == 'unverified' for x in research)
    assert client.get('/api/brains/malicious/memories').status_code == 404


def test_claude_settings_and_encrypted_secret():
    from app.ai import SECRETS_FILE, get_key
    new = client.post('/api/settings',json={
        'claude_key':'sk-test-fake-local-only',
        'claude_daily_budget_usd':1.5,'claude_agent_daily_budget_usd':0.4,
        'claude_cache_enabled':True,'brain_learning_enabled':True,
    })
    assert new.status_code == 200
    cfg = client.get('/api/bootstrap').json()['settings']
    assert cfg['claude_configured'] is True
    assert 'sk-test' not in str(cfg)
    assert get_key('claude') == 'sk-test-fake-local-only'
    assert b'sk-test-fake-local-only' not in SECRETS_FILE.read_bytes()
    assert cfg['provider']=='claude' and cfg['model_selection']=='automatic'
    assert 'gemini_model' not in cfg and 'groq_model' not in cfg
    bad=client.post('/api/settings',json={'claude_hard_model':'claude-opus-5-5'})
    assert bad.status_code == 422
    assert client.post('/api/settings',json={'provider':'gemini'}).status_code == 422


def test_claude_usage_bill_cache_and_no_repeat_http():
    import httpx
    from app.brains import ask_claude, spent_report
    calls=[]
    def mock_response(req):
        calls.append(req)
        assert req.url.host=='api.anthropic.com'
        assert req.headers['anthropic-version']=='2023-06-01'
        assert req.headers['x-api-key']=='sk-test-fake-local-only'
        import json
        body=json.loads(req.content)
        assert body['model']=='claude-haiku-5-5'
        return httpx.Response(200,json={'content':[{'type':'text','text':'Bài học hữu ích từ dữ liệu đã xác nhận.'}],
                                        'usage':{'input_tokens':220,'output_tokens':80,'cache_read_input_tokens':0,'cache_creation_input_tokens':0}})
    with httpx.Client(transport=httpx.MockTransport(mock_response)) as mock_client:
        a=ask_claude('research','Quy tắc phân tích marketing.', 'Đề xuất kế hoạch nghiên cứu sản phẩm.',client=mock_client,max_tokens=200)
        b=ask_claude('research','Quy tắc phân tích marketing.', 'Đề xuất kế hoạch nghiên cứu sản phẩm.',client=mock_client,max_tokens=200)
    assert a==b
    assert len(calls)==1  # second request reused exact local response
    report=spent_report()
    assert report['today_usd']>0
    assert report['agents']['research']>0
    assert client.get('/api/brains').json()['cost']['today_usd']>0


def test_claude_dollar_cap_rejects_requests_before_network():
    from app.brains import ask_claude
    from app.ai import ModelError
    changed=client.post('/api/settings',json={'claude_daily_budget_usd':0,
                                            'claude_agent_daily_budget_usd':0})
    assert changed.status_code==200
    try:
        ask_claude('research','System task','No network should happen',max_tokens=150)
    except ModelError as exc:
        assert 'hạn mức' in str(exc).lower() or 'ngân sách' in str(exc).lower()
    else:
        assert False,'Budget=0 must prohibit a Claude call'
    # Restore budget for other tests.
    assert client.post('/api/settings',json={'claude_daily_budget_usd':1,
        'claude_agent_daily_budget_usd':0.25}).status_code==200


def test_agent_escalation_can_use_claude_without_using_primary(monkeypatch):
    from app.ai import call_llm
    import app.brains as brains
    calls=[]
    def fake_claude(agent_id,system,prompt,purpose,hard=False):
        calls.append((agent_id,hard))
        return 'Claude đã phân tích vấn đề được giao.'
    monkeypatch.setattr(brains,'ask_claude',fake_claude)
    result=call_llm('Bạn là chuyên gia','Giải quyết tranh chấp nội dung','agent_task',agent_id='compliance',hard=True)
    assert result.startswith('Claude')
    assert calls==[('compliance',True)]


def test_brain_dashboard_frontend_available():
    js=client.get('/assets/app.js')
    assert js.status_code == 200
    assert 'renderBrains' in js.text
    assert 'claude_daily_budget_usd' in js.text


def test_claude_haiku_escalates_only_once_when_it_requests_help():
    import httpx
    import json
    from app.brains import ask_claude
    seen=[]
    def fake(req):
        model=json.loads(req.content)['model']
        seen.append(model)
        return httpx.Response(200,json={
            'content':[{'type':'text','text':'NEED_CLAUDE' if model=='claude-haiku-5-5' else 'Giải pháp do Sonnet tổng hợp.'}],
            'usage':{'input_tokens':150,'output_tokens':50}
        })
    with httpx.Client(transport=httpx.MockTransport(fake)) as mock:
        answer=ask_claude('compliance','Rà soát chính sách nội bộ không có tuyên bố thiếu căn cứ.',
                          'Hãy tóm tắt các điểm quan trọng trong quy tắc xuất bản.',max_tokens=150,client=mock)
    assert answer=='Giải pháp do Sonnet tổng hợp.'
    assert seen==['claude-haiku-5-5','claude-sonnet-5-5']
