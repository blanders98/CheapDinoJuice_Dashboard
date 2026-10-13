from pathlib import Path
from prefect import task, get_run_logger
from pipeline.tasks.load import get_connection
from pipeline.config import DB_PATH


# State-level duoarea codes are exactly 3 chars starting with 'S' (e.g. SCA, STX).
# SUBSTR(duoarea, 2) produces the standard 2-letter postal abbreviation.
# Source is monthly EIA retail prices — consistent frequency across all 50 states.
_MONTHLY_ROLLUP = """
CREATE OR REPLACE TABLE mart.monthly_state_prices AS
SELECT
    DATE_TRUNC('month', period)::DATE  AS month,
    duoarea,
    SUBSTR(duoarea, 2)                 AS state_abbrev,
    ANY_VALUE(area_name)               AS area_name,
    ROUND(AVG(value), 3)::DOUBLE       AS avg_price,
    ROUND(MIN(value), 3)::DOUBLE       AS min_price,
    ROUND(MAX(value), 3)::DOUBLE       AS max_price,
    COUNT(*)::INTEGER                  AS week_count
FROM raw.eia_weekly_prices
WHERE value IS NOT NULL
  AND LENGTH(duoarea) = 3
  AND duoarea LIKE 'S%'
GROUP BY 1, 2, 3
ORDER BY 1, 3
"""

_NATIONAL_MONTHLY = """
CREATE OR REPLACE TABLE mart.national_monthly_prices AS
SELECT
    DATE_TRUNC('month', period)::DATE AS month,
    ROUND(AVG(value), 3)::DOUBLE      AS national_avg,
    ROUND(MIN(value), 3)::DOUBLE      AS national_min,
    ROUND(MAX(value), 3)::DOUBLE      AS national_max
FROM raw.eia_weekly_prices
WHERE
    value IS NOT NULL
    AND duoarea = 'NUS'
GROUP BY 1
ORDER BY 1
"""


@task(name="run-transformations")
def run_transformations(db_path: Path = DB_PATH) -> None:
    logger = get_run_logger()
    conn = get_connection(db_path)

    conn.execute(_MONTHLY_ROLLUP)
    state_rows = conn.execute("SELECT COUNT(*) FROM mart.monthly_state_prices").fetchone()[0]
    logger.info(f"mart.monthly_state_prices: {state_rows} rows")

    conn.execute(_NATIONAL_MONTHLY)
    nat_rows = conn.execute("SELECT COUNT(*) FROM mart.national_monthly_prices").fetchone()[0]
    logger.info(f"mart.national_monthly_prices: {nat_rows} rows")

    conn.close()
