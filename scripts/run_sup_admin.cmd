@echo off
cd /d D:\Games\gakumas-agent
set PYTHONPATH=D:\Games\gakumas-agent\src
"D:\Games\MaaGakumasu\python\python.exe" "D:\Games\gakumas-agent\scripts\support_next.py" > "D:\Games\gakumas-agent\data\sup_out.txt" 2>&1
