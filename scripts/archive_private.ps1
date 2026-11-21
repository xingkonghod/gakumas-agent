# Private archive: local bare repo + single-file bundle (+ critical artifacts)
#
# What it does:
#   - local bare repo : D:\GakumasAgentArchive\gakumas-agent.git (private-repo form; clone/push ready)
#   - bundle          : gakumas-agent-YYYYMMDD.bundle (full history, copy to USB/cloud, git clone <bundle>)
#   - artifacts       : out/*.json, data/runs/*.json, data/bench_local/*, capture/traffic.jsonl etc.
#   - redundant copy  : %USERPROFILE%\Documents\gakumas-archive (survives one-disk failure)
#
# Usage (idempotent, re-runnable):
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\archive_private.ps1
#
# Push to a remote private repo (your account; this script never handles credentials):
#   cd D:\GakumasAgentArchive\gakumas-agent.git
#   git remote add origin https://gitee.com/<you>/<repo>.git   (or github.com, via proxy if needed)
#   git push origin master --tags
param(
    [string]$Source = 'D:\Games\gakumas-agent',
    [string]$ArchiveRoot = 'D:\GakumasAgentArchive',
    [string]$CaptureDir = 'C:\GakumasLocal\GakumasUnlock\out',
    [string]$RedundantCopy = (Join-Path $env:USERPROFILE 'Documents\gakumas-archive'),
    # -Push: also push the bare repo to its remote (origin = private Gitee/GitHub URL)
    [switch]$Push
)
$ErrorActionPreference = 'Stop'
$stamp = Get-Date -Format 'yyyyMMdd'
$bare = Join-Path $ArchiveRoot 'gakumas-agent.git'
$bundle = Join-Path $ArchiveRoot "gakumas-agent-$stamp.bundle"
$artifacts = Join-Path $ArchiveRoot 'artifacts'
$tag = "archive-$(Get-Date -Format 'yyyy-MM-dd')"

New-Item -ItemType Directory -Force -Path $ArchiveRoot, $artifacts | Out-Null

# 1) archive tag (idempotent)
Push-Location $Source
try {
    git rev-parse -q --verify "refs/tags/$tag" 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        git tag -a $tag -m "private archive $stamp" | Out-Null
        Write-Host "tag created: $tag"
    } else {
        Write-Host "tag exists: $tag"
    }

    # 2) bare repo: first clone --bare, then fetch
    if (-not (Test-Path (Join-Path $bare 'HEAD'))) {
        git clone --bare $Source $bare | Out-Null
        Write-Host "bare repo created: $bare"
    } else {
        git --git-dir=$bare fetch --prune $Source '+refs/heads/*:refs/heads/*' '+refs/tags/*:refs/tags/*' | Out-Null
        Write-Host "bare repo updated: $bare"
    }

    # 3) bundle (full history, all branches and tags)
    if (Test-Path $bundle) { Remove-Item $bundle -Force }
    git bundle create $bundle --all | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "git bundle create failed" }
    git bundle verify $bundle | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "git bundle verify failed" }
    Write-Host "bundle: $bundle"
} finally {
    Pop-Location
}

# 4) critical runtime artifacts (not in git, small)
Copy-Item (Join-Path $Source 'out\*.json') $artifacts -Force -ErrorAction SilentlyContinue
$runs = Join-Path $artifacts 'runs'
$bench = Join-Path $artifacts 'bench_local'
$capture = Join-Path $artifacts 'capture'
New-Item -ItemType Directory -Force -Path $runs, $bench, $capture | Out-Null
Copy-Item (Join-Path $Source 'data\runs\*.json') $runs -Force -ErrorAction SilentlyContinue
Copy-Item (Join-Path $Source 'data\bench_local\*') $bench -Force -ErrorAction SilentlyContinue
# capture data is the crown jewel: traffic.jsonl + deck snapshots + exam truth
foreach ($name in @('traffic.jsonl', 'deck_snapshots.json', 'exam_truth.json')) {
    $path = Join-Path $CaptureDir $name
    if (Test-Path $path) { Copy-Item $path $capture -Force -ErrorAction SilentlyContinue }
}

# 5) manifest: bundle + artifacts only (bare repo can be rebuilt from bundle)
$manifest = Join-Path $ArchiveRoot 'SHA256SUMS.txt'
$lines = @()
foreach ($file in @(Get-ChildItem $bundle, $artifacts -Recurse -File -ErrorAction SilentlyContinue)) {
    $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
    $lines += "$hash  $($file.FullName)"
}
[System.IO.File]::WriteAllLines($manifest, $lines, [System.Text.UTF8Encoding]::new($false))
Write-Host "manifest: $manifest ($($lines.Count) files)"

# 6) redundant copy on another disk
New-Item -ItemType Directory -Force -Path $RedundantCopy | Out-Null
Copy-Item $bundle $RedundantCopy -Force
Copy-Item $manifest $RedundantCopy -Force
$readme = Join-Path $ArchiveRoot 'README.txt'
if (Test-Path $readme) { Copy-Item $readme $RedundantCopy -Force }
Write-Host "redundant copy: $RedundantCopy"

# 7) optional: push bare repo to private remote (origin must be an https/ssh repo URL)
if ($Push) {
    $origin = & git --git-dir=$bare remote get-url origin 2>$null
    if (-not $origin -or $origin -match '^[A-Za-z]:' -or $origin -match '^/') {
        Write-Host "WARN: bare origin is not a remote URL (got '$origin'); set it once with:"
        Write-Host "      git --git-dir=$bare remote add origin https://gitee.com/<you>/<repo>.git"
    } else {
        & git --git-dir=$bare push origin master --tags 2>&1 | ForEach-Object { Write-Host $_ }
        Write-Host "push exit=$LASTEXITCODE -> $origin"
    }
}

Write-Host "archive ready: $ArchiveRoot"
