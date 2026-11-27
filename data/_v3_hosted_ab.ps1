# v3 托管 A/B 驱动（探针，不提交）：臂A vote0.8（resume 40312fcb77a0）→ 臂B vote2.0（新评测）。
# 服务器间歇性 SYN 丢包（10060）：每臂循环 --resume 直到「0 局待跑」；风暴间隔 90s 重试。
# 顺序跑保证两臂 CPU 负载口径一致（--parallel 3 不加）。日志 out/_v3_ab_hosted.log。
$env:PYTHONIOENCODING = 'utf-8'
Set-Location $PSScriptRoot\bench_repo
$py = '..\..\.venv\Scripts\python.exe'
$log = '..\..\out\_v3_ab_hosted.log'
$algoBase = '\Games\gakumas-agent\data\bench_repo\submissions\gkagent-ex-seed-v3\algo.py:ExSeedV3Algo'

function Run-UntilDone([string]$algo, [string]$resumeId, [string]$tag) {
    for ($i = 1; $i -le 40; $i++) {
        $argv = @('-m', 'gkbench', 'eval', '--algo', $algo, '--parallel', '3', '--budget', '10')
        if ($resumeId) { $argv += @('--resume', $resumeId) } else { $argv += @('--set', 'hif', '--seeds', '2') }
        $out = & $py @argv 2>&1 | Out-String
        Add-Content -Path $log -Value "===== [$tag attempt $i] $(Get-Date -Format 'HH:mm:ss') =====" -Encoding UTF8
        Add-Content -Path $log -Value $out -Encoding UTF8
        $tail = ($out -split "`n" | Select-Object -Last 4) -join ' | '
        Write-Output "[$tag attempt $i] $tail"
        if ($out -match '：0 局待跑') { Write-Output "[$tag] DONE all slots finished"; return }
        if ($out -match '404') { $resumeId = $null; Write-Output "[$tag] eval gone on server (404) -> start fresh next attempt" }
        elseif ($out -match '评测 ([0-9a-f]{12})') { $resumeId = $Matches[1] }
        Start-Sleep -Seconds 90
    }
    Write-Output "[$tag] GAVE UP after 40 attempts (see $log)"
}

Run-UntilDone "$($algoBase):vote_sec_cap=0.8" $null 'A'
Run-UntilDone "$($algoBase):vote_sec_cap=2.0" $null 'B'
Write-Output 'AB DRIVER FINISHED'