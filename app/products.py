"""Local product catalog with owner-supplied facts, folder references and actual image files.

A shared folder URL is stored as a reference; it is not silently crawled or
assumed to grant access. Images usable by agents are explicitly imported.
"""
from __future__ import annotations

import hashlib
import io
import re
import sqlite3
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image, UnidentifiedImageError

from .db import MEDIA_DIR, db, now, one, all_rows, log

PRODUCT_MEDIA_DIR = MEDIA_DIR / 'products'
MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_IMAGE_PIXELS = 30_000_000
MAX_IMAGES_PER_PRODUCT = 80
MAX_BATCH_IMAGES = 20

SCHEMA = '''
CREATE TABLE IF NOT EXISTS products (
 id TEXT PRIMARY KEY,
 name TEXT NOT NULL,
 sku TEXT NOT NULL DEFAULT '',
 category TEXT NOT NULL DEFAULT '',
 ingredients TEXT NOT NULL DEFAULT '',
 description TEXT NOT NULL DEFAULT '',
 approved_facts TEXT NOT NULL DEFAULT '',
 folder_url TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'active',
 created TEXT NOT NULL, updated TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS product_page_links (
 product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
 page_id TEXT NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
 PRIMARY KEY(product_id,page_id)
);
CREATE INDEX IF NOT EXISTS ix_products_created ON products(created);
CREATE INDEX IF NOT EXISTS ix_product_pages_page ON product_page_links(page_id);
CREATE TABLE IF NOT EXISTS product_images (
 id TEXT PRIMARY KEY,
 product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
 filename TEXT NOT NULL UNIQUE,
 original_name TEXT NOT NULL DEFAULT '',
 sha256 TEXT NOT NULL,
 size_bytes INTEGER NOT NULL,
 created TEXT NOT NULL,
 UNIQUE(product_id,sha256)
);
CREATE INDEX IF NOT EXISTS ix_product_images_owner ON product_images(product_id,created);
'''


def init_products():
    PRODUCT_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    with db() as c:
        c.executescript(SCHEMA)


def safe_folder_url(url: str) -> str:
    value = (url or '').strip()
    if not value:
        return ''
    if len(value) > 2000:
        raise ValueError('Link thư mục ảnh không được vượt quá 2000 ký tự.')
    try:
        parsed = urlsplit(value)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError
        if parsed.port not in (None, 443):
            raise ValueError
        if parsed.hostname in ('localhost','127.0.0.1','0.0.0.0'):
            raise ValueError
        if any(ord(ch)<32 for ch in value):
            raise ValueError
    except ValueError as exc:
        raise ValueError('Hãy nhập link thư mục HTTPS hợp lệ, không kèm mật khẩu hoặc cổng nội bộ.') from exc
    # Reference only, never fetched by this server.
    return value


def _normalize(data: dict) -> dict:
    cleaned={}
    for name,limit in [('name',180),('sku',80),('category',160),('ingredients',5000),
                       ('description',8000),('approved_facts',8000)]:
        value=str(data.get(name,'') or '').strip()
        if len(value)>limit:raise ValueError(f'{name} không được vượt quá {limit} ký tự.')
        cleaned[name]=value
    if len(cleaned['name'])<2:raise ValueError('Tên sản phẩm phải có ít nhất 2 ký tự.')
    cleaned['folder_url']=safe_folder_url(data.get('folder_url',''))
    cleaned['status']=data.get('status','active')
    if cleaned['status'] not in ('active','archived'):
        raise ValueError('Trạng thái sản phẩm không hợp lệ.')
    ids=data.get('page_ids') or []
    if not isinstance(ids,list) or len(ids)>100 or any(not isinstance(x,str) for x in ids):
        raise ValueError('Danh sách Fanpage không hợp lệ.')
    cleaned['page_ids']=list(dict.fromkeys(ids))
    return cleaned


def _write_links(c:sqlite3.Connection, product_id:str, page_ids:list[str]):
    for page_id in page_ids:
        if not c.execute('SELECT id FROM pages WHERE id=?',(page_id,)).fetchone():
            raise ValueError(f'Fanpage không tồn tại: {page_id}')
    c.execute('DELETE FROM product_page_links WHERE product_id=?',(product_id,))
    c.executemany('INSERT INTO product_page_links(product_id,page_id) VALUES(?,?)',
                  [(product_id,page_id) for page_id in page_ids])


def _serialize(row:dict, conn:sqlite3.Connection) -> dict:
    item=dict(row)
    item['page_ids']=[r['page_id'] for r in conn.execute('SELECT page_id FROM product_page_links WHERE product_id=? ORDER BY page_id',(row['id'],))]
    images=[]
    for img in conn.execute('SELECT * FROM product_images WHERE product_id=? ORDER BY created,id',(row['id'],)):
        im=dict(img)
        im['url']='/media/products/'+im['filename']
        images.append(im)
    item['images']=images
    item['image_count']=len(images)
    return item


def list_products(limit:int=500)->list[dict]:
    with db() as c:
        return [_serialize(r,c) for r in c.execute('SELECT * FROM products ORDER BY created DESC LIMIT ?', (limit,)).fetchall()]


def get_product(product_id:str)->dict:
    with db() as c:
        r=c.execute('SELECT * FROM products WHERE id=?',(product_id,)).fetchone()
        if not r:raise LookupError('Không tìm thấy sản phẩm.')
        return _serialize(r,c)


def add_product(data:dict)->dict:
    obj=_normalize(data)
    pid='PR'+uuid.uuid4().hex[:12].upper()
    with db() as c:
        c.execute('INSERT INTO products(id,name,sku,category,ingredients,description,approved_facts,folder_url,status,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
            (pid,obj['name'],obj['sku'],obj['category'],obj['ingredients'],obj['description'],obj['approved_facts'],obj['folder_url'],obj['status'],now(),now()))
        _write_links(c,pid,obj['page_ids'])
    log('ceo','product_added',f'Đã thêm sản phẩm {obj["name"]} vào thư viện (dữ liệu do chủ sở hữu cung cấp).')
    return get_product(pid)


def edit_product(product_id:str, data:dict)->dict:
    obj=_normalize(data)
    with db() as c:
        if not c.execute('SELECT id FROM products WHERE id=?',(product_id,)).fetchone():
            raise LookupError('Không tìm thấy sản phẩm.')
        c.execute('UPDATE products SET name=?,sku=?,category=?,ingredients=?,description=?,approved_facts=?,folder_url=?,status=?,updated=? WHERE id=?',
            (obj['name'],obj['sku'],obj['category'],obj['ingredients'],obj['description'],obj['approved_facts'],obj['folder_url'],obj['status'],now(),product_id))
        _write_links(c,product_id,obj['page_ids'])
    log('ceo','product_edited',f'Đã cập nhật hồ sơ sản phẩm {obj["name"]}.')
    return get_product(product_id)


def remove_product(product_id:str)->None:
    images=get_product(product_id)['images']
    with db() as c:
        c.execute('DELETE FROM products WHERE id=?',(product_id,))
    for image in images:
        # Keep assets already attached to existing drafts/published posts.
        if not one('SELECT id FROM contents WHERE media_path=? LIMIT 1',(image['url'],)):
            (PRODUCT_MEDIA_DIR/image['filename']).unlink(missing_ok=True)
    log('ceo','product_deleted',f'Đã xóa dữ liệu sản phẩm {product_id} khỏi thư viện.')


def _checked_image(raw:bytes)->tuple[str,str]:
    if not raw or len(raw)>MAX_IMAGE_BYTES:
        raise ValueError('Mỗi ảnh phải có dung lượng từ 1 byte đến 12MB.')
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.width*image.height>MAX_IMAGE_PIXELS:
                raise ValueError('Ảnh quá lớn (tối đa 30 triệu pixel).')
            fmt=image.format
            image.verify()
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError,Image.DecompressionBombWarning) as exc:
        raise ValueError('Tệp ảnh không hợp lệ.') from exc
    ext={'PNG':'.png','JPEG':'.jpg','WEBP':'.webp'}.get(fmt)
    if not ext:raise ValueError('Chỉ cho phép PNG, JPG và WEBP.')
    return ext,hashlib.sha256(raw).hexdigest()


def add_product_images(product_id:str, uploads:list[tuple[str,bytes]]) -> dict:
    if len(uploads)<1 or len(uploads)>MAX_BATCH_IMAGES:
        raise ValueError('Mỗi lần chỉ được tải từ 1 đến 20 ảnh.')
    get_product(product_id)
    processed=[(str(name or '')[:180],raw,*_checked_image(raw)) for name,raw in uploads]
    created_files=[]
    try:
        with db() as c:
            existing=c.execute('SELECT count(*) FROM product_images WHERE product_id=?',(product_id,)).fetchone()[0]
            known={r[0] for r in c.execute('SELECT sha256 FROM product_images WHERE product_id=?',(product_id,))}
            unique=[]
            for name,raw,ext,digest in processed:
                if digest not in known:
                    known.add(digest)
                    unique.append((name,raw,ext,digest))
            if existing+len(unique)>MAX_IMAGES_PER_PRODUCT:
                raise ValueError('Mỗi sản phẩm được lưu tối đa 80 ảnh.')
            for name,raw,ext,digest in unique:
                filename=uuid.uuid4().hex+ext
                output=PRODUCT_MEDIA_DIR/filename
                output.write_bytes(raw)
                created_files.append(output)
                c.execute('INSERT INTO product_images(id,product_id,filename,original_name,sha256,size_bytes,created) VALUES(?,?,?,?,?,?,?)',
                          ('IMG'+uuid.uuid4().hex[:12].upper(),product_id,filename,name,digest,len(raw),now()))
    except Exception:
        for path in created_files:path.unlink(missing_ok=True)
        raise
    return {'added':len(created_files),'duplicates':len(uploads)-len(created_files),'product':get_product(product_id)}


def remove_product_image(product_id:str, image_id:str)->dict:
    with db() as c:
        record=c.execute('SELECT filename FROM product_images WHERE product_id=? AND id=?',(product_id,image_id)).fetchone()
        if not record:raise LookupError('Không tìm thấy ảnh thuộc sản phẩm này.')
        c.execute('DELETE FROM product_images WHERE product_id=? AND id=?',(product_id,image_id))
    media_url='/media/products/'+record['filename']
    if not one('SELECT id FROM contents WHERE media_path=? LIMIT 1',(media_url,)):
        (PRODUCT_MEDIA_DIR/record['filename']).unlink(missing_ok=True)
    return get_product(product_id)


def product_context_for_page(page_id:str, selected_id:str|None=None)->list[dict]:
    with db() as c:
        sql='''SELECT p.* FROM products p JOIN product_page_links l ON l.product_id=p.id
               WHERE l.page_id=? AND p.status='active' '''
        args=[page_id]
        if selected_id:
            sql+=' AND p.id=?';args.append(selected_id)
        sql+=' ORDER BY p.updated DESC LIMIT 12'
        items=[_serialize(p,c) for p in c.execute(sql,args)]
    return [{
        'id':p['id'],'name':p['name'],'sku':p['sku'],'category':p['category'],
        'ingredients':p['ingredients'],'description':p['description'],
        'owner_supplied_facts_not_independently_verified':p['approved_facts'],
        'folder_url_reference_only':p['folder_url'],
        'uploaded_images':[{'url':i['url'],'filename':i['original_name']} for i in p['images'][:12]],
    } for p in items]


def assign_product(product_id:str,page_id:str,focus:str='Giới thiệu sản phẩm')->dict:
    from .ai import create_task
    product=get_product(product_id)
    if product['status']!='active':raise ValueError('Sản phẩm đang lưu trữ, không thể giao việc.')
    if page_id not in product['page_ids']:
        raise ValueError('Hãy liên kết Fanpage với sản phẩm trước khi giao việc.')
    if not product['ingredients'] and not product['description'] and not product['approved_facts']:
        raise ValueError('Cần nhập mô tả/thành phần/dữ kiện sản phẩm trước khi giao AI.')
    focus=focus.strip()[:300]
    if len(focus)<3:raise ValueError('Hãy nhập chủ đề nội dung.')
    images=[x['url'] for x in product['images'][:10]]
    core=f'''Sản phẩm: {product['name']} (SKU: {product['sku']}).\nThành phần: {product['ingredients']}\nMô tả: {product['description']}\nDữ kiện chủ sở hữu cung cấp (chưa kiểm chứng độc lập): {product['approved_facts']}\nThư mục ảnh tham khảo (không tự đọc được): {product['folder_url']}\nẢnh đã tải vào thư viện (có thể mở trong ứng dụng): {', '.join(images) or 'chưa có ảnh'}\nMục tiêu: {focus}\nChỉ sử dụng dữ kiện có bằng chứng, không phát minh công dụng điều trị hay đánh giá giả. Không nhận đã xem ảnh pixel nếu chưa dùng công cụ phân tích ảnh.'''
    steps=[
        ('research','Nghiên cứu chủ đề phù hợp', 'Phân tích góc nội dung, câu hỏi thường gặp và điều còn thiếu nguồn.'),
        ('strategy','Lập kế hoạch chăm sóc Page','Đề xuất các chủ đề và lịch nội dung phù hợp với sản phẩm và người đọc.'),
        ('content','Viết bài giới thiệu sản phẩm','Soạn một bài Facebook rõ ràng, nguyên bản, tự nhiên, có CTA phù hợp.'),
        ('creative','Thiết kế brief poster sản phẩm','Lập brief ảnh bằng nguồn ảnh đã nhập trong thư viện; không tự nhận đã xuất file PNG.'),
        ('compliance','Rà soát nội dung sản phẩm','Nêu những tuyên bố cần xác minh trước khi dùng trên poster và Fanpage.'),
    ]
    task_ids=[]
    for agent,title,instructions in steps:
        task_ids.append(create_task(agent,f'{product["name"]} · {title}',core+'\n'+instructions,page_id,source='product_manager'))
    log('ceo','product_assignment',f'CEO đã giao {len(task_ids)} nhiệm vụ cho sản phẩm {product["name"]}, Page {page_id}.')
    return {'task_ids':task_ids,'queued':len(task_ids),'product_id':product_id,'page_id':page_id}
