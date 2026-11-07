"""Curated, rights-aware marketing knowledge loader.

Source links from Meta/third-party are reference-only unless the catalog marks
an explicitly permitted Google Developers CC BY 4.0 documentation page.
No Facebook scraping, generic web spider, login automation or rate-limit evasion.
All external downloads are initiated by the owner's local UI.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.robotparser
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .academy import add_source
from .db import db, now, one, all_rows

PACK=Path(__file__).with_name('marketing_knowledge_pack.json')
ALLOW_DOMAINS={'developers.google.com'}
USER_AGENT='AIFanpageCompany-Academy/1.12 (+local-owner-requested-study-import)'
MAX_BYTES=2_000_000
SCHEMA='''
CREATE TABLE IF NOT EXISTS harvest_catalog (
  id TEXT PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL UNIQUE,
  mode TEXT NOT NULL, license TEXT NOT NULL, agent_ids TEXT NOT NULL,
  attribution TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'reference_only',
  last_error TEXT NOT NULL DEFAULT '', source_id TEXT NOT NULL DEFAULT '',
  downloaded_bytes INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_harvest_catalog_status ON harvest_catalog(status,mode);
'''

def pack() -> dict:
    return json.loads(PACK.read_text(encoding='utf-8'))


def init_harvester() -> None:
    payload=pack()
    with db() as c:
        c.executescript(SCHEMA)
        for s in payload['catalog']:
            status='queued' if s['mode']=='licensed_html' else 'reference_only'
            c.execute('''INSERT OR IGNORE INTO harvest_catalog
                 (id,title,url,mode,license,agent_ids,attribution,status,updated_at)
                 VALUES(?,?,?,?,?,?,?,?,?)''',
                 (s['id'],s['title'],s['url'],s['mode'],s['license'],
                  json.dumps(s['agents']),s['attribution'],status,now()))


def overview() -> dict:
    init_harvester()
    stats=one('''SELECT COUNT(*) AS catalog_total,
       SUM(CASE WHEN mode='licensed_html' THEN 1 ELSE 0 END) AS eligible_open,
       SUM(CASE WHEN status='downloaded' THEN 1 ELSE 0 END) AS downloaded,
       SUM(CASE WHEN status='queued' THEN 1 ELSE 0 END) AS waiting,
       SUM(CASE WHEN status='blocked' THEN 1 ELSE 0 END) AS blocked,
       SUM(CASE WHEN status='reference_only' THEN 1 ELSE 0 END) AS reference_only,
       COALESCE(SUM(downloaded_bytes),0) AS downloaded_bytes FROM harvest_catalog''')
    sources=all_rows('''SELECT id,title,url,mode,license,status,last_error,source_id,downloaded_bytes,updated_at
                         FROM harvest_catalog ORDER BY mode DESC,title''')
    originals=pack()['curriculum']
    # A duplicate on content is valid and does not mean 27 newly imported docs.
    imported=one("SELECT COUNT(*) AS n FROM academy_sources WHERE source_ref LIKE 'aifc-curriculum/%'")['n']
    return {'catalog':sources,'counts':{k:(v or 0) for k,v in stats.items()},
            'original_courses':len(originals),'original_imported':imported,
            'notes':'Đã tải xuống = chỉ các trang có giấy phép phù hợp và tải thực sự thành công; các liên kết Meta/khác chỉ là danh mục tham khảo.'}


def import_original_courses() -> dict:
    """One button supplies usable *original* Vietnamese training material to all 9 agents."""
    init_harvester()
    added=0;dup=0;jobs=0
    for item in pack()['curriculum']:
        result=add_source(item['title'],item['body'],source_ref='aifc-curriculum/'+item['id'],agents=item['agents'])
        if result['duplicate']:dup+=1
        else:added+=1;jobs+=result['jobs']
    return {'imported':added,'duplicates':dup,'new_training_jobs':jobs,
            'note':'27 bài học do dự án tự biên soạn, có liên kết nguồn; chưa phải toàn văn của các khóa học bên ngoài.'}


class TextMainExtractor(HTMLParser):
    SKIP={'script','style','nav','footer','header','aside','form','svg','noscript'}
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip=0;self.main_depth=0;self.seen_main=False;self.items=[]
    def handle_starttag(self,tag,attrs):
        if tag in self.SKIP:self.skip+=1
        if tag in ('main','article'):
            self.main_depth+=1;self.seen_main=True
        if tag in ('p','li','h1','h2','h3','h4') and not self.skip:self.items.append('\n')
    def handle_endtag(self,tag):
        if tag in self.SKIP:self.skip=max(0,self.skip-1)
        if tag in ('main','article'):self.main_depth=max(0,self.main_depth-1)
        if tag in ('p','li','h1','h2','h3','h4') and not self.skip:self.items.append('\n')
    def handle_data(self,data):
        if not self.skip and (not self.seen_main or self.main_depth>0):
            d=data.strip()
            if d:self.items.append(d+' ')
    def text(self):
        return re.sub(r'\n{3,}','\n\n',''.join(self.items)).strip()


def _validated_catalog_url(url:str):
    u=urlsplit(url)
    if u.scheme!='https' or u.username or u.password or u.port not in (None,443):
        raise ValueError('Nguồn không phải HTTPS công khai đã được phê duyệt.')
    if u.hostname not in ALLOW_DOMAINS or u.fragment or u.query:
        raise ValueError('Nguồn nằm ngoài danh sách tài liệu mở được duyệt.')
    if not u.path.startswith('/search/docs/'):
        raise ValueError('Chỉ tải các trang hướng dẫn mở cụ thể; không quét toàn miền.')
    return u


def _read_response_bytes(response,max_bytes=MAX_BYTES)->bytes:
    declared=response.headers.get('content-length')
    if declared and int(declared)>max_bytes:raise ValueError('Trang vượt quá giới hạn dung lượng.')
    # Bounded streaming avoids downloading unbounded HTML into process RAM.
    chunks=[];total=0
    for part in response.iter_bytes():
        total+=len(part)
        if total>max_bytes:raise ValueError('Trang vượt quá giới hạn dung lượng.')
        chunks.append(part)
    return b''.join(chunks)


def retrieve_open_page(entry:dict,*,client:httpx.Client|None=None,robot_checker=None)->tuple[str,int]:
    """Download only explicitly CC-BY Google docs and check robots + license.

    Redirects are disabled; user cannot pass arbitrary URL because `entry` comes
    from immutable packaged catalog. Test injection is limited to HTTP client.
    """
    if entry['license']!='CC-BY-4.0' or entry['mode']!='licensed_html':
        raise ValueError('Nguồn không được đánh dấu giấy phép tái sử dụng phù hợp.')
    url=entry['url'];u=_validated_catalog_url(url)
    owns_client=client is None
    if owns_client:client=httpx.Client(timeout=15,follow_redirects=False,headers={'User-Agent':USER_AGENT})
    try:
        robot_url=f'{u.scheme}://{u.hostname}/robots.txt'
        if robot_checker is not None:
            allowed=bool(robot_checker(url))
        else:
            robots=client.get(robot_url)
            if robots.status_code!=200:raise ValueError('Không thể xác minh robots.txt; bỏ qua nguồn.')
            txt=_read_response_bytes(robots, max_bytes=512_000).decode('utf8','replace')
            rp=urllib.robotparser.RobotFileParser();rp.parse(txt.splitlines())
            allowed=rp.can_fetch(USER_AGENT,url)
        if not allowed:raise ValueError('robots.txt không cho phép tải tự động nguồn này.')
        response=client.get(url)
        if response.status_code!=200:raise ValueError(f'Nguồn trả HTTP {response.status_code}.')
        ctype=response.headers.get('content-type','').lower()
        if 'text/html' not in ctype:raise ValueError('Nguồn không trả HTML hợp lệ.')
        raw=_read_response_bytes(response)
        html=raw.decode('utf8','replace')
        # On Google Developers most doc pages have this explicit footer notice;
        # pages lacking it require manual verification and are skipped.
        if 'creativecommons.org/licenses/by/4.0' not in html.lower() and not ('creative commons attribution 4.0' in html.lower()):
            raise ValueError('Không thấy tuyên bố giấy phép CC BY 4.0 trong trang; cần kiểm tra thủ công.')
        ex=TextMainExtractor();ex.feed(html)
        extracted=ex.text()
        if len(extracted)<240:raise ValueError('Trang quá ít nội dung để đào tạo, có thể cần JavaScript.')
        return extracted[:85_000],len(raw)
    finally:
        if owns_client:client.close()


def fetch_one(*,client=None,robot_checker=None) -> dict:
    """Processes at most one approved URL. Do not retry blocked sites continuously."""
    init_harvester()
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        selected=c.execute("SELECT * FROM harvest_catalog WHERE status='queued' AND mode='licensed_html' ORDER BY title LIMIT 1").fetchone()
        if not selected:return {'status':'no_approved_sources'}
        item=dict(selected)
        c.execute("UPDATE harvest_catalog SET status='fetching',updated_at=? WHERE id=?",(now(),item['id']))
    try:
        text,byte_count=retrieve_open_page(item,client=client,robot_checker=robot_checker)
        content=(f'Nguồn: {item["url"]}\n\nTác giả/nguồn: {item["attribution"]}\n'
                 f'Giấy phép: CC BY 4.0; đã truy cập ngày {now()}. Không gồm hình ảnh/thương hiệu.\n\n'+text)
        a=add_source(item['title'],content,source_ref=item['url'],agents=json.loads(item['agent_ids']))
        with db() as c:
            c.execute("UPDATE harvest_catalog SET status='downloaded',source_id=?,downloaded_bytes=?,last_error='',updated_at=? WHERE id=?",
                      (a['source_id'],byte_count,now(),item['id']))
        return {'status':'downloaded','source':item['title'],'bytes':byte_count,'added':not a['duplicate'],'jobs':a['jobs']}
    except Exception as exc:
        safe=str(exc)[:260]
        with db() as c:
            c.execute("UPDATE harvest_catalog SET status='blocked',last_error=?,updated_at=? WHERE id=?",
                      (safe,now(),item['id']))
        return {'status':'blocked','source':item['title'],'reason':safe}


def fetch_approved_batch(max_sources:int=4,*,client=None,robot_checker=None)->dict:
    """Small bounded batch, no full-domain crawling and no hidden background loop."""
    items=[]
    for _ in range(min(4,max(1,int(max_sources)))):
        r=fetch_one(client=client,robot_checker=robot_checker)
        if r['status']=='no_approved_sources':break
        items.append(r)
        time.sleep(.2)  # polite spacing, not throughput maximization
    return {'results':items,'downloaded':sum(x['status']=='downloaded' for x in items),
            'blocked':sum(x['status']=='blocked' for x in items)}
