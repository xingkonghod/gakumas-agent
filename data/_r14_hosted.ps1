# r14 pilot hosted gate (probe, untracked). UTF-8 BOM required (PS 5.1 GBK hazard).
# Net arm ~0.4ms/decision -> negligible CPU, safe concurrent with v3 arm B.
# 4 chunks x 30 problems; storm -> --resume; 404 -> chunk fresh. Log out/_r14_hosted.log.
$env:PYTHONIOENCODING = 'utf-8'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
Set-Location $PSScriptRoot\bench_repo
$py = '..\..\.venv\Scripts\python.exe'
$log = '..\..\out\_r14_hosted.log'
$algo = '\Games\gakumas-agent\data\bench_repo\submissions\gkagent-ei-r14\algo.py:EiR14Algo'
$ids = Get-Content '..\..\out\_hif_ids.json' -Raw | ConvertFrom-Json

function Run-Chunk([string]$only, [string]$tag) {
    $resumeId = $null
    for ($i = 1; $i -le 30; $i++) {
        $argv = @('-m', 'gkbench', 'eval', '--algo', $algo, '--parallel', '3', '--budget', '5',
                  '--set', 'hif', '--seeds', '2', '--only', $only)
        if ($resumeId) { $argv += @('--resume', $resumeId) }
        $out = & $py @argv 2>&1 | Out-String
        Add-Content -Path $log -Value "===== [$tag attempt $i] $(Get-Date -Format 'HH:mm:ss') =====" -Encoding UTF8
        Add-Content -Path $log -Value $out -Encoding UTF8
        $tail = ($out -split "`n" | Select-Object -Last 3) -join ' | '
        Write-Output "[$tag attempt $i] $tail"
        if ($out -match '：0 局待跑') { Write-Output "[$tag] CHUNK DONE"; return }
        if ($out -match '完成：60 局，出错 0 局') { Write-Output "[$tag] CHUNK DONE (completed line)"; return }
        if ($out -match '60/60') { Write-Output "[$tag] CHUNK DONE (60/60 ascii)"; return }
        if ($out -match '404') { $resumeId = $null; Write-Output "[$tag] eval purged (404) -> chunk fresh" }
        elseif ($out -match '评测 ([0-9a-f]{12})') { $resumeId = $Matches[1] }
        Start-Sleep -Seconds 60
    }
    Write-Output "[$tag] GAVE UP after 30 attempts (see $log)"
}

# R0 (175,668) + R1 (244,033) done and persisted -> start at chunk 2.
for ($c = 2; $c -lt 4; $c++) {
    $chunk = ($ids[($c * 30)..(($c * 30) + 29)] -join ',')
    Run-Chunk $chunk "R$c"
}
Write-Output 'R14 HOSTED DONE'