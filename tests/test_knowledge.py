"""Unified knowledge explorer; no paid provider calls or external Facebook data."""
import csv
import io
import json
import uuid

from test_api import client
from app.db import db, now
from app.academy import add_source
from app.knowledge import browse_knowledge, knowledge_overview


def _new_source():
    label='Học về Fanpage '+uuid.uuid4().hex[:8]
    source=add_source(label,'Xây dựng nội dung rõ ràng, nguyên bản, hữu ích và đo hiệu quả. '*55,
                      source_ref='Sổ tay nội bộ',agents=['content'])
    return label,source


def test_all_learned_records_search_and_source_trace():
    title,source=_new_source()
    with db() as c:
        chunks=c.execute('SELECT id FROM academy_chunks WHERE source_id=?',(source['source_id'],)).fetchall()
        for chunk in chunks:
            c.execute("UPDATE academy_chunks SET status='ready',summary=? WHERE id=?",
                      ('Tóm tắt nội bộ về phát triển cộng đồng.',chunk['id']))
            c.execute("UPDATE academy_training_jobs SET status='done',result=?,finished_at=? WHERE chunk_id=? AND agent_id='content'",
                      ('Bài học content cụ thể cho trang.',now(),chunk['id']))
            c.execute("INSERT INTO academy_practice_jobs(id,chunk_id,agent_id,practice_round,status,result,created,finished_at) VALUES(?,?,?,?,?,?,?,?)",
                      (uuid.uuid4().hex,chunk['id'],'content',1,'done','Phản biện cách tăng lượt theo dõi.',now(),now()))
        c.execute("INSERT INTO agent_memories(id,agent_id,kind,content,source_ref,confidence,digest,created) VALUES(?,?,?,?,?,?,?,?)",
                  (uuid.uuid4().hex,'research','observation','Nhận xét nguồn kiểm chứng thử nghiệm', 'local:report','verified',uuid.uuid4().hex,now()))
    response=client.get('/api/knowledge/records',params={'q':'content cụ thể','kind':'lesson','agent_id':'content'})
    assert response.status_code==200,response.text
    payload=response.json()
    assert payload['total']==len(chunks)
    assert all(x['kind']=='lesson' and x['agent_id']=='content' for x in payload['items'])
    assert all(x['source_id']==source['source_id'] and x['confidence']=='unverified' for x in payload['items'])
    overview=client.get('/api/knowledge/overview').json()
    assert overview['by_kind']['digest']>=len(chunks)
    assert overview['by_kind']['lesson']>=len(chunks)
    assert overview['by_kind']['practice']>=len(chunks)
    verified=client.get('/api/knowledge/records',params={'kind':'agent_memory','confidence':'verified'}).json()
    assert any('Nhận xét nguồn' in x['body'] for x in verified['items'])
    unverified=client.get('/api/knowledge/records',params={'kind':'lesson','confidence':'verified'}).json()
    assert unverified['total']==0
    result=client.get('/api/knowledge/sources/'+source['source_id'])
    assert result.status_code==200 and title==result.json()['title']
    assert len(result.json()['body'])>160
    assert client.get('/api/knowledge/sources/unknown-source').status_code==404


def test_export_every_record_including_more_than_page_size_and_csv_injection():
    with db() as c:
        for i in range(113):
            c.execute("INSERT INTO agent_memories(id,agent_id,kind,content,source_ref,confidence,digest,created) VALUES(?,?,?,?,?,?,?,?)",
                      ('export-'+uuid.uuid4().hex,'creative','test',f'Bài học xuất dữ liệu số {i}',
                       'test','unverified',uuid.uuid4().hex,now()))
        c.execute("INSERT INTO agent_memories(id,agent_id,kind,content,source_ref,confidence,digest,created) VALUES(?,?,?,?,?,?,?,?)",
                  ('export-'+uuid.uuid4().hex,'creative','test','=HYPERLINK("https://evil.invalid")',
                   'test','unverified',uuid.uuid4().hex,now()))
    first=client.get('/api/knowledge/records',params={'kind':'agent_memory','agent_id':'creative','limit':25})
    assert first.status_code==200
    assert len(first.json()['items'])==25 and first.json()['total']>=114
    more=client.get('/api/knowledge/records',params={'kind':'agent_memory','agent_id':'creative','offset':25,'limit':25})
    assert more.status_code==200
    assert first.json()['items'][0]['id']!=more.json()['items'][0]['id']
    resp=client.get('/api/knowledge/export',params={'fmt':'jsonl','kind':'agent_memory','agent_id':'creative'})
    assert resp.status_code==200,resp.text
    objects=[json.loads(line) for line in resp.text.splitlines() if line.strip()]
    assert len(objects)>=114 and any(x['body'].startswith('=HYPERLINK') for x in objects)
    csv_response=client.get('/api/knowledge/export',params={'fmt':'csv','kind':'agent_memory','agent_id':'creative'})
    assert csv_response.status_code==200
    rows=list(csv.DictReader(io.StringIO(csv_response.text.lstrip('\ufeff'))))
    assert len(rows)==len(objects)
    assert any(x['body'].startswith("'=HYPERLINK") for x in rows)
    assert client.get('/api/knowledge/export',params={'fmt':'exe'}).status_code==400


def test_filters_safe_and_source_listing_paged():
    assert client.get('/api/knowledge/records',params={'kind':'invalid'}).status_code==400
    assert client.get('/api/knowledge/records',params={'limit':200}).status_code==422
    assert client.get('/api/knowledge/records',params={'confidence':'maybe'}).status_code==400
    assert client.get('/api/knowledge/records',params={'q':'%'}).status_code==200
    assert client.get('/api/knowledge/records',params={'q':'%'}).json()['total']==0
    r=client.get('/api/knowledge/sources',params={'limit':1})
    assert r.status_code==200
    assert len(r.json()['items'])<=1
    appjs=client.get('/assets/app.js').text
    assert 'Kho kiến thức đã học' in appjs
    assert "api('/api/knowledge/records?'" in appjs
    assert 'knowledge.view' in appjs
