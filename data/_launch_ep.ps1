param(
    [string]$Ep = 'ep-t1-a',
    [int]$Steps = 300,
    [switch]$SkipHome,
    [switch]$IgnoreUser
)
$ErrorActionPreference = 'Stop'
$Root = 'D:\Games\gakumas-agent'
$Exe = Join-Path $Root '.venv\Scripts\python.exe'
$Script = Join-Path $Root 'scripts\auto_produce.py'
$Stop = Join-Path $Root 'data\STOP'
if (Test-Path $Stop) { Remove-Item $Stop -Force }
$args = @($Script, "$Steps", $Ep)
if ($SkipHome) { $args += '--skip-home' }
if ($IgnoreUser) { $args += '--ignore-user' }
$Out = Join-Path $Root "data\auto\stdout_$Ep.log"
$Err = Join-Path $Root "data\auto\stderr_$Ep.log"
$p = Start-Process -FilePath $Exe -ArgumentList $args -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput $Out -RedirectStandardError $Err -PassThru
"launched pid=$($p.Id) ep=$Ep steps=$Steps skip_home=$($SkipHome.IsPresent)"
