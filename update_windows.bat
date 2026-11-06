@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title AI Fanpage Company - Cap nhat an toan
where git >nul 2>nul
if errorlevel 1 (
    echo [LOI] Chua cai Git. Tai Git for Windows tai https://git-scm.com/downloads/win
    pause
    exit /b 1
)
git rev-parse --is-inside-work-tree >nul 2>nul
if errorlevel 1 (
    echo [LOI] Thu muc nay khong phai ban git clone. Hay cap nhat bang Git clone truoc.
    pause
    exit /b 1
)
echo [1/2] Tai ban cap nhat tu nhanh main (chi fast-forward, khong ghi de sua doi cuc bo)...
git pull --ff-only origin main
if errorlevel 1 (
    echo [LOI] Cap nhat that bai; code hien tai duoc giu nguyen neu Git chua thay doi tep.
    echo Kiem tra git status va git remote -v. Khong su dung git reset --hard.
    pause
    exit /b 1
)
echo [2/2] Da cap nhat. Neu AI Fanpage Company dang chay qua start_windows.bat,
echo tien trinh giam sat se tu khoi dong lai backend khi cong viec AI dang chay hoan tat.
echo Dang mo giao dien. Neu chua chay, bat dau phan mem...
start "AI Fanpage Company" "%~dp0start_windows.bat"
echo Da gui lenh mo/cap nhat. Ban co the dong cua so nay.
exit /b 0
