"""Seven-day product-to-Page growth sprints.

All plans start as clearly labeled hypotheses, never simulated Facebook results.
Claude may refine content in one bounded call, with the auto model router.
No Meta access or automated engagement is performed by this module.
"""
from __future__ import annotations

import json
import math
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from .db import db, one, all_rows, log, now

VIETNAM_TZ = timezone(timedelta(hours=7))
AGENTS = ('research', 'strategy', 'content', 'creative', 'publishing', 'customer', 'analytics', 'compliance')
SPRINT_SCHEMA = '''
CREATE TABLE IF NOT EXISTS growth_sprints (
 id TEXT PRIMARY KEY,
 page_id TEXT REFERENCES pages(id) ON DELETE SET NULL,
 product_name TEXT NOT NULL,
 ingredients TEXT NOT NULL,
 target_audience TEXT NOT NULL DEFAULT '',
 baseline_followers INTEGER,
 previous_week_new_follows INTEGER,
 target_new_follows INTEGER NOT NULL,
 goal_basis TEXT NOT NULL,
 start_date TEXT NOT NULL,
 end_date TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'draft',
 outline_json TEXT NOT NULL,
 ai_plan_json TEXT NOT NULL DEFAULT '',
 ai_error TEXT NOT NULL DEFAULT '',
 created TEXT NOT NULL,
 updated TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sprints_created ON growth_sprints(created);
CREATE TABLE IF NOT EXISTS growth_progress (
 sprint_id TEXT NOT NULL REFERENCES growth_sprints(id) ON DELETE CASCADE,
 day INTEGER NOT NULL CHECK(day BETWEEN 1 AND 7),
 followers_total INTEGER NOT NULL CHECK(followers_total >= 0),
 views INTEGER NOT NULL DEFAULT 0 CHECK(views >= 0),
 interactions INTEGER NOT NULL DEFAULT 0 CHECK(interactions >= 0),
 notes TEXT NOT NULL DEFAULT '',
 source TEXT NOT NULL DEFAULT 'owner_manual',
 recorded TEXT NOT NULL,
 PRIMARY KEY(sprint_id,day)
);
'''


def init_growth():
    with db() as c:
        c.executescript(SPRINT_SCHEMA)


def follower_target(previous_week: int | None, requested: int | None) -> tuple[int, str]:
    """A planning target, NEVER a forecast or outcome guarantee.

    Without actual prior-period follows, use a small, clearly provisional
    starting target rather than pretending to know organic conversion rates.
    """
    if requested is not None:
        return requested, 'owner_goal'
    if previous_week is None:
        return 25, 'provisional_experiment'
    # Week-over-week stretch target based on a supplied seven-day count.
    return max(10, math.ceil(previous_week * 1.20)), 'prior_week_plus_20pct'


def _days(product: str, ingredients: list[str]) -> list[dict[str, Any]]:
    first = ingredients[0] if ingredients else 'thành phần trên bao bì'
    second = ingredients[1] if len(ingredients)>1 else first
    blueprints = [
      ('Định vị Page', 'reel', f'Bạn đã thực sự hiểu {product} là gì chưa?',
       'Mở đầu bằng câu hỏi khách hàng thường gặp.',
       'Giới thiệu đúng tên, dạng sản phẩm và dữ kiện đã xác thực.',
       'Đưa bao bì thật và nguồn thông tin rõ ràng vào khung hình.',
       'Theo dõi Page để xem kiến thức hữu ích mỗi ngày.'),
      ('Thành phần minh bạch', 'reel', f'Tại sao trong sản phẩm lại có {first}?',
       f'Cho xem tên thành phần {first} từ thông tin người dùng cung cấp.',
       'Giải thích nguồn gốc hoặc vai trò *chỉ khi đã có tài liệu xác thực*.',
       'Nhắc rằng thành phần không tự chứng minh công dụng điều trị.',
       'Bình luận câu hỏi về thành phần bạn muốn tìm hiểu.'),
      ('Cách đọc nhãn', 'carousel', '3 điều nên kiểm tra trước khi chọn một sản phẩm',
       'Mở đầu bằng một nhãn sản phẩm được phép sử dụng.',
       'Hướng dẫn đọc thành phần, quy cách và hướng dẫn sử dụng.',
       'Không đưa lời hứa về công dụng khi chưa đủ chứng cứ.',
       'Lưu bài để lần sau dễ đối chiếu.'),
      ('Giải đáp thắc mắc', 'reel', f'{second} có ý nghĩa gì trên nhãn?',
       'Nêu một câu hỏi trung lập về nhãn.',
       'Đối chiếu thành phần được công bố với hồ sơ sản phẩm.',
       'Nêu điều chưa được xác minh, tránh khẳng định quá mức.',
       'Theo dõi để nhận các giải đáp tiếp theo.'),
      ('Trình diễn thật', 'reel', 'Một lần mở hộp và kiểm tra thông tin sản phẩm',
       'Dùng hộp hoặc ảnh sản phẩm thật, không làm sai bao bì.',
       'Chỉ thao tác theo hướng dẫn sử dụng chính thức nếu có.',
       'Không dựng phản hồi khách hàng giả hoặc kết quả sử dụng.',
       'Bạn muốn xem chi tiết nào ở video kế tiếp?'),
      ('Chủ đề tương tác', 'post', 'Bạn thường xem thông tin nào đầu tiên khi mua hàng?',
       'Đưa câu hỏi lựa chọn đơn giản, không thưởng tương tác giả.',
       'Gợi ý lựa chọn: thành phần, cách dùng, xuất xứ, giá.',
       'Tổng hợp câu hỏi thật để lên nội dung cho tuần sau.',
       'Chia sẻ ý kiến thực tế của bạn trong phần bình luận.'),
      ('Tổng kết & đo lường', 'reel', '7 ngày qua: điều gì bạn muốn hiểu rõ nhất?',
       'Tóm tắt các chủ đề đã đăng trong tuần.',
       'Đề xuất nội dung tiếp theo theo phản hồi có thật.',
       'Mời theo dõi mà không hứa hẹn quà hoặc kết quả không có.',
       'Theo dõi Page để cùng tìm hiểu ở tuần tiếp theo.'),
    ]
    return [dict(day=i, topic=topic, format=fmt, hook=hook, scenes=[s1,s2,s3], cta=cta,
                 objective='Kiểm tra chất lượng lượt xem, bình luận thật và lượt theo dõi mới',
                 review_required=True, source='planning_template_not_facebook_data')
            for i,(topic,fmt,hook,s1,s2,s3,cta) in enumerate(blueprints,1)]


def _normalize_ingredients(ingredients: str) -> list[str]:
    parts=[re.sub(r'\s+',' ',p).strip() for p in re.split(r'[,;\n]+',ingredients)]
    parts=[p for p in parts if p]
    return list(dict.fromkeys(parts))[:30]


def _plan(product: str, ingredients: list[str], target: int, basis: str, audience: str) -> dict:
    return {
      'status':'outline_not_ai_verified',
      'positioning':f'Fanpage chia sẻ thông tin có kiểm chứng về {product}, ưu tiên kiến thức hữu ích trước bán hàng.',
      'target_audience':audience or 'Chưa xác định; nhiệm vụ đầu tiên của Research là thu thập dữ liệu khách hàng.',
      'content_pillars':['Giải thích thành phần','Hướng dẫn đọc nhãn','Câu hỏi thực tế','Trình diễn trung thực'],
      'seven_day_plan':_days(product,ingredients),
      'weekly_target':{'new_follows':target,'basis':basis,'note':'Mục tiêu nội bộ để thử nghiệm, không phải dự báo hay cam kết từ Facebook.'},
      'measurement':['Tổng followers trước và sau tuần','Lượt xem từng video','Bình luận có ích','Tỷ lệ lượt xem chuyển thành lượt theo dõi nếu đủ dữ liệu'],
      'rules':['Không mua hoặc trao đổi follow, view, bình luận giả',
               'Không phát tán bài trùng lặp hàng loạt',
               'Không tự tạo tuyên bố sức khỏe từ tên thành phần',
               'Không tự đăng Facebook khi chưa được phép'],
    }


def create_sprint(*, product_name: str, ingredients: str, page_id: str | None = None,
                  target_audience: str = '', baseline_followers: int | None = None,
                  previous_week_new_follows: int | None = None,
                  goal_override: int | None = None, start_date: str | None = None) -> dict:
    product_name=re.sub(r'\s+',' ',product_name).strip()
    parts=_normalize_ingredients(ingredients)
    if len(product_name)<3 or not parts:
        raise ValueError('Cần tên sản phẩm và ít nhất một thành phần hợp lệ.')
    if len(product_name)>180 or len(ingredients)>5000 or len(target_audience)>500:
        raise ValueError('Dữ liệu đầu vào vượt giới hạn cho phép.')
    for val in (baseline_followers,previous_week_new_follows,goal_override):
        if val is not None and (not isinstance(val,int) or isinstance(val,bool) or val<0 or val>1_000_000):
            raise ValueError('Số follow không hợp lệ.')
    if goal_override is not None and goal_override < 1:
        raise ValueError('Mục tiêu tuần phải ít nhất 1 follow.')
    if page_id and not one('SELECT id FROM pages WHERE id=?',(page_id,)):
        raise ValueError('Không tìm thấy Fanpage được chọn.')
    day=start_date or datetime.now(VIETNAM_TZ).date().isoformat()
    try:
        start=datetime.strptime(day,'%Y-%m-%d').date()
    except ValueError as e:
        raise ValueError('Ngày bắt đầu không hợp lệ.') from e
    goal,basis=follower_target(previous_week_new_follows,goal_override)
    outline=_plan(product_name,parts,goal,basis,target_audience)
    sid='G'+uuid.uuid4().hex[:12].upper()
    stamp=now()
    with db() as c:
        old=c.execute('''SELECT id FROM growth_sprints WHERE COALESCE(page_id,'')=COALESCE(?,'')
                         AND lower(product_name)=lower(?) AND start_date=?''',(page_id,product_name,start.isoformat())).fetchone()
        if old:
            raise ValueError('Sản phẩm đã có chiến dịch bắt đầu cùng ngày cho Page này; hãy mở chiến dịch hiện có.')
        c.execute('''INSERT INTO growth_sprints(id,page_id,product_name,ingredients,target_audience,
               baseline_followers,previous_week_new_follows,target_new_follows,goal_basis,start_date,end_date,
               outline_json,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
               (sid,page_id,product_name,', '.join(parts),target_audience,baseline_followers,
                previous_week_new_follows,goal,basis,start.isoformat(),(start+timedelta(days=6)).isoformat(),
                json.dumps(outline,ensure_ascii=False),stamp,stamp))
    # Queue work explicitly; the existing AI task worker performs each role's real inference.
    from .ai import create_task
    context=f'Sprint {sid}. Sản phẩm: {product_name}. Thành phần do chủ sở hữu cung cấp: {", ".join(parts)}. '
    context+='Chưa được xác minh công dụng hoặc tuyên bố điều trị. Không tự nhận đã truy cập Facebook. '
    specs=[
        ('research','Nghiên cứu khách hàng và nguồn','Tìm chân dung khách hàng, câu hỏi thường gặp, khoảng trống kiến thức và nguồn hợp lệ. Phân biệt giả thuyết với dữ kiện.'),
        ('strategy','Định vị Fanpage và kế hoạch 7 ngày',f'Lập mục tiêu thử nghiệm +{goal} follow/7 ngày (cơ sở: {basis}); định vị nội dung, khung đăng và thử nghiệm A/B.'),
        ('creative','Storyboard và brief 7 nội dung','Lập hướng dẫn quay dựng 7 kịch bản nguyên bản, không bịa chứng nhận hoặc lời chứng thực.'),
        ('publishing','Lịch đăng có kiểm soát','Lên lịch chuẩn bị bài và đưa ra checklist đăng thủ công trên Firefox; không tự đăng hoặc spam.'),
        ('customer','Kế hoạch tương tác cộng đồng','Lập bộ hỏi đáp trung lập, phản hồi bình luận thật, hướng dẫn xử lý khiếu nại; không tạo tương tác giả.'),
        ('analytics','Theo dõi KPI 7 ngày','Thiết kế nhật ký followers, views và tương tác từng ngày; đánh giá so với chỉ tiêu, không tạo số liệu.'),
        ('compliance','Kiểm soát tuyên bố và bản quyền','Kiểm tra thông tin sản phẩm, hạn chế tuyên bố sức khỏe, quyền media, chính sách cộng đồng.'),
    ]
    created=[]
    for agent,title,instructions in specs:
        created.append(create_task(agent, f'{title} · {product_name}', context+instructions,page_id,'ceo_growth_sprint',sid))
    for day in outline['seven_day_plan']:
        created.append(create_task('content',f'Kịch bản ngày {day["day"]}: {day["topic"]}',
                    context+'Hãy viết kịch bản nguyên bản theo khung có sẵn; có hook, 3 cảnh, CTA mềm. '
                    'Không tự bịa công dụng, số liệu, feedback khách hàng. Khung: '+json.dumps(day,ensure_ascii=False),
                    page_id,'ceo_growth_sprint',sid))
    log('ceo','growth_sprint',f'Đã lên chiến dịch {sid} cho {product_name}; mục tiêu +{goal} follow/7 ngày (giả định: {basis}); giao {len(created)} việc.')
    return get_sprint(sid)


def _progress_report(sprint:dict, progress:list[dict])->dict:
    baseline=sprint['baseline_followers']
    latest=progress[-1]['followers_total'] if progress else None
    net=None if baseline is None or latest is None else latest-baseline
    pct=None if net is None else round(max(0,net)*100/max(1,sprint['target_new_follows']),1)
    day=progress[-1]['day'] if progress else 0
    expected=math.ceil(sprint['target_new_follows']*day/7) if day else 0
    return {'baseline_followers':baseline,'last_followers_total':latest,'net_new_follows':net,
            'target_new_follows':sprint['target_new_follows'],'completion_pct':pct,'day':day,
            'pace_target':expected,'on_pace':(net>=expected if net is not None and day else None),
            'total_views':sum(row['views'] for row in progress),
            'total_interactions':sum(row['interactions'] for row in progress),
            'source':'manual_not_verified_by_meta'}


def get_sprint(sid:str)->dict|None:
    s=one('SELECT * FROM growth_sprints WHERE id=?',(sid,))
    if not s:return None
    progress=all_rows('SELECT day,followers_total,views,interactions,notes,source,recorded FROM growth_progress WHERE sprint_id=? ORDER BY day',(sid,))
    s['outline']=json.loads(s.pop('outline_json'))
    s['ai_plan']=json.loads(s.pop('ai_plan_json') or 'null')
    s['progress']=progress
    s['report']=_progress_report(s,progress)
    s['tasks']=all_rows('SELECT id,agent_id,title,status FROM tasks WHERE campaign_id=? ORDER BY created,id',(sid,))
    return s


def list_sprints(limit:int=30)->list[dict]:
    rows=all_rows('SELECT id FROM growth_sprints ORDER BY created DESC LIMIT ?',(limit,))
    return [get_sprint(r['id']) for r in rows]


def record_progress(sid:str, day:int, followers_total:int, views:int=0, interactions:int=0, notes:str='') -> dict:
    if not 1<=day<=7:raise ValueError('Ngày trong chiến dịch phải từ 1 đến 7.')
    for v in (followers_total,views,interactions):
        if v < 0:raise ValueError('KPI không được âm.')
    s=one('SELECT id FROM growth_sprints WHERE id=?',(sid,))
    if not s:raise ValueError('Không tìm thấy chiến dịch.')
    with db() as c:
        c.execute('''INSERT INTO growth_progress(sprint_id,day,followers_total,views,interactions,notes,recorded)
                 VALUES(?,?,?,?,?,?,?) ON CONFLICT(sprint_id,day) DO UPDATE SET
                 followers_total=excluded.followers_total,views=excluded.views,
                 interactions=excluded.interactions,notes=excluded.notes,recorded=excluded.recorded''',
                 (sid,day,followers_total,views,interactions,notes[:1000],now()))
    log('analytics','growth_progress',f'Đã nhập KPI ngày {day} cho sprint {sid} (do người dùng nhập; chưa xác minh Meta).')
    sprint=get_sprint(sid)
    report=sprint['report']
    # Midweek/endweek checkpoints. Only one checkpoint review per day,
    # even if the owner edits the manually entered metric multiple times.
    if day in (3,5,7) and report['on_pace'] is False:
        from .ai import create_task
        existing=one("SELECT id FROM tasks WHERE campaign_id=? AND source=?",
                     (sid, 'growth_checkpoint_'+str(day)))
        if not existing:
            note=(f'Chiến dịch {sid}, ngày {day}, mục tiêu +{report["target_new_follows"]} follow/tuần. '
                  f'Follow mới báo cáo +{report["net_new_follows"]}, tiến độ dự kiến +{report["pace_target"]}. '
                  f'Lượt xem ngày báo cáo {views}, tương tác {interactions}. '
                  'Đây là dữ liệu do chủ sở hữu nhập, không xác minh với Meta. '
                  'Đề xuất 2 giả thuyết và 1 thay đổi thử nghiệm có kiểm duyệt; không cam kết đạt KPI, không mua follow.')
            create_task('analytics',f'Báo cáo tiến độ ngày {day}: {sprint["product_name"]}',
                        note,sprint['page_id'],'growth_checkpoint_'+str(day),sid)
            log('ceo','growth_checkpoint',f'Ngày {day} chưa theo kịp mục tiêu thử nghiệm; đã giao Analytics đánh giá lại.')
    return get_sprint(sid)


def attach_page(sid: str, page_id: str) -> dict:
    # Bind before staff have started work to prevent mixing Page contexts.
    if not one('SELECT id FROM pages WHERE id=?',(page_id,)):
        raise ValueError('Fanpage chưa tồn tại; hãy thêm hồ sơ và xác nhận quyền quản lý trước.')
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        sprint=c.execute('SELECT page_id FROM growth_sprints WHERE id=?',(sid,)).fetchone()
        if not sprint:raise ValueError('Không tìm thấy chiến dịch.')
        if sprint['page_id'] and sprint['page_id'] != page_id:
            raise ValueError('Chiến dịch đã liên kết với một Fanpage khác.')
        running=c.execute("SELECT count(*) FROM tasks WHERE campaign_id=? AND status!='queued'",(sid,)).fetchone()[0]
        if running and sprint['page_id']!=page_id:
            raise ValueError('Đã có nhiệm vụ bắt đầu; không được đổi Page trong lúc đang xử lý.')
        c.execute('UPDATE growth_sprints SET page_id=?,updated=? WHERE id=?',(page_id,now(),sid))
        c.execute('UPDATE tasks SET page_id=? WHERE campaign_id=? AND status="queued"',(page_id,sid))
    log('strategy','growth_page',f'Liên kết chiến dịch {sid} tới Page {page_id}; quyền Facebook cần xác nhận thủ công.')
    return get_sprint(sid)


def set_baseline(sid:str, value:int)->dict:
    if value<0:raise ValueError('Followers không được âm.')
    with db() as c:
        s=c.execute('SELECT * FROM growth_sprints WHERE id=?',(sid,)).fetchone()
        if not s:raise ValueError('Không tìm thấy chiến dịch.')
        if c.execute('SELECT COUNT(*) FROM growth_progress WHERE sprint_id=?',(sid,)).fetchone()[0]:
            raise ValueError('Không thay mốc followers sau khi đã nhập KPI; cần hiệu chỉnh dữ liệu bằng quy trình có nhật ký.')
        c.execute('UPDATE growth_sprints SET baseline_followers=?,updated=? WHERE id=?',(value,now(),sid))
    return get_sprint(sid)


def generate_ceo_plan(sid:str, *, infer=None)->dict:
    """Single bounded Claude CEO request, asynchronous from HTTP route when used live.

    Guard against concurrent generations, malformed replies, and AI changes
    to the human/method-derived follower goal. Never publish a generated post.
    """
    from .ai import get_key, ModelError, parse_json_reply
    from .brains import ask_claude, brain_system
    if not get_key('claude') and infer is None:
        raise ValueError('Cần cấu hình Claude API Key để CEO biên soạn kế hoạch AI.')
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        r=c.execute('SELECT * FROM growth_sprints WHERE id=?',(sid,)).fetchone()
        if not r:raise ValueError('Không tìm thấy chiến dịch.')
        if r['status']=='generating':return {'status':'already_running','id':sid}
        c.execute('UPDATE growth_sprints SET status=?,ai_error=?,updated=? WHERE id=?',('generating','',now(),sid))
    sprint=get_sprint(sid)
    prompt=json.dumps({
        'product_name':sprint['product_name'], 'ingredients_provided_not_verified':sprint['ingredients'],
        'audience':sprint['target_audience'], 'page_id':sprint['page_id'],
        'weekly_goal_new_follows':sprint['target_new_follows'], 'goal_basis':sprint['goal_basis'],
        'template':sprint['outline']['seven_day_plan'],
    },ensure_ascii=False)
    system=brain_system('ceo')+'''Bạn là CEO marketing lên kế hoạch xây dựng một Fanpage thuộc sở hữu công ty.
    Chỉ dựa trên dữ liệu sản phẩm đã nhập, không tự xem Facebook hoặc bịa chỉ số. Không cam kết tăng view/follow, không sử dụng bot/fake engagement.
    Meta ưu tiên nội dung nguyên bản; mỗi ngày tạo một góc tiếp cận khác nhau. Với thành phần sản phẩm, không tự suy diễn tác dụng trị bệnh, bổ thận, chữa mất ngủ, tăng sinh lý...
    Trả về JSON THUẦN có cấu trúc:
    {"positioning":"...", "audience_hypothesis":"...", "weekly_experiments":["...","..."],
    "seven_day_plan":[{"day":1,"topic":"...","hook":"...","scenes":["cảnh 1","cảnh 2","cảnh 3"],"cta":"...","format":"reel"}]}
    seven_day_plan phải có 7 phần tử ngày 1..7, mỗi phần tử có hook mạnh nhưng trung thực, 3 cảnh cụ thể, CTA mời follow tự nhiên. 
    Không sửa chỉ tiêu số lượng followers; đây là mục tiêu thử nghiệm, không phải dự báo.''' 
    try:
        raw=(infer or ask_claude)('ceo',system,prompt,purpose='growth_sprint',hard=True,max_tokens=1600)
        parsed=parse_json_reply(raw)
        if not isinstance(parsed,dict) or not isinstance(parsed.get('seven_day_plan'),list) or len(parsed['seven_day_plan'])!=7:
            raise ValueError('Claude chưa trả đủ 7 kịch bản hợp lệ.')
        days=[]
        for i,d in enumerate(parsed['seven_day_plan'],1):
            if not isinstance(d,dict) or not isinstance(d.get('scenes'),list) or len(d['scenes'])!=3:
                raise ValueError('Cấu trúc 7 kịch bản chưa hợp lệ.')
            if d.get('day')!=i:raise ValueError('Thứ tự ngày trong kế hoạch AI không hợp lệ.')
            days.append({'day':i,'topic':str(d.get('topic',''))[:150], 'hook':str(d.get('hook',''))[:500],
                'scenes':[str(x)[:650] for x in d['scenes']], 'cta':str(d.get('cta',''))[:350],
                'format':str(d.get('format','reel'))[:25], 'review_required':True})
        plan={'positioning':str(parsed.get('positioning',''))[:1000],
              'audience_hypothesis':str(parsed.get('audience_hypothesis',''))[:1000],
              'weekly_experiments':[str(x)[:300] for x in parsed.get('weekly_experiments',[]) if isinstance(x,str)][:5],
              'seven_day_plan':days, 'review_required':True, 'status':'ai_draft_not_reviewed'}
        with db() as c:
            c.execute('UPDATE growth_sprints SET ai_plan_json=?,status=?,updated=? WHERE id=?',
                      (json.dumps(plan,ensure_ascii=False),'ready',now(),sid))
        log('ceo','growth_plan',f'Claude tạo 7 kịch bản nháp cho {sid}; bắt buộc kiểm duyệt trước khi đăng.')
        return {'status':'ready','id':sid}
    except Exception as exc:
        # No automatic repeated Claude call; retain the free local outline.
        with db() as c:
            c.execute('UPDATE growth_sprints SET status=?,ai_error=?,updated=? WHERE id=?',
                      ('needs_review',str(exc)[:350],now(),sid))
        log('ceo','growth_ai_error',f'Không thể tạo kế hoạch AI cho {sid}: {type(exc).__name__}.')
        return {'status':'needs_review','id':sid,'error':str(exc)[:350]}
