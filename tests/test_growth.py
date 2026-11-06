"""Product growth sprint tests; no paid Claude calls or Facebook access."""
import json
import uuid
from test_api import client
from app.db import one
from app.growth import follower_target, generate_ceo_plan, get_sprint


def test_only_product_and_ingredients_is_enough_for_ceo_assignment():
    product='Trà thảo mộc thử nghiệm '+uuid.uuid4().hex[:6]
    r=client.post('/api/growth/sprints',json={'product_name':product,
        'ingredients':'ba kích, đinh lăng, ngọc cẩu, cỏ ngọt','auto_generate':False})
    assert r.status_code==200, r.text
    sprint=r.json()
    assert sprint['product_name']==product
    assert sprint['target_new_follows']==25
    assert sprint['goal_basis']=='provisional_experiment'
    assert sprint['report']['net_new_follows'] is None
    assert len(sprint['outline']['seven_day_plan'])==7
    assert len(sprint['tasks'])==14
    assert len([t for t in sprint['tasks'] if t['agent_id']=='content'])==7
    assert all(t['status']=='queued' for t in sprint['tasks'])
    assert all(day['review_required'] for day in sprint['outline']['seven_day_plan'])
    assert client.get('/api/growth/sprints/'+sprint['id']).status_code==200
    assert client.get('/api/bootstrap').json()['growth_sprints']
    assert client.post('/api/growth/sprints',json={'product_name':product,
      'ingredients':'ba kích','auto_generate':False}).status_code==400


def test_goal_from_baseline_and_manual_daily_kpi():
    r=client.post('/api/growth/sprints',json={'product_name':'Sản phẩm T '+uuid.uuid4().hex[:5],
      'ingredients':'a, b','baseline_followers':200,'previous_week_new_follows':40,'auto_generate':False})
    assert r.status_code==200
    sprint=r.json()
    assert sprint['target_new_follows']==48
    assert sprint['goal_basis']=='prior_week_plus_20pct'
    r=client.post(f"/api/growth/sprints/{sprint['id']}/progress",json={
       'day':3,'followers_total':219,'views':1100,'interactions':80,'notes':'KPI nhập từ báo cáo thủ công'})
    assert r.status_code==200, r.text
    rep=r.json()['report']
    assert rep['net_new_follows']==19
    assert rep['target_new_follows']==48
    assert rep['pace_target']==21
    assert rep['on_pace'] is False
    assert rep['source']=='manual_not_verified_by_meta'
    assert client.post(f"/api/growth/sprints/{sprint['id']}/progress",json={'day':8,'followers_total':100}).status_code==422
    assert client.post(f"/api/growth/sprints/{sprint['id']}/baseline",json={'baseline_followers':50}).status_code==400


def test_missing_baseline_can_be_added_once_before_kpi():
    r=client.post('/api/growth/sprints',json={'product_name':'Sản phẩm Z '+uuid.uuid4().hex[:6],
      'ingredients':'gừng, quế','goal_override':60,'auto_generate':False})
    assert r.status_code==200
    s=r.json()
    assert s['target_new_follows']==60 and s['goal_basis']=='owner_goal'
    r=client.post(f"/api/growth/sprints/{s['id']}/baseline",json={'baseline_followers':800})
    assert r.status_code==200
    assert r.json()['report']['baseline_followers']==800
    assert client.post('/api/growth/sprints',json={'product_name':'X','ingredients':'x'}).status_code==422
    assert client.post('/api/growth/sprints',json={'product_name':'Something','ingredients':' '} ).status_code==422


def test_ceo_plan_mocked_validated_json_and_no_target_change():
    r=client.post('/api/growth/sprints',json={'product_name':'Thử nghiệm AI '+uuid.uuid4().hex[:6],
        'ingredients':'ba kích','auto_generate':False})
    sid=r.json()['id']
    def mock_ceo(agent,system,prompt,**kwargs):
        assert agent=='ceo'
        assert 'không tự' in system.lower()
        assert json.loads(prompt)['weekly_goal_new_follows']==25
        return json.dumps({'positioning':'Kiến thức xác thực','audience_hypothesis':'Chưa xác thực',
            'seven_day_plan':[{'day':i,'topic':f'Chủ đề {i}', 'hook':f'Hook {i}',
                'scenes':['Cảnh 1','Cảnh 2','Cảnh 3'], 'cta':'Theo dõi Page để xem thêm',
                'format':'reel'} for i in range(1,8)]},ensure_ascii=False)
    result=generate_ceo_plan(sid,infer=mock_ceo)
    assert result['status']=='ready'
    s=get_sprint(sid)
    assert s['ai_plan']['status']=='ai_draft_not_reviewed'
    assert s['target_new_follows']==25
    assert s['ai_plan']['seven_day_plan'][0]['review_required'] is True


def test_ai_errors_do_not_erase_free_outline():
    r=client.post('/api/growth/sprints',json={'product_name':'Kế hoạch lỗi '+uuid.uuid4().hex[:6],
      'ingredients':'sâm cau','auto_generate':False})
    sid=r.json()['id']
    result=generate_ceo_plan(sid,infer=lambda *a,**kw:'not valid json')
    assert result['status']=='needs_review'
    s=get_sprint(sid)
    assert len(s['outline']['seven_day_plan'])==7
    assert s['ai_plan'] is None


def test_page_binding_and_no_fake_claims():
    page=client.get('/api/bootstrap').json()['pages'][0]
    result=client.post('/api/growth/sprints',json={
      'product_name':'Mẫu sản phẩm '+uuid.uuid4().hex[:6],
      'ingredients':'ngọc cẩu, ba kích','page_id':page['id'],'auto_generate':False})
    assert result.status_code==200
    sprint=result.json()
    assert sprint['page_id']==page['id']
    from app.db import all_rows
    assert all(t['page_id']==page['id'] for t in all_rows('SELECT page_id FROM tasks WHERE campaign_id=?',(sprint['id'],)))
    assert not any('chữa khỏi' in scene.lower() for d in sprint['outline']['seven_day_plan'] for scene in d['scenes'])
    assert client.post('/api/growth/sprints',json={'product_name':'Khác tên','ingredients':'một thành phần',
        'page_id':'PINVALID','auto_generate':False}).status_code==400


def test_frontend_growth_sprint_route_and_actions():
    js=client.get('/assets/app.js').text
    assert 'Tăng trưởng 7 ngày' in js
    assert "api('/api/growth/sprints'" in js
    assert 'growth.progress' in js
    assert 'CEO lập chiến dịch' in js


def test_sprint_priority_and_checkpoint_reviews_are_deduplicated():
    from app.db import all_rows
    page=client.get('/api/bootstrap').json()['pages'][0]
    r=client.post('/api/growth/sprints',json={'product_name':'Sprint priority '+uuid.uuid4().hex[:6],
          'ingredients':'đinh lăng, ba kích','baseline_followers':500,'goal_override':70,
          'page_id':page['id'],'auto_generate':False})
    s=r.json()
    sid=s['id']
    for _ in range(2):
        x=client.post(f'/api/growth/sprints/{sid}/progress',json={'day':3,'followers_total':501,
             'views':100,'interactions':5})
        assert x.status_code==200
    checkpoint=all_rows('SELECT id FROM tasks WHERE campaign_id=? AND source=?',(sid,'growth_checkpoint_3'))
    assert len(checkpoint)==1
    # A previously unlinked sprint can be attached before workers start.
    other=client.post('/api/growth/sprints',json={'product_name':'Link later '+uuid.uuid4().hex[:6],
          'ingredients':'tía tô, gừng','auto_generate':False}).json()
    link=client.post(f"/api/growth/sprints/{other['id']}/page",json={'page_id':page['id']})
    assert link.status_code==200 and link.json()['page_id']==page['id']
    assert all(t['page_id']==page['id'] for t in all_rows('SELECT page_id FROM tasks WHERE campaign_id=?',(other['id'],)))
