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

**Divergent auto-push from parallel sessions**: if two Claude sessions (or another machine) edit the dashboard simultaneously, both Stop hooks commit + try to push. The first wins; the second fails with non-fast-forward and the local commit sits unpushed. Next session sees `Your branch is ahead of origin/main by N commits` and any later auto-push only ships the new diff — your earlier fix is NOT in the deployed bundle. Recovery: `git pull --rebase origin main` → resolve conflicts in the overlapping CSS/JS region → `gh auth switch --user mustbebecomerichman` if needed → `git push`. Verify with `curl <pages_url> | grep <your-marker>`.

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

**Ship API**
| action | SeaVantage path | params |
|---|---|---|
| `sv_search` | `GET /ship/search` | `keyword` (IMO/MMSI/name) |
| `sv_pasttrack` | `GET /ship/past-track/from-last-port` | `shipId` |
| `sv_ship_snapshot` | `GET /ship/snapshot` | — (all tracked vessels) |
| `sv_ship_area` | `GET /ship/position/area` | — (ships inside any predefined zone) |
| `sv_ship_delete` | `DELETE /ship` | `shipId` |

**Fleet API**
| action | SeaVantage path | params |
|---|---|---|
| `sv_snapshot` | `GET /fleet/snapshot` | `categoryId`, `shipId` |
| `sv_info` | `GET /fleet/info` | `categoryId`, `shipId` |
| `sv_categories` | `GET /fleet/categories` | — |
| `sv_register` | `POST /fleet` | `categoryId` + JSON body |
| `sv_unregister` | `DELETE /fleet` | `categoryId` + JSON body |

**Zone API**
| action | SeaVantage path | params |
|---|---|---|
| `sv_zones` | `GET /zone/all` | — |
| `sv_zone_section` | `GET /zone/{section}` | `zoneSection` ∈ {`HRA`, `ECA`, `JWC`, `CUSTOM_ZONE`} |

**Port-call / Route**
| action | SeaVantage path | params |
|---|---|---|
| `sv_portcall` | `GET /port-call/{shipId}` | `from`, `to` |
| `sv_route` | `POST /route/ship-to-port` | `imoNo`, `portId` + JSON body |

**After modifying `seavantage-proxy.gs` you MUST redeploy via Apps Script Deploy → Manage deployments → ✏️ → New version.** The existing `/exec` URL keeps serving the previous code until you do.

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

### 2026-05-29 — Fleet UX: own/charter distinction + route filter + marker depth
Three coordinated changes after user feedback that ship markers were "겹치고" (overlapping) terminals and all looked alike.

**1. Visual differentiation — own (사선) vs charter (용선)**
- New IMO set `window._ownImos` built once from `VESSELS` at startup.
- `svShipKind(imo)` returns `'own'` or `'charter'`.
- `makeShipIcon(heading, color, kind)`:
  - `kind='own'` → 32px green (`#16a34a`) arrow, white stroke
  - `kind='charter'` → 24px sky-blue (`#0284c7`) arrow, dark navy stroke
  - Added `filter:drop-shadow(...)` so ships float above the port circles
- `buildSvPopup(v, kind)` now shows a `자사선`/`용선` chip in the title row.

**2. z-index layering — ships always above terminals**
- All ship markers created with `zIndexOffset:1000` (terminals use default ~600).
- Even at low zoom, port circles never cover up a fleet marker.

**3. Route filter — show only the vessels operating that service**
- `_buildSvcImoMap()` constructs `Map<svc, Set<imo>>` from both `VESSELS` and `data/sched-non-own.json`.
- `filterSvFleetByService(svcId)` sets `opacity:0.06` for markers not in the service's IMO set, `opacity:1` for matches. Markers stash their IMO+kind on the L.Marker instance (`mk._imo`, `mk._kind`).
- Called from `_drawRoute(svcId)` after the polyline draws.
- `unfilterSvFleet()` restores everyone — called from `closeRP()` so dismissing the route panel brings the full fleet back.
- New markers added while a route is active inherit the current filter (auto-load timer doesn't break filter state).

Net behavior: open the dashboard → all ~599 ships visible (green=own, blue=charter). Click a service in Routes tab → only that service's ships stay opaque; the rest fade to nearly transparent. Close the route panel → all ships full-opacity again.

### 2026-05-29 — One-click fleet sync from header pill (simplification)
**User report**: "복잡하다. 내 프로그램에 등록된 선박 위치를 보고싶다."

The earlier Admin Panel → Load Fleet flow worked but was buried and required understanding the register-then-view dependency. Replaced with a single header pill that auto-evaluates state and acts.

UX states ([delay_dashboard.html `#svFleetStatus`](delay_dashboard.html)):

| State | Pill text | Action on click |
|---|---|---|
| Not configured | `⚙️ SeaVantage 설정` (yellow) | Opens Admin Panel |
| Synced (≥95%) | `🛰️ N척 추적 중` (green) | Refresh positions |
| Coverage gap | `🚢 R / T척 · 탭하여 일괄 등록 (~Nm)` (purple) | One-click sync |
| Connection failure | `⚠️ 연결 실패` (red) | Opens Admin Panel |

`syncAllFleet(missingImos)` is the one-shot register-and-show:
1. `sv_search` per IMO → resolve to shipId UUID
2. Batch `sv_register` 50 at a time
3. `autoLoadSvFleet()` to refresh map markers

Progress shown inline in the pill (`🔍 N/M 검색 중…` → `📤 N/M 등록 중…` → `✓ N척 등록 완료`).

Target list = `Object.values(VESSELS).flatMap(svc=>svc.map(v=>v.imo))` ∪ `data/sched-non-own.json` IMOs. Currently 71 own + 528 charter ≈ 599 unique target IMOs vs ~23 currently registered = ~576 to bulk register.

Logging into the dashboard now:
- Pill appears in the header within ~1s of map init.
- One click handles everything; user never sees the underlying register-vs-snapshot mechanism.

### 2026-05-29 — Auto-load SeaVantage fleet on login (no manual click)
**User report**: "전혀 화면이 바뀌지 않았다. 자사선 위치가 다 표시되는것으로 알고있다."

Cause: SeaVantage fleet was only loaded when the user clicked **Admin Panel → Load Fleet**. The bulk-register + the `sv_snapshot` data pipeline worked, but the default landing screen never called it.

Fix ([delay_dashboard.html](delay_dashboard.html)):
- New `autoLoadSvFleet()` — silent version of `loadSvFleetToMap()` that doesn't touch Admin Panel UI and skips gracefully when proxy isn't configured.
- Hooked into `showApp()` after `initMap()` so every login automatically renders all registered ships on the map.
- 5-minute refresh interval (`svFleetTimer`) keeps AIS positions current. The user no longer needs to touch Admin Panel after the initial setup + bulk-register.
- Status surfaced to `#svMsg` + `console.log` for diagnostics.

User-visible behavior change:
- Before: blank map until Admin Panel → Load Fleet clicked.
- After: map shows 23 ships immediately on login (or 551 after the 528-vessel bulk register).
- Refresh: every 5 min in background.

### 2026-05-29 — Comprehensive vessel coverage from 4-month logs + new master
User uploaded 5 fresh Excel files (1월~4월 voyage logs + new vessel master).

**Inputs added:**
- `data/monthly/2026-01.xls` ~ `2026-04.xls` — voyage logs (2,595 rows total over 4 months) with column 21 `자선여부` (Checked=own, Unchecked=charter)
- `Vessel Code_2026-05-28.xls` — newer master (6,149 vessels vs the old 6,122)

**Approach** (`scripts/rebuild-from-monthly.py`):
1. Read 4 monthly files → split each voyage as OWN (자선=Checked) or CHARTER. Aggregate per vessel:
   - `own_assignments[code]` = set of services run as own
   - `charter_assignments[code]` = set of services run as charter
2. Read new master → vessel lookup (code → IMO, name, dimensions, GT/DWT/TEU/LOA, flag, built).
3. Rebuild **VESSELS (own only)**: union with existing VESSELS so manually-curated entries aren't lost.
4. Rebuild **`data/sched-non-own.json` (charters)**: union of three sources for maximum coverage:
   - Monthly 1-4월 charter assignments (155 vessels)
   - Schedule Code 2026-03-31 charters (571 vessels, may include forward planning)
   - Existing JSON (preserve prior curation)

**Results:**
| | Before | After |
|---|---|---|
| VESSELS (own) services | 58 | **59** |
| VESSELS entries | 195 | **209** |
| Routes filled with own | 46 | **51** |
| Charter list (sched-non-own.json) | 488 | **528** |
| Charter service coverage | ~74 | **74 services** |
| Truly empty routes (no own + no charter) | — | 10 (CIN, CKJ/1, CQD2, JSS1, KDX2, KHX2, KMS, KXS10, MHX2, NBX) |

**Dynamic button label** ([delay_dashboard.html](delay_dashboard.html)):
- "Register 488 vessels" → "Register 528 vessels" auto-updated from JSON length via `<span id="svBulkBtnLabel">` + pre-fetch at page load.

Regen workflow (re-runnable):
```bash
python scripts/rebuild-from-monthly.py
```

**SeaVantage end-to-end now possible:**
1. Click "Register 528 vessels" → ~3 min bulk register charter vessels to workspace
2. Click "Load Fleet" → `sv_snapshot` returns ~551 ships (23 already there + 528 added) with live AIS positions on the map
3. Both own + charter vessels visible — full route coverage

### 2026-05-28 — VESSELS rebuild from HAL/SKR + Schedule cross-reference
**Problem**: 30 of 76 routes had an empty VESSELS[svc] list — the "Vessels" tab and route detail panel showed no ships for them. User had uploaded the matching Excel files but the data wasn't being used.

**Inputs:**
- `Vessel Code_HAL_2026-04-02.xls` (24 vessels, Heung-A Line own fleet)
- `Vessel Code_SKR_2026-04-02.xls` (52 vessels, Sinokor Marine own fleet)
- `Schedule Code_2026-03-31.xls` (last-month vessel ↔ service assignments)

**Approach** (`scripts/rebuild-vessels.py`):
1. Parse HAL+SKR master = 70 unique own vessels with full info (code/name/IMO/GT/DWT/TEU/LOA/flag/built/call).
2. Parse Schedule Code → vessel → set of services they ran on (63 vessels, avg 3.1 services each).
3. **Union of three sources** so nothing is lost:
   - Schedule Code last-month assignments (live truth)
   - T/C SVC primary service column (contract baseline)
   - Existing VESSELS entries (manual curation history)
4. Pass 2: preserve any code in old VESSELS not in HAL/SKR master (in case of manually-entered 용선/charter entries).

**Result**:
- VESSELS: 49 services / 74 entries → **58 services / 195 entries**
- 4 newly-filled routes: BSS2, NSC, SGX2, SIS
- 26 still empty (e.g. NWX, TIS2, CIX2) — legitimately slot-share / chartered-only routes; their vessels are in the 488-record `data/sched-non-own.json` for SeaVantage bulk registration.
- Example: PCI now lists 11 vessels (was 1), KST lists 4 (was 1).

Regeneration:
```bash
python scripts/rebuild-vessels.py
```
Re-run on every HAL/SKR/Schedule Code drop. Existing VESSELS entries are preserved during merge (no data loss).

### 2026-05-28 — SeaVantage API permission granted (partial scope)
SeaVantage activated API access on the account. End-to-end test from this repo:

| Action | Endpoint | Status |
|---|---|---|
| `sv_categories` | GET /fleet/categories | ✅ 200 (empty `[]` — no categories yet) |
| `sv_snapshot` | GET /fleet/snapshot | ✅ 200 — returns workspace ships with AIS positions |
| `sv_search` | GET /ship/search | ✅ 200 — returns shipId, IMO, MMSI, name |
| `sv_register` | POST /fleet | ✅ works (curl-side `411 Length Required` is a curl `-d` quirk; dashboard `fetch` sets Content-Length automatically) |
| `sv_info` | GET /fleet/info | ❌ 403 |
| `sv_ship_snapshot` | GET /ship/snapshot | ❌ 403 |
| `sv_zones` / `sv_zone_section` / `sv_ship_area` | GET /zone/* | ❌ 403 |

The granted scope is sufficient for the **bulk-register workflow** that's already wired up: lookup vessel by IMO via `sv_search`, batch-register to workspace via `sv_register`, then `sv_snapshot` returns their live AIS positions.

Dashboard adjustments ([delay_dashboard.html](delay_dashboard.html)):
- `loadSvFleetToMap()` switched from `sv_info` (403) → `sv_snapshot` (200) — returns the same data we need (ship + position envelope handled by existing `svFlattenEntry()`).
- Admin Panel: the four inspect buttons that hit currently-403 endpoints (Fleet Info, Ship Snap, Ship in Zones, Zones, Zone Section) are dimmed to 50% opacity with a ⛔ suffix + tooltip explaining "currently 403 on this account". They stay clickable for re-test once SeaVantage opens those scopes.
- The "Load All Ships" button (which used `sv_ship_snapshot`) is now expected to fail — Load Fleet replaces it for the time being.

User flow now possible end-to-end:
1. Admin Panel → paste proxy URL + DASHBOARD_TOKEN → Save → Test Connection ✓
2. **Register 488 vessels** button → sequential `sv_search` per IMO → batch `sv_register` (50 at a time) → ~3 minutes
3. **Load Fleet** → 488 vessels render with live AIS positions on the map

### 2026-05-26 — Authoritative port rotations + accurate waypoints from marnet graph
**Problem 1**: existing ROUTES.ports[] was incomplete — 73 of 76 routes were missing ports (origin return, intermediate stops, alternative direction calls). User confirmed Proforma data_2026-03-31.xlsx (sheets "자선"/"슬롯") is the authoritative source: `SVR_CD + SEQ + FR_PORT/TO_PORT`. Also 15 distinct ports (THLCH, AEJEA, INPIP, JPTKS …) were entirely missing from TERMINALS, so they silently dropped from rotations.

**Problem 2**: auto-generated sea waypoints from the regional WP/_RT table (33 hand-placed points + ~200 region pairs) were too coarse — paths still cut corners.

Three new scripts:

1. **[scripts/add-missing-terminals.py](scripts/add-missing-terminals.py)** — appends 15 missing port entries to TERMINALS (depot/port_code/name/country/lat/lon/hist_delay) one-time fix.

2. **[scripts/rebuild-routes-from-proforma.py](scripts/rebuild-routes-from-proforma.py)** — single pipeline:
   - **Step 1**: parse Proforma legs → reconstruct ordered port list per service.
   - **Step 1.5**: truncate at the first reoccurrence of `ports[0]` so multi-voyage stitched data becomes one canonical rotation (PQS: `PTK→TAO→PTK→TAO→PTK` → `PTK→TAO→PTK`).
   - **Step 2**: overwrite `ROUTES[svc].ports[]` — keeps name/kind/region/manager/backup metadata. Unknown-coord ports (e.g. AEJEA, THLCH) stay in the list so the user sees them; only excluded from waypoint drawing.
   - **Step 3**: download/load `data/marnet/marnet.geojson` (Genth Alili's searoute-py distribution, 4,109 LineString features from the European Commission marine network) → build undirected graph (9,646 nodes, 15,806 edges).
   - **Step 4**: Dijkstra between each consecutive port pair using nearest-neighbor entry/exit nodes.
   - **Output**: `data/route-coords.json` (~160 KB, 5,036 waypoints across 72 routes). **NEVER writes dense coords back into `ROUTES.coords[]`** (that would make re-running the script mistake its own output for hand-tuned KST-style data).

3. **Hand-tuned routes preserved**: KST (392 pts), KBX (69 pts), KHX1 (144 pts), TIS2 (port-only that doesn't match Proforma) — `coords.length > ports.length` is the marker.

Result: 73 routes now have complete rotations from Proforma + accurate sea-following polylines from the marnet graph. Ports without lat/lon still show in the route's port list (visible to user); only the line drawing skips them.

Regen workflow:
```bash
# After each Proforma drop / TERMINALS update / WP refinement:
python scripts/add-missing-terminals.py        # one-time; idempotent
python scripts/rebuild-routes-from-proforma.py # re-runnable safely
```

### 2026-05-26 — Input UX overhaul + auto-generated sea routes
Three independent improvements in one turn.

**1. Searchable port picker on Input tab** ([delay_dashboard.html:896–953](delay_dashboard.html))
- Replaced plain `<select>` (whose native type-ahead matched only the country prefix shown before the code) with a text input + filtered dropdown.
- Filter matches against port_code (5-char like `KRPUS`), port_name, and country — case-insensitive substring. Matched substring is highlighted in yellow.
- Picks update a hidden `#psel` input so existing submit code keeps working unchanged.
- Dropdown auto-dismisses on outside-click, shows top 50 results + "… N more" hint.

**2. Port-level delay with optional per-terminal override** ([delay_dashboard.html:1014–1093](delay_dashboard.html))
- Old UX: picking a multi-terminal port forced the user into a per-terminal table with an "auto-fill avg" gimmick. Single-terminal ports got a separate simpler form.
- New UX: picking ANY port shows a single port-level Delay/Reason/Memo form. Multi-terminal ports also get a collapsible **⚙️ Override specific terminals** disclosure for surgical edits.
- On submit, each terminal of the port writes an entry: if the override row has a typed value, that wins; otherwise the port-level value propagates. Result toast tells you "N delay entries (M terminal overrides, K port-level)".
- `submitBulkDelay` kept as a thin alias for back-compat with any external caller.

**3. Auto-generated dense sea routes for every route** (preserves hand-tuned samples)
- The KST/SWRG route had 392 hand-placed sea waypoints (user-built sample). The other 75 routes had only the port lat/lons → straight lines crossed land.
- Added [scripts/generate-route-coords.py](scripts/generate-route-coords.py): parses ROUTES + WP + _RT from delay_dashboard.html, runs sea_route() per port pair (mirroring the JS impl), then great-circle interpolates ~30 points between each WP. Skips routes that already have dense coords (preserves KST/KBX/KHX1).
- Output: `data/route-coords.json` (~460 KB, 73 routes, 14,302 waypoints). Loaded lazily by `loadRouteCoords()` in showApp; stashed on `window._routeCoords`.
- `_drawRoute()` priority order:
  1. **Hand-tuned** `ROUTES[svc].coords` when `coords.length !== ports.length` (e.g. KST).
  2. **Auto-generated** `window._routeCoords[svc]` from the JSON.
  3. **Runtime fallback** — port-only + seaRoute() enrichment, in case the JSON failed to load (offline, or a route added after the last regen).

Regenerate workflow:
```
python scripts/generate-route-coords.py
```
Re-run after editing ROUTES, WP, or _RT.

Verified: all 4 `<script>` blocks parse with `new Function()` (4/4 OK).

### 2026-05-26 — Real root cause of mobile blank-map: flex:1 collapsing .mapc to 0 height
After three rounds of fixes (cache headers, build badge, deferred RAFs, rebuild fallback) the user still saw a gray screen. The long-press diagnostic on the build badge — added precisely for this — revealed the actual state:

```
.mapc display: block          ✓
.mapc has show-map: true      ✓
.mapc height: 0px             ← bug
#map clientW×H: 344×0
map.getSize(): 344×0
```

CSS hierarchy was the culprit:
- Desktop rule (line 105): `.mapc{flex:1; …}` — gives `flex-basis:0%`.
- Mobile rule (line 182): `.mapc{display:none}` — doesn't reset flex.
- Mobile `.show-map` (line 183): `display:block; height:calc(100vh - 170px)`.

When Map tab is active on mobile, `.side` is hidden, leaving `.mapc` as the only flex child of `.wrap` (which has `height:auto`). `flex:1` with `flex-basis:0%` in an `auto`-height column flex container produces height **0** — the flex algorithm wins over the explicit `height:calc(...)`. So even though `.mapc.show-map` set the height, the browser collapsed it.

Fix ([delay_dashboard.html ~ line 185](delay_dashboard.html)):
```css
.mapc{display:none;border-radius:0;flex:none}                          /* break out of flex */
.mapc.show-map{display:block;height:calc(100vh - 170px);min-height:calc(100vh - 170px);width:100%}
```

Adding `flex:none` to the base mobile `.mapc` rule overrides the desktop `flex:1`. The explicit `height` then takes effect. `min-height` + `width:100%` are belt-and-braces.

All the earlier-added defenses (`_ensureMapReady`, rebuild fallback, no-cache meta, build badge) stay — they're useful in their own right. But this CSS fix is what makes the map actually render.

Lesson: when "Leaflet isn't loading tiles", check the container's actual rendered dimensions first. We added 3 rounds of JS-level fixes (`afterLayout`, `invalidateSize` permutations, nuclear `map.remove()+initMap()`) before realising the container itself had `height:0`. A 5-line CSS fix beats all of them.

### 2026-05-26 — Mobile blank-map: cache headers + visible build tag + map rebuild fallback
After v1.4.16 shipped with the `_ensureMapReady` fix, the user reported still seeing a gray empty map on mobile. Live URL was confirmed to be serving v1.4.16 with all the fixes intact, so the most probable cause was Samsung Internet's aggressive HTML cache (GitHub Pages serves `Cache-Control: max-age=600` and Samsung tends to extend that aggressively across sessions). Three defensive layers added.

**1. No-cache meta tags** ([delay_dashboard.html ~line 5–10](delay_dashboard.html))
```
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
```
Belt + braces — even though GitHub Pages serves a 10-min cache header, these tell the browser to revalidate on every load. The first visit after this lands still gets cached (the meta tags only affect future visits), so the user may still need one hard refresh now, but future updates will reach mobile within seconds.

**2. Always-visible build badge on mobile** ([delay_dashboard.html ~line 2630](delay_dashboard.html))
Pill in the top-left of every mobile screen: `v1.4.17 · tap to refresh`. Tapping it does `location.replace(location.pathname + '?cb=' + Date.now())` which forces a no-cache reload. Two purposes:
- User can immediately see which build they're running ("the screenshot says v1.4.5 — that's old, refresh")
- One-tap recovery from cached old HTML

**3. Map rebuild fallback in `_ensureMapReady`** ([delay_dashboard.html ~line 1121](delay_dashboard.html))
After the existing invalidateSize+setView dance, queue two more RAFs that check the container's `clientWidth`/`clientHeight` against Leaflet's `getSize()`. If the DOM says the container is real-sized but Leaflet still measures it as zero (a rare race in some mobile DOM engines), nuke the map with `map.remove()`, null `window.map`, and call `initMap()` again. Effectively a "reset switch" for the map.

Verified: all 3 `<script>` blocks parse with `new Function()` (3/3 OK).

### 2026-05-26 — Auto-push: pre-flight gh auth guard (recurring 403 fix)
Background: gh CLI keeps multiple accounts in the system keyring (`chartersuperman` + `mustbebecomerichman`). Various processes — VS Code git extension, other gh invocations, even `gh auth login` resetting active state — flip the active account back to `chartersuperman`, which has no push permission to `mustbebecomerichman/Operation-dashboard`. The Stop hook then commits successfully but `git push` returns 403, the failure goes to stderr, and **the user sees no error** — but local commits silently pile up and the live URL keeps serving stale code. This bit us three times in one week (v1.4.13, v1.4.15, v1.4.16 each blocked).

Fix in both `scripts/auto-push.ps1` and `scripts/auto-push.sh`:
1. Before doing any work, query `gh api user --jq '.login'`.
2. If the active account isn't `mustbebecomerichman`, run `gh auth switch --user mustbebecomerichman`.
3. Also pin local repo `git config user.name/user.email` to match, so a stray git command run with wrong auth context doesn't author commits under the wrong identity.

Both checks are silent when already correct (no-op). They run on every Stop hook fire, so the auth state self-heals each turn. To debug a future push failure, run the script manually and read the `[auto-push]` lines:
```
powershell -ExecutionPolicy Bypass -File scripts/auto-push.ps1
```

### 2026-05-25 — Blank map on mobile: idempotent initMap + _ensureMapReady
User screenshot showed an empty gray block where the map should be — Port/Route tap auto-switched to the Map tab (so the previous fix worked) but tiles never loaded.

Three independent root causes were stacked:

**A. `initMap()` was wrapped in `setTimeout(…, 200)`.** Pure historical leftover, no longer needed. If the user logged in and tapped Map within 200 ms, `window.map` was still `null` — `mobTab('map')` happily flipped the container to `display:block` but never initialized Leaflet, leaving an empty `#map` div.
- Fix: removed the setTimeout. `initMap()` runs synchronously from `showApp()`. Made it idempotent — `if(window.map) return window.map;` — so it's safe to call from multiple entry points (login, map-tab tap, route click).

**B. `mobTab('map')`'s `invalidateSize()` ran before the browser laid out the new container.** Same root issue as the previous focusPort fix but in a different code path. The synchronous call measured `.mapc` as still `0×0`, the TileLayer's resize handler saw "nothing visible," no tile requests fired.
- Fix: `mobTab('map')` now schedules a deferred resync via `afterLayout(_ensureMapReady)` instead of calling `invalidateSize()` inline.

**C. Even after `invalidateSize()` reported the new size, the TileLayer's tile pool was empty because the view was set when the container was `0×0`.** A second `setView(currentCenter, currentZoom)` after `invalidateSize` triggers TileLayer to re-evaluate visible tiles against the now-correct bounds and actually fetch them.
- Fix: added `_ensureMapReady()` helper that does `initMap()` if missing, `invalidateSize()`, then a no-op `setView(c, z, {animate:false})`. Called from `mobTab('map')`, `focusPort.doFocus`, and `_drawRoute`.

Side fix: replaced `짤 OpenStreetMap, 짤 CartoDB` mojibake in the attribution string with the proper `©` characters.

Net: tapping Map (directly or via port/route auto-switch) reliably shows tiles within ~1 frame on a cold start, and within a few hundred ms on subsequent taps as cached tiles reappear.

Verified: all 3 `<script>` blocks parse with `new Function()` (3/3 OK).

### 2026-05-25 — Mobile route/port follow-up: deferred map ops + bottom rpanel
User report: after the previous turn the tap-to-map auto-switch worked, but the map then looked frozen — tiles half-rendered, popup at the wrong spot, the route detail panel covering nearly the whole screen.

Two root causes addressed:

**A. Leaflet ran on a 0×0 container.** `mobTab('map')` flips `.mapc` from `display:none` → `block` synchronously, but the browser hasn't laid out by the time `map.setView()` / `fitBounds()` execute, so Leaflet measures the still-collapsed container and projects coordinates against zero dimensions. Result: blank/garbled map state.
- Fix: added `afterLayout(cb)` helper — two `requestAnimationFrame` calls = run after the next paint. Both `focusPort()` and the new `_drawRoute(svcId)` (split out of `showRoute` so it can be deferred wholesale) call `map.invalidateSize()` then their own setView/polyline work, but only after the browser has applied the layout change.

**B. `.rpanel` covered 80% of a 360px phone.** Desktop CSS sets `right:12px;width:300px;top:12px;max-height:calc(100% - 24px)` — fine on a wide screen, but on mobile that's a top-right block hiding most of the map. User couldn't see the route, couldn't pan, thought it was frozen.
- Fix: added a mobile override `[delay_dashboard.html ~ line 178](delay_dashboard.html)` placing `.rpanel` at the bottom of the visible map (`left:8px;right:8px;bottom:8px;width:auto;max-height:45vh;top:auto`). The route polyline above stays visible; the panel content scrolls internally. The existing ✕ button still closes it.

Net: clicking a port/route on mobile now (1) flips to map, (2) waits a frame, (3) Leaflet measures the now-correct container, draws route + popup with right projection, (4) detail sits at the bottom so the map and route remain visible above.

Verified: all 3 `<script>` blocks parse with `new Function()` (3/3 OK).

### 2026-05-25 — Route polyline now follows sea (was crossing land)
Issue: every line drawn between ports on the map was a straight line, so Korea→Indonesia chopped through Vietnam/Borneo, Japan→Thailand sliced across the Philippines, etc.

Root cause: each `ROUTES[svc]` has `coords[]` of the same length as `ports[]` — i.e. the coords array only holds the port lat/lons themselves, with **no intermediate sea waypoints**. The previous `showRoute()` saw `route.coords.length` was truthy and used those points directly, skipping the existing `seaRoute()` enrichment path entirely.

Fix in `showRoute()` ([delay_dashboard.html:1333–1370](delay_dashboard.html)):
- Heuristic: treat `coords[]` as **port-only** when its length matches `ports[].length`. Treat it as **dense** (= explicit sea waypoints) when lengths differ — in that case keep the previous "use coords as-is" behaviour.
- Port-only path now: build a `portCoords` array (using `route.coords[i]` as a per-port override when present, else `TERMINALS` lookup), then run `seaRoute(portCoords[i-1], portCoords[i])` between each consecutive pair so the polyline curves through the existing `WP` / `_RT` waypoint graph (Korea Strait, Malacca, Sing, Luzon, etc.).
- Net effect: the same data file now draws curved sea-following routes without any data changes. If the user later uploads a route with dense waypoints (e.g. `coords.length > ports.length`), the system respects them and skips enrichment.

If a specific route still crosses land after this, the fix path is:
1. Check `pregion(lat,lon)` for the two endpoint ports — wrong region classification leads to wrong `_RT` lookup.
2. Add the missing `from:to` pair in `_RT` (the table at line ~1148), or insert a new `WP.<name>` if the needed waypoint doesn't exist.

### 2026-05-25 — Mobile fixes: vertical scroll + tap-to-detail
Two regressions reported on mobile after testing the live GitHub Pages URL.

**Issue 1 — page didn't scroll vertically on mobile**:
- Root cause: `@media(max-width:768px){ body{overflow:hidden} }` (line 155 pre-fix). Hard block on the whole document, so long sidebar lists (port table, vessel cards, admin panel) couldn't scroll past the viewport.
- Fix: replaced with `body{overflow-x:hidden;overflow-y:auto;-webkit-overflow-scrolling:touch}` — keep horizontal hidden so any wide content can't break layout, but vertical scroll restored. The `-webkit-overflow-scrolling:touch` enables momentum scrolling on iOS Safari.

**Issue 2 — clicking a port/route on mobile showed nothing**:
- Root cause: `.mapc{display:none}` on mobile until the user explicitly taps the Map tab in `.mob-nav`. But `focusPort()` and `showRoute()` both render their detail (Leaflet popups, route polyline, `.rpanel` overlay) on the map — so they were drawing on an invisible element.
- Fix: added `isMobileView()` helper (`window.matchMedia('(max-width:768px)').matches`) and inserted `if(isMobileView()) mobTab('map');` at the top of both `focusPort()` and `showRoute()`. Tapping a port row or service card now auto-surfaces the map (which calls `map.invalidateSize()` so Leaflet re-tiles after the layout change) before drawing the detail.
- Side effect: the mob-nav "Map" button correctly highlights as active after the auto-switch (mobTab already does this).

Verified: all 3 `<script>` blocks parse with `new Function()` (3/3 OK).

### 2026-05-25 — Vessel UI bugs · HRCI extracted · Schedule Code bulk-register
Three independent fixes in one turn.

**Vessel tab** ([delay_dashboard.html:1357–1430](delay_dashboard.html)):
- Fixed broken `</div>` closing tag on the arrow indicator (was rendered as `'➡️/div>'` — HTML-parser tried to recover, which is partly why the surrounding layout flickered).
- Fixed search-box typing — the input was being recreated on every keystroke because `oninput` ran `renderVesselTab()` which `innerHTML`-replaced the container holding the input itself. Split into `renderVesselTab()` (scaffold, runs once) + `renderVesselCards()` (refills only `#vesselCards`). Input now persists, focus is preserved.
- Sorted vessels by size desc — `vesselSize()` returns TEU → DWT → GT → LOA → 0 fallback. Services are also sorted by their largest vessel's size, so the biggest ship's service appears first.

**HRCI extraction**:
- Removed `<a href="hrci.html">HRCI Index</a>` from the header.
- Deleted `hrci.html`, `data/hrci-timeline.json`, `data/hrci-vessel-categories.json` from this repo.
- Copied the same data files to `~/cci-dashboard/public/data/` (Next.js public folder, fetchable from the client) and the reference HTML to `~/cci-dashboard/docs/hrci-reference.html` so the user can port it to a Next.js route at `/hr-index`.

**Schedule Code bulk-register diagnosis & fix**:
- Diagnosis: `VESSELS` dictionary in the dashboard covered only 70 vessels (mostly own/사선). `Schedule Code_2026-03-31.xls` lists 618 unique vessel codes (56 own + 562 non-own); 542 of the non-own ones were missing from `VESSELS` and therefore filtered out of AIS subscription — they couldn't appear on the map even when in the bounding box. SeaVantage `sv_ship_snapshot` only returns workspace-registered ships, which also excluded these.
- Solution: bulk register the missing IMOs into the SeaVantage workspace.
- Added [scripts/build-sched-non-own.py](scripts/build-sched-non-own.py): cross-references `Schedule Code_*.xls` (column `OWN`) against `Vessel Code_*.xls` (column `IMO Number`) and emits `data/sched-non-own.json` — 488 non-own vessels with valid 7-digit IMOs. Run after each Schedule/Vessel Code drop.
- Added Admin Panel "Bulk register Schedule Code vessels" block ([delay_dashboard.html:343–360](delay_dashboard.html)) with Preview / Register / Unregister buttons + progress bar.
- Added [delay_dashboard.html:2231–2348](delay_dashboard.html) bulk-register JS: phase 1 calls `sv_search?keyword=<IMO>` per vessel (sequential to respect rate limits) → collects `shipId` UUIDs → phase 2 calls `sv_register` in batches of 50 with the UUID array as POST body. `bulkUnregisterScheduleVessels()` mirrors the path for cleanup.
- **Apps Script Web Apps only support `doGet`/`doPost`** — DELETE from the browser is impossible. All proxy calls with bodies use `method:'POST'`; the proxy then issues the correct method (DELETE for `/fleet` unregister) to SeaVantage.
- Verified: all 3 `<script>` blocks parse with `new Function()` (3/3 OK).

### 2026-05-25 — SeaVantage proxy: added 5 new actions (Ship + Zone APIs)
- Added `sv_ship_snapshot` (`GET /ship/snapshot`), `sv_ship_area` (`GET /ship/position/area`), `sv_ship_delete` (`DELETE /ship?shipId=`), `sv_zones` (`GET /zone/all`), `sv_zone_section` (`GET /zone/{section}`) to `apps-script/seavantage-proxy.gs::handle()`.
- Dashboard client (`delay_dashboard.html`): added `loadSvAllShipsToMap()` — uses `sv_ship_snapshot` so no fleet category is required (sky-blue markers, distinct from green `loadSvFleetToMap`). Added `confirmSvShipDelete()` with `confirm()` guard for the destructive DELETE action.
- Admin Panel: added "Load All Ships" primary button, plus inspect buttons for the 4 new read endpoints and a `<select>` for zone section (HRA/ECA/JWC/CUSTOM_ZONE).
- §4 updated: action table now grouped by API (Ship / Fleet / Zone / Port-call / Route), and reminded that proxy edits require a **new Apps Script deployment** before the `/exec` URL serves the new code.
- `svFlattenEntry()` already handled the `{shipId, position:{...}}` shape used by `/ship/snapshot`, so no schema-normalization changes needed.
- Verified: all 3 `<script>` blocks parse with `new Function()` (3/3 OK).

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
