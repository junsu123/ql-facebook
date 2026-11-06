@echo off
setlocal
cd /d "%~dp0"
where git >nul 2>nul || (echo Git chua duoc cai. Cai Git for Windows truoc. & pause & exit /b 1)
echo === AI Fanpage Company - Push to GitHub ===
echo Tao repository PRIVATE trong GitHub truoc khi chay.
set /p REPO_URL=Nhap URL repository (https://github.com/USER/REPO.git): 
if "%REPO_URL%"=="" (echo Chua nhap URL. & pause & exit /b 1)
git remote get-url origin >nul 2>nul
if not errorlevel 1 (
    echo Origin da ton tai, hay kiem tra bang "git remote -v" de tranh day nham.
    pause
    exit /b 1
)
git remote add origin "%REPO_URL%"
if errorlevel 1 (echo Loi gan remote. & pause & exit /b 1)
git push -u origin main
if errorlevel 1 (echo Khong push duoc. Kiem tra URL, quyen va authentication. & pause & exit /b 1)
echo Push thanh cong!
pause
