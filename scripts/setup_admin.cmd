@echo off
set LOG=D:\Games\gakumas-agent\data\setup_admin.log
echo === setup %DATE% %TIME% === > "%LOG%"
reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" /v ConsentPromptBehaviorAdmin /t REG_DWORD /d 0 /f >> "%LOG%" 2>&1
reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" /v PromptOnSecureDesktop /t REG_DWORD /d 0 /f >> "%LOG%" 2>&1
schtasks /Create /TN GDEAgent /TR "D:\Games\MaaGakumasu\python\python.exe D:\Games\gakumas-agent\scripts\agent_daemon.py" /SC ONCE /ST 23:59 /RL HIGHEST /F >> "%LOG%" 2>&1
echo DONE >> "%LOG%"
