$ErrorActionPreference = 'Stop'

$project = 'D:\Games\gakumas-agent'
$maa = 'D:\Games\MaaGakumasu'

# 1) drop-in custom action
$src = Join-Path $project 'integrations\maa_gakumasu\gkagent_cards.py'
$dst = Join-Path $maa 'agent\custom\action\gkagent_cards.py'
Copy-Item $src $dst -Force
Write-Host "copied action -> $dst"

# 2) make gkagent importable in Maa Python
$site = Join-Path $maa 'python\Lib\site-packages'
$pth = Join-Path $site 'gkagent.pth'
Set-Content -Path $pth -Value (Join-Path $project 'src') -Encoding ASCII
Write-Host "wrote $pth"

# 3) register in action __init__.py (idempotent)
$init = Join-Path $maa 'agent\custom\action\__init__.py'
$content = Get-Content $init -Raw
if ($content -notmatch 'gkagent_cards') {
    Copy-Item $init "$init.bak" -Force
    Add-Content -Path $init -Value "`nfrom .gkagent_cards import *" -Encoding UTF8
    Write-Host "registered gkagent_cards in action/__init__.py (backup: __init__.py.bak)"
} else {
    Write-Host "gkagent_cards already registered"
}

# 4) policy config
$cfgDir = Join-Path $maa 'config'
New-Item -ItemType Directory -Force -Path $cfgDir | Out-Null
$cfg = Join-Path $cfgDir 'cards_policy.json'
if (-not (Test-Path $cfg)) {
    '{"policy":"coach"}' | Set-Content -Path $cfg -Encoding UTF8
    Write-Host "created $cfg (coach mode)"
} else {
    Write-Host "$cfg exists; current: $(Get-Content $cfg -Raw)"
}

Write-Host ""
Write-Host "下一步："
Write-Host "1. 把出牌节点 custom_action 从 ProduceCardsAuto 改为 GkAgentCoach（教练，只记录）"
Write-Host "2. 验证后再改为 GkAgentCardsAuto（插件，点击走 MAA）"
Write-Host "3. cards_policy.json: coach | plugin | maa"
