param(
    [string]$Ep = 'ep-t1-a',
    [int]$Steps = 300,
    [switch]$SkipHome,
    [switch]$IgnoreUser,
    [int]$MaxMinutes = 30,
    [string]$ExamSetup = ''
)
$ErrorActionPreference = 'Stop'
$Root = 'D:\Games\gakumas-agent'
$Exe = Join-Path $Root '.venv\Scripts\python.exe'
$Script = Join-Path $Root 'scripts\auto_produce.py'
$Stop = Join-Path $Root 'data\STOP'
if (Test-Path $Stop) { Remove-Item $Stop -Force }
$argList = @($Script, "$Steps", $Ep)
if ($SkipHome) { $argList += '--skip-home' }
if ($IgnoreUser) { $argList += '--ignore-user' }
$argList += '--max-minutes'
$argList += "$MaxMinutes"
if ($ExamSetup) {
    $argList += '--exam-setup'
    $argList += $ExamSetup
}
$Out = Join-Path $Root "data\auto\stdout_$Ep.log"
$Err = Join-Path $Root "data\auto\stderr_$Ep.log"
$p = Start-Process -FilePath $Exe -ArgumentList $argList -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput $Out -RedirectStandardError $Err -PassThru
"launched pid=$($p.Id) ep=$Ep steps=$Steps skip_home=$($SkipHome.IsPresent) ignore_user=$($IgnoreUser.IsPresent) max_minutes=$MaxMinutes exam_setup=$ExamSetup"
