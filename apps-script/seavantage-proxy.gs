/**
 * SeaVantage Insight API proxy for Operation Dashboard.
 *
 * WHY a proxy?
 *   - SeaVantage uses HTTP Basic Auth. Embedding the password in the public
 *     dashboard (GitHub Pages) would leak it instantly.
 *   - This Apps Script holds the credentials in Script Properties
 *     (Google-encrypted, never in the dashboard source) and signs requests
 *     server-side.
 *   - It also bypasses any CORS limitation the SeaVantage API may have.
 *
 * SETUP — one-time
 *   1. Open https://script.google.com  →  New project
 *   2. Replace the contents of Code.gs with THIS FILE
 *   3. Click the gear icon (Project Settings) → Script Properties → Add:
 *        Name: SV_USERNAME      Value: <your SeaVantage login email>
 *        Name: SV_PASSWORD      Value: <your SeaVantage password>
 *        Name: DASHBOARD_TOKEN  Value: <pick a random ~32-char string>
 *      (Copy the DASHBOARD_TOKEN value separately — you'll paste it into
 *       the dashboard's Admin Panel later.)
 *   4. Deploy → New deployment → Type: Web app
 *        Description: SeaVantage proxy v1
 *        Execute as:  Me (your account)
 *        Who has access: Anyone
 *   5. Copy the deployment "Web app URL" (https://script.google.com/.../exec)
 *      and send it to the dashboard integration step.
 *
 * SMOKE TEST after deploy
 *   In a browser, open:
 *     <WEB_APP_URL>?action=sv_categories&token=<DASHBOARD_TOKEN>
 *   Expected: JSON array of fleet categories from your workspace.
 *
 * Adding/changing endpoints
 *   All SeaVantage paths are dispatched in handle() below. To expose a new
 *   endpoint, add a `case 'sv_<name>'` branch.
 *
 * Security notes
 *   - Anyone with DASHBOARD_TOKEN can call the proxy. The token is embedded
 *     in the public dashboard, so treat it as obscurity, not security.
 *     Rotate it if you suspect leakage (regenerate in Script Properties +
 *     update the dashboard).
 *   - Hardening options (later):
 *       * Verify the caller's email against an allow-list (requires
 *         session-token round-trip).
 *       * Move to OIDC / IAP if you outgrow Apps Script.
 */

var SV_BASE = 'https://insight.seavantage.com/api';

function doGet(e)  { return handle(e, null); }
function doPost(e) {
  var body = null;
  try { body = e.postData && e.postData.contents ? JSON.parse(e.postData.contents) : null; } catch (_) {}
  return handle(e, body);
}

function handle(e, body) {
  var props = PropertiesService.getScriptProperties();
  var expectedToken = props.getProperty('DASHBOARD_TOKEN');
  if (expectedToken && (e.parameter.token || '') !== expectedToken) {
    return jsonOut({ error: 'unauthorized' });
  }
  var action = (e.parameter.action || '').toLowerCase();
  try {
    switch (action) {
      // Ship API
      case 'sv_search':
        return jsonOut(svFetch('/ship/search', { qs: { keyword: e.parameter.keyword } }));
      case 'sv_pasttrack':
        return jsonOut(svFetch('/ship/past-track/from-last-port', { qs: { shipId: e.parameter.shipId } }));

      // Fleet API
      case 'sv_snapshot':
        return jsonOut(svFetch('/fleet/snapshot', { qs: pick(e.parameter, ['categoryId', 'shipId']) }));
      case 'sv_info':
        return jsonOut(svFetch('/fleet/info', { qs: pick(e.parameter, ['categoryId', 'shipId']) }));
      case 'sv_categories':
        return jsonOut(svFetch('/fleet/categories'));
      case 'sv_register':
        return jsonOut(svFetch('/fleet', {
          method: 'post',
          qs: pick(e.parameter, ['categoryId']),
          payload: JSON.stringify(body || [])
        }));
      case 'sv_unregister':
        return jsonOut(svFetch('/fleet', {
          method: 'delete',
          qs: pick(e.parameter, ['categoryId']),
          payload: JSON.stringify(body || [])
        }));

      // Port-call history (used for delay calculation)
      case 'sv_portcall':
        return jsonOut(svFetch('/port-call/' + encodeURIComponent(e.parameter.shipId), {
          qs: pick(e.parameter, ['from', 'to'])
        }));

      // Route calculation
      case 'sv_route':
        return jsonOut(svFetch('/route/ship-to-port', {
          method: 'post',
          qs: pick(e.parameter, ['imoNo', 'portId']),
          payload: JSON.stringify(body || {})
        }));

      default:
        return jsonOut({ error: 'unknown action', got: action });
    }
  } catch (err) {
    return jsonOut({ error: String(err && err.stack || err) });
  }
}

function svFetch(path, options) {
  options = options || {};
  var props = PropertiesService.getScriptProperties();
  var user = props.getProperty('SV_USERNAME');
  var pass = props.getProperty('SV_PASSWORD');
  if (!user || !pass) {
    return { error: 'SV_USERNAME / SV_PASSWORD not set in Script Properties' };
  }

  var url = SV_BASE + path;
  if (options.qs) {
    var qs = Object.keys(options.qs).map(function (k) {
      return k + '=' + encodeURIComponent(options.qs[k]);
    }).join('&');
    if (qs) url += (path.indexOf('?') >= 0 ? '&' : '?') + qs;
  }

  var headers = {
    Authorization: 'Basic ' + Utilities.base64Encode(user + ':' + pass),
    Accept: 'application/json'
  };
  var fetchOpts = {
    method: options.method || 'get',
    headers: headers,
    muteHttpExceptions: true
  };
  if (options.payload) {
    fetchOpts.payload = options.payload;
    fetchOpts.contentType = 'application/json';
  }

  var resp = UrlFetchApp.fetch(url, fetchOpts);
  var code = resp.getResponseCode();
  var text = resp.getContentText();
  if (code >= 400) {
    return { error: 'SeaVantage ' + code, body: safeJson(text) };
  }
  // 204 No Content (register / unregister)
  if (code === 204 || !text) return { ok: true };
  return safeJson(text);
}

function pick(obj, keys) {
  var out = {};
  keys.forEach(function (k) {
    if (obj[k] !== undefined && obj[k] !== '') out[k] = obj[k];
  });
  return out;
}

function safeJson(text) {
  try { return JSON.parse(text); } catch (_) { return { raw: text }; }
}

function jsonOut(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
