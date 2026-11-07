"""Real poster pixels, safe upload and preference learning; zero paid API calls."""
import io
import os
import tempfile
from pathlib import Path

os.environ.setdefault('AIFC_DATA_DIR',tempfile.mkdtemp(prefix='aifc-design-test-'))

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from app.main import app
from app.db import db
from app.design import BACKGROUND, DESIGN_DIR, design_stats, _choose_layout

client=TestClient(app)

def product_png():
    im=Image.new('RGBA',(260,420),(0,0,0,0))
    d=ImageDraw.Draw(im)
    d.rounded_rectangle((40,30,215,400),radius=14,fill=(135,85,43,255))
    d.rectangle((55,130,200,275),fill=(235,226,192,255))
    d.text((75,160),'TRA 3D',fill=(30,32,22))
    stream=io.BytesIO();im.save(stream,'PNG');return stream.getvalue()

def create(ratios='1:1,9:16,16:9', mode='local', **kwargs):
    fields={'product_name':'Trà thảo mộc Ba Kích','ingredients':'Ba kích, Đinh lăng, Ngọc cẩu, Đông trùng hạ thảo',
            'ratios':ratios,'layout_type':'overview','mode':mode,**kwargs}
    return client.post('/api/design/projects',data=fields,files={'image':('product.png',product_png(),'image/png')})

def test_creates_three_real_png_posters_and_safe_top_area():
    r=create();assert r.status_code==200,r.text
    p=r.json();assert p['concept_provider']=='local' and len(p['outputs'])==3
    for img in p['outputs']:
        path=DESIGN_DIR/img['filename'];assert path.is_file()
        with Image.open(path) as png:
            assert png.size==(img['width'],img['height'])
            assert png.format=='PNG'
            width,height=png.size
            sample=png.crop((width//2-75,0,width//2+75,80))
            assert set(sample.getdata())=={BACKGROUND}
            # The uploaded product has a distinct brown body visible in the result.
            assert sum(1 for pixel in png.resize((100,100)).getdata() if pixel[0] in range(100,175) and pixel[1] in range(60,110))>10
    assert client.get('/api/design/projects').json()['items'][0]['id']==p['id']

def test_review_and_designer_level():
    p=create('1:1').json();out=p['outputs'][0]['id']
    r=client.post('/api/design/outputs/'+out+'/review',json={'rating':5,'comment':'Bố cục rõ ràng'})
    assert r.status_code==200
    r=client.post('/api/design/outputs/'+out+'/review',json={'rating':4,'comment':'Đã điều chỉnh'})
    assert r.status_code==200
    assert design_stats()['reviewed']>=1
    assert client.post('/api/design/outputs/notfound/review',json={'rating':5}).status_code==404
    assert client.post('/api/design/outputs/'+out+'/review',json={'rating':7}).status_code==422
    # A small number of reviews must not imply a trained image model.
    assert design_stats()['learning_mode']=='layout_preference_memory'

def test_invalid_upload_does_not_write_project():
    before=len(client.get('/api/design/projects').json()['items'])
    p=client.post('/api/design/projects',data={'product_name':'Test','ingredients':'A','ratios':'1:1','mode':'local'},
          files={'image':('bad.png',b'not an image','image/png')})
    assert p.status_code==400
    assert len(client.get('/api/design/projects').json()['items'])==before
    assert create('2:3').status_code==400
    assert create('1:1',product_name='').status_code in (400,422)

def test_explicit_claude_mode_requires_key_or_reports_error(monkeypatch):
    # Ensure no paid remote call regardless of whether another test saved a key.
    import app.design as design
    def error(*args,**kwargs):raise Exception('Fake Claude offline')
    monkeypatch.setattr(design,'_claude_layout',error)
    r=create('1:1',mode='claude')
    assert r.status_code==400 and 'Claude' in r.text
    r=create('1:1',mode='auto')
    assert r.status_code==200

def test_claude_concept_only_one_call_for_all_ratios(monkeypatch):
    import app.design as design
    from app import ai
    calls=[]
    monkeypatch.setattr(ai,'get_key',lambda key:'dummy-key')
    def fake(*args):
        calls.append(args)
        return ('editorial','Bố cục phân chia hợp lý')
    monkeypatch.setattr(design,'_claude_layout',fake)
    r=create('1:1,9:16,16:9',mode='claude')
    assert r.status_code==200 and len(calls)==1
    assert r.json()['concept_provider']=='claude'
