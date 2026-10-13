import time
import requests
from prefect import task, get_run_logger
from pipeline.config import (
    EIA_BASE_URL, EIA_ENDPOINT, EIA_PRODUCT, EIA_PROCESS,
    BULK_START_DATE, PAGE_SIZE, get_api_key,
)


@task(name="fetch-eia-data", retries=3, retry_delay_seconds=30)
def fetch_eia_records(start_date: str = BULK_START_DATE, frequency: str = "monthly") -> list[dict]:
    """Paginate through the EIA v2 API and return retail gas price records at the given frequency."""
    logger = get_run_logger()
    api_key = get_api_key()
    url = EIA_BASE_URL + EIA_ENDPOINT

    records: list[dict] = []
    offset = 0

    while True:
        params = {
            "api_key": api_key,
            "frequency": frequency,
            "data[0]": "value",
            "facets[product][]": EIA_PRODUCT,
            "facets[process][]": EIA_PROCESS,
            "start": start_date,
            "sort[0][column]": "period",
            "sort[0][direction]": "asc",
            "length": PAGE_SIZE,
            "offset": offset,
        }

        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()

        payload = resp.json().get("response", {})
        batch: list[dict] = payload.get("data", [])
        total: int = int(payload.get("total", 0))

        logger.info(f"[{frequency}] Page offset={offset}: got {len(batch)} of {total} total records")

        for row in batch:
            records.append(_normalize(row, frequency))

        offset += len(batch)
        if offset >= total or not batch:
            break

        time.sleep(0.15)  # stay well within EIA rate limits

    logger.info(f"[{frequency}] Fetch complete — {len(records)} records retrieved")
    return records


def _normalize(row: dict, frequency: str) -> dict:
    """Standardize EIA API field names (hyphens → underscores) and cast value."""
    return {
        "period": row["period"],
        "duoarea": row["duoarea"],
        "area_name": row.get("area-name") or row.get("area_name", ""),
        "product": row["product"],
        "product_name": row.get("product-name") or row.get("product_name", ""),
        "process": row["process"],
        "process_name": row.get("process-name") or row.get("process_name", ""),
        "series": row.get("series", ""),
        "series_description": row.get("series-description") or row.get("series_description", ""),
        "value": float(row["value"]) if row.get("value") is not None else None,
        "units": row.get("units", ""),
        "frequency": frequency,
    }
