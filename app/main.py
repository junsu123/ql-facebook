"""Local-first API for the AI Fanpage Company desktop dashboard.
Start: python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
"""
from __future__ import annotations
import csv
import io
import os
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, Future
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Body, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict
from PIL import Image, UnidentifiedImageError

from .db import BASE, MEDIA_DIR, all_rows, db, initialize, log, now, one, run
from .ai import (ModelError, ceo_message, config, create_task, execute_task,
                 generate_content, save_key, get_key)
from .brains import (agent_brain_overview, relevant_memories, learning_tick,
                     enqueue_learning, spent_report, AGENT_IDS)
from .academy import academy_overview, add_source, academy_tick, recover_interrupted_academy_jobs
from .mirai import available_models, mirai_report, init_mirai, test_mirai_completion
from .growth import (create_sprint, get_sprint, list_sprints, record_progress,
                     set_baseline, generate_ceo_plan, attach_page)
from .firefox import (BrowserError, account_status, create_profile, open_profile,
                      close_profile, confirm_login, delete_profile, executable)
from .firefox_installer import (FirefoxInstallError, start_install as start_firefox_install,
                                status as firefox_install_status)

ROOT=Path(__file__).resolve().parent.parent
WEB=ROOT/'web'
app=FastAPI(title='AI Fanpage Company',version='1.9.0',docs_url='/api/docs',redoc_url=None)
INSTANCE_ID=uuid.uuid4().hex
initialize()
app.mount('/assets',StaticFiles(directory=WEB/'assets'),name='assets')
app.mount('/media',StaticFiles(directory=MEDIA_DIR),name='media')
executor=ThreadPoolExecutor(max_workers=2,thread_name_prefix='aifc-agent')
_worker_lock=threading.Lock()
_submitted:set[str]=set()
_stop=threading.Event()
_academy_lock=threading.Lock()
_academy_future=None
_background_lock=threading.Lock()
_background_jobs:set[Future]=set()

def submit_background(fn, *args):
    """Track asynchronous CEO/growth requests so updates do not stop paid work."""
    with _background_lock:
        future=executor.submit(fn,*args)
        _background_jobs.add(future)
    def completed(done):
        with _background_lock:_background_jobs.discard(done)
    future.add_done_callback(completed)
    return future

@app.middleware('http')
async def local_only(request: Request, call_next):
    # The local dashboard can launch browser processes and handle API keys.
    # Never expose this app to a public interface without adding strong auth.
    host=request.url.hostname
    if host not in ('127.0.0.1','localhost','testserver'):
        return JSONResponse({'detail':'Chỉ cho phép truy cập localhost'},403)
    if request.method not in ('GET','HEAD','OPTIONS'):
        origin=request.headers.get('origin','')
        if origin and (urlparse(origin).hostname not in ('127.0.0.1','localhost','testserver')):
            return JSONResponse({'detail':'Không cho phép yêu cầu từ trang khác'},403)
    return await call_next(request)

@app.get('/')
def index():return FileResponse(WEB/'index.html')

@app.get('/api/health')
def health():
    return {'ok':True,'version':'1.9.0','instance_id':INSTANCE_ID,'supervised':os.environ.get('AIFC_SUPERVISED')=='1','platform':os.name,'firefox_available':bool(executable()),'data_dir':str(BASE)}

@app.get('/api/system/restart-readiness')
def restart_readiness():
    """Signal to the launcher that it is safe to restart this process.

    Do not interrupt Claude calls or academy work to update UI/code.  If work
    is stuck, the user can stop the app explicitly; the watcher does not force
    an automatic restart while a paid AI operation is still running.
    """
    with _worker_lock:
        queued_workers = len(_submitted)
    academy_running = bool(_academy_future and not _academy_future.done())
    with _background_lock:
        background_running=sum(1 for job in _background_jobs if not job.done())
    active = queued_workers + int(academy_running) + background_running
    return {'ready': active == 0, 'active_workers': queued_workers,
            'academy_busy': academy_running, 'background_busy': background_running,
            'reason': 'Có tác vụ Claude / Học viện AI đang chạy.' if active else 'Sẵn sàng khởi động lại.'}

@app.get('/api/bootstrap')
def bootstrap():
    accounts=[account_status(a) for a in all_rows('SELECT * FROM accounts ORDER BY created DESC')]
    agents=all_rows('SELECT * FROM agents')
    for agent in agents:
        agent['active_tasks']=one("SELECT count(*) AS n FROM tasks WHERE agent_id=? AND status='running'",(agent['id'],))['n']
        agent['queued_tasks']=one("SELECT count(*) AS n FROM tasks WHERE agent_id=? AND status='queued'",(agent['id'],))['n']
    return {
        'accounts':accounts,
        'pages':all_rows('SELECT * FROM pages ORDER BY created DESC'),
        'agents':agents,
        'tasks':all_rows('SELECT * FROM tasks ORDER BY created DESC LIMIT 150'),
        'contents':all_rows('SELECT c.*,p.name AS page_name FROM contents c JOIN pages p ON c.page_id=p.id ORDER BY c.created DESC LIMIT 250'),
        'chat':all_rows('SELECT * FROM chats ORDER BY id DESC LIMIT 40')[::-1],
        'activities':all_rows('SELECT a.*,ag.name AS agent_name FROM activity a LEFT JOIN agents ag ON a.agent_id=ag.id ORDER BY a.id DESC LIMIT 100'),
        'metrics':all_rows('SELECT m.*,p.name AS page_name FROM metrics m JOIN pages p ON m.page_id=p.id ORDER BY m.date DESC LIMIT 300'),
        'campaigns':all_rows('SELECT * FROM campaigns ORDER BY created DESC LIMIT 30'),
        'growth_sprints':list_sprints(25),
        'settings':config(),
        'brain_overview':agent_brain_overview(),
        'academy':academy_overview(),
        'firefox_available':bool(executable()),
        'firefox_installer':firefox_install_status(),
        'counts':{
            'pages':one('SELECT count(*) AS n FROM pages')['n'],
            'accounts':len(accounts),
            'queued':one("SELECT count(*) AS n FROM tasks WHERE status='queued'")['n'],
            'running':one("SELECT count(*) AS n FROM tasks WHERE status='running'")['n'],
            'drafts':one("SELECT count(*) AS n FROM contents WHERE status IN ('draft','needs_revision')")['n'],
            'scheduled':one("SELECT count(*) AS n FROM contents WHERE status='scheduled'")['n'],
            'ready':one("SELECT count(*) AS n FROM contents WHERE status='ready'")['n'],
            'posted':one("SELECT count(*) AS n FROM contents WHERE status='published_manual'")['n']
        }
    }

class SettingsChange(BaseModel):
    # Only Claude is configurable. Extra legacy provider/model fields are rejected
    # instead of silently re-enabling another provider.
    model_config = ConfigDict(extra='forbid')
    claude_key:str|None=None
    mirai_key:str|None=None
    academy_mirai_model:str|None=Field(default=None,min_length=1,max_length=100,pattern=r'^[A-Za-z0-9][A-Za-z0-9._:-]*$')
    academy_mirai_ratio:float|None=Field(default=None,ge=0.01,le=100)
    daily_llm_call_limit:int|None=Field(default=None,ge=1,le=10000)
    auto_run_agents:bool|None=None
    firefox_path:str|None=None
    claude_cache_enabled:bool|None=None
    brain_learning_enabled:bool|None=None
    claude_daily_budget_usd:float|None=Field(default=None,ge=0,le=1000)
    claude_agent_daily_budget_usd:float|None=Field(default=None,ge=0,le=1000)
    academy_daily_token_limit:int|None=Field(default=None,ge=10000,le=100000000)
    academy_enabled:bool|None=None
    academy_interval_seconds:int|None=Field(default=None,ge=10,le=3600)

@app.post('/api/settings')
def update_settings(req:SettingsChange):
    values=req.model_dump(exclude_unset=True,exclude_none=True)
    saved=('daily_llm_call_limit','firefox_path','auto_run_agents',
           'claude_cache_enabled','brain_learning_enabled',
           'claude_daily_budget_usd','claude_agent_daily_budget_usd',
           'academy_daily_token_limit','academy_enabled','academy_interval_seconds',
           'academy_mirai_model','academy_mirai_ratio')
    with db() as c:
        c.execute("INSERT INTO settings(key,value) VALUES('provider','claude') ON CONFLICT(key) DO UPDATE SET value='claude'")
        for key in saved:
            if key not in values:
                continue
            value=('1' if values[key] else '0') if key in ('auto_run_agents','claude_cache_enabled','brain_learning_enabled','academy_enabled') else str(values[key])
            c.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,value))
    if 'claude_key' in values:
        save_key('claude',values['claude_key'])
    if 'mirai_key' in values:
        save_key('mirai',values['mirai_key'])
    log('ceo','settings','Đã cập nhật cấu hình Claude và MiraiAPI Học viện (không ghi API key).')
    return {'ok':True,'settings':config()}

@app.post('/api/claude/check')
def claude_connection_check():
    """Checks API-key validity and model access via Models API; no inference tokens."""
    import httpx
    key=get_key('claude')
    if not key:raise HTTPException(400,'Bạn chưa nhập Claude API key.')
    try:
        with httpx.Client(timeout=15) as client:
            response=client.get('https://api.anthropic.com/v1/models',headers={
                'x-api-key':key,'anthropic-version':'2023-06-01'},params={'limit':100})
        response.raise_for_status()
        available={m.get('id') for m in response.json().get('data',[]) if isinstance(m,dict)}
        return {'ok':True,'haiku_available':'claude-haiku-5-5' in available,
                'sonnet_available':'claude-sonnet-5-5' in available,
                'note':'Danh sách model khả dụng theo khóa API tại thời điểm kiểm tra; không gọi suy luận.'}
    except httpx.HTTPStatusError as e:
        raise HTTPException(400,f'Claude từ chối kiểm tra key: HTTP {e.response.status_code}') from e
    except (httpx.RequestError,ValueError) as e:
        raise HTTPException(503,'Không thể kết nối Claude Models API để kiểm tra.') from e

@app.post('/api/mirai/check')
def mirai_connection_check():
    try:
        return available_models()
    except ModelError as exc:
        raise HTTPException(400,str(exc)) from exc

@app.post('/api/mirai/test-call')
def mirai_test_call():
    # Explicitly invoked, paid inference test. The service reads the saved key
    # and model; neither the key nor raw provider payload is sent to the UI.
    try:
        return test_mirai_completion()
    except ModelError as exc:
        raise HTTPException(400,str(exc)) from exc

@app.get('/api/mirai/usage')
def get_mirai_usage():
    return mirai_report()

@app.get('/api/academy')
def get_academy():
    return academy_overview()

class AcademySourceInput(BaseModel):
    title: str=Field(min_length=3,max_length=180)
    content: str=Field(min_length=160,max_length=300000)
    source_ref: str=Field(default='',max_length=350)
    agents: list[str]|None=None
    owner_has_rights: bool=False

@app.post('/api/academy/sources')
def upload_academy_source(req:AcademySourceInput):
    if not req.owner_has_rights:
        raise HTTPException(400,'Hãy xác nhận quyền sử dụng tài liệu trước khi nạp.')
    try:
        return add_source(req.title,req.content,req.source_ref,req.agents)
    except ValueError as error:
        raise HTTPException(400,str(error)) from error

@app.post('/api/academy/step')
def run_academy_step():
    # One paid request in a thread pool, not on the main HTTP worker. Explicit
    # manual trigger still requires enabled setting, and cannot bypass caps.
    global _academy_future
    if config().get('academy_enabled','0')!='1':
        raise HTTPException(400,'Hãy bật Học viện AI trước khi bắt đầu học.')
    if not get_key('mirai'):
        raise HTTPException(400,'Hãy cấu hình MiraiAPI Key cho Học viện trước.')
    with _academy_lock:
        if _academy_future and not _academy_future.done():
            return {'status':'already_running'}
        _academy_future=executor.submit(academy_tick)
    return {'status':'started'}

@app.get('/api/brains')
def brains_overview():
    return agent_brain_overview()

@app.get('/api/brains/{agent_id}/memories')
def agent_memories(agent_id:str):
    if agent_id not in AGENT_IDS:raise HTTPException(404,'Không tìm thấy agent')
    return {'agent_id':agent_id,'items':all_rows("SELECT id,kind,content,source_ref,page_id,confidence,created FROM agent_memories WHERE agent_id=? ORDER BY created DESC LIMIT 100",(agent_id,))}

@app.post('/api/brains/learn-now')
def brain_learn_now():
    return learning_tick(50)

class NewAccount(BaseModel):
    label:str=''
    auto_open:bool=True

@app.get('/api/firefox/installer')
def get_firefox_installer():
    return firefox_install_status()

@app.post('/api/firefox/installer')
def install_firefox():
    # Only user-initiated via the local dashboard; the installer itself is GUI + UAC.
    try:
        return start_firefox_install()
    except FirefoxInstallError as err:
        raise HTTPException(409, str(err))

@app.post('/api/accounts')
def add_account(req:NewAccount):
    profile=create_profile(req.label)
    if req.auto_open:
        try:profile=open_profile(profile['id'])
        except BrowserError as e:return {'account':profile,'warning':str(e)}
    return {'account':profile}

@app.post('/api/accounts/{identifier}/open')
def open_account(identifier:str):
    try:return open_profile(identifier)
    except BrowserError as err:raise HTTPException(400,str(err))

@app.post('/api/accounts/{identifier}/close')
def close_account(identifier:str):
    try:return close_profile(identifier)
    except BrowserError as err:raise HTTPException(400,str(err))

class LoginConfirmation(BaseModel):
    name:str=Field(min_length=1,max_length=100)

@app.post('/api/accounts/{identifier}/confirm')
def confirm_account(identifier:str,req:LoginConfirmation):
    try:return confirm_login(identifier,req.name)
    except BrowserError as err:raise HTTPException(400,str(err))

@app.post('/api/accounts/{identifier}/reload')
def reload_account(identifier:str):
    # Does NOT claim authenticated: opens exact profile for human inspection.
    try:
        account=open_profile(identifier)
        return {'account':account,'verification':'manual_required','note':'Firefox đã được mở. Hãy kiểm tra phiên đăng nhập và xác nhận thủ công.'}
    except BrowserError as err:raise HTTPException(400,str(err))

@app.delete('/api/accounts/{identifier}')
def remove_account(identifier:str):
    try:delete_profile(identifier)
    except BrowserError as err:raise HTTPException(400,str(err))
    return {'ok':True}

def validated_fb_url(url: str) -> str:
    url=url.strip()
    obj=urlparse(url)
    if obj.scheme!='https' or obj.hostname not in ('facebook.com','www.facebook.com','web.facebook.com','m.facebook.com') or not obj.path.strip('/'):
        raise HTTPException(400,'Chỉ chấp nhận đường dẫn Fanpage https://www.facebook.com/...')
    # Canonicalize hostname; no network fetch or scraping.
    return 'https://www.facebook.com'+obj.path.rstrip('/')

class PageCreate(BaseModel):
    name:str=Field(min_length=2,max_length=140)
    url:str
    category:str=''
    tone:str=''
    facts:str=''
    account_id:str|None=None

@app.post('/api/pages')
def add_page(req:PageCreate):
    if one('SELECT count(*) AS n FROM pages')['n']>=100:
        raise HTTPException(400,'Phiên bản này giới hạn 100 Fanpage.')
    if req.account_id and not one('SELECT id FROM accounts WHERE id=?',(req.account_id,)):
        raise HTTPException(400,'Không tồn tại tài khoản Firefox')
    url=validated_fb_url(req.url)
    if one('SELECT id FROM pages WHERE url=?',(url,)):
        raise HTTPException(409,'Fanpage đã được liên kết')
    pid='P'+uuid.uuid4().hex[:10].upper()
    run('INSERT INTO pages(id,name,url,category,tone,facts,account_id,created) VALUES(?,?,?,?,?,?,?,?)',
        (pid,req.name.strip(),url,req.category.strip()[:100],req.tone.strip()[:500],req.facts.strip()[:10000],req.account_id,now()))
    log('strategy','page_added',f'Đã thêm Fanpage {req.name} (do người dùng nhập; chưa xác minh quyền quản trị)')
    return one('SELECT * FROM pages WHERE id=?',(pid,))

@app.put('/api/pages/{page_id}')
def edit_page(page_id:str, req:PageCreate):
    if not one('SELECT id FROM pages WHERE id=?',(page_id,)):
        raise HTTPException(404,'Không tìm thấy Fanpage')
    url=validated_fb_url(req.url)
    if req.account_id and not one('SELECT id FROM accounts WHERE id=?',(req.account_id,)):
        raise HTTPException(400,'Tài khoản Firefox không tồn tại')
    try:
        run('UPDATE pages SET name=?,url=?,category=?,tone=?,facts=?,account_id=? WHERE id=?',
            (req.name.strip(),url,req.category[:100],req.tone[:500],req.facts[:10000],req.account_id,page_id))
    except Exception as e:
        raise HTTPException(400,'URL đã liên kết hoặc dữ liệu không hợp lệ') from e
    return one('SELECT * FROM pages WHERE id=?',(page_id,))

@app.delete('/api/pages/{page_id}')
def delete_page(page_id:str):
    if not one('SELECT id FROM pages WHERE id=?',(page_id,)):
        raise HTTPException(404,'Không tìm thấy Fanpage')
    run('DELETE FROM pages WHERE id=?',(page_id,))
    log('strategy','page_removed',f'Đã xóa hồ sơ nội bộ của Page {page_id}')
    return {'ok':True}

class MemoryNew(BaseModel):
    note:str=Field(min_length=5,max_length=3000)

@app.get('/api/pages/{page_id}/memory')
def get_memory(page_id:str):
    return all_rows('SELECT * FROM memories WHERE page_id=? ORDER BY id DESC',(page_id,))

@app.post('/api/pages/{page_id}/memory')
def add_memory(page_id:str,req:MemoryNew):
    if not one('SELECT id FROM pages WHERE id=?',(page_id,)):
        raise HTTPException(404,'Không tìm thấy Fanpage')
    run('INSERT INTO memories(page_id,note,source,created) VALUES(?,?,?,?)',(page_id,req.note,'owner',now()))
    log('strategy','memory','Đã cập nhật bộ nhớ Fanpage dựa trên dữ liệu do chủ sở hữu cung cấp.')
    return {'ok':True}

class ChatNew(BaseModel):
    message:str=Field(min_length=1,max_length=6000)

@app.post('/api/ceo/chat')
def chat(req:ChatNew):
    return ceo_message(req.message)

class TaskNew(BaseModel):
    agent_id:str
    title:str=Field(min_length=3,max_length=180)
    instructions:str=''
    page_id:str|None=None

class CampaignCreate(BaseModel):
    topic:str=Field(min_length=5,max_length=300)
    category:str=''
    max_pages:int=Field(default=100,ge=1,le=100)

@app.post('/api/ceo/campaigns')
def create_campaign(req:CampaignCreate):
    if req.category:
        pages=all_rows('SELECT id,name FROM pages WHERE category=? AND length(trim(facts))>0 ORDER BY created LIMIT ?',
                       (req.category,req.max_pages))
    else:
        pages=all_rows('SELECT id,name FROM pages WHERE length(trim(facts))>0 ORDER BY created LIMIT ?',
                       (req.max_pages,))
    if not pages:
        raise HTTPException(400,'Không có Page đủ dữ liệu xác thực. Cần bổ sung thông tin sản phẩm trước.')
    cid='CAM'+uuid.uuid4().hex[:9].upper()
    run('INSERT INTO campaigns(id,topic,category,planned_pages,created) VALUES(?,?,?,?,?)',
        (cid,req.topic,req.category,len(pages),now()))
    for p in pages:
        create_task('content',f'{req.topic} · {p["name"]}',
                    f'Soạn một bài Facebook độc lập theo chủ đề: {req.topic}. '
                    'Chỉ dùng dữ liệu đã xác thực của Page, không sao chép các Page khác. '
                    'Đây là bản nháp, tuyệt đối không tự nhận đã xuất bản.',
                    p['id'],'ceo_campaign',cid)
    log('ceo','campaign',f'Tạo chiến dịch {cid}: {len(pages)} Page, chủ đề: {req.topic}')
    return {'id':cid,'queued':len(pages),'topic':req.topic,
            'note':'Đã đưa vào hàng đợi Content. Chưa gọi LLM và chưa xuất bản. Bật tự chạy agent trong Cài đặt nếu muốn xử lý theo hạn mức.'}

@app.get('/api/ceo/campaigns')
def list_campaigns():
    return all_rows('SELECT * FROM campaigns ORDER BY created DESC')

# CEO product-to-Fanpage 7-day growth sprint. No Facebook scraping/posting.
class GrowthSprintInput(BaseModel):
    product_name:str=Field(min_length=3,max_length=180)
    ingredients:str=Field(min_length=2,max_length=5000)
    page_id:str|None=None
    target_audience:str=Field(default='',max_length=500)
    baseline_followers:int|None=Field(default=None,ge=0,le=1000000)
    previous_week_new_follows:int|None=Field(default=None,ge=0,le=1000000)
    goal_override:int|None=Field(default=None,ge=1,le=1000000)
    start_date:str|None=None
    auto_generate:bool=True

@app.post('/api/growth/sprints')
def new_growth_sprint(req:GrowthSprintInput):
    try:
        sprint=create_sprint(**req.model_dump(exclude={'auto_generate'}))
    except ValueError as err:
        raise HTTPException(400,str(err)) from err
    if req.auto_generate and get_key('claude'):
        # Generate AI draft in background; HTTP returns the persisted local plan.
        submit_background(generate_ceo_plan,sprint['id'])
        sprint['ai_generation_queued']=True
    else:
        sprint['ai_generation_queued']=False
    return sprint

@app.get('/api/growth/sprints')
def growth_sprints():
    return list_sprints(30)

@app.get('/api/growth/sprints/{sid}')
def growth_sprint_detail(sid:str):
    result=get_sprint(sid)
    if not result:raise HTTPException(404,'Không tìm thấy chiến dịch.')
    return result

@app.post('/api/growth/sprints/{sid}/generate')
def regenerate_growth_sprint(sid:str):
    if not get_sprint(sid):raise HTTPException(404,'Không tìm thấy chiến dịch.')
    if not get_key('claude'):raise HTTPException(400,'Hãy cấu hình Claude API key trước.')
    if one('SELECT status FROM growth_sprints WHERE id=?',(sid,))['status']=='generating':
        return {'status':'already_running'}
    submit_background(generate_ceo_plan,sid)
    return {'status':'submitted','note':'CEO sẽ tạo kế hoạch AI, không đăng Facebook tự động.'}

class GrowthPageInput(BaseModel):
    page_id:str=Field(min_length=2,max_length=100)

@app.post('/api/growth/sprints/{sid}/page')
def growth_link_page(sid:str,req:GrowthPageInput):
    try:return attach_page(sid,req.page_id)
    except ValueError as err:raise HTTPException(400,str(err)) from err

class GrowthBaselineInput(BaseModel):
    baseline_followers:int=Field(ge=0,le=1000000)

@app.post('/api/growth/sprints/{sid}/baseline')
def growth_baseline(sid:str,req:GrowthBaselineInput):
    try:return set_baseline(sid,req.baseline_followers)
    except ValueError as err:raise HTTPException(400,str(err)) from err

class GrowthProgressInput(BaseModel):
    day:int=Field(ge=1,le=7)
    followers_total:int=Field(ge=0,le=1000000)
    views:int=Field(default=0,ge=0,le=1000000000)
    interactions:int=Field(default=0,ge=0,le=1000000000)
    notes:str=Field(default='',max_length=1000)

@app.post('/api/growth/sprints/{sid}/progress')
def growth_progress(sid:str,req:GrowthProgressInput):
    try:return record_progress(sid,**req.model_dump())
    except ValueError as err:raise HTTPException(400,str(err)) from err

@app.post('/api/tasks')
def new_task(req:TaskNew):
    try:tid=create_task(req.agent_id,req.title,req.instructions,req.page_id,source='owner')
    except ValueError as err:raise HTTPException(400,str(err))
    return one('SELECT * FROM tasks WHERE id=?',(tid,))


def _submit(task_id:str):
    with _worker_lock:
        if task_id in _submitted:return False
        _submitted.add(task_id)
    def work():
        try:execute_task(task_id)
        finally:
            with _worker_lock:_submitted.discard(task_id)
    executor.submit(work)
    return True

@app.post('/api/tasks/{task_id}/run')
def run_task(task_id:str):
    task=one('SELECT * FROM tasks WHERE id=?',(task_id,))
    if not task:raise HTTPException(404,'Không tìm thấy nhiệm vụ')
    if task['status'] not in ('queued','failed'):raise HTTPException(400,'Nhiệm vụ không thể chạy')
    _submit(task_id)
    return {'ok':True,'status':'submitted'}

@app.post('/api/tasks/run-queued')
def run_queued():
    tasks=all_rows("SELECT id FROM tasks WHERE status='queued' AND agent_id != 'ceo' ORDER BY CASE WHEN source='ceo_growth_sprint' THEN 0 ELSE 1 END, created LIMIT 20")
    n=sum(1 for t in tasks if _submit(t['id']))
    return {'submitted':n}

class DraftCreate(BaseModel):
    page_id:str
    topic:str=Field(min_length=2,max_length=200)
    body:str=Field(min_length=3,max_length=15000)

@app.post('/api/contents')
def create_draft(req:DraftCreate):
    if not one('SELECT id FROM pages WHERE id=?',(req.page_id,)):
        raise HTTPException(404,'Không tìm thấy Fanpage')
    cid='C'+uuid.uuid4().hex[:10].upper()
    run('INSERT INTO contents(id,page_id,topic,body,created,updated) VALUES(?,?,?,?,?,?)',
        (cid,req.page_id,req.topic.strip(),req.body.strip(),now(),now()))
    log('content','draft',f'Đã thêm bản nháp: {req.topic}')
    return one('SELECT * FROM contents WHERE id=?',(cid,))

class GenerateRequest(BaseModel):
    page_id:str
    topic:str=Field(min_length=2,max_length=300)

@app.post('/api/contents/generate')
def generate(req:GenerateRequest):
    try:return generate_content(req.page_id,req.topic)
    except (ModelError,ValueError) as err:raise HTTPException(400,str(err))

class DraftEdit(BaseModel):
    topic:str=Field(min_length=2,max_length=200)
    body:str=Field(min_length=3,max_length=15000)

@app.put('/api/contents/{cid}')
def update_draft(cid:str, req:DraftEdit):
    if not one('SELECT id FROM contents WHERE id=?',(cid,)):
        raise HTTPException(404,'Không tìm thấy bài viết')
    run('UPDATE contents SET topic=?,body=?,status=?,review_details=?,updated=? WHERE id=?',
        (req.topic.strip(),req.body.strip(),'draft','',now(),cid))
    return one('SELECT * FROM contents WHERE id=?',(cid,))

# Conservative checker. Passing this check is NOT a legal guarantee.
BANNED_PATTERNS=[
    r'\b(chữa khỏi|điều trị dứt điểm|trị tận gốc|cam kết khỏi|khỏi 100%|chắc chắn khỏi)\b',
    r'\b(thuốc tiên|thần dược|tác dụng ngay lập tức)\b',
    r'\b(đã được bác sĩ chứng nhận)\b'
]

def evaluate_content(item:dict) -> list[str]:
    issues=[]
    content=item['body'].strip()
    page=one('SELECT * FROM pages WHERE id=?',(item['page_id'],))
    if len(content)<35:issues.append('Nội dung quá ngắn (<35 ký tự).')
    if len(content)>10000:issues.append('Nội dung vượt giới hạn nội bộ (10.000 ký tự).')
    if not page or not page['facts'].strip():issues.append('Page chưa có nguồn thông tin sản phẩm/kiến thức xác thực.')
    for pattern in BANNED_PATTERNS:
        if re.search(pattern,content,re.I):
            issues.append('Phát hiện tuyên bố rủi ro: '+pattern.replace('\\b','')[:55])
    other=all_rows('SELECT id,body FROM contents WHERE page_id=? AND id!=? ORDER BY created DESC LIMIT 100',(item['page_id'],item['id']))
    for row in other:
        if SequenceMatcher(None,content.casefold(),row['body'].casefold()).ratio()>0.9:
            issues.append('Nội dung rất giống bài '+row['id'])
            break
    return issues

@app.post('/api/contents/{cid}/review')
def review(cid:str):
    item=one('SELECT * FROM contents WHERE id=?',(cid,))
    if not item:raise HTTPException(404,'Không tìm thấy bài viết')
    issues=evaluate_content(item)
    status='needs_revision' if issues else 'approved'
    run('UPDATE contents SET status=?,review_details=?,updated=? WHERE id=?',
        (status,'\n'.join(issues) if issues else 'Đạt các quy tắc kiểm tra tự động cơ bản. Chưa chứng minh tuân thủ toàn bộ chính sách.',now(),cid))
    log('compliance','review',f'Kiểm duyệt {cid}: {status}')
    return {'status':status,'issues':issues,'item':one('SELECT * FROM contents WHERE id=?',(cid,))}

class ScheduleReq(BaseModel):
    scheduled_at:str

def as_time(raw:str):
    try:
        dt=datetime.fromisoformat(raw.replace('Z','+00:00'))
        if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone(timedelta(hours=7)))
        return dt.astimezone(timezone.utc)
    except ValueError:raise HTTPException(400,'Thời gian phải theo ISO 8601')

@app.post('/api/contents/{cid}/schedule')
def schedule(cid:str,req:ScheduleReq):
    item=one('SELECT * FROM contents WHERE id=?',(cid,))
    if not item:raise HTTPException(404,'Không tìm thấy bài viết')
    if item['status']!='approved':raise HTTPException(400,'Bài chưa được duyệt theo quy tắc')
    dt=as_time(req.scheduled_at)
    if dt<=datetime.now(timezone.utc):raise HTTPException(400,'Thời điểm phải ở tương lai')
    run('UPDATE contents SET status=?,scheduled_at=?,updated=? WHERE id=?',('scheduled',dt.isoformat(),now(),cid))
    log('publishing','scheduled',f'Đã lập lịch chuẩn bị bài {cid} vào {dt.isoformat()}')
    return one('SELECT * FROM contents WHERE id=?',(cid,))

@app.post('/api/contents/{cid}/prepare')
def prepare(cid:str):
    item=one('SELECT c.*,p.account_id,p.url AS page_url FROM contents c JOIN pages p ON c.page_id=p.id WHERE c.id=?',(cid,))
    if not item:raise HTTPException(404,'Không tìm thấy bài viết')
    if item['status'] not in ('approved','ready','scheduled'):
        raise HTTPException(400,'Bài chưa được duyệt')
    if item['status']=='scheduled' and as_time(item['scheduled_at'])>datetime.now(timezone.utc):
        raise HTTPException(400,'Bài chưa tới lịch')
    if not item['account_id']:raise HTTPException(400,'Page chưa liên kết Firefox Profile')
    try:account=open_profile(item['account_id'],item['page_url']+'/')
    except BrowserError as e:raise HTTPException(400,str(e))
    run('UPDATE contents SET status=?,updated=? WHERE id=?',('ready',now(),cid))
    log('publishing','prepare',f'Đã mở Page để người dùng đăng bài {cid} thủ công. CHƯA xuất bản.')
    return {'status':'ready','browser':account,'body':item['body'],'page_url':item['page_url'],
            'note':'Đã mở Firefox; hãy sao chép nội dung và thực hiện đăng bài thủ công. Không có thao tác đăng Facebook tự động.'}

class ConfirmPublished(BaseModel):
    confirmed:bool=False
    post_url:str=''

@app.post('/api/contents/{cid}/complete')
def confirm_published(cid:str,req:ConfirmPublished):
    item=one('SELECT * FROM contents WHERE id=?',(cid,))
    if not item:raise HTTPException(404,'Không tìm thấy bài viết')
    if not req.confirmed:raise HTTPException(400,'Cần xác nhận đã tự đăng bài trên Facebook')
    if item['status'] not in ('ready','approved','scheduled'):
        raise HTTPException(400,'Bài chưa ở trạng thái có thể hoàn thành')
    post_url=req.post_url.strip()
    if post_url:
        host=urlparse(post_url).hostname
        if urlparse(post_url).scheme!='https' or host not in ('facebook.com','www.facebook.com','web.facebook.com'):
            raise HTTPException(400,'Đường dẫn bài đăng không phải Facebook HTTPS')
    run('UPDATE contents SET status=?,publish_url=?,published_at=?,updated=? WHERE id=?',
        ('published_manual',post_url,now(),now(),cid))
    log('publishing','manual_confirm',f'Người dùng xác nhận đã đăng {cid} (không được xác thực từ Meta).')
    return one('SELECT * FROM contents WHERE id=?',(cid,))

@app.post('/api/contents/{cid}/cancel-schedule')
def cancel_schedule(cid:str):
    item=one('SELECT * FROM contents WHERE id=?',(cid,))
    if not item:raise HTTPException(404,'Không tìm thấy bài viết')
    if item['status'] not in ('scheduled','ready'):raise HTTPException(400,'Không có lịch đang hoạt động')
    run('UPDATE contents SET status=?,scheduled_at=NULL,updated=? WHERE id=?',('approved',now(),cid))
    return {'ok':True}

@app.post('/api/media')
async def upload_media(file:UploadFile=File(...)):
    if not (file.content_type or '').startswith('image/'):
        raise HTTPException(400,'Chỉ hỗ trợ hình ảnh PNG/JPEG/WEBP ở phiên bản này')
    blob=await file.read(12*1024*1024+1)
    if len(blob)>12*1024*1024:raise HTTPException(400,'Tệp lớn hơn 12MB')
    try:
        with Image.open(io.BytesIO(blob)) as im:
            im.verify()
        with Image.open(io.BytesIO(blob)) as im:
            fmt=im.format
    except (UnidentifiedImageError,OSError):raise HTTPException(400,'Ảnh không hợp lệ')
    ext={'PNG':'.png','JPEG':'.jpg','WEBP':'.webp'}.get(fmt)
    if not ext:raise HTTPException(400,'Định dạng ảnh không được hỗ trợ')
    name=uuid.uuid4().hex+ext
    (MEDIA_DIR/name).write_bytes(blob)
    return {'url':'/media/'+name,'filename':name}

class AttachMedia(BaseModel):
    path:str

@app.post('/api/contents/{cid}/media')
def attach_media(cid:str,req:AttachMedia):
    name=req.path.removeprefix('/media/')
    if '/' in name or '\\' in name or not (MEDIA_DIR/name).is_file():raise HTTPException(400,'Ảnh chưa được tải lên hệ thống')
    run('UPDATE contents SET media_path=?,status=?,review_details=?,updated=? WHERE id=?',
        ('/media/'+name,'draft','',now(),cid))
    return one('SELECT * FROM contents WHERE id=?',(cid,))

class MetricRow(BaseModel):
    page_id:str
    date:str
    views:int=Field(default=0,ge=0)
    likes:int=Field(default=0,ge=0)
    comments:int=Field(default=0,ge=0)
    shares:int=Field(default=0,ge=0)

class MetricImport(BaseModel):
    rows:list[MetricRow]=Field(min_length=1,max_length=5000)

@app.post('/api/metrics/import')
def import_metrics(req:MetricImport):
    count=0
    with db() as c:
        for r in req.rows:
            if not c.execute('SELECT id FROM pages WHERE id=?',(r.page_id,)).fetchone():continue
            try:datetime.strptime(r.date,'%Y-%m-%d')
            except ValueError:continue
            c.execute('INSERT INTO metrics(page_id,date,views,likes,comments,shares,source) VALUES(?,?,?,?,?,?,?) ON CONFLICT(page_id,date,source) DO UPDATE SET views=excluded.views,likes=excluded.likes,comments=excluded.comments,shares=excluded.shares',
                (r.page_id,r.date,r.views,r.likes,r.comments,r.shares,'manual_import'))
            count+=1
    log('analytics','metrics_imported',f'Người dùng nhập {count} dòng KPI; số liệu chưa xác thực từ Facebook.')
    return {'imported':count}

@app.post('/api/pages/{page_id}/learn')
def learn(page_id:str):
    rows=all_rows('SELECT * FROM metrics WHERE page_id=? ORDER BY date DESC LIMIT 90',(page_id,))
    if len(rows)<5:raise HTTPException(400,'Cần ít nhất 5 bản ghi KPI thực tế do người dùng nhập.')
    total_views=sum(r['views'] for r in rows)
    total_interactions=sum(r['likes']+r['comments']+r['shares'] for r in rows)
    best=max(rows,key=lambda r:r['likes']+r['comments']+r['shares'])
    note=(f'Tổng hợp từ {len(rows)} bản ghi KPI được nhập thủ công: '
          f'{total_views} lượt xem, {total_interactions} lượt tương tác (like+comment+share). '
          f'Ngày có tổng tương tác cao nhất trong mẫu: {best["date"]}. '
          'Đây là quan sát, chưa đủ để khẳng định quan hệ nhân quả hay khung giờ tối ưu.')
    run('INSERT INTO memories(page_id,note,source,created) VALUES(?,?,?,?)',(page_id,note,'metrics_summary',now()))
    enqueue_learning('analytics','metric_observation',note,source_ref='kpi_manual:'+page_id,page_id=page_id)
    log('analytics','learning',f'Đã lưu bài học có nguồn dữ liệu cho Page {page_id}')
    return {'note':note,'samples':len(rows)}


def scheduler_tick():
    rows=all_rows("SELECT id,scheduled_at FROM contents WHERE status='scheduled' AND scheduled_at IS NOT NULL")
    for row in rows:
        try:
            if as_time(row['scheduled_at'])<=datetime.now(timezone.utc):
                with db() as c:
                    changed=c.execute("UPDATE contents SET status='ready',updated=? WHERE id=? AND status='scheduled'",(now(),row['id'])).rowcount
                if changed:log('publishing','ready',f'Bài {row["id"]} đến lịch; sẵn sàng để xuất bản thủ công.')
        except Exception:
            pass


def scheduler_loop():
    global _academy_future
    last_brain_cycle=0.0
    last_academy_cycle=0.0
    while not _stop.wait(10):
        try:
            scheduler_tick()
            cfg=config()
            # Offline event processing keeps each memory updated while the app
            # is running, even with no Claude key and zero idle Claude calls.
            import time
            if time.monotonic()-last_brain_cycle>=60:
                learning_tick(40)
                last_brain_cycle=time.monotonic()
            if cfg.get('academy_enabled','0')=='1' and get_key('mirai'):
                interval=max(10,int(cfg.get('academy_interval_seconds','35')))
                if time.monotonic()-last_academy_cycle>=interval:
                    with _academy_lock:
                        if not _academy_future or _academy_future.done():
                            _academy_future=executor.submit(academy_tick)
                            last_academy_cycle=time.monotonic()
            if cfg.get('auto_run_agents')=='1' and get_key('claude'):
                with _worker_lock:
                    available=max(0,2-len(_submitted))
                if available:
                    queued=all_rows("SELECT id FROM tasks WHERE status='queued' AND agent_id!='ceo' ORDER BY CASE WHEN source='ceo_growth_sprint' THEN 0 ELSE 1 END, created LIMIT ?",(available,))
                    for task in queued:_submit(task['id'])
        except Exception:pass

@app.on_event('startup')
async def on_startup():
    recover_interrupted_academy_jobs()
    scheduler_tick()
    learning_tick(40)
    thread=threading.Thread(target=scheduler_loop,name='schedule-checker',daemon=True)
    thread.start()

@app.on_event('shutdown')
async def on_shutdown():
    _stop.set()
    executor.shutdown(wait=False,cancel_futures=True)
