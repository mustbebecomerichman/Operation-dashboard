# Operation Dashboard — Claude Code working notes

> **For future Claude sessions and PC migrations.** This file is auto-loaded by Claude Code when it opens this repo. Read it first.

---

## 1. What this repo is

A **single-file HTML PWA** (`delay_dashboard.html`, ~2250 lines) that visualises shipping-route port delays on a Leaflet map. Backed by:

- **GitHub Pages** — serves `delay_dashboard.html` from `main` at <https://mustbebecomerichman.github.io/Operation-dashboard/delay_dashboard.html>. Pushes go live in ~1 min.
- **Google Apps Script (delays sheet)** — `CONFIG.appsScriptUrl` in the HTML. Reads/writes the `getDelays` action. URL is per-user, stored in `localStorage` only.
- **Google Apps Script (SeaVantage proxy)** — `apps-script/seavantage-proxy.gs`. Holds SeaVantage Basic Auth creds in Script Properties; dashboard calls it via `callSV()` with a `DASHBOARD_TOKEN`.
- **aisstream.io WebSocket** — free live AIS, key stored in browser only.

Other top-level data files (`*.xls`, `*.xlsx`, `data/`) are operational sheets, git-ignored — they live on each user's machine. Copy them by hand on a new PC if you need them.

---

## 2. How code flows to production

1. Edit `delay_dashboard.html` locally.
2. **Stop hook** (`.claude/settings.json` → `scripts/auto-push.ps1`) fires after every Claude turn that left dirty changes:
   - bumps `CONFIG.version` patch by +1
   - commits with a message describing the diff
   - pushes to `origin/main`
   - silently no-ops if the tree is clean (so empty turns don't create empty commits)
3. GitHub Actions runs `.github/workflows/validate.yml` to lint the HTML/JS.
4. Each running dashboard's "Check for update" routine detects the new `CONFIG.version` and prompts users to reload.

**The auto-push hook is currently Windows / PowerShell only.** On a Mac/Linux box, either:
- run `git add -A && git commit && git push` manually after each Claude session, OR
- port `scripts/auto-push.ps1` to a `bash` equivalent and update `.claude/settings.json` to invoke the right one per platform (use a conditional `command`).

Git remote is HTTPS:
```
origin  https://github.com/mustbebecomerichman/Operation-dashboard.git
```
On a new machine you'll need a GitHub PAT or `gh auth login` so the auto-push can push without prompting.

---

## 3. File encoding — important

`delay_dashboard.html` is **UTF-8 with BOM**. Earlier in the project a different encoding pass corrupted many emoji + Korean strings into mojibake. As of the cleanup pass (2026-05) the user-visible strings are restored, but a few **intentionally-kept** mojibake regions remain — see §5.

When editing strings:
- Stay UTF-8. Don't paste from sources that round-trip through CP949 / Windows-1252.
- Emojis like ✓ ✗ → — · … ⚠️ 🚢 🛰️ are all fine — the file is UTF-8.
- If you ever see new `??` or `?<korean-syllable>` patterns appearing, that's a re-encoding regression. Stop and diagnose before saving.

To verify the JS still parses after edits:
```bash
node -e "
const fs=require('fs'),html=fs.readFileSync('delay_dashboard.html','utf8');
const re=/<script\b[^>]*>([\s\S]*?)<\/script>/gi;
let m,i=0,fails=0;
while((m=re.exec(html))!==null){i++;const s=m[1];if(!s.trim())continue;try{new Function(s);}catch(e){fails++;console.log('FAIL #'+i,e.message);}}
console.log('Scripts:',i,'Failures:',fails);
"
```
Expected: `Scripts: 3 Failures: 0`.

---

## 4. SeaVantage integration — current status & checklist

The proxy code (`apps-script/seavantage-proxy.gs`, 171 lines) is complete and the dashboard client (`callSV` and friends in `delay_dashboard.html` around line 2017–2200) is wired up. **What's needed is per-user setup** — none of this lives in git:

### Required one-time setup on the user's Google account

1. **SeaVantage credentials** — a working login at <https://insight.seavantage.com> (email + password).
2. **Apps Script project** — <https://script.google.com> → New project → replace `Code.gs` content with the full contents of `apps-script/seavantage-proxy.gs`.
3. **Script Properties** (⚙️ Project Settings → Script Properties):
   - `SV_USERNAME` = SeaVantage login email
   - `SV_PASSWORD` = SeaVantage password
   - `DASHBOARD_TOKEN` = any ~32-char random string (treat as obscurity, not security)
4. **Deploy** → New deployment → Type: Web app · Execute as: Me · Who has access: **Anyone** → copy the `.../exec` URL.
5. **Smoke test** in a browser:
   ```
   <WEB_APP_URL>?action=sv_categories&token=<DASHBOARD_TOKEN>
   ```
   should return a JSON array of fleet categories.
6. **Dashboard input** — open Admin Panel → SeaVantage Insight Integration → paste URL + token → Save → Test Connection.

### Available proxy actions
Defined in `seavantage-proxy.gs::handle()`. Adding a new endpoint = add a `case 'sv_<name>'` branch.

| action | SeaVantage path | params |
|---|---|---|
| `sv_search` | `/ship/search` | `keyword` |
| `sv_pasttrack` | `/ship/past-track/from-last-port` | `shipId` |
| `sv_snapshot` | `/fleet/snapshot` | `categoryId`, `shipId` |
| `sv_info` | `/fleet/info` | `categoryId`, `shipId` |
| `sv_categories` | `/fleet/categories` | — |
| `sv_register` | `POST /fleet` | `categoryId` + JSON body |
| `sv_unregister` | `DELETE /fleet` | `categoryId` + JSON body |
| `sv_portcall` | `/port-call/{shipId}` | `from`, `to` |
| `sv_route` | `POST /route/ship-to-port` | `imoNo`, `portId` + JSON body |

### Common failure patterns (Test Connection output)

| Message | Diagnosis |
|---|---|
| `Enter URL and Token first, then Save.` | Inputs are blank — fill both fields, click Save, then Test |
| `SeaVantage proxy not configured (Admin Panel)` | Same as above but seen from `callSV` |
| `unauthorized` | The token in the dashboard ≠ `DASHBOARD_TOKEN` in Script Properties |
| `SV_USERNAME / SV_PASSWORD not set in Script Properties` | Step 3 incomplete |
| `SeaVantage 401` | SV credentials wrong (step 1 — try logging in at insight.seavantage.com) |
| Long hang then nothing | Deployment "Who has access" is wrong, set it to Anyone |

After modifying the proxy code, you **must redeploy** (Deploy → Manage deployments → ✏️ → New version) — the existing `/exec` URL keeps serving the old version until then.

---

## 5. Intentionally-kept mojibake (do NOT "fix")

These regions still have garbled bytes but are deliberate skips:

| Location | Why |
|---|---|
| `delay_dashboard.html` line 426 (`var ROUTES = {...}`) | Korean manager / route names — business data. Restoring requires the source of truth, not guessing. |
| `delay_dashboard.html` line 429 (`var SVC_INFO = [...]`) | Same — Korean manager names. |
| ~12 JS comments throughout the file (lines 416, 470, 554, 625, 963, 1029, 1031, 1234, 1239, 1258, 1487, 1686) | Not user-visible. Touching them risks misinterpreting intent. |

Everything **user-visible** (HTML body text, JS string literals that surface in the UI) was cleaned up in the 2026-05 pass. Emojis used:
✓ ✗ → — · … ↻ ⚙️ 👥 📤 📥 🔄 💡 🔔 🔍 🛰️ ⚠️ 🔗 🚢 💾 📱 👤 📋 ✏️ 🗺️ 🌐 ➡️ ✕

---

## 6. Conventions for this codebase

- **Don't touch** `CONFIG` defaults, auth logic, or `apps-script/seavantage-proxy.gs` unless the task is explicitly about them.
- **Don't touch** `ROUTES` / `SVC_INFO` JSON blobs — they're business data with separate Korean mojibake. If a route definition needs to change, the user updates it via the source spreadsheet, not by editing the HTML directly.
- The HTML is a single file by design (PWA installability). Resist splitting it without an explicit ask.
- Inline styles are used heavily — match the existing style rather than refactoring to classes.
- The Stop hook commits *everything dirty* in one commit per Claude turn. If you need separate commits, instruct the user to run them manually.

---

## 7. Quick orientation map (line numbers as of 2026-05-15)

| What | Where (`delay_dashboard.html`) |
|---|---|
| `CONFIG` defaults (admin email, version, URLs) | ~410–425 |
| `ROUTES` data | ~426 |
| `SVC_INFO` data | ~429 |
| Live delays fetch (`fetchLive`) | ~564 |
| Port-tab rendering | ~620–675 |
| Service / Route rendering | ~680–760 |
| Update-tab form (`renderUpdateTab`) | ~770–870 |
| Vessel modal + route panel | ~1226–1370 |
| aisstream.io WebSocket logic | ~1610–1710 |
| Admin Panel UI | HTML lines ~229–340 |
| User management functions | ~1850–2000 |
| **SeaVantage section UI** | HTML lines ~309–335 |
| **SeaVantage client functions** | ~2017–2200 (`saveSvConfig`, `callSV`, `loadSvFleetToMap`, `testSvConnection`, `inspectSv`) |
| Mobile nav | HTML lines ~2210–2215 |

Line numbers will drift — use `grep -n` rather than trusting these.

---

## 8. New-machine restoration in 60 seconds

```bash
# 1. Clone
git clone https://github.com/mustbebecomerichman/Operation-dashboard.git
cd Operation-dashboard

# 2. GitHub auth so auto-push can push
gh auth login                  # or set up a PAT manually

# 3. (Windows) the Stop hook will just work. (Mac/Linux) port scripts/auto-push.ps1 to bash first.

# 4. Open in Claude Code — this file (CLAUDE.md) gets auto-loaded; you'll have the same context.
```

Per-user secrets that **don't** travel with the repo and have to be re-pasted in the dashboard's Admin Panel after restore:
- aisstream.io API key
- Apps Script URL (delays sheet)
- SeaVantage proxy URL + DASHBOARD_TOKEN

These all live in `localStorage` only (keys: `pd_aiskey`, `pd_surl`, `pd_svurl`, `pd_svtok`) — copy them between browsers via Admin Panel re-entry.

---

## 9. Where session-by-session notes go

Don't pile session diaries into this file — it should stay evergreen. For per-session handoffs:
- Use Claude Code's `/remember` if a fact is worth permanent storage in `~/.claude/CLAUDE.md` (user-level, doesn't travel with repo).
- For "what we just did" notes that should survive a PC switch, append a dated bullet to §10 below.

---

## 10. Recent work log (append-only, newest first)

### 2026-05-19 — auth flow: Apps Script fallback for fresh-browser first login
- Modified `handleLogin()` to fall back to `?action=getUsers` on the user's Apps Script when the email isn't in this browser's local `pd_u`. Enables testers / new users to log in on a fresh browser without manual admin pre-seeding.
- Added `DEFAULT_APPS_SCRIPT_URL` constant near CONFIG — leave empty by default, or paste a deployed `/exec` URL to enable the hardcoded fallback (useful for fresh browsers that have never opened the admin panel).
- Added `_completeLogin()` helper to share post-fetch login logic.
- Apps Script must implement `doGet(e)` with `?action=getUsers` returning `{users:[{email, role, name}, ...]}`. The Google Sheet must have a "Users" tab with `email | name | role` columns (`viewer`/`reporter`/`admin`).
- Graceful degradation: on fetch failure or no-match, the old "Email not registered" alert still fires.
- Verified: all 3 `<script>` blocks parse with `new Function()` (3/3 OK).

### 2026-05-15 — mojibake cleanup pass
- Cleaned 45 `??` → proper symbols (✓ ✗ → — · …) across HTML and JS string literals.
- Restored 20+ emoji icons across Admin Panel, route cards, mobile nav (⚙️ 👥 📤 📥 🔄 💡 🔔 🔍 🛰️ ⚠️ 🔗 🚢 💾 📱 👤 📋 ✏️ 🗺️ 🌐 ➡️).
- Normalised separators (`쨌` → `·`, `째` → `°`) globally.
- Korean status text → English (`Offline mode`, `Connecting…`, `Live · `, `Connection failed`, `N ships`, `No entries today`, `Saved`).
- ROUTES / SVC_INFO Korean business data **deliberately left as-is** — needs source-of-truth restoration, not guessing.
- All 3 `<script>` blocks verified parsing with `new Function()`.
- SeaVantage code path: **not touched** — fully functional, awaiting per-user setup (see §4).
