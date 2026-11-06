"""Persistent native Firefox profiles, manual login and safe lifecycle.
No Facebook scraping, UI login detection, CAPTCHA bypass, or automated posting.
"""
from __future__ import annotations
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from datetime import datetime
import psutil
from .db import PROFILE_DIR, all_rows, db, log, now, one, run

class BrowserError(Exception): pass


def executable() -> str | None:
    from .db import one as fetch
    setting = fetch("SELECT value FROM settings WHERE key='firefox_path'")
    custom = (setting or {}).get('value','').strip()
    candidates=[custom]
    if os.name=='nt':
        for p in (os.getenv('PROGRAMFILES',''), os.getenv('PROGRAMFILES(X86)','')):
            if p:candidates.append(str(Path(p)/'Mozilla Firefox'/'firefox.exe'))
    candidates.extend([shutil.which('firefox'),shutil.which('firefox.exe')])
    return next((str(Path(p)) for p in candidates if p and Path(p).is_file()),None)


def _proc(row: dict):
    pid=row.get('pid')
    if not pid:return None
    try:
        proc=psutil.Process(int(pid))
        if row.get('process_created') and abs(proc.create_time()-float(row['process_created']))>2:return None
        args=' '.join(proc.cmdline()).lower().replace('\\','/')
        expected=row['profile_path'].lower().replace('\\','/')
        if expected not in args:return None
        if not proc.is_running() or proc.status()==psutil.STATUS_ZOMBIE:return None
        return proc
    except (psutil.Error, ValueError, TypeError):return None


def account_status(row: dict) -> dict:
    result = dict(row)
    proc=_proc(result)
    result['browser_open']=bool(proc)
    if result['status']=='open' and not proc:
        result['status']='closed'
    return result


def create_profile(label: str = '') -> dict:
    identifier='FB'+uuid.uuid4().hex[:8].upper()
    path=PROFILE_DIR/identifier/'firefox'
    path.mkdir(parents=True,exist_ok=False)
    run('INSERT INTO accounts(id,label,profile_path,status,created) VALUES(?,?,?,?,?)',
        (identifier,(label.strip() or f'Facebook {identifier}'),str(path),'created',now()))
    log('publishing','profile_created',f'Tạo profile Firefox {identifier}')
    return one('SELECT * FROM accounts WHERE id=?',(identifier,))


def open_profile(identifier: str, url='https://www.facebook.com/') -> dict:
    row=one('SELECT * FROM accounts WHERE id=?',(identifier,))
    if not row:raise BrowserError('Không tìm thấy profile')
    if _proc(row):return account_status(row)
    app=executable()
    if not app:
        raise BrowserError('Chưa tìm thấy Firefox trên máy chạy server. Cài Firefox hoặc cấu hình đường dẫn ở Cài đặt.')
    # URLs are fixed to Facebook or saved Page URLs validated by the API.
    if not url.startswith('https://www.facebook.com/'):
        raise BrowserError('Chỉ mở địa chỉ Facebook hợp lệ.')
    try:
        flags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0
        proc=subprocess.Popen([app,'--no-remote','--profile',row['profile_path'],url],
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            creationflags=flags)
        p=psutil.Process(proc.pid)
        run('UPDATE accounts SET status=?,pid=?,process_created=?,last_checked=? WHERE id=?',
            ('open',proc.pid,p.create_time(),now(),identifier))
        log('publishing','profile_open',f'Mở Firefox {identifier}')
    except OSError as e:
        raise BrowserError(f'Không mở được Firefox: {str(e)[:200]}') from e
    return account_status(one('SELECT * FROM accounts WHERE id=?',(identifier,)))


def close_profile(identifier: str) -> dict:
    row=one('SELECT * FROM accounts WHERE id=?',(identifier,))
    if not row:raise BrowserError('Không tìm thấy profile')
    proc=_proc(row)
    if proc:
        try:
            proc.terminate()
            proc.wait(timeout=8)
        except psutil.TimeoutExpired:
            raise BrowserError('Firefox chưa đóng. Hãy lưu công việc và tự đóng cửa sổ Firefox rồi thử lại.')
        except psutil.Error as e:
            raise BrowserError(f'Lỗi đóng Firefox: {str(e)[:180]}') from e
    run('UPDATE accounts SET status=?,pid=NULL,process_created=NULL WHERE id=?',('closed',identifier))
    log('publishing','profile_closed',f'Đóng Firefox {identifier}')
    return account_status(one('SELECT * FROM accounts WHERE id=?',(identifier,)))


def confirm_login(identifier: str, label: str) -> dict:
    if not label.strip():raise BrowserError('Hãy nhập tên tài khoản để xác nhận thủ công.')
    row=one('SELECT * FROM accounts WHERE id=?',(identifier,))
    if not row:raise BrowserError('Không tìm thấy profile')
    run('UPDATE accounts SET label=?,confirmed=1,last_checked=? WHERE id=?',(label.strip()[:100],now(),identifier))
    log('publishing','login_confirmed',f'Người dùng tự xác nhận đăng nhập của {identifier}; không xác minh qua Facebook API.')
    return account_status(one('SELECT * FROM accounts WHERE id=?',(identifier,)))


def delete_profile(identifier: str) -> None:
    row=one('SELECT * FROM accounts WHERE id=?',(identifier,))
    if not row:raise BrowserError('Không tìm thấy profile')
    if _proc(row):raise BrowserError('Cần đóng Firefox trước khi xóa profile')
    # Only delete app-managed path underneath the dedicated profiles root.
    folder=Path(row['profile_path']).resolve().parent
    if folder.parent != PROFILE_DIR.resolve() or folder.name != identifier:
        raise BrowserError('Đường dẫn profile không hợp lệ, từ chối xóa')
    shutil.rmtree(folder)
    run('DELETE FROM accounts WHERE id=?',(identifier,))
    log('publishing','profile_deleted',f'Xóa profile {identifier} theo yêu cầu người dùng')
