"""Intensive Mirai academy tests use local stubs. They never call paid APIs."""
from test_api import client
from app.db import db, one, all_rows
from app.academy import add_source, academy_tick, academy_overview
from app.ai import save_key
from app.mirai import mirai_report


def test_paid_test_success_enables_intensive_without_leaking_key(monkeypatch):
    from app import main
    save_key('mirai', 'sk-private-test-mirai-intensive')
    saved = client.post('/api/settings',json={
        'academy_intensive_mode':True,'academy_practice_rounds':3,
        'academy_mirai_model':'claude-opus-4.8','academy_mirai_ratio':1.0,
        'academy_enabled':False,'academy_daily_token_limit':10_000_000})
    assert saved.status_code==200
    called=[]
    def simulate_paid_test():
        called.append(1)
        return {'ok':True,'provider':'MiraiAPI','model':'claude-opus-4.8','reply':'OK',
                'quota_status':'actual_usage','quota_used':30,'prompt_tokens':20,'completion_tokens':2}
    monkeypatch.setattr(main,'test_mirai_completion',simulate_paid_test)
    result=client.post('/api/mirai/test-call')
    assert result.status_code==200 and result.json()['academy_auto_started'] is True
    assert len(called)==1
    cfg=client.get('/api/bootstrap').json()['settings']
    assert cfg['academy_enabled']=='1' and cfg['academy_mirai_verified']=='1'
    assert 'sk-private-test' not in str(result.json())
    # Unchanged ratio must not force a new paid test.
    assert client.post('/api/settings',json={'academy_mirai_ratio':1.0}).status_code==200
    assert client.get('/api/bootstrap').json()['settings']['academy_mirai_verified']=='1'


def test_changed_mirai_key_invalidates_prior_verification():
    new=client.post('/api/settings',json={'mirai_key':'sk-private-rotated-key'})
    assert new.status_code==200
    cfg=client.get('/api/bootstrap').json()['settings']
    assert cfg['academy_mirai_verified']=='0' and cfg['academy_enabled']=='0'
    assert 'sk-private-rotated-key' not in str(new.json())


def test_practice_jobs_are_grounded_bounded_and_shared_across_agents():
    client.post('/api/settings',json={'academy_intensive_mode':True,'academy_practice_rounds':2,
                                      'academy_enabled':True,'academy_daily_token_limit':10_000_000})
    source=add_source('Hướng dẫn thực hành kiểm thử 10M V110',
        'Tài liệu này hướng dẫn lập kế hoạch cho Fanpage sản phẩm thực tế theo nguồn đã xác nhận. '
        'Cần nghiên cứu khách hàng, xây dựng nội dung có ích, kiểm tra tính đúng đắn của các thông tin sản phẩm. '
        'Mỗi ngày tổng hợp chỉ số từ nguồn dữ liệu hợp lệ và đánh giá mức tiến triển. '
        'Không nên cố tạo tương tác giả hoặc khẳng định kết quả khi chưa có dữ liệu. ' * 3,
        source_ref='Tài liệu kiểm thử cục bộ')
    assert not source['duplicate']
    touched=[]
    def fake_mirai(agent,system,prompt,purpose,max_tokens):
        touched.append((agent,purpose,prompt))
        return ('Bài học được đối chiếu với tài liệu; đề xuất xây dựng kịch bản theo ngày, '
                'đo KPI từ dữ liệu hợp lệ, không tự động thao tác Facebook, cần xác minh thực tế.')
    for _ in range(300):
        info=academy_tick(caller=fake_mirai)
        assert info['status']!='failed',info
        ready=one('''SELECT COUNT(*) AS n FROM academy_practice_jobs p JOIN academy_chunks k ON p.chunk_id=k.id
                     WHERE k.source_id=? AND p.status='done' ''',(source['source_id'],))
        if ready and ready['n']>=source['jobs']*2:
            break
    else:
        raise AssertionError('Not all practice jobs completed')
    rows=all_rows('''SELECT p.agent_id,p.practice_round,p.status FROM academy_practice_jobs p JOIN academy_chunks k
                    ON p.chunk_id=k.id WHERE k.source_id=?''',(source['source_id'],))
    assert len(rows)==source['jobs']*2
    assert len(set(row['agent_id'] for row in rows))==9
    assert set(row['practice_round'] for row in rows)=={1,2}
    assert all(row['status']=='done' for row in rows)
    # Re-enqueue is idempotent: no infinite synthetic training loop.
    from app.academy import enqueue_practice_for_completed_training
    assert enqueue_practice_for_completed_training(rounds=2)==0
    assert any(purpose=='academy_practice' for _,purpose,_ in touched)
    notes=all_rows("SELECT source_ref,confidence FROM agent_memories WHERE kind='academy_simulation'")
    assert any(source['source_id'] in row['source_ref'] for row in notes)
    assert all(row['confidence']=='unverified' for row in notes)
    overview=academy_overview()
    assert overview['intensive_mode'] is True
    assert overview['counts']['practice_done']>=source['jobs']*2
    quota=mirai_report()
    assert 'quota_by_agent' in quota and quota['daily_quota_limit']==10_000_000


def test_invalid_intensive_settings_fail_validation():
    assert client.post('/api/settings',json={'academy_practice_rounds':99}).status_code==422
    assert client.post('/api/settings',json={'academy_practice_rounds':0}).status_code==422
