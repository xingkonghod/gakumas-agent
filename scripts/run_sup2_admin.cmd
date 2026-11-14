@echo off
cd /d D:\Games\gakumas-agent
set PYTHONPATH=D:\Games\gakumas-agent\src
"D:\Games\MaaGakumasu\python\python.exe" "D:\Games\gakumas-agent\scripts\support_confirm.py" > "D:\Games\gakumas-agent\data\sup2_out.txt" 2>&1
