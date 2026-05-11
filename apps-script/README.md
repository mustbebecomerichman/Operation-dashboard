# Apps Script proxies

Google Apps Script Web Apps that the dashboard talks to.

## seavantage-proxy.gs

Proxies REST calls to [insight.seavantage.com/api](https://insight.seavantage.com/api/swagger-ui/index.html) so the dashboard can read fleet/ship data without exposing the SeaVantage Basic Auth credentials.

**Setup instructions live at the top of the file** (search for `SETUP — one-time`). Brief recap:

1. New Apps Script project → paste `seavantage-proxy.gs` into `Code.gs`.
2. Project Settings → Script Properties — add:
   - `SV_USERNAME` — SeaVantage login email
   - `SV_PASSWORD` — SeaVantage password
   - `DASHBOARD_TOKEN` — random ~32-char string (you also paste this into the dashboard)
3. Deploy → New deployment → Web app, execute as Me, anyone has access.
4. Copy the Web app URL — that's what the dashboard calls.

## Endpoint surface

| `action=` | SeaVantage path | Use |
|---|---|---|
| `sv_search&keyword=` | `GET /ship/search` | IMO/MMSI/name → ship UUID |
| `sv_categories` | `GET /fleet/categories` | List workspace fleet categories |
| `sv_snapshot&categoryId=&shipId=` | `GET /fleet/snapshot` | Current positions of registered ships |
| `sv_info&categoryId=&shipId=` | `GET /fleet/info` | Registered ships + destination + PTA |
| `sv_register&categoryId=` (POST body: `[uuid, ...]`) | `POST /fleet` | Add ships to category |
| `sv_unregister&categoryId=` (DELETE body: `[uuid, ...]`) | `DELETE /fleet` | Remove ships from category |
| `sv_portcall&shipId=&from=&to=` | `GET /port-call/{shipId}` | Arrival/departure history |
| `sv_pasttrack&shipId=` | `GET /ship/past-track/from-last-port` | Track since last port |
| `sv_route&imoNo=&portId=` (POST body: route opts) | `POST /route/ship-to-port` | Calculated route + ETA |

All calls require `&token=<DASHBOARD_TOKEN>`.

## Quick smoke test

After deploy, open in a browser:

```
<WEB_APP_URL>?action=sv_categories&token=<DASHBOARD_TOKEN>
```

Should return a JSON array of your workspace's fleet categories. A `401` or `unauthorized` means the token is wrong; `403` from SeaVantage means the credentials are wrong.
