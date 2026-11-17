"""Interpolate user-transcribed official capacity values, in gauge datum."""
from pathlib import Path
import numpy as np
import pandas as pd


def capacity(path: Path, elevations_ft: pd.Series) -> pd.Series:
    table = pd.read_csv(path, usecols=["elevation_ft", "capacity_acre_ft"])
    if len(table) < 2 or not np.isfinite(table.to_numpy()).all():
        raise ValueError("Capacity table needs at least two finite rows")
    table = table.sort_values("elevation_ft")
    if (np.diff(table["elevation_ft"]) <= 0).any() or (np.diff(table["capacity_acre_ft"]) < 0).any():
        raise ValueError("Capacity table elevations must increase and capacity must not decrease")
    return pd.Series(np.interp(elevations_ft, table["elevation_ft"], table["capacity_acre_ft"],
                               left=np.nan, right=np.nan), index=elevations_ft.index)
