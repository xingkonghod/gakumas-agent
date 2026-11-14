@echo off
cd /d D:\Games\gakumas-agent
set PYTHONPATH=D:\Games\gakumas-agent\src
"D:\Games\MaaGakumasu\python\python.exe" "%TEMP%\ok2.py" > "D:\Games\gakumas-agent\data\ok2_out.txt" 2>&1
