#Requires -Version 5.1
<#
.SYNOPSIS
    Bumps delay_dashboard.html version (patch +1) when it changed,
    then commits and pushes any uncommitted work to origin/main.

.DESCRIPTION
    Invoked automatically by the Claude Code Stop hook
    (see ../.claude/settings.json) — runs once per Claude turn,
    so a turn that touches many files still produces one commit.

    Safe to run manually:
        powershell -ExecutionPolicy Bypass -File scripts/auto-push.ps1

    Exits 0 silently if there is nothing to commit, so it can fire
    on every Claude turn without producing empty commits.
#>

$ErrorActionPreference = 'Stop'

# Always run relative to the repo root, not wherever the hook fires from.
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot

# Anything to do?
$dirty = git status --porcelain
if (-not $dirty) {
    Write-Host "[auto-push] clean tree — nothing to push"
    exit 0
}

# Bump delay_dashboard.html version only if the dashboard itself is dirty.
$dashboard = Join-Path $repoRoot 'delay_dashboard.html'
$dashboardDirty = (git status --porcelain -- 'delay_dashboard.html') -ne $null
$bumpedVer = $null

if ($dashboardDirty -and (Test-Path -LiteralPath $dashboard)) {
    $content = Get-Content -LiteralPath $dashboard -Raw
    $verRegex = "version:\s*'(\d+)\.(\d+)\.(\d+)'"
    $m = [regex]::Match($content, $verRegex)
    if ($m.Success) {
        $major = [int]$m.Groups[1].Value
        $minor = [int]$m.Groups[2].Value
        $patch = [int]$m.Groups[3].Value + 1
        $bumpedVer = "$major.$minor.$patch"
        $content = [regex]::Replace($content, $verRegex, "version: '$bumpedVer'", 1)
        Set-Content -LiteralPath $dashboard -Value $content -NoNewline -Encoding UTF8
        Write-Host "[auto-push] bumped dashboard version -> $bumpedVer"
    } else {
        Write-Host "[auto-push] dashboard changed but no version literal found — skipping bump"
    }
}

git add -A | Out-Null

$staged = git diff --cached --name-only
if (-not $staged) {
    Write-Host "[auto-push] no staged changes after add — nothing to commit"
    exit 0
}

$fileList = ($staged | ForEach-Object { "  - $_" }) -join "`n"
$title = if ($bumpedVer) { "chore(dashboard): auto v$bumpedVer" } else { "chore: auto-update" }

$body = @"
$title

Auto-pushed by Claude Code Stop hook.

Changed:
$fileList

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
"@

# git writes status messages to stderr; suppress strict-mode escalation for native calls.
$priorEAP = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
git commit -m $body | Out-Null
$pushOutput = git push origin main 2>&1
$pushExit = $LASTEXITCODE
$ErrorActionPreference = $priorEAP

$pushOutput | ForEach-Object { Write-Host "[auto-push] $_" }
if ($pushExit -ne 0) {
    Write-Error "[auto-push] git push failed with exit $pushExit"
    exit $pushExit
}
Write-Host "[auto-push] done$( if ($bumpedVer) { " (v$bumpedVer)" } )"
