@echo off
cd /d D:\Games\gakumas-agent
set PYTHONPATH=D:\Games\gakumas-agent\src
"D:\Games\MaaGakumasu\python\python.exe" "D:\Games\gakumas-agent\scripts\try_confirm_inputs.py" > "D:\Games\gakumas-agent\data\confirm_inputs_out.txt" 2>&1
