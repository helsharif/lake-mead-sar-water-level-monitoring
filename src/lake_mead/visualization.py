"""Interactive geemap views and reproducible publication figures."""
import base64
from importlib.util import find_spec
from itertools import cycle
import logging
from pathlib import Path

import ee
import plotly.graph_objects as go
from plotly import io as pio
from plotly.subplots import make_subplots
import pandas as pd
import requests

from . import inundation, shoreline
from .water_detection import Water
from .workflow import Analysis

LOG = logging.getLogger(__name__)

BASIN_COLORS = {"overton": "#954b19", "boulder": "#1a6394", "virgin": "#267553"}
CHANGE_COLORS = ["#c45b30", "#1b7abd"]
WATER_COLOR = "#168ad0"
DEM_PALETTE = ["ede4cc", "9d895e", "624638", "322319"]


def interactive(analysis: Analysis, before: Water, after: Water | None = None,
                samples: pd.DataFrame | None = None, modeled: ee.Image | None = None):
    """Open SAR and terrain diagnostics with optional paired observation and scenario."""
    import geemap
    from ipyleaflet import CircleMarker, LayerGroup

    result = geemap.Map(ee_initialize=False, center=[36.21, -114.47], zoom=9, scale_ctrl=True)
    result.add_layer(analysis.bounds, {"color": "888888"}, "Monitoring search window", False)
    result.add_layer(analysis.corridor, {"palette": ["c2aa59"]}, "Historical monitoring corridor",
                     False, 0.50)
    for name, geometry in analysis.domains.items():
        outline = ee.FeatureCollection([ee.Feature(geometry)]).style(
            color=BASIN_COLORS[name].lstrip("#"), fillColor="00000000", width=2
        )
        result.add_layer(outline, {}, name.title() + " sampling window")
    result.add_layer(analysis.terrain.elevation, {"min": 300, "max": 900, "palette": DEM_PALETTE},
                     "GEM-15 DTM, m EGM96", False)
    result.add_layer(analysis.terrain.hillshade, {"min": 0, "max": 255}, "GEM-15 hillshade", False)
    result.add_layer(analysis.terrain.quality.select("dsm_std_m"),
                     {"min": 0, "max": 5, "palette": ["eff7ff", "0d2f68"]},
                     "GEM-15 within-cell DSM variability, m", False)
    result.add_layer(analysis.terrain.elevation.mask().Not().selfMask().updateMask(analysis.corridor),
                     {"palette": ["e53a87"]}, "Missing GEM-15 terrain in corridor", False)
    result.add_layer(before.db.clip(analysis.bounds), {"min": -27, "max": -4},
                     "Sentinel-1 filtered backscatter, dB", False)
    result.add_layer(before.mask.selfMask(), {"palette": [WATER_COLOR.lstrip("#")]}, "Earlier SAR water")
    result.add_layer(shoreline.shoreline(before, analysis.settings), {"palette": ["fff185"]},
                     "Earlier observed shoreline", False)
    if after is not None:
        result.add_layer(after.mask.selfMask(), {"palette": ["10496e"]}, "Later SAR water", False)
        change = inundation.changes(before, after)
        for value, label, color in zip((-1, 1), ("Newly exposed", "Newly inundated"), CHANGE_COLORS):
            result.add_layer(change.eq(value).selfMask(), {"palette": [color.lstrip("#")]}, label)
    if modeled is not None:
        result.add_layer(modeled, {"palette": ["78b962"]}, "Modeled connected land gain", False)
    if samples is not None and not samples.empty:
        visible = samples.sample(n=min(500, len(samples)), random_state=11)
        markers = [CircleMarker(location=(row.lat, row.lon), radius=3, weight=1,
                                color=BASIN_COLORS.get(row.domain, "#7722bb"))
                   for row in visible.itertuples()]
        result.add(LayerGroup(layers=markers, name="GEM-15 shoreline samples"))
    result.add_legend(title="Observed classes",
                      legend_dict={"Earlier water": WATER_COLOR, "Shoreline": "#fff185",
                                   "Newly exposed": CHANGE_COLORS[0],
                                   "Newly inundated": CHANGE_COLORS[1]})
    result.add_colorbar({"min": 300, "max": 900, "palette": DEM_PALETTE},
                        label="GEM-15 DTM elevation (m EGM96)", layer_name="GEM-15 DTM, m EGM96")
    return result


def _save_figures(figures: dict[str, go.Figure], output: Path) -> dict[str, go.Figure]:
    for name, figure in figures.items():
        figure.write_html(output / f"{name}.html", include_plotlyjs="directory")
    if figures and find_spec("kaleido") is not None:
        paths = [output / f"{name}.png" for name in figures]
        try:
            pio.write_images(list(figures.values()), paths, scale=2,
                             width=[fig.layout.width for fig in figures.values()],
                             height=[fig.layout.height for fig in figures.values()])
            for figure, path in zip(figures.values(), paths, strict=True):
                if not path.is_file():
                    figure.write_image(path, scale=2)
        except (ValueError, RuntimeError) as error:
            LOG.warning("Static export did not finish: %s", error)
    return figures


def _save(fig: go.Figure, output: Path, name: str) -> go.Figure:
    _save_figures({name: fig}, output)
    return fig


def _chart(x_label: str, y_label: str, title: str | None = None) -> go.Figure:
    return go.Figure().update_layout(
        template="plotly_white", title=title, xaxis_title=x_label, yaxis_title=y_label,
        height=480, width=950, legend=dict(orientation="h", y=1.03, x=0),
        margin=dict(l=75, r=35, t=85 if title else 55, b=75),
    )


def plot_results(areas: pd.DataFrame, estimates: pd.DataFrame, matched: pd.DataFrame,
                 output: Path) -> dict[str, go.Figure]:
    """Save interactive figures for available, QC-passing analysis rows."""
    figures = {}
    if "water_m2" not in areas:
        return figures
    valid_area = areas[areas["qc"].eq("pass")].sort_values("date")
    if valid_area.empty:
        return figures
    fig = _chart("Acquisition date (MST)", "Observed water area (km²)")
    fig.add_scatter(x=pd.to_datetime(valid_area["date"]), y=valid_area["water_m2"] / 1e6,
                    mode="lines+markers", line_color=WATER_COLOR, name="Observed area")
    figures["water_area"] = fig
    if "elevation_m" not in estimates:
        return _save_figures(figures, output)
    fig = _chart("Acquisition date (MST)", "Spatial block IQR (m)")
    measured = estimates.dropna(subset=["block_iqr_m"]).sort_values("date")
    for name, rows in measured.groupby("domain"):
        fig.add_scatter(x=pd.to_datetime(rows["date"]), y=rows["block_iqr_m"],
                        mode="lines+markers", line_color=BASIN_COLORS.get(name),
                        name=name.title(), text=rows["qc"],
                        hovertemplate="%{x|%Y-%m-%d}<br>IQR %{y:.2f} m<br>%{text}")
    if fig.data:
        figures["shoreline_dispersion"] = fig
    valid = estimates[estimates["qc"].eq("pass")].sort_values("date")
    if valid.empty:
        return _save_figures(figures, output)
    fig = _chart("Acquisition date (MST)", "Shoreline estimate (m EGM96)")
    for name, rows in valid.groupby("domain"):
        dates = pd.to_datetime(rows["date"])
        color = BASIN_COLORS.get(name, "#555555")
        rgb = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
        fig.add_scatter(x=dates, y=rows["block_q25_m"], line_width=0, showlegend=False,
                        hoverinfo="skip", legendgroup=name)
        fig.add_scatter(x=dates, y=rows["block_q75_m"], line_width=0, showlegend=False,
                        fill="tonexty", fillcolor=f"rgba({rgb[0]},{rgb[1]},{rgb[2]},0.18)",
                        hoverinfo="skip", legendgroup=name)
        fig.add_scatter(x=dates, y=rows["elevation_m"], mode="lines+markers", line_color=color,
                        name=name.title(), legendgroup=name,
                        customdata=rows[["block_q25_m", "block_q75_m"]].to_numpy(),
                        hovertemplate="%{x|%Y-%m-%d}<br>%{y:.2f} m EGM96<br>"
                        "Block quartiles %{customdata[0]:.2f}–%{customdata[1]:.2f} m")
    figures["estimated_elevation"] = fig
    fig = _chart("Shoreline estimate (m EGM96)", "Observed water area (km²)")
    joined = valid.merge(valid_area[["index", "water_m2"]], on="index")
    for name, rows in joined.groupby("domain"):
        fig.add_scatter(x=rows["elevation_m"], y=rows["water_m2"] / 1e6, mode="markers",
                        name=name.title(), marker_color=BASIN_COLORS.get(name), text=rows["date"])
    figures["area_elevation"] = fig
    if matched.empty or matched["residual_m"].isna().all():
        return _save_figures(figures, output)
    paired = matched.dropna(subset=["residual_m"]).sort_values("date")
    raw = paired["comparison_basis"].iloc[0].startswith("unharmonized")
    gauge_label = "Gauge (m USGS 1912)" if raw else "Gauge (m EGM96, transformed)"
    title = "Unharmonized gauge and terrain datums" if raw else None
    fig = _chart(gauge_label, "Shoreline estimate (m EGM96)", title)
    low = paired[["comparison_gauge_m", "elevation_m"]].min().min()
    high = paired[["comparison_gauge_m", "elevation_m"]].max().max()
    fig.add_scatter(x=[low, high], y=[low, high], mode="lines", name="1:1",
                    line=dict(color="#777777", dash="dot"), hoverinfo="skip")
    for name, rows in paired.groupby("domain"):
        fig.add_scatter(x=rows["comparison_gauge_m"], y=rows["elevation_m"], mode="markers",
                        name=name.title(), marker_color=BASIN_COLORS.get(name), text=rows["date"])
    figures["gauge_comparison"] = fig
    title = "Residuals include vertical datum differences" if raw else None
    fig = _chart("Acquisition date (MST)", "Estimate minus gauge (m)", title)
    fig.add_hline(y=0, line_color="#777777", line_dash="dot")
    for name, rows in paired.groupby("domain"):
        fig.add_scatter(x=pd.to_datetime(rows["date"]), y=rows["residual_m"],
                        mode="lines+markers", name=name.title(), line_color=BASIN_COLORS.get(name))
    figures["gauge_residuals"] = fig
    return _save_figures(figures, output)


def plot_thresholds(waters: list[tuple[str, Water]], output: Path) -> go.Figure:
    """Show corridor histograms and chosen per-date thresholds."""
    fig = _chart("Filtered backscatter (dB)", "Fraction of histogram pixels per bin")
    for (label, water), color in zip(waters, cycle(("#164a70", "#ae542d", "#3f7959"))):
        centers = water.histogram["bucketMeans"]
        counts = water.histogram["histogram"]
        total = sum(counts)
        fig.add_scatter(x=centers, y=[count / total for count in counts], mode="lines",
                        line=dict(color=color, shape="hvh"),
                        name=f"{label} (separation {water.separation:.2f})")
        fig.add_vline(x=water.threshold, line_color=color, line_dash="dot")
    return _save(fig, output, "classification_thresholds")


def export_map(analysis: Analysis, before: Water, after: Water, output: Path,
               samples: pd.DataFrame | None = None,
               labels: tuple[str, str] = ("Earlier", "Later")) -> go.Figure:
    """Export four map panels in a common UTM view."""
    terrain = analysis.terrain.hillshade.visualize(min=0, max=255)
    blank = ee.Image.constant([237, 239, 237]).rename(
        ["vis-red", "vis-green", "vis-blue"]
    ).toByte()
    terrain = blank.blend(terrain)
    before_water = before.mask.selfMask().visualize(palette=[WATER_COLOR.lstrip("#")])
    after_water = after.mask.selfMask().visualize(palette=[WATER_COLOR.lstrip("#")])
    change = inundation.changes(before, after)
    gain = change.eq(1).selfMask().visualize(palette=[CHANGE_COLORS[1].lstrip("#")])
    loss = change.eq(-1).selfMask().visualize(palette=[CHANGE_COLORS[0].lstrip("#")])
    study = terrain.blend(analysis.corridor.visualize(palette=["e1c271"], opacity=.72))
    for name, geometry in analysis.domains.items():
        outline = ee.FeatureCollection([ee.Feature(geometry)]).style(
            color=BASIN_COLORS[name].lstrip("#"), fillColor="00000000", width=2
        )
        study = study.blend(outline)
    earlier = before.db.clip(analysis.bounds).visualize(min=-27, max=-4).blend(before_water)
    edges = shoreline.shoreline(after, analysis.settings).visualize(palette=["fff185"])
    later = terrain.blend(after_water).blend(edges)
    has_samples = samples is not None and not samples.empty
    if has_samples:
        capped = samples.sample(n=min(500, len(samples)), random_state=11)
        points = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([row.lon, row.lat]))
                                       for row in capped.itertuples()])
        later = later.blend(points.style(color="dd1959", pointSize=2))
    later_label = "Water and shoreline samples" if has_samples else "Water and shoreline"
    titles = ("Study area and sampling windows", f"Sentinel-1 classification, {labels[0]}",
              f"{later_label}, {labels[1]}", "Observed water change")
    fig = make_subplots(rows=2, cols=2, subplot_titles=titles, vertical_spacing=.075)
    for index, image in enumerate((study, earlier, later, terrain.blend(gain).blend(loss))):
        url = image.getThumbURL({"region": analysis.bounds, "dimensions": 1000, "format": "png",
                                 "crs": "EPSG:32611"})
        response = requests.get(url, timeout=90)
        response.raise_for_status()
        source = base64.b64encode(response.content).decode("ascii")
        fig.add_trace(go.Image(source=f"data:image/png;base64,{source}", hoverinfo="skip"),
                      row=index // 2 + 1, col=index % 2 + 1)
    locators = [(name.title(), BASIN_COLORS[name]) for name in analysis.domains]
    classes = [("Water", WATER_COLOR), ("Shoreline", "#fff185")]
    if has_samples:
        classes.append(("Samples", "#dd1959"))
    classes.extend([("Exposed", CHANGE_COLORS[0]), ("Inundated", CHANGE_COLORS[1])])
    for label, color in locators + classes:
        fig.add_scatter(x=[None], y=[None], mode="markers", name=label, showlegend=True,
                        marker=dict(color=color, symbol="square", size=11), hoverinfo="skip",
                        row=2, col=1)
    fig.update_xaxes(visible=False).update_yaxes(visible=False)
    fig.update_layout(
        template="plotly_white", height=1050, width=1200,
        title=dict(text="Lake Mead | Sentinel-1 water extent and GEM-15 terrain",
                   subtitle=dict(text="GEM-15 attribution · This dataset is produced by Google")),
        legend=dict(orientation="h", y=-.035, x=.5, xanchor="center"),
        margin=dict(l=35, r=35, t=110, b=90),
    )
    return _save(fig, output, "study_and_water_maps")
