"""Retrieve or import independent daily Reclamation elevations."""
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from .config import LOCAL_ZONE

RISE_URL = "https://data.usbr.gov/rise/api/result"
RISE_ITEM = 6123
GAUGE_DATUM = "USGS 1912"
FEET_TO_METRES = 0.3048


def clean(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize one finite, physically plausible reading per civil date."""
    dates = pd.to_datetime(frame["date"], format="%Y-%m-%d", errors="coerce")
    feet = pd.to_numeric(frame["elevation_ft"], errors="coerce")
    valid = dates.notna() & np.isfinite(feet) & feet.between(800, 1300)
    data = pd.DataFrame({"date": dates[valid], "gauge_ft": feet[valid]}).drop_duplicates()
    if data["date"].duplicated().any():
        raise ValueError("Conflicting reservoir observations on the same local date")
    if data.empty:
        raise ValueError("No valid Lake Mead observations")
    data["gauge_m_usgs1912"] = data["gauge_ft"] * FEET_TO_METRES
    return data.sort_values("date").reset_index(drop=True)


def read_csv(path: Path) -> pd.DataFrame:
    return clean(pd.read_csv(path, usecols=["date", "elevation_ft"]))


def download(start: date, end: date) -> pd.DataFrame:
    """Fetch official daily records for a half-open interval and retain source date."""
    records = []
    with requests.Session() as http:
        http.headers["Accept"] = "application/vnd.api+json"
        while start < end:
            stop = min(start + timedelta(days=30), end)
            page = 1
            while True:
                response = http.get(
                    RISE_URL, params={"itemId": RISE_ITEM, "itemsPerPage": 25, "page": page,
                                      "dateTime[after]": (start - timedelta(days=1)).isoformat(),
                                      "dateTime[before]": (stop + timedelta(days=1)).isoformat()},
                    timeout=30,
                )
                response.raise_for_status()
                batch = response.json()["data"]
                for record in batch:
                    row = record["attributes"]
                    day = pd.Timestamp(row["dateTime"]).tz_convert(LOCAL_ZONE).date()
                    if start <= day < stop and row["itemId"] == RISE_ITEM:
                        records.append((day.isoformat(), row["result"]))
                if len(batch) < 25:
                    break
                page += 1
                if page > 4:
                    raise ValueError("Unexpected pagination for a daily RISE series")
            start = stop
    return clean(pd.DataFrame(records, columns=["date", "elevation_ft"]))
