@echo off
rem T1 起跑器：由 elevated GDEAgent daemon 调起，Start-Process 脱离父进程
rem 用法: _launch_ep.cmd <episode>
setlocal
set ROOT=D:\Games\gakumas-agent
set EP=%~1
if "%EP%"=="" set EP=ep-t1-a
del /q "%ROOT%\data\STOP" >nul 2>&1
powershell -NoProfile -Command "Start-Process -FilePath '%ROOT%\.venv\Scripts\python.exe' -ArgumentList '%ROOT%\scripts\auto_produce.py','300','%EP%' -WorkingDirectory '%ROOT%' -WindowStyle Hidden -RedirectStandardOutput '%ROOT%\data\auto\stdout_%EP%.log' -RedirectStandardError '%ROOT%\data\auto\stderr_%EP%.log'"
echo launched %EP%
endlocal
