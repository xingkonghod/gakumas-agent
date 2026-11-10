param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = 'Continue'
$out = 'D:\Games\gakumas-agent\data\admin_out.txt'
if (Test-Path $out) { Remove-Item $out -Force }

$argString = ($Rest | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }) -join ' '
$cmdLine = '/c "D:\Games\gakumas-agent\scripts\run_task_admin.cmd" ' + $argString

Start-Process -FilePath 'cmd.exe' -ArgumentList $cmdLine -Verb RunAs -Wait
Start-Sleep -Milliseconds 300
if (Test-Path $out) {
    Get-Content $out -Raw
} else {
    Write-Host "no output file (UAC cancelled?)"
}
