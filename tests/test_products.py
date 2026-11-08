"""End-to-end local product catalog: facts, page association, actual images, agent tasks."""
import io
import uuid
from PIL import Image
from fastapi.testclient import TestClient

from app.main import app
from app.db import one
from app.products import PRODUCT_MEDIA_DIR, product_context_for_page

client=TestClient(app)

def _page():
    suffix=uuid.uuid4().hex[:10]
    result=client.post('/api/pages',json={'name':'Page thử '+suffix,'url':'https://www.facebook.com/test-product-'+suffix})
    assert result.status_code==200,result.text
    return result.json()['id']

def _png(color='red'):
    stream=io.BytesIO()
    Image.new('RGBA',(350,350),color).save(stream,format='PNG')
    return stream.getvalue()

def _product(page_ids):
    x=client.post('/api/products',json={'name':'Trà thảo mộc thử nghiệm','sku':'TR-V116',
         'category':'Trà thảo mộc','ingredients':'Đinh lăng, cỏ ngọt',
         'description':'Sản phẩm túi lọc 30 gói','approved_facts':'30 gói x 3 g ghi trên bao bì',
         'folder_url':'https://drive.google.com/drive/folders/1234','page_ids':page_ids})
    assert x.status_code==200,x.text
    return x.json()

def test_create_link_and_full_read():
    page=_page();product=_product([page]);pid=product['id']
    assert product['page_ids']==[page]
    assert product['image_count']==0
    assert 'drive.google.com' in product['folder_url']
    assert client.get('/api/products').status_code==200
    assert client.get('/api/products/'+pid).json()['name']==product['name']
    assert any(x['name']==product['name'] for x in client.get('/api/bootstrap').json()['products'])
    assert product_context_for_page(page)[0]['owner_supplied_facts_not_independently_verified']=='30 gói x 3 g ghi trên bao bì'
    assert product_context_for_page('nonexistent')==[]
    body={key:product[key] for key in ('name','sku','category','ingredients','description','approved_facts','folder_url','status','page_ids')}
    assert client.post('/api/products',json={**body,'name':'Bad','folder_url':'http://127.0.0.1/secrets'}).status_code==400
    assert client.post('/api/products',json={**body,'name':'Bad','folder_url':'javascript:alert(1)'}).status_code==400
    assert client.post('/api/products',json={**body,'name':'Bad','page_ids':['badpage']}).status_code==400
    assert client.get('/api/products/unknown').status_code==404

def test_upload_images_dedupe_block_invalid_and_delete():
    page=_page();pid=_product([page])['id'];png=_png('orange')
    files=[('files',('photo.png',png,'image/png')),('files',('copy.png',png,'image/png'))]
    result=client.post('/api/products/'+pid+'/images',files=files)
    assert result.status_code==200,result.text
    body=result.json();assert body['added']==1 and body['duplicates']==1
    im=body['product']['images'][0]
    assert client.get(im['url']).status_code==200
    assert (PRODUCT_MEDIA_DIR/im['filename']).is_file()
    assert product_context_for_page(page)[0]['uploaded_images'][0]['url']==im['url']
    bad=client.post('/api/products/'+pid+'/images',files=[('files',('evil.png',b'malicious','image/png'))])
    assert bad.status_code==400
    assert client.post('/api/products/'+pid+'/images',files=[('files',('evil.svg',b'<svg/>','image/svg+xml'))]).status_code==400
    assert client.post('/api/products/unknown/images',files=[('files',('yes.png',png,'image/png'))]).status_code==404
    assert client.delete('/api/products/'+pid+'/images/invalid').status_code==404
    assert client.delete('/api/products/'+pid+'/images/'+im['id']).status_code==200
    assert not (PRODUCT_MEDIA_DIR/im['filename']).exists()
    assert client.get('/api/products/'+pid).json()['images']==[]
    client.delete('/api/products/'+pid)

def test_edit_rollback_and_delete_files():
    p1=_page();p2=_page();product=_product([p1]);pid=product['id'];
    photo=client.post('/api/products/'+pid+'/images',files=[('files',('tea.png',_png('purple'),'image/png'))]).json()['product']['images'][0]
    change={key:product[key] for key in ('name','sku','category','ingredients','description','approved_facts','folder_url','status','page_ids')}
    change.update(name='Đã sửa tên',page_ids=[p2])
    result=client.put('/api/products/'+pid,json=change)
    assert result.status_code==200,result.text
    assert result.json()['page_ids']==[p2] and result.json()['image_count']==1
    assert product_context_for_page(p1)==[]
    assert product_context_for_page(p2)[0]['name']=='Đã sửa tên'
    bad={**change,'page_ids':['nonexistent']}
    assert client.put('/api/products/'+pid,json=bad).status_code==400
    assert client.get('/api/products/'+pid).json()['page_ids']==[p2] # transaction rolled back
    assert client.delete('/api/products/'+pid).status_code==200
    assert not (PRODUCT_MEDIA_DIR/photo['filename']).exists()
    assert client.get('/api/products/'+pid).status_code==404

def test_assign_five_agents_and_product_context_for_task():
    page=_page();product=_product([page]);pid=product['id']
    result=client.post('/api/products/'+pid+'/assign',json={'page_id':page,'focus':'Giới thiệu sản phẩm có ích'})
    assert result.status_code==200,result.text
    r=result.json();assert r['queued']==5 and len(set(r['task_ids']))==5
    tasks=[one('SELECT * FROM tasks WHERE id=?',(tid,)) for tid in r['task_ids']]
    assert {task['agent_id'] for task in tasks}=={'research','strategy','content','creative','compliance'}
    assert all(task['page_id']==page for task in tasks)
    assert any('Đinh lăng' in task['instructions'] for task in tasks)
    other=_page()
    assert client.post('/api/products/'+pid+'/assign',json={'page_id':other,'focus':'Xây dựng trang'}).status_code==400

def test_generate_product_content_and_auto_attach_image(monkeypatch):
    page=_page();product=_product([page]);pid=product['id']
    image=client.post('/api/products/'+pid+'/images',files=[('files',('tea.png',_png('blue'),'image/png'))]).json()['product']['images'][0]
    import app.ai as ai
    called=[]
    def fake_llm(system,prompt,*args,**kwargs):
        called.append(prompt);return 'Bài viết nguyên bản về trà đinh lăng, dùng theo hướng dẫn.'
    monkeypatch.setattr(ai,'call_llm',fake_llm)
    result=client.post('/api/contents/generate',json={'page_id':page,'topic':'Giới thiệu trà','product_id':pid})
    assert result.status_code==200,result.text
    assert result.json()['media_path']==image['url']
    assert called and 'Đinh lăng' in called[0]
    other=_page()
    assert client.post('/api/contents/generate',json={'page_id':other,'topic':'Giới thiệu trà','product_id':pid}).status_code==400


def test_using_catalog_image_in_draft_and_asset_survives_product_deletion():
    page=_page();pid=_product([page])['id']
    im=client.post('/api/products/'+pid+'/images',files=[('files',('tea.png',_png('green'),'image/png'))]).json()['product']['images'][0]
    post=client.post('/api/contents',json={'page_id':page,'topic':'Hình ảnh sản phẩm','body':'Bài giới thiệu một sản phẩm'}).json()
    assert client.post('/api/contents/'+post['id']+'/media',json={'path':im['url']}).status_code==200
    other=_page()
    other_post=client.post('/api/contents',json={'page_id':other,'topic':'Khác','body':'Một bản nháp khác'}).json()
    assert client.post('/api/contents/'+other_post['id']+'/media',json={'path':im['url']}).status_code==400
    assert client.delete('/api/products/'+pid+'/images/'+im['id']).status_code==200
    assert (PRODUCT_MEDIA_DIR/im['filename']).exists()  # Post already uses this image
    assert client.get(im['url']).status_code==200
