@echo off
cd /d D:\Games\gakumas-agent
set PYTHONPATH=D:\Games\gakumas-agent\src
"D:\Games\MaaGakumasu\python\python.exe" "D:\Games\gakumas-agent\scripts\click_game.py" 360 1090 > "D:\Games\gakumas-agent\data\cl1.txt" 2>&1
"D:\Games\MaaGakumasu\python\python.exe" "D:\Games\gakumas-agent\scripts\click_game.py" 360 1090 > "D:\Games\gakumas-agent\data\cl2.txt" 2>&1
