"""Verify Plotly chart content and portable HTML export."""
import pandas as pd

from lake_mead import visualization


def test_plotly_result_bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(visualization, "find_spec", lambda name: None)
    areas = pd.DataFrame({"index": ["a", "b"], "date": ["2022-07-01", "2022-07-02"],
                          "qc": "pass", "water_m2": [12e6, 11e6]})
    estimates = areas[["index", "date", "qc"]].assign(
        domain="overton", elevation_m=[321.0, 320.0], block_iqr_m=[2, 3],
        block_q25_m=[320, 319], block_q75_m=[322, 322],
    )
    matched = estimates.assign(comparison_basis="unharmonized_terrain_minus_USGS1912",
                               comparison_gauge_m=[320.0, 319.0], residual_m=1.0)
    figures = visualization.plot_results(areas, estimates, matched, tmp_path)
    assert set(figures) == {"water_area", "shoreline_dispersion", "estimated_elevation",
                           "area_elevation", "gauge_comparison", "gauge_residuals"}
    assert len(figures["estimated_elevation"].data) == 3
    assert figures["gauge_comparison"].layout.title.text.startswith("Unharmonized")
    assert (tmp_path / "plotly.min.js").is_file()
    assert all("Plotly.newPlot" in (tmp_path / f"{key}.html").read_text(encoding="utf-8")
               for key in figures)
