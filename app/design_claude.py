"""Direct Claude visual brief workflow.

1. Owner uploads an image and a product prompt.
2. Claude Vision returns *only* structured text / a design brief; no image pixels.
3. The unchanged source photo and verified JSON are saved for later rendering.
4. A separate action renders PNG posters locally with Pillow, without another API call.

The Claude response is evidence of a suggestion, not verified product claims or a
training of a model's weights. Reviews can teach the local layout preference engine.
"""
from __future__ import annotations

import base64
import io
import json
import re
import uuid
from typing import Any

import httpx
from PIL import Image

from .ai import ModelError, get_key
from .brains import (_update_usage, enqueue_learning, reserve_budget,
                     route_claude_model, teach_agent)
from .db import db, now, one, all_rows, log
from .design import (_image_from_bytes, DESIGN_DIR, RATIOS, LAYOUTS, TYPES,
                     render_poster, design_stats)

MAX_PROMPT_LENGTH = 4000
MAX_OUTPUT_TOKENS = 2000

DESIGN_SCHEMA = {
    'type': 'object',
    'properties': {
        'concept_name': {'type': 'string'},
        'visual_style': {'type': 'string'},
        'headline': {'type': 'string'},
        'subheadline': {'type': 'string'},
        'bullets': {'type': 'array', 'items': {'type': 'string'}},
        'cta': {'type': 'string'},
        'slogan': {'type': 'string'},
        'image_prompt': {'type': 'string'},
        'layout_1_1': {'type': 'string', 'enum': ['hero', 'editorial', 'minimal']},
        'layout_9_16': {'type': 'string', 'enum': ['hero', 'editorial', 'minimal']},
        'layout_16_9': {'type': 'string', 'enum': ['hero', 'editorial', 'minimal']},
        'reasoning_summary': {'type': 'string'},
    },
    'required': ['concept_name', 'visual_style', 'headline', 'subheadline',
                 'bullets', 'cta', 'slogan', 'image_prompt', 'layout_1_1',
                 'layout_9_16', 'layout_16_9', 'reasoning_summary'],
    'additionalProperties': False,
}

SYSTEM = '''Bạn là chuyên gia concept poster sản phẩm cho Fanpage và thương mại điện tử.
Chỉ trả bản thiết kế JSON theo schema, không tạo pixels, không tự nhận đã render ảnh.
Phân tích ảnh bao bì được cung cấp; không bịa tên, màu, chữ, thành phần bao bì.
Hãy chọn bố cục trong đúng ba mẫu hero/editorial/minimal.
Nền poster là xám ghi #777973; chừa nguyên vùng trống 150×80px ở chính giữa mép trên.
Chữ dễ đọc trên điện thoại. Không thêm logo nền tảng, giá bán, chứng nhận hoặc đánh giá khách hàng nếu không có nguồn.
Không tự khẳng định chữa bệnh, điều trị, tăng cường sinh lý, các lợi ích sức khỏe chưa được chứng minh.
Chỉ mô tả thông tin sản phẩm do người dùng cung cấp; không khẳng định hiệu quả nếu không có căn cứ.
image_prompt là prompt hướng dẫn cho một dịch vụ sinh ảnh khác; phần mềm này dùng Pillow để dựng poster từ bố cục và ảnh gốc.
reasoning_summary chỉ tóm tắt lý do chọn thiết kế, không tiết lộ suy luận nội bộ.'''

CREATE_SQL = '''
CREATE TABLE IF NOT EXISTS design_claude_concepts (
 id TEXT PRIMARY KEY, product_name TEXT NOT NULL, ingredients TEXT NOT NULL,
 user_prompt TEXT NOT NULL, image_filename TEXT NOT NULL,
 result_json TEXT NOT NULL, model TEXT NOT NULL,
 input_tokens INTEGER NOT NULL DEFAULT 0, output_tokens INTEGER NOT NULL DEFAULT 0,
 page_id TEXT, created TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_design_claude_created ON design_claude_concepts(created);
CREATE TABLE IF NOT EXISTS design_concept_projects (
 concept_id TEXT NOT NULL REFERENCES design_claude_concepts(id) ON DELETE CASCADE,
 project_id TEXT NOT NULL REFERENCES design_projects(id) ON DELETE CASCADE,
 PRIMARY KEY(concept_id,project_id)
);
'''


def initialize_concepts():
    with db() as con:
        con.executescript(CREATE_SQL)


def _prepare_preview(original: Image.Image) -> tuple[bytes, str]:
    # Use a resized image *for Claude Vision only*, not the poster's source.
    preview = original.copy()
    preview.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
    canvas = Image.new('RGB', preview.size, (244, 244, 244))
    canvas.paste(preview, (0, 0), preview.getchannel('A'))
    out = io.BytesIO()
    canvas.save(out, format='JPEG', quality=82, optimize=True)
    return out.getvalue(), 'image/jpeg'


def _validate_input(product_name: str, ingredients: str, user_prompt: str, page_id: str | None):
    product_name=(product_name or '').strip()
    ingredients=(ingredients or '').strip()
    user_prompt=(user_prompt or '').strip()
    if not (2 <= len(product_name) <= 180):
        raise ValueError('Tên sản phẩm phải từ 2 đến 180 ký tự.')
    if not (1 <= len(ingredients) <= 1800):
        raise ValueError('Thành phần không được để trống và tối đa 1800 ký tự.')
    if len(user_prompt) > MAX_PROMPT_LENGTH:
        raise ValueError('Prompt tối đa 4000 ký tự.')
    if page_id and not one('SELECT id FROM pages WHERE id=?', (page_id,)):
        raise ValueError('Fanpage liên kết không tồn tại.')
    return product_name,ingredients,user_prompt


def _validate_result(obj: Any) -> dict:
    if not isinstance(obj,dict) or set(obj.keys()) != set(DESIGN_SCHEMA['required']):
        raise ValueError('Claude trả về kết quả thiếu trường hoặc không đúng schema.')
    for key in DESIGN_SCHEMA['required']:
        if key=='bullets':
            if not isinstance(obj[key],list) or len(obj[key])>6 or not all(isinstance(x,str) and len(x.strip())<=180 for x in obj[key]):
                raise ValueError('Danh sách bullet Claude không hợp lệ.')
        elif key.startswith('layout_'):
            if obj[key] not in LAYOUTS:
                raise ValueError('Bố cục Claude nằm ngoài danh sách hỗ trợ.')
        elif not isinstance(obj[key],str) or len(obj[key])> (1800 if key=='image_prompt' else 250):
            raise ValueError('Một trường trong kết quả Claude vượt giới hạn.')
    return obj


def _make_request(model, prompt, preview, mime):
    image_block={'type':'image','source':{'type':'base64','media_type':mime,
              'data':base64.b64encode(preview).decode('ascii')}}
    return {'model':model,'max_tokens':MAX_OUTPUT_TOKENS,'system':SYSTEM,
            'messages':[{'role':'user','content':[image_block,{'type':'text','text':prompt}]}],
            'output_config':{'format':{'type':'json_schema','schema':DESIGN_SCHEMA}}}


def _claude_message(model, prompt, preview, mime, *, client=None):
    """One real Anthropic Messages request; return raw JSON and usage.

    Financial reservation includes a conservative additional estimate for image
    input; ambiguous transport errors preserve reservation instead of retrying.
    """
    key=get_key('claude')
    if not key:raise ValueError('Chưa cấu hình Claude API Key.')
    from .brains import reserve_budget
    try:
        reservation,_=reserve_budget('creative',model,'design_direct',prompt,SYSTEM,
                MAX_OUTPUT_TOKENS,'user_direct_design',extra_input_tokens=4000)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    response=None
    try:
        payload=_make_request(model,prompt,preview,mime)
        headers={'x-api-key':key,'anthropic-version':'2023-06-01','content-type':'application/json'}
        if client is None:
            with httpx.Client(timeout=90) as session:
                response=session.post('https://api.anthropic.com/v1/messages',json=payload,headers=headers)
        else:
            response=client.post('https://api.anthropic.com/v1/messages',json=payload,headers=headers)
        response.raise_for_status()
        data=response.json()
        usage=data.get('usage') or {}
        _update_usage(reservation,'completed',usage,model)
        raw=''.join(part.get('text','') for part in data.get('content',[]) if part.get('type')=='text')
        result=_validate_result(json.loads(raw))
        return result,{'input_tokens':int(usage.get('input_tokens',0)),
                       'output_tokens':int(usage.get('output_tokens',0))},model
    except httpx.HTTPStatusError as exc:
        _update_usage(reservation,'failed',model=model)
        raise ValueError(f'Claude HTTP {exc.response.status_code}: {exc.response.text[:220]}') from exc
    except (httpx.TimeoutException,httpx.TransportError) as exc:
        # Provider may have billed request even without a response; keep reservation.
        raise ValueError('Không xác định được kết quả Claude do mất kết nối. Khoản dự trù được giữ lại để tránh gọi trùng.') from exc
    except (json.JSONDecodeError,KeyError,TypeError) as exc:
        raise ValueError('Claude đã phản hồi nhưng JSON không hợp lệ. Lượt gọi được tính theo usage API.') from exc


def create_claude_concept(product_name,ingredients,user_prompt,image_bytes,page_id=None,client=None):
    initialize_concepts()
    product_name,ingredients,user_prompt=_validate_input(product_name,ingredients,user_prompt,page_id)
    image=_image_from_bytes(image_bytes)
    preview,mime=_prepare_preview(image)
    prompt=json.dumps({'product_name':product_name,'ingredients':ingredients,
                       'user_prompt':user_prompt or 'Thiết kế poster sản phẩm đẹp, rõ chữ, mobile-first.'},ensure_ascii=False)
    model,_=route_claude_model('creative','design_direct',prompt)
    # Call first; only keep uploaded source after successfully recording JSON.
    brief,usage,model=_claude_message(model,prompt,preview,mime,client=client)
    filename=uuid.uuid4().hex+'.png'
    concept_id='DC'+uuid.uuid4().hex[:14].upper()
    image.save(DESIGN_DIR/filename,'PNG')
    try:
        with db() as con:
            con.execute('''INSERT INTO design_claude_concepts
              (id,product_name,ingredients,user_prompt,image_filename,result_json,model,input_tokens,output_tokens,page_id,created)
              VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
              (concept_id,product_name,ingredients,user_prompt,filename,json.dumps(brief,ensure_ascii=False),
               model,usage['input_tokens'],usage['output_tokens'],page_id,now()))
    except Exception:
        (DESIGN_DIR/filename).unlink(missing_ok=True)
        raise
    # Result learning is a local event and is NOT a second Claude call.
    lesson=(f'Claude đề xuất concept {brief["concept_name"][:90]} cho {product_name}. '
        f'Layout: 1:1={brief["layout_1_1"]}, 9:16={brief["layout_9_16"]}, 16:9={brief["layout_16_9"]}. '
        f'Prompt người dùng: {user_prompt[:300]}. Gợi ý chưa có kiểm chứng hiệu suất.')
    teach_agent('creative',lesson,source_ref=concept_id,page_id=page_id,verified=False,kind='design_example')
    enqueue_learning('creative','design_claude_example',
        f'Claude đề xuất concept {brief["concept_name"][:90]} cho {product_name}. '
        f'Layout: 1:1={brief["layout_1_1"]}, 9:16={brief["layout_9_16"]}, 16:9={brief["layout_16_9"]}. '
        f'Prompt người dùng: {user_prompt[:450]}. Đây là gợi ý chưa có xác minh CTR.',
        source_ref=concept_id,page_id=page_id)
    log('creative','design_claude_direct',f'Nhận concept {concept_id} từ Claude; chưa render ảnh.')
    return {'ok':True,'concept_id':concept_id,'design_result':brief,'model':model,
            'usage':usage,'source_image_url':'/media/design/'+filename,
            'message':'Đã lưu kết quả Claude. Chưa tạo poster; sử dụng nút Dùng kết quả để tạo PNG.'}


def get_concepts(limit=30):
    initialize_concepts()
    rows=all_rows('SELECT * FROM design_claude_concepts ORDER BY created DESC,id DESC LIMIT ?', (min(limit,100),))
    for c in rows:
        c['design_result']=json.loads(c.pop('result_json'))
        c['source_image_url']='/media/design/'+c.pop('image_filename')
        c['outputs']=all_rows('''SELECT o.id,o.ratio,o.width,o.height,o.filename, r.rating
            FROM design_concept_projects cp JOIN design_outputs o ON o.project_id=cp.project_id
            LEFT JOIN design_reviews r ON r.output_id=o.id WHERE cp.concept_id=? ORDER BY o.ratio''',(c['id'],))
        for out in c['outputs']:out['url']='/media/design/'+out['filename']
    return rows


def _assert_safe_copy(result):
    # Fail closed for common illegal health/absolute guarantee claims. Human
    # review remains necessary for other product categories and legal claims.
    untrusted=' '.join([result['headline'],result['subheadline'],result['cta'],result['slogan'],*result['bullets']]).lower()
    if re.search(r'\b(chữa khỏi|chữa bệnh|điều trị|trị dứt điểm|cam kết khỏi|100% khỏi|hiệu quả 100%)\b',untrusted):
        raise ValueError('Claude đề xuất tuyên bố sức khỏe chưa xác thực. Hãy kiểm tra trước khi tạo ảnh.')


def render_claude_concept(concept_id,ratios,layout_type='overview'):
    initialize_concepts()
    row=one('SELECT * FROM design_claude_concepts WHERE id=?',(concept_id,))
    if not row:raise LookupError('Không tìm thấy concept Claude.')
    if layout_type not in TYPES:raise ValueError('Loại poster không hỗ trợ.')
    ratios=list(dict.fromkeys(ratios))
    if not ratios or any(x not in RATIOS for x in ratios):
        raise ValueError('Chọn tỷ lệ 1:1, 9:16 hoặc 16:9.')
    result=_validate_result(json.loads(row['result_json']))
    _assert_safe_copy(result)
    src=DESIGN_DIR/row['image_filename']
    if not src.is_file():raise ValueError('Ảnh sản phẩm nguồn đã bị xóa.')
    image=_image_from_bytes(src.read_bytes())
    project_id='D'+uuid.uuid4().hex[:12].upper()
    created=now();outputs=[]
    mapping={'1:1':'layout_1_1','9:16':'layout_9_16','16:9':'layout_16_9'}
    try:
        for ratio in ratios:
            layout=result[mapping[ratio]]
            output_name,w,h=render_poster({
                'product_name':row['product_name'],'ingredients':row['ingredients'],
                'layout_type':layout_type,'layout_name':layout,'claude_copy':result
            },image,ratio)
            outputs.append({'id':'O'+uuid.uuid4().hex[:12].upper(),'ratio':ratio,
                            'filename':output_name,'width':w,'height':h,'url':'/media/design/'+output_name})
        with db() as con:
            # Store display layout as the primary ratio. Every output's ratio-specific
            # choice is still recorded in the immutable Claude concept JSON.
            con.execute('''INSERT INTO design_projects
                 (id,product_name,ingredients,note,image_filename,layout_type,layout_name,guidance,provider,page_id,created)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                 (project_id,row['product_name'],row['ingredients'],row['user_prompt'],row['image_filename'],
                  layout_type,result[mapping[ratios[0]]],result['reasoning_summary'],'claude_direct',row['page_id'],created))
            con.executemany('''INSERT INTO design_outputs (id,project_id,ratio,filename,width,height,created)
                                VALUES(?,?,?,?,?,?,?)''',
                 [(x['id'],project_id,x['ratio'],x['filename'],x['width'],x['height'],created) for x in outputs])
            con.execute('INSERT INTO design_concept_projects(concept_id,project_id) VALUES(?,?)',(concept_id,project_id))
        log('creative','design_concept_render',f'Đã tạo {len(outputs)} ảnh PNG từ concept Claude {concept_id}; không gọi Claude lại.')
    except Exception:
        for out in outputs:(DESIGN_DIR/out['filename']).unlink(missing_ok=True)
        raise
    return {'ok':True,'concept_id':concept_id,'project_id':project_id,'outputs':outputs,'brain':design_stats()}
