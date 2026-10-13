from pathlib import Path
import pandas as pd
import duckdb
from prefect import task, get_run_logger
from pipeline.config import DB_PATH, DUCKDB_MEMORY_LIMIT, DUCKDB_THREADS


def get_connection(db_path: Path = DB_PATH) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_path))
    conn.execute(f"SET memory_limit='{DUCKDB_MEMORY_LIMIT}'")
    conn.execute(f"SET threads={DUCKDB_THREADS}")
    return conn


@task(name="setup-schema")
def setup_schema(db_path: Path = DB_PATH) -> None:
    conn = get_connection(db_path)
    conn.execute("CREATE SCHEMA IF NOT EXISTS raw")
    conn.execute("CREATE SCHEMA IF NOT EXISTS mart")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS raw.eia_weekly_prices (
            period             DATE      NOT NULL,
            duoarea            VARCHAR   NOT NULL,
            area_name          VARCHAR,
            product            VARCHAR   NOT NULL,
            product_name       VARCHAR,
            process            VARCHAR   NOT NULL,
            process_name       VARCHAR,
            series             VARCHAR,
            series_description VARCHAR,
            value              DOUBLE,
            units              VARCHAR,
            frequency          VARCHAR,
            ingested_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Schema migration: add frequency column to any pre-existing DB
    existing = {r[0] for r in conn.execute("DESCRIBE raw.eia_weekly_prices").fetchall()}
    if "frequency" not in existing:
        conn.execute("ALTER TABLE raw.eia_weekly_prices ADD COLUMN frequency VARCHAR")
    conn.close()


@task(name="load-records")
def load_records(records: list[dict], db_path: Path = DB_PATH) -> int:
    """
    Upsert records into raw.eia_weekly_prices.
    Strategy: delete any existing rows that overlap the incoming date range, then insert.
    This is safe for both full reloads (CI) and incremental local runs.
    """
    logger = get_run_logger()
    if not records:
        logger.warning("No records to load - skipping")
        return 0

    df = pd.DataFrame(records)
    df["period"] = pd.to_datetime(df["period"]).dt.date

    conn = get_connection(db_path)

    min_period = df["period"].min()
    max_period = df["period"].max()

    stale = conn.execute(
        "SELECT COUNT(*) FROM raw.eia_weekly_prices WHERE period BETWEEN ? AND ?",
        [min_period, max_period],
    ).fetchone()[0]
    conn.execute(
        "DELETE FROM raw.eia_weekly_prices WHERE period BETWEEN ? AND ?",
        [min_period, max_period],
    )

    # DuckDB can SELECT directly from a pandas DataFrame in-process - no CSV/temp files needed
    conn.execute("""
        INSERT INTO raw.eia_weekly_prices
            (period, duoarea, area_name, product, product_name,
             process, process_name, series, series_description, value, units, frequency)
        SELECT
            period::DATE, duoarea, area_name, product, product_name,
            process, process_name, series, series_description, value, units, frequency
        FROM df
    """)

    total = conn.execute("SELECT COUNT(*) FROM raw.eia_weekly_prices").fetchone()[0]
    conn.close()

    logger.info(f"Removed {stale} stale rows; inserted {len(records)}; table total: {total}")
    return total


@task(name="get-latest-period")
def get_latest_period(db_path: Path = DB_PATH) -> str:
    """Return the start date for incremental fetch: 2 weeks before the latest stored period."""
    from datetime import timedelta
    from pipeline.config import BULK_START_DATE

    conn = get_connection(db_path)
    result = conn.execute("SELECT MAX(period) FROM raw.eia_weekly_prices").fetchone()
    conn.close()

    if result[0] is None:
        return BULK_START_DATE

    latest = result[0]
    # Overlap by 2 weeks to catch any late-arriving EIA revisions
    return (latest - timedelta(weeks=2)).isoformat()
