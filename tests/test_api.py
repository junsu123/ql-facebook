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
    if cfg.get('gemini_configured'):
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
    payload={'provider':'gemini','gemini_model':'gemini-2.5-flash','groq_model':'llama-3.3-70b-versatile',
             'daily_llm_call_limit':20,'auto_run_agents':False,'firefox_path':''}
    assert client.post('/api/settings',json=payload).status_code==200
    assert client.get('/api/bootstrap').json()['settings']['auto_run_agents']=='0'
