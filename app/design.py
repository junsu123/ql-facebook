"""Product poster designer: local pixel-safe rendering, optional Claude layout adviser.

Claude does not render image pixels; Pillow composes verified user inputs and the
uploaded product photo. Memory learns layout preferences from explicit reviews;
no model weights are modified and no Facebook metrics are fabricated.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import uuid
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps, UnidentifiedImageError

from .db import MEDIA_DIR, db, now, one, all_rows, log

DESIGN_DIR = MEDIA_DIR / 'design'
DESIGN_DIR.mkdir(parents=True, exist_ok=True)
RATIOS = {'1:1': (1024, 1024), '9:16': (1080, 1920), '16:9': (1600, 900)}
TYPES = {'overview', 'ingredients', 'offer'}
LAYOUTS = {'hero', 'editorial', 'minimal'}
BACKGROUND = (119, 121, 115)  # #777973, original warm-grey poster palette

SCHEMA = '''
CREATE TABLE IF NOT EXISTS design_projects (
 id TEXT PRIMARY KEY, product_name TEXT NOT NULL, ingredients TEXT NOT NULL,
 note TEXT NOT NULL DEFAULT '', image_filename TEXT NOT NULL, layout_type TEXT NOT NULL,
 layout_name TEXT NOT NULL, guidance TEXT NOT NULL DEFAULT '', provider TEXT NOT NULL,
 page_id TEXT, created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS design_outputs (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES design_projects(id) ON DELETE CASCADE,
 ratio TEXT NOT NULL, filename TEXT NOT NULL, width INTEGER NOT NULL,
 height INTEGER NOT NULL, created TEXT NOT NULL, UNIQUE(project_id,ratio)
);
CREATE TABLE IF NOT EXISTS design_reviews (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES design_projects(id) ON DELETE CASCADE,
 output_id TEXT NOT NULL REFERENCES design_outputs(id) ON DELETE CASCADE,
 rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5), comment TEXT NOT NULL DEFAULT '',
 created TEXT NOT NULL, UNIQUE(output_id)
);
CREATE INDEX IF NOT EXISTS idx_design_projects_date ON design_projects(created);
CREATE INDEX IF NOT EXISTS idx_design_reviews_project ON design_reviews(project_id);
'''


def init_design():
    with db() as c:
        c.executescript(SCHEMA)


def design_stats():
    r = one('''SELECT count(*) n,COALESCE(SUM(CASE WHEN rating>=4 THEN 1 ELSE 0 END),0) good
               FROM design_reviews''') or {'n': 0, 'good': 0}
    good = int(r['good'])
    # Levels are product/UI heuristics, not trained model ability or proven CTR.
    level = 3 if good >= 75 else 2 if good >= 25 else 1 if good >= 5 else 0
    return {'level': level, 'reviewed': int(r['n']), 'positive_reviews': good,
            'next_level_positive': (5 if level == 0 else 25 if level == 1 else 75 if level == 2 else None),
            'learning_mode': 'layout_preference_memory',
            'note': 'Học từ đánh giá về bố cục; không fine-tune Claude hay huấn luyện mô hình tạo ảnh.'}


def _font_path(bold=False) -> str:
    paths = ([
        'C:/Windows/Fonts/arialbd.ttf',
        'C:/Windows/Fonts/seguisb.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        '/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf',
    ] if bold else [
        'C:/Windows/Fonts/arial.ttf',
        'C:/Windows/Fonts/segoeui.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf',
    ])
    for path in paths:
        if Path(path).exists():
            return path
    raise RuntimeError('Máy chưa có font Unicode thích hợp. Cài đặt Arial hoặc DejaVu Sans.')


def _font(size: int, *, bold=False):
    return ImageFont.truetype(_font_path(bold), size)


def _lines(draw, text: str, font, width: int, max_lines: int = 4):
    words = re.split(r'\s+', (text or '').strip())
    lines = []
    line = ''
    for word in words:
        # Long fragments (e.g. SKU) must not escape the canvas.
        if draw.textbbox((0, 0), word, font=font)[2] > width:
            pieces = []
            fragment = ''
            for char in word:
                probe = fragment + char
                if fragment and draw.textbbox((0, 0), probe, font=font)[2] > width:
                    pieces.append(fragment)
                    fragment = char
                else:
                    fragment = probe
            if fragment:pieces.append(fragment)
        else:pieces = [word]
        for piece in pieces:
            probe = (line+' '+piece).strip()
            if line and draw.textbbox((0, 0), probe, font=font)[2] > width:
                lines.append(line)
                line = piece
            else:line = probe
    if line:lines.append(line)
    if len(lines) > max_lines:
        lines=lines[:max_lines]
        last=lines[-1]
        while last and draw.textbbox((0, 0),last+'…',font=font)[2] > width:
            last=last[:-1]
        lines[-1]=last+'…'
    return lines


def _write_wrapped(draw, text, xy, width, font_size, color, max_lines=3, bold=False, line_height=1.22, min_font=19):
    font_size=max(min_font,font_size)
    for fs in range(font_size,min_font-1,-2):
        font=_font(fs,bold=bold)
        lines=_lines(draw,text,font,width,max_lines=max_lines)
        # If text was truncated, reduce font until all content fits, if possible.
        if not lines or not lines[-1].endswith('…') or fs <= min_font:
            break
    y=xy[1]
    for ln in lines:
        draw.text((xy[0],y),ln,font=font,fill=color,stroke_width=0)
        y+=int(fs*line_height)
    return y


def _image_from_bytes(blob: bytes):
    if not blob or len(blob)>12*1024*1024:
        raise ValueError('Ảnh sản phẩm cần nhỏ hơn hoặc bằng 12MB.')
    try:
        with Image.open(io.BytesIO(blob)) as i:
            if i.format not in ('PNG','JPEG','WEBP'):
                raise ValueError('Chỉ hỗ trợ ảnh PNG, JPEG hoặc WEBP.')
            if i.width*i.height > 24_000_000 or i.width<60 or i.height<60:
                raise ValueError('Ảnh không hợp lệ hoặc vượt 24 megapixel.')
            i.verify()
        with Image.open(io.BytesIO(blob)) as i:
            # Orientation is applied but packaging contents are never redrawn.
            return ImageOps.exif_transpose(i).convert('RGBA')
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError('Không đọc được ảnh sản phẩm.') from exc


def _choose_layout(layout_type, guidance=''):
    stats = design_stats()
    if stats['level'] >= 1:
        rows = all_rows('''SELECT p.layout_name, count(*) n
            FROM design_projects p JOIN design_outputs o ON o.project_id=p.id
            JOIN design_reviews r ON r.output_id=o.id
            WHERE p.layout_type=? AND r.rating>=4 GROUP BY p.layout_name ORDER BY n DESC LIMIT 1''',(layout_type,))
        if rows and rows[0]['n'] >= 3 and rows[0]['layout_name'] in LAYOUTS:
            return rows[0]['layout_name']
    return 'hero' if layout_type!='ingredients' else 'editorial'


def _claude_layout(product_name, ingredients, layout_type, note, default_layout):
    """One optional Claude request per project, never per aspect ratio."""
    from .ai import call_llm, parse_json_reply
    safe_input=json.dumps({'product_name': product_name, 'ingredients': ingredients,
                           'user_note': note,'type':layout_type,'layout_options': sorted(LAYOUTS)},ensure_ascii=False)
    system=('Bạn là chuyên gia bố cục poster. Trả về một JSON duy nhất gồm layout (hero/editorial/minimal), '
            'guidance (không quá 220 ký tự, chỉ mô tả bố cục), không viết claim/công dụng mới. '
            'Bạn KHÔNG tạo ra ảnh, chỉ tư vấn bố cục. Tránh mọi tuyên bố y tế chưa có chứng cứ.')
    raw=call_llm(system,safe_input,'poster_concept',agent_id='creative')
    obj=parse_json_reply(raw)
    layout=obj.get('layout',default_layout)
    if layout not in LAYOUTS:layout=default_layout
    return layout,str(obj.get('guidance',''))[:220]


def _paste_product(canvas, photo, box):
    x,y,w,h=box
    pw,ph=photo.size
    scale=min(w/pw,h/ph)
    target=photo.resize((max(1,round(pw*scale)),max(1,round(ph*scale))),Image.Resampling.LANCZOS)
    px=int(x+(w-target.width)/2);py=int(y+(h-target.height)/2)
    # Only a faint floor shadow is added; the original packaging is untouched.
    shadow_layer=Image.new('RGBA',canvas.size,(0,0,0,0))
    shade=ImageDraw.Draw(shadow_layer)
    baseline=min(canvas.height-30,py+target.height+6)
    shade.ellipse((px+target.width*.16,baseline-18,px+target.width*.84,baseline+22),fill=(0,0,0,65))
    shadow_layer=shadow_layer.filter(ImageFilter.GaussianBlur(max(6,round(canvas.width*.012))))
    canvas.alpha_composite(shadow_layer)
    canvas.alpha_composite(target,(px,py))


def render_poster(project: dict, image: Image.Image, ratio: str) -> tuple[str,int,int]:
    if ratio not in RATIOS:raise ValueError('Tỷ lệ ảnh không được hỗ trợ.')
    w,h=RATIOS[ratio]
    poster=Image.new('RGBA',(w,h),BACKGROUND+(255,))
    draw=ImageDraw.Draw(poster)
    name=project['product_name']
    concept=project.get('claude_copy') or {}
    components=([str(b).strip() for b in concept.get('bullets',[]) if str(b).strip()] if concept
        else [i.strip() for i in re.split(r'[,;\n]+',project['ingredients']) if i.strip()])
    main_title=concept.get('headline') or name
    section_title=(concept.get('subheadline') or name) if concept else None
    footer=(concept.get('cta') or 'TÌM HIỂU SẢN PHẨM') if concept else 'TÌM HIỂU SẢN PHẨM'
    typ=project['layout_type'];layout=project['layout_name']
    bright=(250,249,240);soft=(234,231,220);accent=(247,228,180)

    # Preserve unmarked 150x80px at center of top edge, same as background.
    # Every other element starts at y>=125 so this region remains exactly clear.
    if ratio=='1:1':
        margin=62
        title_bottom=_write_wrapped(draw,main_title.upper(),(margin,165),495,56,bright,3,True,1.17,33)
        subtitle_y=max(415,title_bottom+20)
        _write_wrapped(draw,(section_title or ('THÀNH PHẦN' if typ=='ingredients' else 'TRÀ / SẢN PHẨM')),
                       (margin,subtitle_y),460,27,accent,1,True)
        _paste_product(poster,image,(490,350,485,560) if layout!='minimal' else (515,395,445,505))
        lines=components[:5] if typ=='ingredients' else components[:4]
        curr=subtitle_y+50
        for c in lines:
            if curr>852:break
            draw.ellipse((margin,curr+14,margin+9,curr+23),fill=accent)
            curr=_write_wrapped(draw,c,(margin+22,curr),390,25,soft,2,False,1.2,20)+13
        _write_wrapped(draw,footer,(margin,930),w-2*margin,20,accent,1,True,min_font=19)
    elif ratio=='9:16':
        margin=76
        y=_write_wrapped(draw,main_title.upper(),(margin,185),w-2*margin,75,bright,4,True,1.2,45)
        draw.line((margin,min(535,y+30),w-margin,min(535,y+30)),fill=accent,width=3)
        _paste_product(poster,image,(100,540,880,1000) if layout!='minimal' else (155,640,760,850))
        ly=1510 if layout!='minimal' else 1480
        _write_wrapped(draw,section_title or 'THÀNH PHẦN', (margin,ly),w-2*margin,38,accent,1,True)
        curr=ly+72
        for c in components[:6]:
            if curr>1802:break
            draw.ellipse((margin,curr+16,margin+10,curr+26),fill=accent)
            curr=_write_wrapped(draw,c,(margin+27,curr),w-2*margin-27,31,soft,2,False,1.22,23)+13
        _write_wrapped(draw,footer,(margin,1850),w-2*margin,25,accent,1,True,min_font=20)
    else:
        margin=85
        y=_write_wrapped(draw,main_title.upper(),(margin,173),800,73,bright,3,True,1.17,40)
        y=max(435,y+25)
        _write_wrapped(draw,section_title or 'THÀNH PHẦN', (margin,y),800,31,accent,1,True)
        curr=y+55
        for c in components[:4]:
            if curr>765:break
            draw.ellipse((margin,curr+13,margin+10,curr+23),fill=accent)
            curr=_write_wrapped(draw,c,(margin+24,curr),750,28,soft,2,False,1.2,21)+10
        _paste_product(poster,image,(920,115,630,710) if layout!='minimal' else (975,155,540,640))
        _write_wrapped(draw,footer,(margin,818),800,21,accent,1,True,min_font=19)

    if concept:
        # Always include the source product name even when Claude proposes a slogan.
        # Position below the reserved 150×80 top-center area.
        _write_wrapped(draw,name,(62 if ratio=='1:1' else 76 if ratio=='9:16' else 85,123),
                       400 if ratio=='1:1' else 820 if ratio=='9:16' else 750,
                       22,soft,1,False,min_font=18)

    # The user provided note is kept in project metadata, not asserted as an
    # unverified health/discount claim on the rendered poster.
    outfile=f'{uuid.uuid4().hex}.png'
    poster.convert('RGB').save(DESIGN_DIR/outfile,format='PNG',optimize=True)
    return outfile,w,h


def create_posters(product_name: str, ingredients: str, image_bytes: bytes, ratios: list[str],
                   layout_type='overview', mode='auto', note='', page_id=None):
    init_design()
    product_name=product_name.strip();ingredients=ingredients.strip();note=note.strip()
    if len(product_name)<2 or len(product_name)>180 or not ingredients or len(ingredients)>1800:
        raise ValueError('Nhập tên sản phẩm (2–180 ký tự) và thành phần (tối đa 1800 ký tự).')
    if len(note)>1000:raise ValueError('Ghi chú tối đa 1000 ký tự.')
    if layout_type not in TYPES or mode not in ('auto','local','claude'):
        raise ValueError('Loại poster hoặc chế độ AI không hợp lệ.')
    ratios=list(dict.fromkeys(ratios))
    if not ratios or any(r not in RATIOS for r in ratios):raise ValueError('Chọn tỷ lệ 1:1, 9:16 hoặc 16:9.')
    if page_id and not one('SELECT id FROM pages WHERE id=?',(page_id,)):
        raise ValueError('Fanpage không tồn tại.')
    image=_image_from_bytes(image_bytes)
    # Store the pixel-equivalent PNG source with correct EXIF orientation; no generated packaging.
    iid=uuid.uuid4().hex
    source_filename=iid+'.png' # lossless standard format
    image.save(DESIGN_DIR/source_filename,'PNG')
    layout=_choose_layout(layout_type)
    guidance='Bố cục nội bộ từ mẫu đã được đánh giá.'
    provider='local'
    from .ai import get_key
    must_ask = mode=='claude'
    should_ask = must_ask or (mode=='auto' and design_stats()['level']<2 and bool(get_key('claude')))
    if should_ask:
        try:
            layout,guidance=_claude_layout(product_name,ingredients,layout_type,note,layout)
            provider='claude'
        except Exception as exc:
            if must_ask:
                (DESIGN_DIR/source_filename).unlink(missing_ok=True)
                raise ValueError('Không nhận được concept từ Claude: '+str(exc)[:200]) from exc
            guidance='Claude tạm thời không khả dụng; sử dụng bố cục cục bộ.'
    project_id='D'+uuid.uuid4().hex[:12].upper()
    created=now()
    images=[]
    try:
        for ratio in ratios:
            filename,w,h=render_poster({'product_name':product_name,'ingredients':ingredients,
                                        'layout_type':layout_type,'layout_name':layout},image,ratio)
            images.append({'id':'O'+uuid.uuid4().hex[:12].upper(),'ratio':ratio,'filename':filename,
                           'width':w,'height':h,'url':'/media/design/'+filename})
        with db() as c:
            c.execute('''INSERT INTO design_projects (id,product_name,ingredients,note,image_filename,
                       layout_type,layout_name,guidance,provider,page_id,created) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                      (project_id,product_name,ingredients,note,source_filename,layout_type,layout,guidance,provider,page_id,created))
            c.executemany('''INSERT INTO design_outputs (id,project_id,ratio,filename,width,height,created)
                             VALUES(?,?,?,?,?,?,?)''',[(i['id'],project_id,i['ratio'],i['filename'],i['width'],i['height'],created) for i in images])
        log('creative','poster_created',f'Tạo {len(images)} poster cho {product_name}, nguồn concept: {provider}')
        return {'id':project_id,'product_name':product_name,'layout_name':layout,
                'concept_provider':provider,'guidance':guidance,'outputs':images,'brain':design_stats()}
    except Exception:
        for i in images:(DESIGN_DIR/i['filename']).unlink(missing_ok=True)
        (DESIGN_DIR/source_filename).unlink(missing_ok=True)
        raise


def list_projects(limit=25):
    init_design()
    projects=all_rows('SELECT * FROM design_projects ORDER BY created DESC LIMIT ?',(limit,))
    for project in projects:
        project['outputs']=all_rows('''SELECT o.id,o.ratio,o.width,o.height,o.filename,
                             r.rating,r.comment FROM design_outputs o LEFT JOIN design_reviews r ON r.output_id=o.id
                             WHERE o.project_id=? ORDER BY o.width DESC''',(project['id'],))
        for x in project['outputs']:x['url']='/media/design/'+x['filename']
        project['original_url']='/media/design/'+project['image_filename']
    return {'items':projects,'brain':design_stats()}


def submit_feedback(output_id: str, rating: int, comment=''):
    if not isinstance(rating,int) or not 1<=rating<=5:raise ValueError('Điểm phải từ 1 đến 5.')
    if len(comment)>500:raise ValueError('Nhận xét quá dài.')
    record=one('SELECT project_id FROM design_outputs WHERE id=?',(output_id,))
    if not record:raise ValueError('Không tìm thấy poster.')
    with db() as c:
        c.execute('''INSERT INTO design_reviews(id,project_id,output_id,rating,comment,created) VALUES(?,?,?,?,?,?)
                  ON CONFLICT(output_id) DO UPDATE SET rating=excluded.rating,comment=excluded.comment,created=excluded.created''',
                  ('R'+uuid.uuid4().hex[:12].upper(),record['project_id'],output_id,rating,comment.strip(),now()))
    from .brains import enqueue_learning
    project=one('SELECT product_name,layout_name,layout_type,page_id FROM design_projects WHERE id=?',(record['project_id'],))
    if project:
        enqueue_learning('creative','poster_feedback',
            f'Người dùng đánh giá poster {rating}/5 sao cho sản phẩm {project["product_name"]}, '
            f'bố cục {project["layout_name"]}, loại {project["layout_type"]}. '
            f'Nhận xét: {comment[:240] or "Không có"}. Đây là phản hồi chủ quan, chưa phải dữ liệu hiệu suất Facebook.',
            source_ref=output_id,page_id=project['page_id'])
    return {'ok':True,'brain':design_stats()}
