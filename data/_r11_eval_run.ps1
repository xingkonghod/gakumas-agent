# r11 eval driver (run after training; one-time, not committed). Evals need idle CPU (beam timing).
# NOTE: ASCII-only comments -- Windows PowerShell 5.1 misreads UTF-8 Chinese without BOM.
$py = '.venv\Scripts\python.exe'
$env:OPENBLAS_NUM_THREADS = '8'; $env:OMP_NUM_THREADS = '8'
& $py scripts\eval_ei.py --net-model out\ei_r11_v11_mix.json --baseline-net out\ei_r6_v6_mix.json --scenario large --games 500 --seed 3000 --no-within --json out\ei_r11_eval_v11_large500.json 2>&1 | Select-Object -Last 4
Write-Host '=== small500 ==='
& $py scripts\eval_ei.py --net-model out\ei_r11_v11_mix.json --baseline-net out\ei_r6_v6_mix.json --scenario small --games 500 --seed 3000 --no-within --json out\ei_r11_eval_v11_small500.json 2>&1 | Select-Object -Last 4
Write-Host '=== large fresh6000 (120) ==='
& $py scripts\eval_ei.py --net-model out\ei_r11_v11_mix.json --baseline-net out\ei_r6_v6_mix.json --scenario large --games 120 --seed 6000 --no-within --no-greedy --json out\ei_r11_eval_v11_large_fresh6000.json 2>&1 | Select-Object -Last 4
Write-Host '=== small select (80) ==='
& $py scripts\eval_ei.py --net-model out\ei_r11_v11_mix.json --baseline-net out\ei_r6_v6_mix.json --scenario small --games 80 --seed 2000 --no-within --no-greedy --json out\ei_r11_eval_v11_small_select.json 2>&1 | Select-Object -Last 4
Write-Host '=== PROMOTE (exit 1 = gate fail, no promote) ==='
& $py data\_r11_promote.py
Write-Host "promote exit: $LASTEXITCODE"
Write-Host '=== COMPARE (P2-1b) ==='
& $py data\_r11_compare.py
Write-Host '=== R11 EVAL DONE ==='
