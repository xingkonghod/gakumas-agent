@echo off
cd /d D:\Games\gakumas-agent
set PYTHONPATH=D:\Games\gakumas-agent\src
"D:\Games\MaaGakumasu\python\python.exe" "D:\Games\gakumas-agent\scripts\nav_click.py" %* > "D:\Games\gakumas-agent\data\nav_out.txt" 2>&1
