"""Per-agent learning memory and cost-capped Claude escalation.

24/7 means event-driven local work while the application is running. There is
NO polling of external sites or perpetual LLM request loop. Per-agent memories
are kept isolated; no unverified work result is promoted into a verified fact.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import time
import uuid
from datetime import datetime, timezone, timedelta, time as clock_time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Any

import httpx

from .db import db, now, one, all_rows, run

# Anthropic published API IDs/rates as checked in Nov 2026.
# Review prices before production; invoices can differ from estimates.
# Haiku 5.5 has a lower tier for prompts below 100k tokens.
CLAUDE_PRICING = {
    'claude-haiku-5-5': (0.10, 0.50),
    'claude-haiku-4-5': (1.00, 5.00),
    'claude-sonnet-5-5': (2.00, 10.00),
    'claude-opus-5-5': (4.00, 20.00),
}
DEFAULT_CHEAP = 'claude-haiku-5-5'
DEFAULT_HARD = 'claude-sonnet-5-5'
AGENT_IDS = ('ceo','research','strategy','content','creative','publishing','customer','analytics','compliance')
# Distinct professional mandates are always combined with each agent's own
# private memory. An agent is a role-specific worker, not an always-on LLM.
BRAIN_PERSONAS = {
    'ceo':'Điều phối các phòng ban, phân rã mục tiêu, kiểm tra kết quả và ngân sách. Chỉ được báo cáo tình trạng có bằng chứng.',
    'research':'Nghiên cứu dữ liệu nội bộ và tài liệu người dùng cung cấp; tách sự thật, giả thuyết và điều chưa rõ. Không giả vờ đã tìm Facebook.',
    'strategy':'Thiết kế lịch nội dung theo Page, đối tượng và KPI có nguồn. Ưu tiên thử nghiệm nhỏ, có giả thuyết và cách đo.',
    'content':'Viết nội dung nguyên bản theo sự thật sản phẩm đã xác minh; tránh lặp, phóng đại, làm giả khách hàng hay tuyên bố chữa bệnh.',
    'creative':'Lập brief ảnh/video và kiểm tra quyền sử dụng media. Không mô tả rằng đã tạo file media khi chưa có công cụ.',
    'publishing':'Quản lý lịch, chuẩn bị bài và xác nhận đăng thủ công. Không tự thao tác Facebook nếu chưa có cách được cho phép.',
    'customer':'Phân loại bình luận được cung cấp và đề xuất câu trả lời phù hợp; không tự nhận đã gửi tin nhắn.',
    'analytics':'Tổng hợp KPI có nguồn, tính so sánh công bằng và chỉ tạo giả thuyết khi số mẫu đủ.',
    'compliance':'Rà soát tuyên bố, chính sách nội dung và rủi ro trước xuất bản. Nếu thiếu bằng chứng thì chặn hoặc yêu cầu xác minh.',
}

def brain_system(agent_id: str) -> str:
    return ('Vai trò cố định: '+ BRAIN_PERSONAS.get(agent_id,'Trợ lý nội bộ') +
            ' Trí nhớ của agent là ghi chú có mức tin cậy; bản ghi chưa xác minh không được dùng làm căn cứ khẳng định. '
            'Không tiết lộ dữ liệu riêng giữa các agent. Nếu khó giải quyết, nêu rõ thiếu dữ liệu hoặc xin Claude hỗ trợ. ')

HARD_MARKERS = ('rủi ro pháp lý','tuyên bố chữa bệnh','tranh chấp','mâu thuẫn dữ kiện',
                'khủng hoảng','rủi ro cao','chiến lược phức tạp','không giải quyết được','escalate_claude')

BRAIN_SCHEMA = '''
CREATE TABLE IF NOT EXISTS agent_memories (
 id TEXT PRIMARY KEY, agent_id TEXT NOT NULL REFERENCES agents(id),
 kind TEXT NOT NULL, content TEXT NOT NULL, source_ref TEXT NOT NULL DEFAULT '',
 page_id TEXT, confidence TEXT NOT NULL DEFAULT 'unverified',
 digest TEXT NOT NULL, created TEXT NOT NULL,
 UNIQUE(agent_id,digest)
);
CREATE INDEX IF NOT EXISTS ix_agent_mem_agent ON agent_memories(agent_id,created);
CREATE TABLE IF NOT EXISTS agent_learning_events (
 id TEXT PRIMARY KEY, agent_id TEXT NOT NULL REFERENCES agents(id),
 event_type TEXT NOT NULL, body TEXT NOT NULL, source_ref TEXT NOT NULL DEFAULT '',
 page_id TEXT, status TEXT NOT NULL DEFAULT 'pending', created TEXT NOT NULL, processed_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_learning_pending ON agent_learning_events(status,created);
CREATE TABLE IF NOT EXISTS agent_brain_state (
 agent_id TEXT PRIMARY KEY REFERENCES agents(id),last_cycle TEXT,processed_events INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS claude_usage (
 id TEXT PRIMARY KEY, agent_id TEXT NOT NULL REFERENCES agents(id), model TEXT NOT NULL,
 purpose TEXT NOT NULL, status TEXT NOT NULL,
 estimated_reservation_usd REAL NOT NULL DEFAULT 0,
 cost_usd REAL NOT NULL DEFAULT 0, input_tokens INTEGER NOT NULL DEFAULT 0,
 output_tokens INTEGER NOT NULL DEFAULT 0, cache_read_tokens INTEGER NOT NULL DEFAULT 0,
 cache_write_tokens INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL, finished_at TEXT,
 route_reason TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_claude_usage_day ON claude_usage(created,agent_id,status);
CREATE TABLE IF NOT EXISTS brain_response_cache (
 key TEXT PRIMARY KEY, agent_id TEXT NOT NULL REFERENCES agents(id),
 model TEXT NOT NULL, response TEXT NOT NULL, created_epoch INTEGER NOT NULL
);
'''


def init_brains():
    with db() as c:
        c.executescript(BRAIN_SCHEMA)
        # Existing V1.3 databases must remain usable; never delete local memory.
        columns={row[1] for row in c.execute('PRAGMA table_info(claude_usage)')}
        if 'route_reason' not in columns:
            c.execute("ALTER TABLE claude_usage ADD COLUMN route_reason TEXT NOT NULL DEFAULT ''")
        c.executemany('INSERT OR IGNORE INTO agent_brain_state(agent_id) VALUES (?)',[(a,) for a in AGENT_IDS])
        defaults = {
            'claude_daily_budget_usd':'1.00',
            'claude_agent_daily_budget_usd':'0.25',
            'claude_cache_enabled':'1',
            'brain_learning_enabled':'1',
            'brain_cycle_seconds':'60',
        }
        c.executemany('INSERT OR IGNORE INTO settings(key,value) VALUES (?,?)',defaults.items())


def budget_settings():
    settings={r['key']:r['value'] for r in all_rows('SELECT key,value FROM settings')}
    return settings


def is_hard_problem(instructions: str) -> bool:
    raw=(instructions or '').lower()
    return any(w in raw for w in HARD_MARKERS)


def route_claude_model(agent_id: str, purpose: str, prompt: str, *, hard: bool=False) -> tuple[str,str]:
    """Deterministic, no-extra-API-call model routing for each agent.

    The low-cost model is used unless the task is explicitly risky/complex.
    If Haiku cannot finish, it may return NEED_CLAUDE for ONE Sonnet call.
    This classification is heuristic and not a substitute for human approval.
    """
    if agent_id not in AGENT_IDS:
        raise ValueError('Agent không tồn tại')
    if hard:
        return DEFAULT_HARD, 'complex_explicit'
    if is_hard_problem(prompt):
        return DEFAULT_HARD, 'complex_keywords'
    # Long multi-part instructions are less likely to fit Haiku reliably.
    if purpose in ('ceo','strategy') and len(prompt) > 6000:
        return DEFAULT_HARD, 'long_complex_plan'
    return DEFAULT_CHEAP, 'routine_low_cost'


def _tokens_upper(text: str) -> int:
    # Deliberately conservative to limit reservations and context growth.
    return max(64,len(text.encode('utf-8'))+64)  # Conservative reservation upper bound


def _rates(model: str, prompt_tokens: int=0) -> tuple[float,float]:
    if model not in CLAUDE_PRICING:
        raise ValueError('Model Claude chưa được hỗ trợ tính chi phí; hãy chọn model trong danh sách.')
    if model=='claude-haiku-5-5' and prompt_tokens>100_000:
        return (0.50,2.50)  # Conservative higher tier, not used for normal short prompts.
    return CLAUDE_PRICING[model]


def _max_reservation(model: str,prompt: str,system: str,max_tokens:int) -> float:
    ip,op=_rates(model,_tokens_upper(system+prompt))
    # Reservation covers a generous upper bound on input, full response output,
    # and possible cache write premium.  Values in USD.
    return round((_tokens_upper(system+prompt)*ip*1.25+max_tokens*op)/1_000_000 + 0.000001,9)


def _vietnam_billing_timezone():
    """Vietnam time for daily Claude budgets, including Windows without tzdata.

    Normal installations use the IANA database.  Vietnam has no daylight-saving
    time and its current civil offset is UTC+07, so the fixed-offset fallback is
    safe for daily *current* spending boundaries if tzdata is missing or broken.
    """
    try:
        return ZoneInfo('Asia/Ho_Chi_Minh')
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=7), name='Asia/Ho_Chi_Minh fallback')


def _vietnam_day_start_utc(instant:datetime|None=None) -> str:
    """UTC ISO timestamp of local midnight for the instant's Vietnam date."""
    instant=instant or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError('Expected timezone-aware datetime')
    tz=_vietnam_billing_timezone()
    day=instant.astimezone(tz).date()
    return datetime.combine(day,clock_time(0),tzinfo=tz).astimezone(timezone.utc).isoformat(timespec='seconds')


def _spent_today(c:sqlite3.Connection, agent_id:str|None=None) -> float:
    clauses="created>=? AND status IN ('reserved','completed')"
    args=[_vietnam_day_start_utc()]
    if agent_id:
        clauses+=' AND agent_id=?';args.append(agent_id)
    r=c.execute(f'''SELECT COALESCE(SUM(CASE WHEN status='reserved' THEN estimated_reservation_usd ELSE cost_usd END),0) AS dollars FROM claude_usage WHERE {clauses}''',args).fetchone()
    return float(r['dollars'])


def reserve_budget(agent_id:str, model:str, purpose:str, prompt:str,system:str,max_tokens:int, route_reason:str='') -> tuple[str,float]:
    if agent_id not in AGENT_IDS:
        raise ValueError('Agent không tồn tại')
    cfg=budget_settings()
    total_cap=max(0,float(cfg.get('claude_daily_budget_usd','1')))
    agent_cap=max(0,float(cfg.get('claude_agent_daily_budget_usd','.25')))
    amount=_max_reservation(model,prompt,system,max_tokens)
    rid='R'+uuid.uuid4().hex
    with db() as c:
        # BEGIN IMMEDIATE serializes reservations across workers and processes.
        c.execute('BEGIN IMMEDIATE')
        # Strict request count, shared by all agents and their escalations.
        max_calls=max(1,int(cfg.get('daily_llm_call_limit','200')))
        used_calls=c.execute("SELECT COUNT(*) FROM claude_usage WHERE created>=? AND status IN ('reserved','completed')",
                            (_vietnam_day_start_utc(),)).fetchone()[0]
        if used_calls>=max_calls:
            raise ValueError('Đã đạt hạn mức lượt gọi Claude hôm nay.')
        if _spent_today(c)+amount>total_cap+1e-10:
            raise ValueError('Đã hết hạn mức Claude toàn công ty hôm nay.')
        if _spent_today(c,agent_id)+amount>agent_cap+1e-10:
            raise ValueError(f'Agent {agent_id} đã chạm ngân sách Claude ngày.')
        c.execute('''INSERT INTO claude_usage(id,agent_id,model,purpose,status,estimated_reservation_usd,created,route_reason)
                     VALUES(?,?,?,?,?,?,?,?)''',(rid,agent_id,model,purpose,'reserved',amount,now(),route_reason))
    return rid,amount


def _update_usage(rid:str, status:str, usage:dict|None=None, model:str=''):
    usage=usage or {}
    inp=int(usage.get('input_tokens') or 0)
    out=int(usage.get('output_tokens') or 0)
    cr=int(usage.get('cache_read_input_tokens') or 0)
    cw=int(usage.get('cache_creation_input_tokens') or 0)
    ip,op=_rates(model,inp+cr+cw) if model else (0,0)
    # Input tokens do not include cached tokens; charge cached hits/writes separately.
    cache_read_multiplier=(0.05 if model=='claude-sonnet-5-5' else 0.1)
    cost=(inp*ip + out*op + cr*ip*cache_read_multiplier + cw*ip*1.25)/1_000_000
    run('''UPDATE claude_usage SET status=?,cost_usd=?,estimated_reservation_usd=0,
       input_tokens=?,output_tokens=?,cache_read_tokens=?,cache_write_tokens=?,finished_at=? WHERE id=?''',
       (status,round(cost,9),inp,out,cr,cw,now(),rid))
    return round(cost,9)


def spent_report():
    with db() as c:
        company=_spent_today(c)
        per={a:round(_spent_today(c,a),6) for a in AGENT_IDS}
    cfg=budget_settings()
    return {'today_usd':round(company,6),'daily_limit_usd':float(cfg.get('claude_daily_budget_usd','1')),
            'per_agent_limit_usd':float(cfg.get('claude_agent_daily_budget_usd','.25')),
            'agents':per,'currency':'USD',
            'disclaimer':'Ứng dụng chỉ ước tính chi phí Claude từ usage API; hóa đơn thực tế do Anthropic quyết định.'}


def _cache_key(agent_id,model,system,prompt) -> str:
    return hashlib.sha256(json.dumps([agent_id,model,system,prompt],ensure_ascii=False).encode()).hexdigest()


def ask_claude(agent_id: str,system: str,prompt: str,purpose:str='agent_task',hard:bool=False,
               client: httpx.Client|None=None,max_tokens:int=850) -> str:
    """Spend-capped Claude request; no implicit retries or high-model loops."""
    from .ai import get_key, ModelError
    init_brains()
    key=get_key('claude')
    if not key:raise ModelError('Chưa cấu hình Claude API key trong mục Cài đặt.')
    cfg=budget_settings()
    model,route_reason=route_claude_model(agent_id,purpose,prompt,hard=hard)
    system=system[:7000];prompt=prompt[:9000]
    max_tokens=min(1600,max(64,int(max_tokens)))
    cache_key=_cache_key(agent_id,model,system,prompt)
    if cfg.get('claude_cache_enabled','1')=='1':
        cached=one('SELECT response,created_epoch FROM brain_response_cache WHERE key=?',(cache_key,))
        if cached and time.time()-int(cached['created_epoch'])<6*3600:
            return cached['response']
    try:
        rid,_=reserve_budget(agent_id,model,purpose,prompt,system,max_tokens,route_reason)
    except ValueError as e:
        raise ModelError(str(e)) from e
    request={
        'model':model,'max_tokens':max_tokens,
        'system':system,
        'messages':[{'role':'user','content':prompt}],
    }
    # Anthropic prompt caching is only potentially useful with substantial
    # stable prefixes; short prompts get no forced cache write.
    if cfg.get('claude_cache_enabled','1')=='1' and len(system)>2500:
        request['cache_control']={'type':'ephemeral'}
    try:
        if client is None:
            with httpx.Client(timeout=55) as http_client:
                response=http_client.post('https://api.anthropic.com/v1/messages',headers={
                    'x-api-key':key,'anthropic-version':'2023-06-01','content-type':'application/json'},json=request)
        else:
            response=client.post('https://api.anthropic.com/v1/messages',headers={
                'x-api-key':key,'anthropic-version':'2023-06-01','content-type':'application/json'},json=request)
        response.raise_for_status()
        result=response.json()
        usage=result.get('usage') or {}
        output=''.join(block.get('text','') for block in result.get('content',[])
                       if block.get('type')=='text').strip()
        if not output:raise ModelError('Claude không trả văn bản.')
        _update_usage(rid,'completed',usage,model)
        if output.strip().upper()=='NEED_CLAUDE' and model==DEFAULT_CHEAP and not hard:
            # One escalation only; the high-model call is independently budget-checked.
            return ask_claude(agent_id,system,prompt,purpose,hard=True,client=client,max_tokens=max_tokens)
        if cfg.get('claude_cache_enabled','1')=='1':
            run('''INSERT INTO brain_response_cache(key,agent_id,model,response,created_epoch) VALUES(?,?,?,?,?)
                   ON CONFLICT(key) DO UPDATE SET response=excluded.response,created_epoch=excluded.created_epoch''',
                (cache_key,agent_id,model,output,int(time.time())))
        return output
    except httpx.HTTPStatusError as e:
        _update_usage(rid,'failed',model=model)
        raise ModelError(f'Claude API HTTP {e.response.status_code}: {e.response.text[:200]}') from e
    except (httpx.RequestError,KeyError,ValueError,ModelError) as e:
        _update_usage(rid,'failed',model=model)
        raise ModelError(f'Không thể hoàn tất Claude: {str(e)[:200]}') from e


def enqueue_learning(agent_id:str,event_type:str,body:str,source_ref:str='',page_id:str|None=None):
    if agent_id not in AGENT_IDS:return None
    # Observations are stored locally; LLM isn't called by this function.
    if not (body or '').strip():return None
    eid='E'+uuid.uuid4().hex[:16]
    run('''INSERT INTO agent_learning_events(id,agent_id,event_type,body,source_ref,page_id,created)
           VALUES(?,?,?,?,?,?,?)''',(eid,agent_id,event_type,body[:1800],source_ref[:150],page_id,now()))
    return eid


def teach_agent(agent_id:str,note:str,source_ref:str='',page_id:str|None=None,verified=False,kind='observation'):
    if agent_id not in AGENT_IDS:raise ValueError('Agent không hợp lệ')
    note=' '.join((note or '').strip().split())[:900]
    if len(note)<8:raise ValueError('Bài học quá ngắn')
    digest=hashlib.sha256(f'{kind}|{page_id}|{note.lower()}'.encode()).hexdigest()
    confidence='verified' if verified else 'unverified'
    mid='M'+uuid.uuid4().hex[:16]
    with db() as c:
        c.execute('''INSERT OR IGNORE INTO agent_memories(id,agent_id,kind,content,source_ref,page_id,confidence,digest,created)
                     VALUES(?,?,?,?,?,?,?,?,?)''',(mid,agent_id,kind,note,source_ref,page_id,confidence,digest,now()))
    return one('SELECT id,agent_id,kind,content,source_ref,page_id,confidence,created FROM agent_memories WHERE agent_id=? AND digest=?',(agent_id,digest))


def learning_tick(batch_size:int=30):
    """Process local learning events while service is up; costs $0 in Claude tokens."""
    init_brains()
    if budget_settings().get('brain_learning_enabled','1')!='1':return {'processed':0}
    processed=0
    rows=all_rows("SELECT * FROM agent_learning_events WHERE status='pending' ORDER BY created,id LIMIT ?",(min(batch_size,100),))
    for e in rows:
        kind='verified_metric' if e['event_type']=='verified_metric' else 'work_observation'
        verified=e['event_type']=='verified_metric'
        teach_agent(e['agent_id'],e['body'],e['source_ref'],e['page_id'],verified,kind)
        with db() as c:
            changed=c.execute("UPDATE agent_learning_events SET status='processed',processed_at=? WHERE id=? AND status='pending'",(now(),e['id'])).rowcount
            if changed:
                c.execute('UPDATE agent_brain_state SET processed_events=processed_events+1,last_cycle=? WHERE agent_id=?',(now(),e['agent_id']))
                processed+=1
    return {'processed':processed}


def _terms(s:str)->set[str]:
    return {x for x in re.findall(r'[\wÀ-ỹ]+',s.lower()) if len(x)>=3}


def relevant_memories(agent_id:str,task:str,page_id:str|None=None,limit:int=4):
    """Local lexical ranking: no vector/embedding API costs or cross-agent leaks."""
    if agent_id not in AGENT_IDS:return []
    rows=all_rows('''SELECT content,confidence,kind,source_ref,page_id,created FROM agent_memories
       WHERE agent_id=? AND (page_id IS NULL OR page_id=?) ORDER BY created DESC LIMIT 150''',(agent_id,page_id))
    terms=_terms(task)
    ranking=[]
    for row in rows:
        score=len(terms&_terms(row['content']))
        if row['page_id'] and row['page_id']==page_id:score+=2
        if row['confidence']=='verified':score+=1
        if score>0:ranking.append((score,row))
    ranking.sort(key=lambda x:x[0],reverse=True)
    return [r for _,r in ranking[:min(limit,6)]]


def agent_brain_overview():
    state=all_rows('''SELECT a.id,a.name,bs.last_cycle,bs.processed_events,
       (SELECT COUNT(*) FROM agent_memories m WHERE m.agent_id=a.id) AS memory_count,
       (SELECT COUNT(*) FROM agent_learning_events e WHERE e.agent_id=a.id AND e.status='pending') AS pending_learning
       FROM agents a LEFT JOIN agent_brain_state bs ON bs.agent_id=a.id ORDER BY a.rowid''')
    recent=all_rows('''SELECT agent_id,model,purpose,route_reason,status,cost_usd,created
                         FROM claude_usage ORDER BY created DESC LIMIT 12''')
    return {'agents':state,'cost':spent_report(),
            'routing':{'mode':'automatic','routine_model':DEFAULT_CHEAP,
                       'complex_model':DEFAULT_HARD,'recent':recent},
            'learning_mode':'local_events_while_server_running','claude_calls_when_idle':0}
