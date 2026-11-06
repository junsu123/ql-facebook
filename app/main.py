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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Body, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from PIL import Image, UnidentifiedImageError

from .db import BASE, MEDIA_DIR, all_rows, db, initialize, log, now, one, run
from .ai import (ModelError, ceo_message, config, create_task, execute_task,
                 generate_content, save_key, get_key)
from .brains import (agent_brain_overview, relevant_memories, learning_tick,
                     enqueue_learning, spent_report, AGENT_IDS, CLAUDE_PRICING)
from .firefox import (BrowserError, account_status, create_profile, open_profile,
                      close_profile, confirm_login, delete_profile, executable)
from .firefox_installer import (FirefoxInstallError, start_install as start_firefox_install,
                                status as firefox_install_status)

ROOT=Path(__file__).resolve().parent.parent
WEB=ROOT/'web'
app=FastAPI(title='AI Fanpage Company',version='1.3.2',docs_url='/api/docs',redoc_url=None)
initialize()
app.mount('/assets',StaticFiles(directory=WEB/'assets'),name='assets')
app.mount('/media',StaticFiles(directory=MEDIA_DIR),name='media')
executor=ThreadPoolExecutor(max_workers=2,thread_name_prefix='aifc-agent')
_worker_lock=threading.Lock()
_submitted:set[str]=set()
_stop=threading.Event()

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
    return {'ok':True,'version':'1.3.2','platform':os.name,'firefox_available':bool(executable()),'data_dir':str(BASE)}

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
        'settings':config(),
        'brain_overview':agent_brain_overview(),
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
    provider:str='gemini'
    gemini_model:str='gemini-2.5-flash'
    groq_model:str='llama-3.3-70b-versatile'
    daily_llm_call_limit:int=Field(default=200,ge=1,le=10000)
    auto_run_agents:bool=False
    firefox_path:str=''
    gemini_key:str|None=None
    groq_key:str|None=None
    claude_key:str|None=None
    claude_cheap_model:str='claude-haiku-5-5'
    claude_hard_model:str='claude-sonnet-5-5'
    claude_escalation:bool=True
    claude_cache_enabled:bool=True
    brain_learning_enabled:bool=True
    claude_daily_budget_usd:float=Field(default=1.0,ge=0,le=1000)
    claude_agent_daily_budget_usd:float=Field(default=0.25,ge=0,le=1000)

@app.post('/api/settings')
def update_settings(req:SettingsChange):
    if req.provider not in ('gemini','groq','claude'):raise HTTPException(400,'Nhà cung cấp không hợp lệ')
    if req.claude_cheap_model not in CLAUDE_PRICING or req.claude_hard_model not in CLAUDE_PRICING:
        raise HTTPException(400,'Model Claude không nằm trong danh sách tính phí đã xác minh')
    with db() as c:
        for key in ('provider','gemini_model','groq_model','daily_llm_call_limit','firefox_path',
                    'auto_run_agents','claude_cheap_model','claude_hard_model','claude_escalation',
                    'claude_cache_enabled','brain_learning_enabled','claude_daily_budget_usd','claude_agent_daily_budget_usd'):
            value=('1' if getattr(req,key) else '0') if key in ('auto_run_agents','claude_escalation','claude_cache_enabled','brain_learning_enabled') else str(getattr(req,key))
            c.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,value))
    for provider in ('gemini','groq','claude'):
        val=getattr(req,provider+'_key')
        if val is not None:save_key(provider,val)
    log('ceo','settings','Chủ sở hữu cập nhật cấu hình hệ thống (không lưu khóa trong log).')
    return {'ok':True,'settings':config()}

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
    tasks=all_rows("SELECT id FROM tasks WHERE status='queued' AND agent_id != 'ceo' ORDER BY created LIMIT 20")
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
    last_brain_cycle=0.0
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
            if cfg.get('auto_run_agents')=='1' and (get_key(cfg.get('provider','gemini')) or get_key('claude')):
                with _worker_lock:
                    available=max(0,2-len(_submitted))
                if available:
                    queued=all_rows("SELECT id FROM tasks WHERE status='queued' AND agent_id!='ceo' ORDER BY created LIMIT ?",(available,))
                    for task in queued:_submit(task['id'])
        except Exception:pass

@app.on_event('startup')
async def on_startup():
    scheduler_tick()
    learning_tick(40)
    thread=threading.Thread(target=scheduler_loop,name='schedule-checker',daemon=True)
    thread.start()

@app.on_event('shutdown')
async def on_shutdown():
    _stop.set()
    executor.shutdown(wait=False,cancel_futures=True)
