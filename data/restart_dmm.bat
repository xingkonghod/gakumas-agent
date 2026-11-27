@echo off
taskkill /F /IM DMMGamePlayer.exe >nul 2>&1
timeout /t 2 >nul
start "" "D:\DMM\GamePlayer\DMMGamePlayer.exe"
exit /b 0
