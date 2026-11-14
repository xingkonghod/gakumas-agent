@echo off
cd /d D:\Games\gakumas-agent
set PYTHONPATH=D:\Games\gakumas-agent\src
"D:\Games\MaaGakumasu\python\python.exe" "D:\Games\gakumas-agent\scripts\click_game.py" 360 900 > "D:\Games\gakumas-agent\data\claim1_out.txt" 2>&1
"D:\Games\MaaGakumasu\python\python.exe" "D:\Games\gakumas-agent\scripts\click_game.py" 360 1100 > "D:\Games\gakumas-agent\data\claim2_out.txt" 2>&1
