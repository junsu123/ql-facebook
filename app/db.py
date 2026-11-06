"""SQLite storage; every operation uses a short-lived connection with WAL enabled."""
from __future__ import annotations
import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone

BASE = Path(os.getenv('AIFC_DATA_DIR') or (Path(os.getenv('LOCALAPPDATA')) / 'AI-Fanpage-Company' if os.getenv('LOCALAPPDATA') else Path(__file__).resolve().parent.parent / 'data')).resolve()
BASE.mkdir(parents=True, exist_ok=True)
DB_PATH = BASE / 'company.sqlite3'
PROFILE_DIR = BASE / 'profiles'
MEDIA_DIR = BASE / 'media'
PROFILE_DIR.mkdir(exist_ok=True)
MEDIA_DIR.mkdir(exist_ok=True)

def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

@contextmanager
def db():
    con = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    con.execute('PRAGMA busy_timeout=30000')
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

def all_rows(sql: str, params: tuple = ()) -> list[dict]:
    with db() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]

def one(sql: str, params: tuple = ()) -> dict | None:
    with db() as c:
        r = c.execute(sql, params).fetchone()
        return dict(r) if r else None

def run(sql: str, params: tuple = ()) -> int:
    with db() as c:
        cursor = c.execute(sql, params)
        return cursor.lastrowid

AGENTS = [
    ('ceo', 'AI CEO', 'Tổng giám đốc', 'Điều phối, phân công, kiểm soát ngân sách', '👨🏻‍💼'),
    ('research', 'AI Nghiên cứu', 'Phòng nghiên cứu', 'Nghiên cứu chủ đề và nhu cầu khách hàng', '🔎'),
    ('strategy', 'AI Chiến lược', 'Phòng chiến lược', 'Xây dựng lịch và định vị từng Page', '🎯'),
    ('content', 'AI Content', 'Phòng nội dung', 'Soạn nội dung nguyên bản cho Fanpage', '✍️'),
    ('creative', 'AI Sáng tạo', 'Phòng thiết kế', 'Brief hình ảnh/video và kiểm tra tài sản', '🎨'),
    ('publishing', 'AI Xuất bản', 'Phòng vận hành', 'Lịch và công việc xuất bản', '📅'),
    ('customer', 'AI CSKH', 'Phòng khách hàng', 'Đề xuất phản hồi lịch sự, đúng thông tin', '💬'),
    ('analytics', 'AI Phân tích', 'Phòng phân tích', 'Đọc KPI được nhập và rút kinh nghiệm', '📊'),
    ('compliance', 'AI Kiểm duyệt', 'Phòng kiểm duyệt', 'Đối chiếu quy tắc và rủi ro nội dung', '🛡️')
]

SCHEMA = '''
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ai_calls(id INTEGER PRIMARY KEY AUTOINCREMENT,provider TEXT,model TEXT,request_type TEXT,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agents(id TEXT PRIMARY KEY, name TEXT NOT NULL, title TEXT, description TEXT, emoji TEXT);
CREATE TABLE IF NOT EXISTS accounts(
 id TEXT PRIMARY KEY, label TEXT NOT NULL, profile_path TEXT NOT NULL UNIQUE,
 status TEXT NOT NULL DEFAULT 'created', confirmed INTEGER NOT NULL DEFAULT 0,
 last_checked TEXT, pid INTEGER, process_created REAL, created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pages(
 id TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL UNIQUE,
 category TEXT NOT NULL DEFAULT '', tone TEXT NOT NULL DEFAULT '',
 facts TEXT NOT NULL DEFAULT '', account_id TEXT REFERENCES accounts(id) ON DELETE SET NULL,
 created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks(
 id TEXT PRIMARY KEY, agent_id TEXT NOT NULL REFERENCES agents(id), title TEXT NOT NULL,
 instructions TEXT NOT NULL DEFAULT '', page_id TEXT REFERENCES pages(id) ON DELETE SET NULL,
 status TEXT NOT NULL DEFAULT 'queued', result TEXT NOT NULL DEFAULT '',
 source TEXT NOT NULL DEFAULT 'user', campaign_id TEXT, error TEXT NOT NULL DEFAULT '', created TEXT NOT NULL, updated TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS campaigns(
 id TEXT PRIMARY KEY, topic TEXT NOT NULL, category TEXT, planned_pages INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'queued', created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chats(
 id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT NOT NULL, body TEXT NOT NULL, created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS activity(
 id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id TEXT, kind TEXT NOT NULL,
 message TEXT NOT NULL, task_id TEXT, created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS contents(
 id TEXT PRIMARY KEY, page_id TEXT NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
 topic TEXT NOT NULL, body TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft',
 review_details TEXT NOT NULL DEFAULT '', media_path TEXT,
 scheduled_at TEXT, publish_url TEXT, published_at TEXT,
 created TEXT NOT NULL, updated TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memories(
 id INTEGER PRIMARY KEY AUTOINCREMENT, page_id TEXT NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
 note TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'manual', created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS metrics(
 id INTEGER PRIMARY KEY AUTOINCREMENT, page_id TEXT NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
 date TEXT NOT NULL, views INTEGER NOT NULL DEFAULT 0, likes INTEGER NOT NULL DEFAULT 0,
 comments INTEGER NOT NULL DEFAULT 0, shares INTEGER NOT NULL DEFAULT 0,
 source TEXT NOT NULL DEFAULT 'manual', UNIQUE(page_id, date, source)
);
CREATE INDEX IF NOT EXISTS ix_tasks_status ON tasks(status, created);
CREATE INDEX IF NOT EXISTS ix_contents_status ON contents(status, scheduled_at);
CREATE INDEX IF NOT EXISTS ix_activities_created ON activity(created);
'''

def initialize():
    with db() as c:
        c.executescript(SCHEMA)
        c.executemany('INSERT OR IGNORE INTO agents(id,name,title,description,emoji) VALUES(?,?,?,?,?)', AGENTS)
        c.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)', ('provider','claude'))
        c.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)', ('daily_llm_call_limit','200'))
        c.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)', ('auto_run_agents','0'))
        c.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)', ('firefox_path',''))
    # Keep migrations idempotent for existing local databases.
    from .brains import init_brains
    init_brains()

def log(agent: str, kind: str, message: str, task_id: str | None = None):
    run('INSERT INTO activity(agent_id,kind,message,task_id,created) VALUES(?,?,?,?,?)',
        (agent,kind,message[:2000],task_id,now()))
