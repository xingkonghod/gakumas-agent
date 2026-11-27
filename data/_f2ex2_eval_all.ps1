# f2-ex2 两版正式跑分（顺序执行，避免 CPU 争抢）：A hif → A hajime → B hif → B hajime，均 --seeds 2 --parallel 3
$ErrorActionPreference = 'Continue'
$env:GKMS_ROOT = 'D:\Games\gakumas-agent\data\GKMSMainWheel'
$env:GKMSCLIGPU_LIB = 'D:\Games\gakumas-agent\data\GKMSMainWheel\GakumasCLI\native\build\gkmscore.dll'
$env:PYTHONPATH = 'D:\Games\gakumas-agent\data\bench_repo'
$env:PYTHONIOENCODING = 'utf-8'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$py = 'D:\Games\gakumas-agent\.venv\Scripts\python.exe'
Set-Location 'D:\Games\gakumas-agent\data\GKMSMainWheel\GakumasCLI'
$ex = '..\..\bench_repo\submissions\gkagent-expectimax\algo.py:ExpectimaxAlgo:worlds=6,mode=eval,threads=4,use_prior=0'
$sd = '..\..\bench_repo\submissions\gkagent-ex-seed\algo.py:ExSeedAlgo:procs=8,use_prior=0'
$stages = @(
    @{ name = 'a_hif';    set = 'hif';    algo = $ex },
    @{ name = 'a_hajime'; set = 'hajime'; algo = $ex },
    @{ name = 'b_hif';    set = 'hif';    algo = $sd },
    @{ name = 'b_hajime'; set = 'hajime'; algo = $sd }
)
foreach ($s in $stages) {
    $log = "D:\Games\gakumas-agent\data\_f2ex2_eval_$($s.name).log"
    Write-Output "=== $($s.name) START $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="
    & $py -m gkbench eval --set $s.set --algo $s.algo --seeds 2 --parallel 6 *>&1 |
        ForEach-Object { "$_" } | Out-File -FilePath $log -Encoding utf8
    Write-Output "=== $($s.name) EXIT=$LASTEXITCODE $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="
}
Write-Output 'ALL DONE'