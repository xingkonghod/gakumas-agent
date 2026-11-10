@echo off
chcp 65001 >nul
setlocal

set PYTHONPATH=D:\Games\gakumas-agent\src
set PY=D:\Games\MaaGakumasu\python\python.exe
set RUN=D:\Games\gakumas-agent\run.py
set OUT=D:\Games\gakumas-agent\data
if not exist "%OUT%" mkdir "%OUT%"

echo [0/6] game window
"%PY%" "%RUN%" capture --out "%OUT%\live_before.png"
if errorlevel 1 goto fail

echo [1/6] home
"%PY%" "%RUN%" home
if errorlevel 1 goto fail

echo [2/6] activity_fee
"%PY%" "%RUN%" task activity_fee
if errorlevel 1 goto fail

echo [3/6] work
"%PY%" "%RUN%" task work
if errorlevel 1 goto fail

echo [4/6] challenge
"%PY%" "%RUN%" task challenge
if errorlevel 1 goto fail

echo [5/6] society
"%PY%" "%RUN%" task society
if errorlevel 1 goto fail

echo [6/6] ALL OK
goto end

:fail
echo FAILED at the step above. Check data\live_before.png and the task message.
:end
pause
