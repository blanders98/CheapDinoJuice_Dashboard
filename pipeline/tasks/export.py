import json
from datetime import datetime, timezone
from pathlib import Path

import requests
from prefect import task, get_run_logger

from pipeline.config import DB_PATH, DOCS_DATA_DIR, GEOJSON_URL, GEOJSON_PATH
from pipeline.tasks.load import get_connection


@task(name="ensure-geojson")
def ensure_geojson() -> None:
    """Download the US states GeoJSON once and commit it alongside the data exports."""
    if GEOJSON_PATH.exists():
        return

    logger = get_run_logger()
    logger.info(f"Downloading US states GeoJSON from {GEOJSON_URL}")
    GEOJSON_PATH.parent.mkdir(parents=True, exist_ok=True)

    resp = requests.get(GEOJSON_URL, timeout=30)
    resp.raise_for_status()
    GEOJSON_PATH.write_text(resp.text, encoding="utf-8")
    logger.info(f"Saved GeoJSON to {GEOJSON_PATH}")


@task(name="export-monthly-json")
def export_monthly_json(db_path: Path = DB_PATH, output_dir: Path = DOCS_DATA_DIR) -> list[str]:
    """
    Write one JSON file per month plus a manifest.json.
    Only months with at least one state data point are exported.
    """
    logger = get_run_logger()
    output_dir.mkdir(parents=True, exist_ok=True)
    conn = get_connection(db_path)

    months = [
        row[0]
        for row in conn.execute(
            "SELECT DISTINCT month FROM mart.monthly_state_prices ORDER BY month"
        ).fetchall()
    ]

    exported: list[str] = []

    for month in months:
        month_str = month.strftime("%Y-%m")

        states_df = conn.execute("""
            SELECT
                s.duoarea,
                s.state_abbrev,
                s.area_name,
                s.avg_price,
                s.min_price,
                s.max_price,
                s.week_count
            FROM mart.monthly_state_prices s
            WHERE s.month = ?
            ORDER BY s.area_name
        """, [month]).df()

        national_row = conn.execute("""
            SELECT national_avg, national_min, national_max
            FROM mart.national_monthly_prices
            WHERE month = ?
        """, [month]).fetchone()

        payload = {
            "month": month_str,
            "stats": {
                "national_avg": national_row[0] if national_row else None,
                "national_min": national_row[1] if national_row else None,
                "national_max": national_row[2] if national_row else None,
                "state_min": float(states_df["avg_price"].min()),
                "state_max": float(states_df["avg_price"].max()),
                "state_min_name": states_df.loc[states_df["avg_price"].idxmin(), "area_name"],
                "state_max_name": states_df.loc[states_df["avg_price"].idxmax(), "area_name"],
            },
            "states": states_df.to_dict(orient="records"),
        }

        out_path = output_dir / f"prices_{month_str}.json"
        out_path.write_text(json.dumps(payload, default=str), encoding="utf-8")
        exported.append(month_str)

    conn.close()

    manifest = {
        "available_months": exported,
        "latest_month": exported[-1] if exported else None,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "record_count": len(exported),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    logger.info(f"Exported {len(exported)} monthly JSON files + manifest.json")
    return exported
