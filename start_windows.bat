@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Tao Python virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 (
    echo Khong tao duoc venv. Cai Python 3.11+ va thu lai.
    pause
    exit /b 1
  )
)
echo [2/3] Cai dat thu vien...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (echo Loi cai dat thu vien. & pause & exit /b 1)
echo [3/3] Khoi dong AI Fanpage Company...
".venv\Scripts\python.exe" scripts\launcher.py
pause
