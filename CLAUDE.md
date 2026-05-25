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
2. **Stop hook** (`.claude/settings.json` → `scripts/auto-push.js` → `scripts/auto-push.ps1` on Win, `auto-push.sh` on *nix) fires after every Claude turn that left dirty changes:
   - bumps `CONFIG.version` patch by +1
   - validates inline JS (`scripts/validate-html-js.js`) — aborts push on syntax errors
   - commits with a message describing the diff
   - pushes to `origin/main`
   - silently no-ops if the tree is clean
3. **Two GitHub Actions workflows run in parallel on every push to `main`:**
   - `validate.yml` — re-lints HTML/JS as a CI gate (mirrors local validator)
   - `pages.yml` — uploads the repo root via `actions/upload-pages-artifact@v3` and deploys via `actions/deploy-pages@v4`
4. GitHub Pages goes live in ~30–60s at <https://mustbebecomerichman.github.io/Operation-dashboard/delay_dashboard.html>
5. Each running dashboard's "Check for update" routine detects the new `CONFIG.version` and prompts users to reload.

**Deployment method**: GitHub Pages source is set to **GitHub Actions** (not the legacy Jekyll build). `.nojekyll` at the repo root keeps any future Jekyll detection inert. The legacy Jekyll build was unreliable for this single-file PWA — it failed silently on the very files it was meant to serve. Don't switch back to the legacy source.

**Auth setup (per machine)**:
```bash
gh auth login                              # authenticate as mustbebecomerichman
gh auth switch --user mustbebecomerichman  # if multiple accounts in keyring
git config user.name "mustbebecomerichman"
git config user.email "mustbebecomerichman@users.noreply.github.com"
```
If `git push` returns 403 to `chartersuperman` (or any non-owner), you forgot `gh auth switch`. Confirm with `gh auth status | head -3`.

**Editing workflow files (`.github/workflows/*.yml`)**: regular `git push` of workflow changes can return HTTP 500 ("Internal Server Error") even with `workflow` token scope. Workaround: use the Contents API via `gh api -X PUT repos/.../contents/path -f content="$(base64 file)"` — server-side commits bypass the push restriction. Pulled back with `git fetch && git reset --hard origin/main`.

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

## 5. Encoding hygiene

As of the 2026-05-25 restoration pass, **all known mojibake is resolved**. ROUTES, VESSELS, and SVC_INFO Korean data plus ~10 JS comments were restored from the initial commit (`37dd2f4`) — the original bytes were never lost in git history, only in the current working copy.

If new mojibake appears (`??` patterns, `?<korean-syllable>`, `�` U+FFFD characters):
1. Don't guess the original — check `git show 37dd2f4:delay_dashboard.html` first; the structure is identical so line numbers may have shifted but the strings can usually be matched by surrounding ASCII context.
2. Use Node to do the replacement so BOM (`EF BB BF`) is preserved.
3. Verify with the script-block parse check (§3) — expect `Scripts: 3 Failures: 0`.

Emojis used in the file (UTF-8, all valid):
✓ ✗ → — – · … ↻ ⚙️ 👥 📤 📥 🔄 💡 🔔 🔍 🛰️ ⚠️ 🔗 🚢 💾 📱 👤 📋 ✏️ 🗺️ 🌐 ➡️ ✕ ──

---

## 6. Conventions for this codebase

- **Don't touch** `CONFIG` defaults, auth logic, or `apps-script/seavantage-proxy.gs` unless the task is explicitly about them.
- `ROUTES` / `VESSELS` / `SVC_INFO` are business data — read freely, but only edit when the user explicitly asks to update a route, vessel, or service-manager assignment. The source of truth is the user's spreadsheet; the HTML mirrors it.
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

### 2026-05-25 — Pages: legacy Jekyll → GitHub Actions deployment
- Diagnosed: legacy Pages classic builds had been failing silently for the past 3 versions (v1.4.8, v1.4.9 errored with `duration: 0`). Active gh CLI account was `chartersuperman` (no push permission to `mustbebecomerichman/Operation-dashboard`), so the Stop hook's `git push` was silently failing too — local commits piled up unpushed.
- Switched git auth: `gh auth switch --user mustbebecomerichman` + `git config user.name/email` to match. Both accounts were already in the keyring.
- Added `.nojekyll` to disable Jekyll processing.
- Added `.github/workflows/pages.yml` using `actions/configure-pages@v5` + `actions/upload-pages-artifact@v3` + `actions/deploy-pages@v4`.
- Switched Pages source from `legacy` to `workflow` via `gh api -X PUT repos/.../pages -f build_type=workflow`.
- Workflow-file pushes returned 500 ISE despite `workflow` token scope — used Contents API as workaround (see §2). Future workflow edits will need this same path.
- Verified end-to-end: pushed → workflow ran (success) → live URL serves v1.4.10 with correct Korean (`"중국 PQS"`, `"manager": "장명준"`, etc.) and zero mojibake.

### 2026-05-25 — mojibake fully resolved (ROUTES / VESSELS / SVC_INFO + comments)
- Discovered the initial commit `37dd2f4` still had **correct UTF-8 Korean** for ROUTES (route names + manager/backup), VESSELS (`owner: 사선/용선`), and SVC_INFO (~80 service entries with managers). Structure (keys / vessel codes / svc IDs) was byte-identical to current, only the Korean strings had been corrupted in a later encoding pass.
- Restored 3 data lines (433 `ROUTES`, 435 `VESSELS`, 436 `SVC_INFO`) by copying the exact lines from the initial commit via Node — BOM preserved (`EF BB BF`).
- Fixed 10 JS comment mojibake patterns (lines 423, 477, 604, 675, 1013, 1079, 1081, 1284, 1537, 1736): restored `—` / `–` / `→` / `──` separators and the Korean comment `// ── Map 항적선: coords[] WP 직접 사용 (실제 항행 경로) ──`.
- Updated §5 and §6: removed the "do NOT fix" warnings — they were based on the (incorrect) assumption that the original Korean was lost. Now §5 is general encoding hygiene guidance.
- Verified: all 3 `<script>` blocks parse with `new Function()` (3/3 OK). Zero `??` and zero `U+FFFD` characters remain.

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
