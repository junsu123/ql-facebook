"""Rights-aware source harvesting; no external website or paid AI call in tests."""
from __future__ import annotations

import uuid
from test_api import client
from app.source_harvester import (pack,overview,import_original_courses,
  retrieve_open_page,fetch_one,_validated_catalog_url)
from app.db import db, one

class Response:
    def __init__(self,content,content_type='text/html',status=200):
        self.status_code=status
        self.headers={'content-type':content_type}
        self.content=content.encode('utf8')
    def iter_bytes(self):
        yield self.content

class FakeWebClient:
    def __init__(self,include_license=True):self.requests=[];self.include_license=include_license
    def get(self,url):
        self.requests.append(url)
        if url.endswith('/robots.txt'):return Response('User-agent: *\nAllow: /','text/plain')
        text='<main><h1>Marketing principles</h1><p>'+('Helpful customer experiences and original research with documented evidence. '*14)+'</p></main>'
        if self.include_license:text+='<footer>Except as otherwise noted, content licensed under Creative Commons Attribution 4.0 https://creativecommons.org/licenses/by/4.0/</footer>'
        return Response('<html>'+text+'</html>')

def test_catalog_and_27_original_chapters_are_importable_and_idempotent():
    s=client.get('/api/academy/harvester')
    assert s.status_code==200
    data=s.json()
    assert data['original_courses']==27
    assert data['counts']['catalog_total']>=15
    assert data['counts']['reference_only']>=10
    r=client.post('/api/academy/harvester/import-original')
    assert r.status_code==200
    assert r.json()['imported']+r.json()['duplicates']==27
    x=client.post('/api/academy/harvester/import-original')
    assert x.status_code==200 and x.json()['imported']==0
    assert x.json()['duplicates']==27
    assert client.get('/api/academy').json()['counts']['sources']>=27
    assert client.get('/api/knowledge/records').status_code==200

def test_rejects_nonlicensed_or_untrusted_urls():
    for url in ['http://developers.google.com/search/docs/fundamentals/x',
                'https://127.0.0.1/search/docs/fundamentals/x',
                'https://developers.google.com.evil.org/search/docs/x',
                'https://developers.google.com@evil.org/search/docs/x',
                'https://developers.google.com/terms/site-policies']:
        try:_validated_catalog_url(url)
        except ValueError:pass
        else:raise AssertionError('Unsafe or non-catalog route: '+url)
    entry=next(x for x in pack()['catalog'] if x['mode']=='reference_only')
    try:retrieve_open_page(entry,client=FakeWebClient(),robot_checker=lambda u:True)
    except ValueError as e:assert 'giấy phép' in str(e)
    else:raise AssertionError('Reference-only page was downloaded')

def test_licensed_download_requires_license_and_robots():
    approved=next(x for x in pack()['catalog'] if x['mode']=='licensed_html')
    http=FakeWebClient()
    data,size=retrieve_open_page(approved,client=http,robot_checker=lambda u:True)
    assert len(data)>240 and size>240
    assert http.requests==[approved['url']]
    try:retrieve_open_page(approved,client=FakeWebClient(),robot_checker=lambda u:False)
    except ValueError as e:assert 'robots' in str(e)
    else:raise AssertionError('robots denied fetch should be blocked')
    try:retrieve_open_page(approved,client=FakeWebClient(include_license=False),robot_checker=lambda u:True)
    except ValueError as e:assert 'giấy phép' in str(e)
    else:raise AssertionError('No CC license accepted')

def test_download_status_records_real_result_with_mocked_http():
    from app.source_harvester import init_harvester
    init_harvester()
    with db() as c:
        c.execute("UPDATE harvest_catalog SET status='blocked' WHERE mode='licensed_html'")
        row=c.execute("SELECT id FROM harvest_catalog WHERE mode='licensed_html' LIMIT 1").fetchone()
        c.execute("UPDATE harvest_catalog SET status='queued' WHERE id=?",(row['id'],))
    outcome=fetch_one(client=FakeWebClient(),robot_checker=lambda u:True)
    assert outcome['status']=='downloaded' and outcome['added']
    stored=one('SELECT source_id,status,downloaded_bytes FROM harvest_catalog WHERE id=?',(row['id'],))
    assert stored['status']=='downloaded' and stored['downloaded_bytes']>0
    assert one('SELECT COUNT(*) n FROM academy_sources WHERE id=?',(stored['source_id'],))['n']==1
    # blocked mode doesn't report a fake downloaded count
    summary=overview()
    assert summary['counts']['downloaded']>=1
