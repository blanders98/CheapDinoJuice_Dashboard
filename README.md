# CheapDinoJuice

Interactive US regular gasoline price dashboard. State-level weekly prices from the [EIA Open Data API](https://www.eia.gov/opendata/), stored in DuckDB, exported as static JSON, rendered with Leaflet.js on GitHub Pages.

**Website:** https://blanders98.github.io/CheapDinoJuice_Dashboard/

## Stack

| Layer | Tool |
|---|---|
| Orchestration | [Prefect 3](https://docs.prefect.io/) |
| Storage | [DuckDB](https://duckdb.org/) |
| Source | [EIA API v2](https://www.eia.gov/opendata/) |
| Frontend | [Leaflet.js](https://leafletjs.com/) |
| Hosting | GitHub Pages |
| CI/CD | GitHub Actions (weekly) |

## Architecture

```
EIA API  -->  fetch.py  -->  raw.eia_weekly_prices (DuckDB)
                        |
                        | transform.py
                        |
                  mart.monthly_state_prices (DuckDB)
                        |
                        | export.py
                        |
              docs/data/prices_YYYY-MM.json --> Leaflet map
```

The pipeline runs in GitHub Actions every Monday. DuckDB is stateless in CI - all data is fetched fresh from EIA each run. Locally, the pipeline is incremental by default after the first full load.

## Setup

### 1. Prerequisites

```bash
python -m venv .venv
source .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. API key

Get a free key at <https://www.eia.gov/opendata/> and put it in `./config/eia_api_key.txt`:

The file is gitignored. In CI, set the `EIA_API_KEY` repository secret.

### 3. First run (bulk load from Jan 2024)

```bash
python -m pipeline.flows.gas_prices
```

This will:
1. Fetch thousands of weekly state-level price records from EIA
2. Store them in `db/gas_prices.duckdb`
3. Build `mart.monthly_state_prices` via SQL
4. Export one JSON per month + `manifest.json` to `docs/data/`
5. Download `docs/data/us-states.geojson` if not present

### 4. Subsequent runs (incremental)

```bash
python -m pipeline.flows.gas_prices --incremental
```

### 5. Local preview

Open `docs/index.html` in a browser via a local server (required for `fetch()` to work):

```bash
python -m http.server 8000 --directory docs
# then open http://localhost:8000
```

## DuckDB schema

```sql
-- Raw layer: append-only weekly readings
raw.eia_weekly_prices   (period, duoarea, area_name, product, process, value, ...)

-- Mart: monthly averages per state
mart.monthly_state_prices  (month, duoarea, state_abbrev, area_name, avg_price, ...)

-- Mart: national monthly averages (from NUS duoarea)
mart.national_monthly_prices  (month, national_avg, national_min, national_max)
```
