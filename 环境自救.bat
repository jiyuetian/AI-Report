@echo off
chcp 65001 >nul
setlocal
title AI快速BI报表工具 - 环境自救
echo ============================================================
echo   AI快速BI报表工具 - 环境自救脚本
echo   用于：启动异常 / Toolhost环境锁 / 端口占用 / 前后端起不来
echo ============================================================
echo.

:: 确认操作
set /p cfm=本脚本将结束所有残留的 python/node 进程并重启服务，是否继续？(Y/N) 
if /i not "%cfm%"=="Y" (echo 已取消 & pause & exit /b)

:: ---------- 1. 清理残留进程 ----------
echo.
echo [1/3] 结束残留 python/node 进程...
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM node.exe >nul 2>&1
timeout /t 2 /nobreak >nul
echo     已清理。

:: ---------- 2. 清理临时 job 状态 ----------
echo [2/3] 清理临时作业状态目录...
if exist "%USERPROFILE%\AppData\Local\Temp\trae-agent-toolhost\jobs" (
    takeown /F "%USERPROFILE%\AppData\Local\Temp\trae-agent-toolhost\jobs" /R /A >nul 2>&1
    rmdir /S /Q "%USERPROFILE%\AppData\Local\Temp\trae-agent-toolhost\jobs" >nul 2>&1
    echo     已清理 trae-agent-toolhost\jobs。
) else (
    echo     无该目录，跳过。
)

:: ---------- 3. 引导启动 ----------
echo [3/3] 环境已清理，接下来请双击「一键启动.bat」重新启动服务。
echo       若仍被锁死，请彻底重启 TRAE 客户端（完全退出再打开）。
echo.
echo 完成。按任意键打开「一键启动.bat」所在目录...
pause >nul
start "" explorer "%~dp0"
endlocal