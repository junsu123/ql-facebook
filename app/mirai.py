"""MiraiAPI transport shared by the Academy and the Design Agent.

CEO / ordinary staff tasks continue to use a separate direct Anthropic key;
the Academy and poster design both consume MiraiAPI quota from one ledger.
No credentials or image payloads are logged.
"""
from __future__ import annotations

import base64
import math
import re
import sqlite3
import time
import uuid
from datetime import datetime, timezone, timedelta

import httpx

from .ai import ModelError, get_key
from .db import db, now, one, all_rows

MIRAI_BASE = 'https://api.miraiapi.com/v1'
DEFAULT_MODEL = 'claude-opus-4.8'  # Example in MiraiAPI docs; user must verify key access.
DEFAULT_RATIO = 1.0  # Placeholder: set the model's real ratio from miraiapi.com/usage/#models
MODEL_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$')
SCHEMA = '''
CREATE TABLE IF NOT EXISTS mirai_academy_usage (
    id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, model TEXT NOT NULL,
    ratio REAL NOT NULL, purpose TEXT NOT NULL,
    status TEXT NOT NULL,
    quota_reserved INTEGER NOT NULL DEFAULT 0,
    quota_used INTEGER NOT NULL DEFAULT 0,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    usage_source TEXT NOT NULL DEFAULT '',
    created TEXT NOT NULL, finished_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_mirai_academy_day ON mirai_academy_usage(created,status);
'''

def init_mirai():
    with db() as c:
        c.executescript(SCHEMA)
        c.executemany('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)', [
            ('academy_mirai_model', DEFAULT_MODEL),
            ('academy_mirai_ratio', str(DEFAULT_RATIO)),
        ])


def _today_start_utc() -> str:
    # Vietnam uses UTC+07 for current calendar days, no timezone database needed.
    tz=timezone(timedelta(hours=7))
    local_date=datetime.now(tz).date()
    return datetime.combine(local_date,datetime.min.time(),tzinfo=tz).astimezone(timezone.utc).isoformat(timespec='seconds')


def _quota_today(c:sqlite3.Connection) -> int:
    row=c.execute('''SELECT COALESCE(SUM(CASE WHEN status IN ('reserved','unknown') THEN quota_reserved
                       WHEN status='completed' THEN quota_used ELSE 0 END),0) AS quota
                       FROM mirai_academy_usage WHERE created>=?''',(_today_start_utc(),)).fetchone()
    return int(row['quota'])


def mirai_report() -> dict:
    init_mirai()
    cfg={row['key']:row['value'] for row in all_rows('SELECT key,value FROM settings')}
    cap=int(cfg.get('academy_daily_token_limit','10000000'))
    with db() as c:
        used=_quota_today(c)
        rows=c.execute('''SELECT status,COALESCE(COUNT(*),0) n,
             COALESCE(SUM(input_tokens),0) input_tokens,
             COALESCE(SUM(output_tokens),0) output_tokens
             FROM mirai_academy_usage WHERE created>=? GROUP BY status''',(_today_start_utc(),)).fetchall()
    with db() as c:
        by_agent=c.execute('''SELECT agent_id,COALESCE(SUM(CASE
              WHEN status IN ('reserved','unknown') THEN quota_reserved
              WHEN status='completed' THEN quota_used ELSE 0 END),0) AS quota
              FROM mirai_academy_usage WHERE created>=? GROUP BY agent_id''',(_today_start_utc(),)).fetchall()
    return {'provider':'miraiapi.com','used_quota_today':used,'daily_quota_limit':cap,
            'target_quota_today':cap,'quota_by_agent':{x['agent_id']:x['quota'] for x in by_agent},
            'target_status':'reached' if used>=cap else 'in_progress',
            'quota_remaining':max(0,cap-used),
            'model':cfg.get('academy_mirai_model',DEFAULT_MODEL),
            'model_ratio':float(cfg.get('academy_mirai_ratio',str(DEFAULT_RATIO))),
            'configured':bool(get_key('mirai')),
            'details':{x['status']:{'calls':x['n'],'input_tokens':x['input_tokens'],
                      'output_tokens':x['output_tokens']} for x in rows},
            'note':'Quota từ học viện, test API và thiết kế poster đều dùng chung hạn mức MiraiAPI. Đối chiếu số dư tại miraiapi.com/usage/.'}


def _reserve(agent_id:str, purpose:str, system:str, prompt:str, max_tokens:int, model:str, ratio:float, *, extra_input_tokens:int=0)->tuple[str,int]:
    # Estimate conservatively before network request to avoid quota overshoot.
    input_upper=len((system+'\n'+prompt).encode('utf-8'))+256+max(0,int(extra_input_tokens))
    reserved=math.ceil((input_upper + max_tokens*5)*ratio)
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        cap_row=c.execute("SELECT value FROM settings WHERE key='academy_daily_token_limit'").fetchone()
        cap=int(cap_row['value']) if cap_row else 10_000_000
        spent=_quota_today(c)
        if spent+reserved>cap:
            raise ModelError('Học viện đã đạt giới hạn quota MiraiAPI nội bộ hôm nay; không gửi yêu cầu mới.')
        rid='M'+uuid.uuid4().hex
        c.execute('''INSERT INTO mirai_academy_usage
          (id,agent_id,model,ratio,purpose,status,quota_reserved,created)
          VALUES(?,?,?,?,?,?,?,?)''', (rid,agent_id,model,ratio,purpose,'reserved',reserved,now()))
    return rid,reserved


def _finish(rid:str,status:str,*,in_tokens:int=0,out_tokens:int=0,quota:int=0,source:str=''):
    with db() as c:
        c.execute('''UPDATE mirai_academy_usage SET status=?,input_tokens=?,output_tokens=?,
           quota_used=?,usage_source=?,finished_at=? WHERE id=?''',
           (status,in_tokens,out_tokens,quota,source,now(),rid))


def ask_mirai(agent_id:str,system:str,prompt:str,purpose:str='academy_training',
              *,max_tokens:int=850,client:httpx.Client|None=None,return_receipt:bool=False)->str|dict:
    """Academy request using MiraiAPI OpenAI-compatible chat completions.

    No implicit retries and no network call when quota is exceeded. A timeout
    is considered ambiguous: the reservation stays counted until reconciled.
    """
    from .brains import AGENT_IDS
    if agent_id not in AGENT_IDS:raise ModelError('Agent không hợp lệ')
    key=get_key('mirai')
    if not key:raise ModelError('Hãy nhập MiraiAPI Key trong Cài đặt Học viện 10M.')
    init_mirai()
    cfg={x['key']:x['value'] for x in all_rows('SELECT key,value FROM settings')}
    model=cfg.get('academy_mirai_model',DEFAULT_MODEL).strip()
    if not MODEL_RE.fullmatch(model):raise ModelError('Model MiraiAPI không hợp lệ.')
    try: ratio=float(cfg.get('academy_mirai_ratio',str(DEFAULT_RATIO)))
    except ValueError:raise ModelError('Hệ số quota MiraiAPI không hợp lệ.')
    if not math.isfinite(ratio) or ratio<0.01 or ratio>100:
        raise ModelError('Hệ số quota MiraiAPI phải từ 0.01 đến 100.')
    max_tokens=max(64,min(1800,int(max_tokens)))
    system=system[:8000];prompt=prompt[:10000]
    rid,estimated=_reserve(agent_id,purpose,system,prompt,max_tokens,model,ratio)
    started=time.monotonic()
    payload={'model':model,'messages':[{'role':'system','content':system},
              {'role':'user','content':prompt}], 'max_tokens':max_tokens,'stream':False}
    try:
        if client is None:
            with httpx.Client(timeout=65,follow_redirects=False) as http:
                response=http.post(MIRAI_BASE+'/chat/completions',
                    headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},json=payload)
        else:
            response=client.post(MIRAI_BASE+'/chat/completions',
                    headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},json=payload)
        if response.status_code>=400:
            _finish(rid,'failed',source='http_'+str(response.status_code))
            if response.status_code in (401,403):
                raise ModelError('MiraiAPI từ chối key, model hoặc quota (HTTP '+str(response.status_code)+').')
            if response.status_code==429:
                raise ModelError('MiraiAPI đang giới hạn tốc độ (429).')
            raise ModelError('MiraiAPI trả HTTP '+str(response.status_code)+'.')
        data=response.json()
        choices=data.get('choices') or []
        msg=choices[0].get('message',{}) if choices and isinstance(choices[0],dict) else {}
        content=msg.get('content','')
        if isinstance(content,list):
            content='\n'.join(x.get('text','') for x in content if isinstance(x,dict))
        if not isinstance(content,str) or not content.strip():
            _finish(rid,'unknown',source='missing_text')
            raise ModelError('MiraiAPI không trả nội dung văn bản hợp lệ; đã giữ quota dự trù để đối soát.')
        usage=data.get('usage') or {}
        in_count=usage.get('prompt_tokens',usage.get('input_tokens'))
        out_count=usage.get('completion_tokens',usage.get('output_tokens'))
        if in_count is None or out_count is None:
            _finish(rid,'unknown',source='missing_usage')
            in_count=out_count=None
            quota=estimated
            quota_status='reserved_unknown_usage'
        else:
            in_count=max(0,int(in_count));out_count=max(0,int(out_count))
            quota=math.ceil((in_count+out_count*5)*ratio)
            _finish(rid,'completed',in_tokens=in_count,out_tokens=out_count,quota=quota,source='api_usage')
            quota_status='actual_usage'
        if return_receipt:
            return {'ok':True,'provider':'MiraiAPI','model':model,'reply':content.strip()[:320],
                    'latency_ms':round((time.monotonic()-started)*1000),
                    'prompt_tokens':in_count,'completion_tokens':out_count,
                    'quota_used':quota,'quota_status':quota_status,
                    'note':('Quota tính từ usage trả về.' if quota_status=='actual_usage'
                            else 'Không có usage trong phản hồi. Đã giữ quota dự trù để tránh vượt hạn mức.')}
        return content.strip()
    except ModelError:
        raise
    except (httpx.RequestError,ValueError,KeyError,TypeError) as ex:
        # Timeouts/transport drops can occur after upstream has billed the call.
        _finish(rid,'unknown',source='request_unconfirmed')
        raise ModelError('Không xác định kết quả MiraiAPI; đã giữ quota dự trù, vui lòng kiểm tra trạng thái kết nối.') from ex


def ask_mirai_design_vision(system: str, prompt: str, image_bytes: bytes, mime: str,
                            *, client: httpx.Client|None=None, max_tokens: int=2000) -> dict:
    """One Claude-vision concept request through MiraiAPI's OpenAI interface.

    Uses the SAME persisted key, model, model ratio and 10M quota ledger as the
    academy. This endpoint never falls back to Anthropic, never retries, and
    never stores or logs the base64 image in API call history.
    """
    key=get_key('mirai')
    if not key:
        raise ModelError('Chưa cấu hình MiraiAPI Key. Vào Cài đặt > MiraiAPI trước khi thiết kế.')
    init_mirai()
    cfg={row['key']:row['value'] for row in all_rows('SELECT key,value FROM settings')}
    model=cfg.get('academy_mirai_model',DEFAULT_MODEL).strip()
    if not MODEL_RE.fullmatch(model) or not model.lower().startswith('claude-'):
        raise ModelError('Hãy chọn một model Claude có hỗ trợ ảnh trong cấu hình MiraiAPI.')
    try:
        ratio=float(cfg.get('academy_mirai_ratio',str(DEFAULT_RATIO)))
    except ValueError as exc:
        raise ModelError('Hệ số quota MiraiAPI không hợp lệ.') from exc
    if not math.isfinite(ratio) or not 0.01 <= ratio <= 100:
        raise ModelError('Hệ số quota MiraiAPI phải từ 0.01 đến 100.')
    if mime not in ('image/jpeg','image/png','image/webp') or not image_bytes:
        raise ModelError('Ảnh gửi MiraiAPI không hợp lệ.')
    # Images consume provider-dependent vision tokens. Reserve extra headroom;
    # this is a safety ESTIMATE, not a guarantee of exact upstream billing.
    image_reserve_tokens=max(16000,math.ceil(len(image_bytes)/24))
    max_tokens=max(100,min(3000,int(max_tokens)))
    system=system[:8000]
    prompt=prompt[:12000]
    rid,estimated=_reserve('creative','design_direct',system,prompt,max_tokens,
                           model,ratio,extra_input_tokens=image_reserve_tokens)
    encoded=base64.b64encode(image_bytes).decode('ascii')
    payload={
       'model':model,'max_tokens':max_tokens,'stream':False,
       'messages':[{'role':'system','content':system},
          {'role':'user','content':[
             {'type':'text','text':prompt},
             {'type':'image_url','image_url':{'url':f'data:{mime};base64,{encoded}'}}
          ]}]
    }
    headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'}
    try:
        if client is None:
            with httpx.Client(timeout=90,follow_redirects=False) as session:
                response=session.post(MIRAI_BASE+'/chat/completions',headers=headers,json=payload)
        else:
            response=client.post(MIRAI_BASE+'/chat/completions',headers=headers,json=payload)
    except httpx.RequestError as exc:
        _finish(rid,'unknown',source='vision_network_unconfirmed')
        raise ModelError('Không rõ MiraiAPI đã xử lý yêu cầu ảnh hay chưa. Đã giữ quota dự trù, không gọi lại tự động.') from exc

    if response.status_code >= 400:
        _finish(rid,'failed',source='vision_http_'+str(response.status_code))
        if response.status_code in (401,403):
            raise ModelError(f'MiraiAPI từ chối khóa API hoặc model (HTTP {response.status_code}).')
        if response.status_code==429:
            raise ModelError('MiraiAPI đang giới hạn tốc độ (HTTP 429).')
        if response.status_code==400:
            raise ModelError('MiraiAPI từ chối yêu cầu (HTTP 400). Hãy kiểm tra model Claude có hỗ trợ ảnh Vision.')
        raise ModelError(f'MiraiAPI trả HTTP {response.status_code}.')

    try:
        response_json=response.json()
        choices=response_json.get('choices') or []
        content=choices[0]['message'].get('content') if choices else None
        if isinstance(content,list):
            content='\n'.join(part.get('text','') for part in content if isinstance(part,dict))
        usage=response_json.get('usage') or {}
        in_count=usage.get('prompt_tokens',usage.get('input_tokens'))
        out_count=usage.get('completion_tokens',usage.get('output_tokens'))
    except (ValueError,KeyError,TypeError,IndexError,AttributeError) as exc:
        _finish(rid,'unknown',source='vision_invalid_response')
        raise ModelError('MiraiAPI trả cấu trúc phản hồi không hợp lệ. Đã giữ quota dự trù để đối soát.') from exc

    if in_count is None or out_count is None:
        quota=estimated
        in_count=out_count=None
        quota_status='reserved_unknown_usage'
        _finish(rid,'unknown',source='vision_missing_usage')
    else:
        try:
            in_count=max(0,int(in_count));out_count=max(0,int(out_count))
        except (ValueError,TypeError) as exc:
            _finish(rid,'unknown',source='vision_invalid_usage')
            raise ModelError('MiraiAPI trả số token không hợp lệ; giữ quota dự trù.') from exc
        quota=math.ceil((in_count+out_count*5)*ratio)
        quota_status='actual_usage'
        _finish(rid,'completed',in_tokens=in_count,out_tokens=out_count,
                quota=quota,source='api_usage_vision')
    if not isinstance(content,str) or not content.strip():
        raise ModelError('MiraiAPI không trả nội dung concept, nhưng yêu cầu có thể đã tiêu quota.')
    return {'text':content.strip(),'model':model,'input_tokens':in_count,
            'output_tokens':out_count,'quota_used':quota,'quota_status':quota_status,
            'provider':'miraiapi'}


def available_models(*,client:httpx.Client|None=None) -> dict:
    """GET models uses no inference tokens. The user's key decides accessibility."""
    key=get_key('mirai')
    if not key:raise ModelError('Chưa lưu MiraiAPI Key.')
    try:
        if client is None:
            with httpx.Client(timeout=20,follow_redirects=False) as http:
                response=http.get(MIRAI_BASE+'/models',headers={'Authorization':'Bearer '+key})
        else:response=client.get(MIRAI_BASE+'/models',headers={'Authorization':'Bearer '+key})
        if response.status_code>=400:
            raise ModelError(f'Không thể kiểm tra danh sách model MiraiAPI (HTTP {response.status_code}).')
        data=response.json()
        models=[str(x['id']) for x in data.get('data',[]) if isinstance(x,dict) and MODEL_RE.fullmatch(str(x.get('id','')))]
        return {'ok':True,'models':models[:250], 'note':'Model đúng theo key. Hệ số quota cần đối chiếu tại trang Model & giá của MiraiAPI.'}
    except (httpx.RequestError,ValueError,KeyError) as ex:
        raise ModelError('Không thể kết nối MiraiAPI Models API; kiểm tra Base URL và mạng.') from ex


def test_mirai_completion(*,client:httpx.Client|None=None)->dict:
    """A real, small paid request. Never return the API key to the frontend.

    Unlike the existing GET /models check, this verifies the configured model
    actually answers POST /chat/completions. Account quota may be charged.
    """
    return ask_mirai('research',
                     'Bạn đang kiểm tra kết nối API. Chỉ trả lời ngắn gọn.',
                     'Phản hồi một từ: OK',
                     purpose='connection_test',max_tokens=64,
                     client=client,return_receipt=True)
