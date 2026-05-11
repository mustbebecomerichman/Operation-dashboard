# Operation Dashboard

Port Delay Monitoring Dashboard — single-file HTML PWA with Leaflet map, port/service tracking, and Google Apps Script backend.

## Live

- **Dashboard:** https://smmoon2030.github.io/Operation-dashboard/delay_dashboard.html
- **Version source of truth:** `delay_dashboard.html` (`CONFIG.version`)

The deployed page is served by GitHub Pages straight from `main`. Pushes to `main` are picked up within ~1 minute.

## How updates flow

1. Edit `delay_dashboard.html` locally.
2. `scripts/auto-push.ps1` bumps the patch version, commits, and pushes (run automatically by the Claude Code PostToolUse hook in `.claude/settings.json`, or run manually).
3. GitHub Pages republishes the new file.
4. Each running dashboard's "Check for update" routine sees the new `CONFIG.version` and prompts the user to refresh.

## Working on a new machine

```bash
git clone https://github.com/smmoon2030/Operation-dashboard.git
cd Operation-dashboard
# Operational data files (xls/csv/xlsx) are git-ignored and live only on the
# original machine. Copy them in by hand if needed, or remove the matching
# lines from `.gitignore` to start tracking them.
```

## Manual push

```powershell
pwsh -File scripts/auto-push.ps1
```

## Layout

- `delay_dashboard.html` — the app
- `scripts/` — version-bump + auto-push helpers
- `.claude/settings.json` — Claude Code hook config (auto-push on edit)
- `.gitignore` — excludes operational data files by default
