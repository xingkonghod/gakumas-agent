@echo off
cd /d D:\Games\gakumas-agent
set PYTHONPATH=D:\Games\gakumas-agent\src
taskkill /F /PID 11364 >nul 2>&1
"D:\Games\MaaGakumasu\python\python.exe" "D:\Games\gakumas-agent\scripts\click_game.py" 360 1000 > "D:\Games\gakumas-agent\data\card1_out.txt" 2>&1
"D:\Games\MaaGakumasu\python\python.exe" "D:\Games\gakumas-agent\scripts\click_game.py" 360 1000 > "D:\Games\gakumas-agent\data\card2_out.txt" 2>&1
