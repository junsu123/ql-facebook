"""Offline startup diagnostics. Does not read or print API keys, profiles or cookies."""
from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import socket
import sys
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def diagnostic_text() -> str:
    info = [
        'AI FANPAGE COMPANY — KIEM TRA KHOI DONG',
        'Thoi gian: ' + datetime.now().isoformat(timespec='seconds'),
        'He dieu hanh: ' + platform.platform(),
        'Python: ' + sys.version.split()[0],
        'Python duong dan: ' + sys.executable,
        'Project: ' + str(ROOT),
        'Launcher py: ' + str(bool(shutil.which('py'))),
    ]
    modules = {'fastapi':'fastapi','uvicorn':'uvicorn','httpx':'httpx',
               'cryptography':'cryptography','psutil':'psutil','PIL':'Pillow',
               'multipart':'python-multipart'}
    for mod, pkg in modules.items():
        info.append(f'Thu vien {pkg}: ' + ('OK' if importlib.util.find_spec(mod) else 'THIEU'))
    for port in (8765,8766,8767):
        sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        try:
            sock.settimeout(0.5)
            info.append(f'Cong {port}: ' + ('DANG SU DUNG' if sock.connect_ex(('127.0.0.1',port))==0 else 'TRONG'))
        finally:
            sock.close()
    local=os.environ.get('AIFC_DATA_DIR') or (str(Path(os.environ['LOCALAPPDATA'])/'AI-Fanpage-Company') if os.environ.get('LOCALAPPDATA') else str(ROOT/'data'))
    data=Path(local)
    info.append('Du lieu cuc bo: ' + str(data))
    try:
        data.mkdir(parents=True, exist_ok=True)
        probe=data/'.write_test'
        probe.write_text('ok',encoding='utf-8')
        probe.unlink()
        info.append('Quyen ghi du lieu: OK')
    except Exception as exc:
        info.append('Quyen ghi du lieu: LOI - '+type(exc).__name__)
    log=data/'logs'/'startup.log'
    if log.exists():
        # Startup log only, not raw settings, cookies, keys, prompts.
        lines=log.read_text(encoding='utf-8',errors='replace').splitlines()
        info.append('\n--- NHAT KY KHOI DONG (30 DONG CUOI) ---')
        info.extend(lines[-30:])
    else:
        info.append('Chua co startup.log')
    info.append('\nNeu van bi loi, hay chup anh thong bao loi hoac gui noi dung bao cao nay. Khong gui API key hay cookie.')
    return '\n'.join(info)


def main() -> int:
    report=diagnostic_text()
    print(report)
    try:
        target=ROOT/'diagnostics.txt'
        target.write_text(report,encoding='utf-8')
        print('\nDa luu:',target)
    except OSError:
        print('Khong the luu diagnostics.txt trong thu muc du an.')
    return 0


if __name__=='__main__':
    sys.exit(main())
