@echo off
chcp 65001 >nul
setlocal
title AI快速BI报表工具(开发版) - 一键启动
echo ============================================================
echo    AI快速BI报表工具（开发版·最新功能） 一键启动
echo    前端 http://localhost:5173
echo    后端 http://localhost:8000
echo ============================================================
echo.

set "ROOT=%~dp0"
cd /d "%ROOT%"

set "PYTHON=%~dp0vm\tools\python\python.exe"

:: ---------- 1. 释放端口 ----------
echo [1/4] 释放端口...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000 " ^| findstr LISTENING') do taskkill /PID %%p /F >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5173 " ^| findstr LISTENING') do taskkill /PID %%p /F >nul 2>&1

:: ---------- 2. 启动后端 ----------
echo [2/4] 启动后端服务(自动用SQLite，无需装数据库)...
pushd "%ROOT%backend"
start "AIBI-Backend" /min cmd /c "%PYTHON% -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > server.log 2>&1"
popd
set /a tries=0
:wait_backend
timeout /t 2 /nobreak >nul
set /a tries+=1
"%PYTHON%" -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/api/v1/health',timeout=2);print('OK')" >nul 2>&1
if %errorlevel%==0 goto backend_ok
if %tries% lss 15 goto wait_backend
echo      [警告] 后端健康检查超时，查看 backend\server.log
goto frontend
:backend_ok
echo      后端已就绪 http://localhost:8000 ✓

:: ---------- 3. 启动前端 ----------
:frontend
echo [3/4] 启动前端服务...
pushd "%ROOT%frontend"
start "AIBI-Frontend" /min cmd /c "npm run dev > vite.log 2>&1"
popd
set /a ftries=0
:wait_frontend
timeout /t 2 /nobreak >nul
set /a ftries+=1
for /f "delims=" %%a in ('powershell -Command "try{(Invoke-WebRequest -Uri 'http://localhost:5173/' -UseBasicParsing -TimeoutSec 2).StatusCode}catch{'0'}" 2^>nul') do set code=%%a
if "%code%"=="200" goto frontend_ok
if %ftries% lss 15 goto wait_frontend
echo      [警告] 前端未就绪，查看 frontend\vite.log
:frontend_ok
echo      前端已就绪 http://localhost:5173 ✓

:: ---------- 4. 打开浏览器 ----------
echo [4/4] 打开浏览器...
start http://localhost:5173/

echo.
echo 启动完成！浏览器已打开最新开发版界面。
echo   - 后端日志 backend\server.log  前端日志 frontend\vite.log
echo   - 关闭本窗口不停止服务；停止需关闭"Backend/Frontend"两个新窗口
echo.
pause