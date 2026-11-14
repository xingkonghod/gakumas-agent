@echo off
cd /d D:\Games\gakumas-agent
set PYTHONPATH=D:\Games\gakumas-agent\src
"D:\Games\MaaGakumasu\python\python.exe" "D:\Games\gakumas-agent\scripts\test_postmessage.py" > "D:\Games\gakumas-agent\data\pm_out.txt" 2>&1
