$ErrorActionPreference = 'Continue'
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'agent_daemon' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Remove-Item 'D:\Games\gakumas-agent\data\agent_cmd.json' -ErrorAction SilentlyContinue
Remove-Item 'D:\Games\gakumas-agent\data\agent_result.json' -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
Start-Process -FilePath 'D:\Games\MaaGakumasu\python\python.exe' `
    -ArgumentList '"D:\Games\gakumas-agent\scripts\agent_daemon.py"' `
    -WorkingDirectory 'D:\Games\gakumas-agent'
Write-Host 'daemon restarted'
