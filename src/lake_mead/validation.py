"""Same-day matching and explicit cross-datum comparisons."""
import numpy as np
import pandas as pd


ESTIMATORS = ("elevation_m", "lower_quartile_m", "sample_median_m", "screened_elevation_m")


def metrics(estimate: pd.Series, observed: pd.Series) -> dict:
    pairs = pd.concat([estimate, observed], axis=1)
    values = pairs.to_numpy(dtype=float)
    values = values[np.isfinite(values).all(axis=1)]
    if not len(values):
        return {"n": 0, "mae_m": None, "rmse_m": None, "bias_m": None, "r2": None}
    residual = values[:, 0] - values[:, 1]
    sse = np.dot(residual, residual)
    sst = ((values[:, 1] - values[:, 1].mean()) ** 2).sum()
    return {"n": len(values), "mae_m": float(np.abs(residual).mean()),
            "rmse_m": float(np.sqrt(sse / len(values))), "bias_m": float(residual.mean()),
            "r2": float(1 - sse / sst) if len(values) > 1 and sst > 0 else None}


def compare(estimates: pd.DataFrame, gauge: pd.DataFrame,
            gauge_to_terrain_m: float | None = None) -> tuple[pd.DataFrame, list[dict]]:
    """Match each basin and sensor acquisition to the same fixed-MST gauge date."""
    estimates = estimates.assign(date=pd.to_datetime(estimates["date"]))
    matched = estimates.merge(gauge, how="left", on="date", validate="many_to_one")
    matched["comparison_gauge_m"] = matched["gauge_m_usgs1912"]
    basis = "unharmonized_terrain_minus_USGS1912"
    if gauge_to_terrain_m is not None:
        matched["comparison_gauge_m"] += gauge_to_terrain_m
        basis = "external_gauge_to_terrain_shift"
    matched["comparison_basis"] = basis
    matched["residual_m"] = (matched["elevation_m"] - matched["comparison_gauge_m"]).where(
        matched["qc"].eq("pass")
    )
    summaries = []
    for domain, rows in matched.groupby("domain"):
        eligible = rows.loc[rows["qc"].eq("pass")]
        for name in ESTIMATORS:
            if name not in rows:
                continue
            subset = eligible.loc[eligible["screened_qc"].eq("pass")] if (
                name == "screened_elevation_m" and "screened_qc" in eligible
            ) else eligible
            valid = subset.dropna(subset=[name, "comparison_gauge_m"])
            result = metrics(valid[name], valid["comparison_gauge_m"])
            summaries.append({"domain": domain, "estimator": name, "basis": basis, **result})
            if name == "screened_elevation_m":
                result = metrics(valid["elevation_m"], valid["comparison_gauge_m"])
                summaries.append({"domain": domain, "estimator": "median_on_screened_dates",
                                  "basis": basis, **result})
    return matched, summaries
