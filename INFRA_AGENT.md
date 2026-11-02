# Infrastructure Agent

Third agent in the sidebar (after Identity and Compliance). It shows ITOM site
health and raises iEngage tickets for problem devices.

## What it does
1. A donut chart of all locations by combined score status (critical, warning, healthy), from query 2.
2. Click a status to list its sites, with score, device counts and healthy %.
3. Click a site to see its problem devices (name, status, source, type, last seen, silent for), from query 1.
4. Tick devices (or use "Select all shown devices") and raise one iEngage ticket for the site. The
   ticket description lists every selected device name with its status and source.

## Files
| File | Purpose |
|---|---|
| `App/integration/itom/sql/site_alerts.sql` | Query 1: problem devices at P1/P2 sites (latest successful sync) |
| `App/integration/itom/sql/site_scores.sql` | Query 2: one row per location with score and device counts |
| `App/integration/itom/client.py` | Read-only ITOM client (runs only the two bundled SELECT queries) |
| `App/integration/itom/config.py` | `ITOM_DB_*` settings |
| `App/integration/itom/mock_data.py` | Sample data for `ITOM_USE_MOCK_DATA=true` / UI preview |
| `App/services/infra/service.py` | Status summary, sites per status, devices per site |
| `App/services/infra/ticket_service.py` | Builds and raises the site ticket |
| `App/integration/iengage/infra_ticket_service.py` | iEngage payload and description (reuses the patch ticket client) |
| `StreamlitApp/infra_agent_page.py` | The dashboard page |
| `Tests/test_infra_agent.py` | Tests (mock data, no database needed) |

## .env settings
```
# ITOM database (read-only). Separate from TechAdmin's own DB_* settings.
ITOM_DB_HOST=172.18.51.38
ITOM_DB_PORT=5432
ITOM_DB_NAME=itom_db
ITOM_DB_USER=itom_ro
ITOM_DB_PASSWORD=<itom_ro password>
ITOM_USE_MOCK_DATA=false          # true = sample data, no database
ITOM_CACHE_SECONDS=300            # how long the page reuses query results

# Optional iEngage overrides for infrastructure tickets (fall back to IENGAGE_*)
INFRA_IENGAGE_CATEGORY_ID=
INFRA_IENGAGE_SUBCATEGORY_ID=
INFRA_IENGAGE_PRIORITY_ID=
INFRA_IENGAGE_P1_PRIORITY_ID=     # used for critical sites
INFRA_IENGAGE_P2_PRIORITY_ID=     # used for warning sites
```
iEngage itself uses the existing `IENGAGE_*` settings, including `IENGAGE_DRY_RUN`.

## Safety
- Every ITOM connection is opened with `default_transaction_read_only=on` and a statement timeout,
  and only the two bundled SELECT queries can run.
- Tickets need an explicit "Approve and raise" in a confirmation dialog that previews the description.

## Try it without the database
```
TECHADMIN_UI_PREVIEW=true streamlit run StreamlitApp/app.py
```
or set `ITOM_USE_MOCK_DATA=true` in a normal run.
