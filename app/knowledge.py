"""Read-only, complete knowledge explorer for the local AI Academy.

Show actual stored outputs, not hallucinated summaries or LLM hidden reasoning.
Paged browsing uses a UNION ALL over the sources of learning. CSV/JSONL export
streams *all* matching rows without the UI's page-size restriction.
"""
from __future__ import annotations

import csv
import io
import json
import sqlite3
from typing import Iterator

from .db import all_rows, db, one

KINDS = {
    'digest': 'Tóm tắt tài liệu',
    'lesson': 'Bài học chuyên môn',
    'practice': 'Thực hành / phản biện',
    'agent_memory': 'Trí nhớ nhân viên',
    'page_memory': 'Trí nhớ Fanpage',
}

# Untrusted source texts are deliberately treated as unverified. A completed
# Claude/Mirai task does not mean the information was externally verified.
QUERY = '''
WITH knowledge AS (
  SELECT 'digest:' || k.id AS id, 'digest' AS kind,
    NULL AS agent_id, NULL AS agent_name, NULL AS page_id, NULL AS page_name,
    s.title || ' · đoạn ' || (k.position+1) AS title, k.summary AS body,
    s.id AS source_id, s.title AS source_title, s.source_ref AS source_ref,
    'unverified' AS confidence, k.created AS created
  FROM academy_chunks k JOIN academy_sources s ON s.id=k.source_id
  WHERE k.status='ready' AND LENGTH(TRIM(k.summary))>0
  UNION ALL
  SELECT 'lesson:' || j.id, 'lesson', j.agent_id, a.name, NULL, NULL,
    s.title || ' · đoạn ' || (k.position+1), j.result,
    s.id, s.title, s.source_ref, 'unverified', COALESCE(j.finished_at,j.created)
  FROM academy_training_jobs j
    JOIN academy_chunks k ON k.id=j.chunk_id
    JOIN academy_sources s ON s.id=k.source_id
    LEFT JOIN agents a ON a.id=j.agent_id
  WHERE j.status='done' AND LENGTH(TRIM(j.result))>0
  UNION ALL
  SELECT 'practice:' || p.id, 'practice', p.agent_id, a.name, NULL, NULL,
    s.title || ' · thực hành vòng ' || p.practice_round,
    p.result, s.id, s.title, s.source_ref,
    'unverified', COALESCE(p.finished_at,p.created)
  FROM academy_practice_jobs p
    JOIN academy_chunks k ON k.id=p.chunk_id
    JOIN academy_sources s ON s.id=k.source_id
    LEFT JOIN agents a ON a.id=p.agent_id
  WHERE p.status='done' AND LENGTH(TRIM(p.result))>0
  UNION ALL
  SELECT 'agent_memory:' || m.id, 'agent_memory', m.agent_id, a.name,
    m.page_id, pg.name, m.kind, m.content, NULL, '', m.source_ref,
    m.confidence, m.created
  FROM agent_memories m
    LEFT JOIN agents a ON a.id=m.agent_id
    LEFT JOIN pages pg ON pg.id=m.page_id
  WHERE LENGTH(TRIM(m.content))>0
  UNION ALL
  SELECT 'page_memory:' || m.id, 'page_memory', NULL, NULL,
    m.page_id, pg.name, 'Kinh nghiệm Fanpage', m.note,
    NULL, '', m.source, 'unverified', m.created
  FROM memories m JOIN pages pg ON pg.id=m.page_id
  WHERE LENGTH(TRIM(m.note))>0
)
'''

# Dynamically built SQL contains only predefined field names and bind params.
FILTERS = {
    'all': '',
    **{kind: 'kind=?' for kind in KINDS},
}


def _filters(*, kind: str='all', agent_id: str='', q: str='', confidence: str='all') -> tuple[str, list]:
    if kind not in FILTERS:
        raise ValueError('Loại kiến thức không hợp lệ.')
    if confidence not in ('all','verified','unverified'):
        raise ValueError('Bộ lọc xác minh không hợp lệ.')
    if len(agent_id)>90 or len(q)>160:
        raise ValueError('Bộ lọc quá dài.')
    conditions=[]
    args=[]
    if kind!='all':
        conditions.append('kind=?');args.append(kind)
    if agent_id:
        conditions.append('agent_id=?');args.append(agent_id)
    if confidence=='verified':
        conditions.append("confidence='verified'")
    elif confidence=='unverified':
        conditions.append("confidence!='verified'")
    if q.strip():
        # LIKE literals, not wildcards; avoid user-entered % or _ matching all.
        value=q.strip().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        conditions.append("(title LIKE ? ESCAPE '\\' OR body LIKE ? ESCAPE '\\' "
                          "OR source_title LIKE ? ESCAPE '\\' OR source_ref LIKE ? ESCAPE '\\' "
                          "OR agent_name LIKE ? ESCAPE '\\' OR page_name LIKE ? ESCAPE '\\')")
        args.extend(['%'+value+'%']*6)
    return (' WHERE '+' AND '.join(conditions) if conditions else ''), args


def knowledge_overview() -> dict:
    """Metadata only; never downloads source bodies in the dashboard overview."""
    totals={kind:0 for kind in KINDS}
    with db() as c:
        for row in c.execute(QUERY+'SELECT kind,COUNT(*) AS n FROM knowledge GROUP BY kind'):
            totals[row['kind']]=int(row['n'])
        docs=c.execute('SELECT COUNT(*) FROM academy_sources').fetchone()[0]
        agents=[dict(r) for r in c.execute('''SELECT a.id,a.name,
            (SELECT COUNT(*) FROM academy_training_jobs j WHERE j.agent_id=a.id AND j.status='done') AS lessons,
            (SELECT COUNT(*) FROM academy_practice_jobs p WHERE p.agent_id=a.id AND p.status='done') AS practices,
            (SELECT COUNT(*) FROM agent_memories m WHERE m.agent_id=a.id) AS memories
            FROM agents a ORDER BY a.rowid''')]
    return {'total_records':sum(totals.values()),'by_kind':totals,'sources':docs,'agents':agents,
            'note':'Nội dung AI sinh ra và tài liệu do người dùng cung cấp không mặc định được xác minh.'}


def browse_knowledge(*, kind='all', agent_id='', q='', confidence='all', limit=25, offset=0) -> dict:
    limit=int(limit);offset=int(offset)
    if not 1<=limit<=100 or not 0<=offset<=1_000_000:
        raise ValueError('Phân trang không hợp lệ.')
    where,args=_filters(kind=kind,agent_id=agent_id,q=q,confidence=confidence)
    with db() as c:
        total=c.execute(QUERY+'SELECT COUNT(*) FROM knowledge'+where,args).fetchone()[0]
        rows=[dict(row) for row in c.execute(QUERY+'SELECT * FROM knowledge'+where+' ORDER BY created DESC,id DESC LIMIT ? OFFSET ?',args+[limit,offset])]
    return {'items':rows,'total':total,'offset':offset,'limit':limit,'has_more':offset+len(rows)<total}


def source_detail(source_id: str) -> dict|None:
    if not source_id or len(source_id)>80:return None
    item=one('''SELECT id,title,source_ref,body,created FROM academy_sources WHERE id=?''',(source_id,))
    if item is None:return None
    item['chunks']=one('SELECT COUNT(*) AS n FROM academy_chunks WHERE source_id=?',(source_id,))['n']
    return item


def list_sources(*, q: str='', limit: int=30, offset: int=0) -> dict:
    if not 1<=limit<=100 or not 0<=offset<=1_000_000 or len(q)>160:
        raise ValueError('Phân trang hoặc từ khóa không hợp lệ.')
    escaped=q.strip().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
    where=" WHERE (title LIKE ? ESCAPE '\\' OR source_ref LIKE ? ESCAPE '\\')" if escaped else ''
    args=['%'+escaped+'%']*2 if escaped else []
    total=one('SELECT COUNT(*) AS n FROM academy_sources'+where,tuple(args))['n']
    items=all_rows('''SELECT s.id,s.title,s.source_ref,s.created,
        (SELECT COUNT(*) FROM academy_chunks k WHERE k.source_id=s.id) AS chunks,
        (SELECT COUNT(*) FROM academy_training_jobs j JOIN academy_chunks k ON j.chunk_id=k.id
         WHERE k.source_id=s.id AND j.status='done') AS lessons
        FROM academy_sources s'''+where+' ORDER BY s.created DESC,s.id DESC LIMIT ? OFFSET ?',tuple(args+[limit,offset]))
    return {'items':items,'total':total,'limit':limit,'offset':offset,'has_more':offset+len(items)<total}


def export_knowledge(*, fmt='csv', kind='all', agent_id='', q='', confidence='all') -> Iterator[str]:
    """Stream all matching records. No arbitrary first-100/first-1000 cutoff."""
    if fmt not in ('csv','jsonl'):
        raise ValueError('Định dạng xuất không hợp lệ.')
    where,args=_filters(kind=kind,agent_id=agent_id,q=q,confidence=confidence)
    headers=['id','kind','agent_id','agent_name','page_id','page_name','title','body',
             'source_id','source_title','source_ref','confidence','created']
    if fmt=='csv':
        yield '\ufeff'  # UTF-8 BOM to allow Excel to open Vietnamese correctly.
        buf=io.StringIO()
        writer=csv.writer(buf)
        writer.writerow(headers)
        yield buf.getvalue();buf.seek(0);buf.truncate(0)
    with db() as c:
        cursor=c.execute(QUERY+'SELECT * FROM knowledge'+where+' ORDER BY created DESC,id DESC',args)
        while True:
            batch=cursor.fetchmany(200)
            if not batch:break
            for record in batch:
                row=dict(record)
                if fmt=='jsonl':
                    yield json.dumps(row,ensure_ascii=False)+'\n'
                else:
                    # Prevent formula injection when opened as a spreadsheet.
                    safe=[]
                    for name in headers:
                        value=str(row.get(name) or '')
                        if value.lstrip().startswith(('=','+','-','@')):
                            value="'"+value
                        safe.append(value)
                    writer.writerow(safe)
                    yield buf.getvalue();buf.seek(0);buf.truncate(0)
