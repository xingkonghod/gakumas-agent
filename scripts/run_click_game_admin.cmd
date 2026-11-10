@echo off
cd /d D:\Games\gakumas-agent
set PYTHONPATH=D:\Games\gakumas-agent\src
"D:\Games\MaaGakumasu\python\python.exe" "D:\Games\gakumas-agent\scripts\click_game.py" %* > "D:\Games\gakumas-agent\data\click_game_out.txt" 2>&1
