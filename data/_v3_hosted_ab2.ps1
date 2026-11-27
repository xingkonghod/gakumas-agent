# v3 hosted A/B driver v2 (probe, untracked). UTF-8 BOM required: PS 5.1 reads BOM-less
# UTF-8 as GBK (Chinese comment tail bytes swallowed newlines -> parse bug; Chinese
# match strings garbled -> completion detection broken). OutputEncoding set below so
# python utf-8 stdout decodes correctly for the Chinese progress patterns.
# Server eval registry is an in-memory map (wiped on restart; two 404 purges observed),
# but uploaded episodes persist on disk and leaderboard merges same algo+rules runs
# (same problem+seed takes latest) -> chunking is safe.
# Arm A (vote0.8) FINAL = salvaged 238/240 pairs from purged eval 9ba9c00fb468
# (data/_v3_partial_cmp.py: +56444 CI[-9.8k,+124.6k], 118W/81L/39T, over 7 vs 43).
# Missing 2 slots not re-run (marginal; re-run would overwrite settled slots).
# This driver runs Arm B (vote2.0) only: 4 chunks x 30 problems sequential (~30min each).
# Within chunk: storm -> --resume; 404 -> chunk fresh. Log out/_v3_ab2_hosted.log.
$env:PYTHONIOENCODING = 'utf-8'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
Set-Location $PSScriptRoot\bench_repo
$py = '..\..\.venv\Scripts\python.exe'
$log = '..\..\out\_v3_ab2_hosted.log'
$algoBase = '\Games\gakumas-agent\data\bench_repo\submissions\gkagent-ex-seed-v3\algo.py:ExSeedV3Algo'
$ids = Get-Content '..\..\out\_hif_ids.json' -Raw | ConvertFrom-Json

function Run-Chunk([string]$algo, [string]$only, [string]$tag) {
    $resumeId = $null
    for ($i = 1; $i -le 30; $i++) {
        $argv = @('-m', 'gkbench', 'eval', '--algo', $algo, '--parallel', '3', '--budget', '10',
                  '--set', 'hif', '--seeds', '2', '--only', $only)
        if ($resumeId) { $argv += @('--resume', $resumeId) }
        $out = & $py @argv 2>&1 | Out-String
        Add-Content -Path $log -Value "===== [$tag attempt $i] $(Get-Date -Format 'HH:mm:ss') =====" -Encoding UTF8
        Add-Content -Path $log -Value $out -Encoding UTF8
        $tail = ($out -split "`n" | Select-Object -Last 3) -join ' | '
        Write-Output "[$tag attempt $i] $tail"
        if ($out -match '：0 局待跑') { Write-Output "[$tag] CHUNK DONE"; return }
        if ($out -match '完成：20 局，出错 0 局') { Write-Output "[$tag] CHUNK DONE (completed line)"; return }
        if ($out -match '20/20') { Write-Output "[$tag] CHUNK DONE (20/20 ascii)"; return }
        if ($out -match '404') { $resumeId = $null; Write-Output "[$tag] eval purged (404) -> chunk fresh" }
        elseif ($out -match '评测 ([0-9a-f]{12})') { $resumeId = $Matches[1] }
        Start-Sleep -Seconds 60
    }
    Write-Output "[$tag] GAVE UP after 30 attempts (see $log)"
}

# 10 problems/chunk = 20 games ~3.5min < server purge interval (~5-10min).
for ($c = 0; $c -lt 12; $c++) {
    $chunk = ($ids[($c * 10)..(($c * 10) + 9)] -join ',')
    Run-Chunk "$($algoBase):vote_sec_cap=2.0" $chunk "B$c"
}
Write-Output 'B ARM DONE / AB2 DRIVER FINISHED'