from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from lake_mead.config import Settings
from lake_mead.dem import QUALITY_BANDS, Terrain
from lake_mead.elevation import estimate
from lake_mead.observations import clean
from lake_mead.sentinel1 import Scene, choose_track
from lake_mead.storage import capacity
from lake_mead.validation import compare, metrics
from lake_mead.water_detection import ClassificationError, otsu


@pytest.mark.parametrize("changes", [{"track": 0}, {"land_min_m": 5}, {"polarization": "HH"},
                                     {"max_dsm_std_m": 0}, {"sample_slope_max": 40}])
def test_parameters(changes):
    with pytest.raises(ValueError):
        replace(Settings(), **changes)


def test_otsu():
    threshold, separation = otsu({"bucketMeans": [-22, -20, -18, -16, -14, -12, -10],
                                  "histogram": [10, 20, 0, 0, 0, 20, 10]})
    assert threshold == -16
    assert .95 < separation <= 1
    with pytest.raises(ClassificationError):
        otsu({"bucketMeans": [-12], "histogram": [10]})


def test_spatial_blocks_and_outliers():
    samples = pd.DataFrame({"x": [0] * 20 + [500, 1000, 1500, 2000, 2500, 3000],
                            "y": 0, "slope": 4,
                            "elevation_m": [322] * 20 + [320, 320, 320, 319, 321, 400]})
    result = estimate(samples, Settings())
    assert result["blocks"] == 6
    assert result["samples"] == 26
    assert result["retained"] == 25
    assert result["sample_median_m"] == 322
    assert result["elevation_m"] == 320
    assert result["qc"] == "pass"
    assert estimate(samples.iloc[:0], Settings())["qc"] == "no_valid_terrain"
    assert "too_few_blocks" in estimate(samples.iloc[:20], Settings())["qc"]


def test_quality_screening_does_not_modify_baseline():
    terrain = Terrain(None, None, None, None, "fixture", "EGM96", 15, QUALITY_BANDS)
    data = pd.DataFrame(dict(zip(QUALITY_BANDS, ([1, 3, 1], [3, 3, np.nan], [1, 1, 1]))))
    assert terrain.screen(data, Settings()).index.tolist() == [0]
    assert len(data) == 3


def test_observations_and_matching():
    observations = clean(pd.DataFrame({"date": ["2022-01-01", "2022-01-02", "2022-01-02", "oops"],
                                       "elevation_ft": [1000, 1001, 1001, 1200]}))
    assert observations["gauge_m_usgs1912"].iloc[0] == pytest.approx(304.8)
    estimates = pd.DataFrame({"date": ["2022-01-01", "2022-01-02", "2022-01-03"],
                              "domain": "overton", "elevation_m": [307.8, 310, 310],
                              "qc": ["pass", "too_few_blocks", "pass"]})
    paired, summary = compare(estimates, observations, 2)
    assert paired["residual_m"].dropna().tolist() == pytest.approx([1])
    assert summary[0]["n"] == 1 and summary[0]["r2"] is None
    assert summary[0]["mae_m"] == pytest.approx(1)
    _, raw = compare(estimates, observations)
    assert raw[0]["basis"].startswith("unharmonized")
    assert raw[0]["bias_m"] == pytest.approx(3)


def test_conflicting_gauge_values():
    with pytest.raises(ValueError, match="Conflicting"):
        clean(pd.DataFrame({"date": ["2022-01-01"] * 2, "elevation_ft": [1000, 1001]}))


def test_metrics():
    values = metrics(pd.Series([320.0, 324.0]), pd.Series([322.0, 323.0]))
    assert values == {"n": 2, "mae_m": 1.5, "rmse_m": pytest.approx(np.sqrt(2.5)),
                      "bias_m": -.5, "r2": -9}


def test_capacity_uses_gauge_datum_and_does_not_extrapolate(tmp_path: Path):
    table = tmp_path / "capacity.csv"
    table.write_text("elevation_ft,capacity_acre_ft\n1000,500\n1100,800\n", encoding="utf-8")
    result = capacity(table, pd.Series([950, 1050, 1200]))
    assert result.iloc[1] == 650
    assert result.isna().sum() == 2


def test_single_track_choice_uses_typical_footprint():
    sample = Scene("ex", 0, 7, "A", "ASCENDING", 1, ("ex",), 0.6)
    rows = [sample, replace(sample, footprint_fraction=.7),
            replace(sample, track=9, footprint_fraction=.9)]
    assert choose_track(rows) == 9
