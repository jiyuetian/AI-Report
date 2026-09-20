@echo off
cd /d "%~dp0"
start "AIBI-Backend" /min cmd /c "C:\Users\Asus009\AppData\Local\Programs\Python\Python312\python.exe -u run_backend.py 1> C:\Users\Asus009\WorkBuddy\2026-09-04-21-35-26\aireport_backend.log 2>&1"
echo started
