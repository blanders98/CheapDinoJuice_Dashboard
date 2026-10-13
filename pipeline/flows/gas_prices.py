"""
Main Prefect flow for the CheapDinoJuice gas price pipeline.

Run modes:
    - Full reload (default in CI / first local run):
        python -m pipeline.flows.gas_prices

    - Incremental (detects latest period in DB automatically):
        python -m pipeline.flows.gas_prices --incremental
"""

import argparse
from prefect import flow, get_run_logger

from pipeline.config import BULK_START_DATE, DB_PATH, DOCS_DATA_DIR
from pipeline.tasks.fetch import fetch_eia_records
from pipeline.tasks.load import setup_schema, load_records, get_latest_period
from pipeline.tasks.transform import run_transformations
from pipeline.tasks.export import ensure_geojson, export_monthly_json


@flow(name="gas-prices-pipeline", log_prints=True)
def gas_prices_pipeline(incremental: bool = False) -> None:
    logger = get_run_logger()

    # 1. Guarantee schema exists
    setup_schema(DB_PATH)

    # 2. Determine fetch window
    if incremental:
        start_date = get_latest_period(DB_PATH)
        logger.info(f"Incremental load - fetching from {start_date}")
    else:
        start_date = BULK_START_DATE
        logger.info(f"Full reload - fetching from {start_date}")

    # 3. Fetch monthly retail prices from EIA (monthly = nationwide state coverage)
    records = fetch_eia_records(start_date, frequency="monthly")

    # 4. Load into raw layer
    load_records(records, DB_PATH)

    # 5. Build mart tables via SQL transforms
    run_transformations(DB_PATH)

    # 6. Export static JSON for GitHub Pages
    ensure_geojson()
    months = export_monthly_json(DB_PATH, DOCS_DATA_DIR)

    logger.info(f"Pipeline complete — {len(months)} months exported to {DOCS_DATA_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the gas prices pipeline")
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Fetch only new data since the last stored period (default: full reload)",
    )
    args = parser.parse_args()
    gas_prices_pipeline(incremental=args.incremental)
