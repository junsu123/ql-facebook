"""Direct Claude design: one paid brief, reusable local poster rendering and lessons."""
import io
import json
import tempfile
import os

os.environ.setdefault('AIFC_DATA_DIR',tempfile.mkdtemp(prefix='aifc-v114-direct-'))

import httpx
from fastapi.testclient import TestClient
from PIL import Image,ImageDraw

from app.main import app
from app.design import DESIGN_DIR, BACKGROUND
from app import design_claude

client=TestClient(app)


def png():
    im=Image.new('RGBA',(280,440),(0,0,0,0))
    d=ImageDraw.Draw(im)
    d.rounded_rectangle((42,32,236,415),radius=10,fill=(131,85,45,255))
    d.text((55,140),'GOI TRA 3D',fill=(255,255,255))
    out=io.BytesIO();im.save(out,format='PNG');return out.getvalue()


def fake_result():
    return {
        'concept_name':'Poster sạch, dễ đọc',
        'visual_style':'Tối giản và sang trọng',
        'headline':'Trà thảo mộc mỗi ngày',
        'subheadline':'Thành phần tuyển chọn',
        'bullets':['Ba kích','Đinh lăng','Đông trùng hạ thảo'],
        'cta':'Khám phá thêm',
        'slogan':'Thưởng trà tự nhiên',
        'image_prompt':'Poster thương mại điện tử nền #777973, hộp sản phẩm gốc ở trung tâm, chữ nổi bật',
        'layout_1_1':'hero',
        'layout_9_16':'minimal',
        'layout_16_9':'editorial',
        'reasoning_summary':'Ưu tiên dễ nhìn trên điện thoại'
    }


def test_claude_direct_only_stores_result_and_render_reuses_it(monkeypatch):
    calls=[]
    def mock_claude(model,prompt,preview,mime,*,client=None):
        calls.append((model,prompt,mime))
        assert preview and mime=='image/jpeg'
        return fake_result(),{'input_tokens':160,'output_tokens':340},model
    monkeypatch.setattr(design_claude,'_claude_message',mock_claude)
    r=client.post('/api/design/claude-direct', data={
        'product_name':'Trà thảo mộc Ba Kích',
        'ingredients':'Ba kích, Đinh lăng, Đông trùng hạ thảo',
        'user_prompt':'Poster tối giản, chữ lớn',
    },files={'image':('product.png',png(),'image/png')})
    assert r.status_code==200,r.text
    obj=r.json(); cid=obj['concept_id'];assert len(calls)==1
    assert obj['design_result']==fake_result()
    from app.db import one
    assert one("SELECT id FROM agent_memories WHERE agent_id='creative' AND source_ref=?",(cid,))
    assert 'outputs' not in obj
    assert (DESIGN_DIR/obj['source_image_url'].split('/')[-1]).is_file()
    listed=client.get('/api/design/concepts').json()['items']
    assert listed[0]['id']==cid and listed[0]['outputs']==[]
    after=client.post('/api/design/concepts/'+cid+'/render',json={
        'ratios':['1:1','9:16','16:9'],'layout_type':'overview'})
    assert after.status_code==200,after.text
    assert len(calls)==1
    assert len(after.json()['outputs'])==3
    for item in after.json()['outputs']:
        with Image.open(DESIGN_DIR/item['filename']) as i:
            assert i.size==(item['width'],item['height'])
            assert i.format=='PNG'
            sub=i.crop((i.width//2-75,0,i.width//2+75,80))
            assert all(pixel==BACKGROUND for pixel in sub.getdata())
    # Projects are visible in normal poster library, tagged as direct Claude output.
    projects=client.get('/api/design/projects').json()['items']
    assert any(x['id']==after.json()['project_id'] and x['provider']=='claude_direct' for x in projects)
    linked=client.get('/api/design/concepts').json()['items'][0]['outputs']
    assert len(linked)==3
    assert client.post('/api/design/outputs/'+linked[0]['id']+'/review',json={'rating':5,'comment':'Dễ đọc'}).status_code==200


def test_direct_result_is_validated_and_blocks_dangerous_render(monkeypatch):
    illegal=fake_result();illegal['headline']='Chữa khỏi bệnh 100%'
    monkeypatch.setattr(design_claude,'_claude_message',lambda model,prompt,preview,mime,client=None:
                        (illegal,{'input_tokens':10,'output_tokens':20},model))
    r=client.post('/api/design/claude-direct',data={'product_name':'Trà X','ingredients':'Ba kích'},
                  files={'image':('x.png',png(),'image/png')})
    assert r.status_code==200
    r2=client.post('/api/design/concepts/'+r.json()['concept_id']+'/render',json={'ratios':['1:1']})
    assert r2.status_code==400 and 'sức khỏe' in r2.text


def test_bad_input_never_triggers_paid_call(monkeypatch):
    calls=[]
    monkeypatch.setattr(design_claude,'_claude_message',lambda *a,**kw:calls.append(1))
    r=client.post('/api/design/claude-direct',data={'product_name':'X','ingredients':'B'},
                  files={'image':('x.png',png(),'image/png')})
    assert r.status_code==400 and not calls
    r=client.post('/api/design/claude-direct',data={'product_name':'Trà xanh','ingredients':'Lá trà'},
                  files={'image':('broken.png',b'not an image','image/png')})
    assert r.status_code==400 and not calls
    assert client.post('/api/design/concepts/does-not-exist/render',json={'ratios':['1:1']}).status_code==404


def test_one_anthropic_vision_request_with_json_schema(monkeypatch):
    monkeypatch.setattr(design_claude,'get_key',lambda name:'test-key')
    events=[]
    def mock_post(request):
        assert request.url.host=='api.anthropic.com'
        assert request.headers['x-api-key']=='test-key'
        body=json.loads(request.content)
        assert body['messages'][0]['content'][0]['type']=='image'
        assert body['messages'][0]['content'][0]['source']['media_type']=='image/jpeg'
        assert body['output_config']['format']['type']=='json_schema'
        assert body['model'] in ('claude-haiku-5-5','claude-sonnet-5-5')
        events.append(body['model'])
        return httpx.Response(200,json={'content':[{'type':'text','text':json.dumps(fake_result())}],
                                        'usage':{'input_tokens':100,'output_tokens':200}})
    with httpx.Client(transport=httpx.MockTransport(mock_post)) as mock:
        result,usage,model=design_claude._claude_message('claude-haiku-5-5','brief',b'jpg','image/jpeg',client=mock)
    assert len(events)==1 and result['headline']==fake_result()['headline']
    assert usage=={'input_tokens':100,'output_tokens':200}


def test_http_error_reported_and_not_retry(monkeypatch):
    monkeypatch.setattr(design_claude,'get_key',lambda name:'test-key')
    attempts=[]
    def fail(request):
        attempts.append(1)
        return httpx.Response(401,text='invalid_api_key')
    with httpx.Client(transport=httpx.MockTransport(fail)) as mock:
        try:
            design_claude._claude_message('claude-haiku-5-5','brief',b'jpg','image/jpeg',client=mock)
        except ValueError as e:
            assert '401' in str(e)
        else:
            raise AssertionError('Missing error')
    assert len(attempts)==1
