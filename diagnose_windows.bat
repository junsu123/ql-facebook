@echo off
setlocal
cd /d "%~dp0"
title AI Fanpage Company - Kiem tra loi
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\diagnose.py
) else (
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3 scripts\diagnose.py
  ) else (
    python scripts\diagnose.py
  )
)
echo.
echo Neu co file diagnostics.txt, ban co the gui noi dung de xac dinh loi.
echo Khong gui mat khau, API key, cookie Facebook.
pause
