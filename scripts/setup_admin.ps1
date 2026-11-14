$ErrorActionPreference = 'Stop'

# 1) DMM GamePlayer 始终以管理员身份启动（防 120000 / 权限类错误码）
$layers = 'HKCU:\Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers'
New-Item -Path $layers -Force | Out-Null
Set-ItemProperty -Path $layers -Name 'D:\DMM\GamePlayer\DMMGamePlayer.exe' -Value '~ RUNASADMIN'
Write-Host 'DMM RUNASADMIN ok'

# 2) UAC：管理员账户不再弹“是否允许”，重启后生效
$sys = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System'
Set-ItemProperty -Path $sys -Name ConsentPromptBehaviorAdmin -Value 0 -Type DWord
Set-ItemProperty -Path $sys -Name PromptOnSecureDesktop -Value 0 -Type DWord
Write-Host 'UAC prompt disabled ok'

# 3) 计划任务：常驻 agent 以最高权限运行，之后 schtasks /run 不再弹 UAC
$tr = '"D:\Games\MaaGakumasu\python\python.exe" "D:\Games\gakumas-agent\scripts\agent_daemon.py"'
schtasks /Create /TN GDEAgent /TR $tr /SC ONCE /ST 23:59 /RL HIGHEST /F | Out-Null
Write-Host 'GDEAgent task ok'
