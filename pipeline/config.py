from pathlib import Path
import os

ROOT_DIR = Path(__file__).parent.parent

DB_PATH = ROOT_DIR / "db" / "gas_prices.duckdb"
DOCS_DATA_DIR = ROOT_DIR / "docs" / "data"

EIA_BASE_URL = "https://api.eia.gov/v2"
EIA_ENDPOINT = "/petroleum/pri/gnd/data/"

# Regular Gasoline (All Formulations), Retail Prices
EIA_PRODUCT = "EPM0"
EIA_PROCESS = "PTE"

BULK_START_DATE = "2024-01-01"
PAGE_SIZE = 5000

# DuckDB runtime settings (conservative for CI; local has plenty of headroom)
DUCKDB_MEMORY_LIMIT = os.environ.get("DUCKDB_MEMORY_LIMIT", "2GB")
DUCKDB_THREADS = int(os.environ.get("DUCKDB_THREADS", "4"))

# US states GeoJSON - well-known public domain source, committed on first pipeline run
GEOJSON_URL = (
    "https://raw.githubusercontent.com/PublicaMundi/MappingAPI"
    "/master/data/geojson/us-states.json"
)
GEOJSON_PATH = DOCS_DATA_DIR / "us-states.geojson"


def get_api_key() -> str:
    key = os.environ.get("EIA_API_KEY", "").strip()
    if key:
        return key
    # Check both the new config/ location and the repo root (backwards compat)
    for candidate in (ROOT_DIR / "config" / "eia_api_key.txt", ROOT_DIR / "eia_api_key.txt"):
        if candidate.exists():
            return candidate.read_text().strip()
    raise EnvironmentError(
        "EIA API key not found. Set EIA_API_KEY env var or create config/eia_api_key.txt."
    )
