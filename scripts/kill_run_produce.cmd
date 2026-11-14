@echo off
cd /d D:\Games\gakumas-agent
set PYTHONPATH=D:\Games\gakumas-agent\src
taskkill /F /PID 30008 >nul 2>&1
"D:\Games\MaaGakumasu\python\python.exe" "D:\Games\gakumas-agent\run.py" task produce --resume > "D:\Games\gakumas-agent\data\admin_out.txt" 2>&1
