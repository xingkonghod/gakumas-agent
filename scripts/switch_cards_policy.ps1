param(
    [ValidateSet('coach', 'plugin', 'maa')]
    [string]$Mode = 'coach'
)

$ErrorActionPreference = 'Stop'
$maa = 'D:\Games\MaaGakumasu'
$target = @{
    coach  = 'GkAgentCoach'
    plugin = 'GkAgentCardsAuto'
    maa    = 'ProduceCardsAuto'
}[$Mode]

$files = @(
    (Join-Path $maa 'resource\base\pipeline\Produce.json'),
    (Join-Path $maa 'resource\base\pipeline\IdolRoad.json')
)

foreach ($f in $files) {
    if (-not (Test-Path $f)) { continue }
    $bak = "$f.bak-gde"
    if (-not (Test-Path $bak)) { Copy-Item $f $bak -Force }
    $raw = Get-Content $f -Raw
    $raw = $raw -replace '"custom_action": "ProduceCardsAuto"', ('"custom_action": "' + $target + '"')
    $raw = $raw -replace '"custom_action": "GkAgentCoach"', ('"custom_action": "' + $target + '"')
    $raw = $raw -replace '"custom_action": "GkAgentCardsAuto"', ('"custom_action": "' + $target + '"')
    [IO.File]::WriteAllText($f, $raw, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "patched $f -> $target"
}

$cfg = Join-Path $maa 'config\cards_policy.json'
New-Item -ItemType Directory -Force -Path (Split-Path $cfg) | Out-Null
('{"policy":"' + $Mode + '"}') | Set-Content -Path $cfg -Encoding UTF8
Write-Host "cards_policy.json -> $Mode"
Write-Host "restart MAA to apply."
