"""Real optional Gemini/Groq model calls and auditable CEO task routing.
No simulated AI results: without a configured key, tasks wait for configuration.
"""
from __future__ import annotations
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
import httpx
from cryptography.fernet import Fernet, InvalidToken
from .db import BASE, all_rows, db, log, now, one, run

KEY_FILE = BASE / 'local_secret.key'
SECRETS_FILE = BASE / 'api_secrets.json.enc'

class ModelError(Exception):
    pass


def _cipher():
    if not KEY_FILE.exists():
        with KEY_FILE.open('xb') as file:
            file.write(Fernet.generate_key())
        try:
            KEY_FILE.chmod(0o600)
        except OSError:
            pass
    return Fernet(KEY_FILE.read_bytes())


def load_keys() -> dict:
    if SECRETS_FILE.exists():
        try:
            return json.loads(_cipher().decrypt(SECRETS_FILE.read_bytes()))
        except (InvalidToken, ValueError) as err:
            raise ModelError('Không thể giải mã khóa API cục bộ. Kiểm tra file dữ liệu.') from err
    return {}


def save_key(provider: str, value: str):
    if provider not in ('gemini','groq'):
        raise ValueError('Nhà cung cấp không được hỗ trợ')
    keys = load_keys()
    if value:
        keys[provider] = value.strip()
    else:
        keys.pop(provider,None)
    SECRETS_FILE.write_bytes(_cipher().encrypt(json.dumps(keys).encode('utf-8')))
    try:
        SECRETS_FILE.chmod(0o600)
    except OSError:
        pass


def get_key(provider: str) -> str:
    return os.getenv(f'{provider.upper()}_API_KEY','') or load_keys().get(provider,'')


def config() -> dict:
    rows = all_rows('SELECT key,value FROM settings')
    out = {r['key']:r['value'] for r in rows}
    for provider in ('gemini','groq'):
        out[f'{provider}_configured'] = bool(get_key(provider))
    return out


def record_usage(provider, model, request_type):
    run('INSERT INTO ai_calls(provider,model,request_type,created) VALUES(?,?,?,?)',
        (provider, model, request_type, now()))


def call_llm(system: str, prompt: str, purpose: str = 'task') -> str:
    cfg = config()
    provider = cfg.get('provider','gemini')
    key = get_key(provider)
    if not key:
        raise ModelError(f'Chưa cấu hình API key {provider}. Vào mục Cài đặt để thêm key.')
    limit = max(1,min(100000,int(cfg.get('daily_llm_call_limit',200))))
    count = one("SELECT count(*) AS n FROM ai_calls WHERE created >= ?",(datetime.now(timezone.utc).date().isoformat(),))['n']
    if count >= limit:
        raise ModelError('Đã đạt hạn mức số lần gọi AI trong ngày.')
    try:
        with httpx.Client(timeout=45) as client:
            if provider == 'gemini':
                model = cfg.get('gemini_model') or 'gemini-2.5-flash'
                url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
                response = client.post(url,headers={'x-goog-api-key':key},json={
                    'systemInstruction':{'parts':[{'text':system}]},
                    'contents':[{'role':'user','parts':[{'text':prompt}]}],
                    'generationConfig':{'temperature':0.55,'maxOutputTokens':1800}
                })
                response.raise_for_status()
                choices = response.json().get('candidates') or []
                parts = choices[0].get('content',{}).get('parts',[]) if choices else []
                text = ''.join(p.get('text','') for p in parts)
            elif provider == 'groq':
                model = cfg.get('groq_model') or 'llama-3.3-70b-versatile'
                response = client.post('https://api.groq.com/openai/v1/chat/completions',
                    headers={'Authorization':f'Bearer {key}'},json={
                        'model':model,'messages':[{'role':'system','content':system},{'role':'user','content':prompt}],
                        'temperature':0.55,'max_tokens':1800
                    })
                response.raise_for_status()
                text = response.json()['choices'][0]['message']['content']
            else:
                raise ModelError('Nhà cung cấp không được hỗ trợ')
    except httpx.HTTPStatusError as e:
        raise ModelError(f'API {provider} trả lỗi HTTP {e.response.status_code}: {e.response.text[:240]}') from e
    except (httpx.RequestError, ValueError, KeyError, IndexError) as e:
        raise ModelError(f'Lỗi khi gọi API {provider}: {str(e)[:240]}') from e
    if not text.strip():
        raise ModelError('Mô hình không trả về văn bản.')
    record_usage(provider,model,purpose)
    return text.strip()


def parse_json_reply(raw: str):
    raw = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw.strip(), flags=re.I)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r'\{[\s\S]+\}',raw)
        if match:
            return json.loads(match.group())
    raise ModelError('CEO AI trả dữ liệu không đúng định dạng JSON; chưa tự động phân công để tránh sai.')


def create_task(agent, title, instructions='', page_id=None, source='ceo', campaign_id=None) -> str:
    task_id = 'T' + uuid.uuid4().hex[:10].upper()
    if agent not in ['ceo','research','strategy','content','creative','publishing','customer','analytics','compliance']:
        raise ValueError('Agent không hợp lệ')
    if page_id and not one('SELECT id FROM pages WHERE id=?',(page_id,)):
        raise ValueError('Page không tồn tại')
    stamp = now()
    run('INSERT INTO tasks(id,agent_id,title,instructions,page_id,source,campaign_id,created,updated) VALUES(?,?,?,?,?,?,?,?,?)',
        (task_id,agent,title[:180],instructions[:8000],page_id,source,campaign_id,stamp,stamp))
    log('ceo','assignment',f'Giao {agent}: {title}',task_id)
    return task_id


def ceo_message(message: str) -> dict:
    if not message.strip():
        raise ValueError('Nội dung yêu cầu trống')
    run('INSERT INTO chats(role,body,created) VALUES(?,?,?)',('user',message.strip(),now()))
    pages = all_rows('SELECT id,name,category FROM pages ORDER BY created DESC LIMIT 100')
    stats = {
        'pages':len(pages),
        'open_tasks':one("SELECT count(*) AS n FROM tasks WHERE status IN ('queued','running')")['n'],
        'drafts':one("SELECT count(*) AS n FROM contents WHERE status='draft'")['n']
    }
    if not get_key(config().get('provider','gemini')):
        tid = create_task('ceo','Yêu cầu của chủ sở hữu',message,source='owner_pending_ai')
        reply = 'Tôi đã lưu yêu cầu của bạn vào hàng đợi CEO. Cần cấu hình Gemini hoặc Groq trong Cài đặt để CEO phân tích và giao nhiệm vụ bằng AI thật. Tôi chưa thực thi công việc.'
        run('INSERT INTO chats(role,body,created) VALUES(?,?,?)',('assistant',reply,now()))
        return {'reply':reply,'task_ids':[tid],'mode':'awaiting_ai_configuration'}
    system = '''Bạn là AI CEO của công ty marketing vận hành Fanpage thuộc sở hữu doanh nghiệp.
Chỉ lập kế hoạch và giao việc trong hệ thống nội bộ, không tự nhận đã đăng bài hay xem dữ liệu Facebook.
Tạo JSON THUẦN: {"reply":"...", "assignments":[{"agent":"research|strategy|content|creative|publishing|customer|analytics|compliance", "title":"...", "instructions":"...", "page_id":null}]}
Tối đa 8 nhiệm vụ/lượt, ngắn gọn, đúng dữ liệu được cung cấp. page_id phải nằm trong danh sách nếu có. Không tạo nhiệm vụ tự động nhắn tin hay đăng hàng loạt trên Facebook. Nếu thiếu Page, giao nhiệm vụ nghiên cứu/lập kế hoạch tổng quát. Không giả mạo thống kê hay kết quả.'''
    try:
        raw = call_llm(system,json.dumps({'message':message,'pages':pages,'stats':stats},ensure_ascii=False),'ceo')
        response = parse_json_reply(raw)
        reply = str(response.get('reply','Đã tạo kế hoạch.'))[:3000]
        assigned = []
        for item in response.get('assignments',[])[:8]:
            if not isinstance(item,dict):continue
            agent = item.get('agent','')
            if agent not in ('research','strategy','content','creative','publishing','customer','analytics','compliance'):continue
            page_id = item.get('page_id')
            if page_id and not any(p['id']==page_id for p in pages):page_id=None
            assigned.append(create_task(agent,str(item.get('title','Nhiệm vụ')),
                str(item.get('instructions','')),page_id))
        run('INSERT INTO chats(role,body,created) VALUES(?,?,?)',('assistant',reply,now()))
        log('ceo','decision',f'CEO giao {len(assigned)} nhiệm vụ và báo cáo: {reply[:400]}')
        return {'reply':reply,'task_ids':assigned,'mode':'ai'}
    except ModelError as err:
        reply = f'Chưa giao nhiệm vụ tự động vì lỗi AI: {err}. Yêu cầu đã được lưu; vui lòng kiểm tra cài đặt và thử lại.'
        run('INSERT INTO chats(role,body,created) VALUES(?,?,?)',('assistant',reply,now()))
        return {'reply':reply,'task_ids':[],'mode':'error'}


def page_context(page_id: str | None) -> dict:
    if not page_id:return {}
    page = one('SELECT id,name,category,tone,facts,url FROM pages WHERE id=?',(page_id,))
    if not page:return {}
    page['memories'] = all_rows('SELECT note,source FROM memories WHERE page_id=? ORDER BY id DESC LIMIT 8',(page_id,))
    page['recent_content'] = all_rows('SELECT topic,body FROM contents WHERE page_id=? ORDER BY created DESC LIMIT 5',(page_id,))
    page['metrics'] = all_rows('SELECT date,views,likes,comments,shares FROM metrics WHERE page_id=? ORDER BY date DESC LIMIT 14',(page_id,))
    return page


def execute_task(task_id: str) -> dict:
    task = one('SELECT * FROM tasks WHERE id=?',(task_id,))
    if not task:raise ValueError('Không tìm thấy nhiệm vụ')
    if task['status'] not in ('queued','failed'):
        raise ValueError('Nhiệm vụ không thể chạy ở trạng thái hiện tại')
    run('UPDATE tasks SET status=?,error=?,updated=? WHERE id=?',('running','',now(),task_id))
    log(task['agent_id'],'start',f'Đang xử lý: {task["title"]}',task_id)
    context = page_context(task['page_id'])
    system = f'''Bạn là {task['agent_id']} - một chuyên viên AI thuộc công ty marketing.
Chỉ hoàn thành nhiệm vụ bằng nội dung hoặc đề xuất có thể xác minh. Không tự nhận đã truy cập hay đăng Facebook, không bịa ra chỉ số. Không dùng tuyên bố chữa bệnh hoặc cam kết kết quả. Nếu thiếu dữ liệu hãy nêu rõ.
Trả lời tiếng Việt dạng văn bản rõ ràng, ngắn gọn, phù hợp chuyên môn.'''
    prompt = json.dumps({'title':task['title'],'instructions':task['instructions'],'page_context':context},ensure_ascii=False)
    try:
        if task['agent_id']=='publishing':
            result = 'Đã ghi nhận yêu cầu vận hành. Trong chế độ không dùng Meta API, công việc xuất bản phải thực hiện qua luồng chuẩn bị bài và xác nhận thủ công. Không có thao tác đăng tự động trên Facebook.'
        else:
            result = call_llm(system,prompt,'agent_task')
        with db() as c:
            c.execute('UPDATE tasks SET status=?,result=?,updated=? WHERE id=?',('done',result,now(),task_id))
            if task['agent_id']=='content' and task['page_id']:
                cid='C'+uuid.uuid4().hex[:10].upper()
                c.execute('INSERT INTO contents(id,page_id,topic,body,created,updated) VALUES(?,?,?,?,?,?)',
                    (cid,task['page_id'],task['title'],result,now(),now()))
        log(task['agent_id'],'done',f'Đã hoàn tất: {task["title"]}',task_id)
        return one('SELECT * FROM tasks WHERE id=?',(task_id,))
    except ModelError as err:
        run('UPDATE tasks SET status=?,error=?,updated=? WHERE id=?',('failed',str(err),now(),task_id))
        log(task['agent_id'],'error',str(err),task_id)
        return one('SELECT * FROM tasks WHERE id=?',(task_id,))


def generate_content(page_id: str, topic: str) -> dict:
    page = page_context(page_id)
    if not page:raise ValueError('Không tìm thấy Fanpage')
    if not page.get('facts'):
        raise ValueError('Cần nhập dữ liệu sản phẩm/kiến thức đã xác minh cho Page trước khi tạo nội dung bằng AI.')
    system = '''Bạn là copywriter marketing. Viết MỘT bài Facebook nguyên bản tiếng Việt ngắn gọn, hữu ích, có lời mời tương tác tự nhiên. CHỈ dùng dữ kiện sản phẩm được cung cấp. Không thổi phồng, không tuyên bố chữa bệnh, không nói điều chưa có bằng chứng. Không tạo bình luận hoặc đánh giá khách hàng giả. Trả về trực tiếp nội dung bài đăng.'''
    text = call_llm(system,json.dumps({'topic':topic,'page':page},ensure_ascii=False),'content')
    cid='C'+uuid.uuid4().hex[:10].upper()
    run('INSERT INTO contents(id,page_id,topic,body,created,updated) VALUES(?,?,?,?,?,?)',
        (cid,page_id,topic[:200],text,now(),now()))
    log('content','draft',f'Tạo bản nháp mới: {topic[:100]}')
    return one('SELECT * FROM contents WHERE id=?',(cid,))
