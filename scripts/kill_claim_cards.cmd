@echo off
cd /d D:\Games\gakumas-agent
set PYTHONPATH=D:\Games\gakumas-agent\src
taskkill /F /PID 4520 >nul 2>&1
"D:\Games\MaaGakumasu\python\python.exe" "D:\Games\gakumas-agent\scripts\click_game.py" 200 900 > "D:\Games\gakumas-agent\data\rc1.txt" 2>&1
"D:\Games\MaaGakumasu\python\python.exe" "D:\Games\gakumas-agent\scripts\click_game.py" 360 1100 > "D:\Games\gakumas-agent\data\rc2.txt" 2>&1
"D:\Games\MaaGakumasu\python\python.exe" "D:\Games\gakumas-agent\scripts\click_game.py" 360 1100 > "D:\Games\gakumas-agent\data\rc3.txt" 2>&1
