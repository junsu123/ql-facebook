@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title AI Fanpage Company - Khoi dong
set "PYEXE="

if exist ".venv\Scripts\python.exe" goto existing_venv
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import sys; exit(sys.version_info < (3,11))" >nul 2>nul
    if not errorlevel 1 set "PYEXE=py -3"
)
if not defined PYEXE (
    where python >nul 2>nul
    if not errorlevel 1 (
        python -c "import sys; exit(sys.version_info < (3,11))" >nul 2>nul
        if not errorlevel 1 set "PYEXE=python"
    )
)
if not defined PYEXE goto missing_python

echo [1/3] Tao moi truong Python rieng...
%PYEXE% -m venv .venv
if errorlevel 1 goto venv_failed
:existing_venv
if not exist ".venv\Scripts\python.exe" goto venv_failed
".venv\Scripts\python.exe" -c "import sys;exit(sys.version_info < (3,11))" >nul 2>nul
if errorlevel 1 goto venv_failed

echo [2/3] Kiem tra va cai thu vien can thiet...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto pip_failed

echo [3/3] Mo AI Fanpage Company...
".venv\Scripts\python.exe" scripts\launcher.py
if errorlevel 1 goto server_failed
echo Da dong phan mem.
goto end

:missing_python
echo [LOI] Khong tim thay Python 3.11+.
echo Cai tu https://www.python.org/downloads/windows/ va chon Add Python to PATH.
goto error
:venv_failed
echo [LOI] Khong tao/mo duoc moi truong .venv.
echo Kiem tra Python, quyen ghi thu muc; KHONG xoa thu muc data hoac profiles.
goto error
:pip_failed
echo [LOI] Cai thu vien that bai. Kiem tra mang internet, proxy, antivirus.
echo Chay: ".venv\Scripts\python.exe" scripts\diagnose.py
goto error
:server_failed
echo [LOI] Backend khong khoi dong duoc.
echo Chay: ".venv\Scripts\python.exe" scripts\diagnose.py
echo Gui anh man hinh loi hoac file diagnostics.txt de duoc ho tro.
goto error
:error
pause
exit /b 1
:end
pause
exit /b 0
