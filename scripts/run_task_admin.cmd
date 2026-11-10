@echo off
cd /d D:\Games\gakumas-agent
set PYTHONPATH=D:\Games\gakumas-agent\src
"D:\Games\MaaGakumasu\python\python.exe" "D:\Games\gakumas-agent\run.py" %* > "D:\Games\gakumas-agent\data\admin_out.txt" 2>&1
