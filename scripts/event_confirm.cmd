@echo off
cd /d D:\Games\gakumas-agent
set PYTHONPATH=D:\Games\gakumas-agent\src
"D:\Games\MaaGakumasu\python\python.exe" "D:\Games\gakumas-agent\scripts\click_game.py" 360 835 > "D:\Games\gakumas-agent\data\ev1_out.txt" 2>&1
"D:\Games\MaaGakumasu\python\python.exe" "D:\Games\gakumas-agent\scripts\click_game.py" 360 1050 > "D:\Games\gakumas-agent\data\ev2_out.txt" 2>&1
