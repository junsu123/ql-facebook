"""Academy tests: all inference is mocked, never calls paid Claude API."""
import uuid
# Import the shared isolated client FIRST; it sets AIFC_DATA_DIR before app imports.
from test_api import client
from app.academy import add_source, academy_overview, academy_tick, chunk_document
from app.brains import reserve_budget, spent_report
from app.db import db, run, one
from app.ai import save_key


def test_training_ingestion_is_source_grounded_and_deduplicated():
    body=('Quy tắc Facebook Page: thông tin minh bạch, nội dung nguyên bản. ' * 90)
    res=add_source('Tài liệu kiểm thử chuyên môn ' + uuid.uuid4().hex,body,'Sổ tay đã được phép')
    assert res['chunks']>=1
    assert res['jobs']==res['chunks']*9
    second=add_source('Bản sao tài liệu',body,'Sổ tay đã được phép')
    assert second['duplicate'] is True and second['source_id']==res['source_id']
    assert academy_overview()['counts']['sources']>=1
    assert chunk_document('a'*12000)


def test_no_unapproved_or_unlicensed_training():
    bad=client.post('/api/academy/sources',json={'title':'abc','content':'x'*200,
         'owner_has_rights':False})
    assert bad.status_code==400
    config=client.post('/api/settings',json={'academy_enabled':False,'academy_daily_token_limit':10_000_000})
    assert config.status_code==200
    assert academy_tick(caller=lambda *a,**k: (_ for _ in ()).throw(AssertionError('should not be called')))['status']=='disabled'


def test_digest_then_agent_learning_without_real_api(monkeypatch):
    with db() as c:
        c.execute('DELETE FROM academy_training_jobs')
        c.execute('DELETE FROM academy_chunks')
        c.execute('DELETE FROM academy_sources')
        c.execute('DELETE FROM claude_usage')
    src=add_source('Kiểm thử quy trình 24 giờ', 'Hướng dẫn làm nội dung Facebook có ích. '*80,agents=['research','content'])
    save_key('claude','sk-test-academy-no-network')
    r=client.post('/api/settings',json={'academy_enabled':True,'academy_daily_token_limit':10_000_000,
        'claude_daily_budget_usd':100,'claude_agent_daily_budget_usd':50})
    assert r.status_code==200
    calls=[]
    def mock_claude(agent,system,prompt,purpose,max_tokens):
        calls.append((agent,purpose))
        return 'Kiến thức tóm tắt có nguồn; chỉ áp dụng quy tắc sau khi xác minh và tuân thủ chính sách Meta.'
    outcomes=[academy_tick(caller=mock_claude) for _ in range(src['chunks']+src['jobs'])]
    assert any(x['status']=='digested' for x in outcomes)
    assert any(x['status']=='trained' for x in outcomes)
    assert len(calls)==src['chunks']+src['jobs']
    assert one('SELECT COUNT(*) AS n FROM academy_training_jobs WHERE status="done"')['n']==src['jobs']
    note=one('SELECT source_ref,confidence FROM agent_memories WHERE kind="academy_training" ORDER BY created DESC')
    assert note['source_ref'].startswith('academy:')
    assert note['confidence']=='unverified'
    assert client.get('/api/academy').status_code==200
    assert client.get('/api/bootstrap').json()['academy']['counts']['jobs_done']>=src['jobs']


def test_total_token_quota_prevents_provider_call():
    with db() as c:
        c.execute('DELETE FROM claude_usage')
    assert client.post('/api/settings',json={'academy_daily_token_limit':10000,
        'claude_daily_budget_usd':100,'claude_agent_daily_budget_usd':100,
        'daily_llm_call_limit':10000}).status_code==200
    try:
        reserve_budget('content','claude-haiku-5-5','academy_training','z'*12000,'system',900)
    except ValueError as error:
        assert 'token' in str(error).lower()
    else:
        raise AssertionError('Token quota must deny oversized reservation before calling Claude')
    info=spent_report()
    assert info['daily_token_limit']==10000 and info['tokens_remaining']<=10000
    assert 'tokens_by_agent' in info


def test_academy_ui_uses_real_backend_and_exposes_no_scraping():
    js=client.get('/assets/app.js').text
    assert 'Học viện 10M' in js
    assert "api('/api/academy/sources'" in js
    assert 'academy_daily_token_limit' in js
    assert 'Bật Học viện AI' in js
