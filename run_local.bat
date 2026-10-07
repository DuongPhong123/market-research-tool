@echo off
chcp 65001 >nul
title Market Research Tool

REM === Di chuyen ve thu muc chua bat file (fix cd path) ===
cd /d "%~dp0"

echo.
echo  ========================================
echo   Market Research Tool - Khoi dong local
echo   Shopee / Facebook / Instagram
echo  ========================================
echo.

REM === Kiem tra Python ===
python --version >nul 2>&1
if errorlevel 1 (
    echo [LOI] Chua cai Python!
    echo Tai Python 3.11+ tai: https://www.python.org/downloads/
    echo Nho tick "Add Python to PATH" khi cai dat
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Python %PYVER% da san sang

REM === Tao file .env neu chua co ===
if not exist .env (
    echo.
    echo [INFO] Chua co file .env - dang tao tu .env.example...
    copy .env.example .env >nul
    echo [INFO] Mo file .env de dien API keys...
    echo.
    echo  Huong dan lay API keys:
    echo  - Shopee Affiliate: https://affiliate.shopee.vn/open-api/manage
    echo  - Facebook Token:   https://developers.facebook.com/tools/explorer/
    echo.
    notepad .env
    echo Nhan phim bat ky sau khi da dien xong API keys...
    pause >nul
)

REM === Tao thu muc data ===
if not exist data mkdir data

REM === Cai dat thu vien Python ===
echo.
echo [INFO] Dang kiem tra va cai dat thu vien Python...
cd /d "%~dp0backend"
if errorlevel 1 (
    echo [LOI] Khong tim thay thu muc backend!
    echo Kiem tra: da clone du toan bo repo chua? Thu muc backend\ co ton tai khong?
    pause
    exit /b 1
)
python -m pip install -r requirements.txt -q --disable-pip-version-check
if errorlevel 1 (
    echo [LOI] Cai dat thu vien that bai!
    echo Thu chay lai voi quyen Admin: click chuot phai run_local.bat - Run as administrator
    pause
    exit /b 1
)
echo [OK] Thu vien da san sang

REM === Cai Playwright (lan dau) ===
python -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); p.stop()" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Dang cai Chromium cho Playwright (lan dau, co the mat 1-2 phut)...
    python -m playwright install chromium --quiet
)
echo [OK] Playwright san sang

REM === Kiem tra port 8000 ===
netstat -ano | findstr ":8000 " >nul 2>&1
if not errorlevel 1 (
    echo.
    echo [CANH BAO] Port 8000 dang bi chiem dung!
    echo Co the tool dang chay roi. Mo trinh duyet: http://localhost:8000
    start "" "http://localhost:8000"
    pause
    exit /b 0
)

REM === Khoi dong server ===
echo.
echo  ========================================
echo   Server dang khoi dong...
echo   Trinh duyet se tu dong mo sau 3 giay
echo   Nhan Ctrl+C de dung server
echo  ========================================
echo.

REM Mo trinh duyet sau 3 giay
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:8000"

REM Chay FastAPI
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

echo.
echo Server da dung.
pause
