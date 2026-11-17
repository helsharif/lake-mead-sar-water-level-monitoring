"""Spatially balanced elevation estimators and robust diagnostics."""
import numpy as np
import pandas as pd

from .config import Settings


def estimate(samples: pd.DataFrame, settings: Settings) -> dict:
    """Give occupied grid blocks equal weight and screen gross DEM outliers."""
    if samples.empty:
        return {"samples": 0, "retained": 0, "blocks": 0, "qc": "no_valid_terrain"}
    blocks = np.floor(samples[["x", "y"]] / settings.block_m)
    grouped = samples.groupby([blocks["x"], blocks["y"]])["elevation_m"]
    medians = grouped.median()
    center = medians.median()
    mad = float((medians - center).abs().median())
    good = medians.index[(medians - center).abs() <= max(3.0, 3.5 * 1.4826 * mad)]
    retained = medians.loc[good]
    quartiles = retained.quantile([0.25, 0.75])
    iqr = float(quartiles.iloc[1] - quartiles.iloc[0])
    flags = []
    if len(retained) < settings.min_blocks:
        flags.append("too_few_blocks")
    if iqr > settings.max_block_iqr_m:
        flags.append("high_spatial_dispersion")
    if len(retained) < 0.7 * len(medians):
        flags.append("many_rejected_blocks")
    return {
        "samples": len(samples), "retained": int(grouped.size().loc[good].sum()),
        "blocks": len(retained), "candidate_blocks": len(medians),
        "elevation_m": float(retained.median()),
        "lower_quartile_m": float(quartiles.iloc[0]),
        "sample_median_m": float(samples["elevation_m"].median()),
        "block_q25_m": float(quartiles.iloc[0]), "block_q75_m": float(quartiles.iloc[1]),
        "block_iqr_m": iqr,
        "median_slope_deg": float(samples["slope"].median()),
        "nominal_strip_midpoint_rise_m": float(((settings.land_min_m + settings.land_max_m) / 2) * np.tan(np.deg2rad(samples["slope"].median()))),
        "qc": ";".join(flags) or "pass",
    }
