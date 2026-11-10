@echo off
cd /d D:\Games\gakumas-agent
set PYTHONPATH=D:\Games\gakumas-agent\src
"D:\Games\MaaGakumasu\python\python.exe" "D:\Games\gakumas-agent\scripts\hide_click.py" %* > "D:\Games\gakumas-agent\data\hide_click_out.txt" 2>&1
