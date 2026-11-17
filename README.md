# Lake Mead water extent and shoreline elevation

A Python research workflow for tracking Lake Mead surface water in Sentinel-1 radar imagery and estimating water-surface elevation from landward samples of the Google GEM-15 bare-earth terrain model. It compares Overton Arm estimates with two other basin windows and matches each eligible acquisition to an independent Hoover Dam gauge observation.

- **Observed water extent** comes from Sentinel-1. Paired change maps distinguish newly inundated and newly exposed pixels on common coverage.
- **Estimated elevation** comes from GEM-15 DTM elevations near the observed shoreline, reported in metres EGM96.
- **Modeled land gain** maps low, valid terrain connected to an observed reservoir footprint under a specified higher level. The scenario leaves masked terrain unresolved. Reservoir storage is available separately through user-supplied official capacity values.

## Setup

Install [uv](https://docs.astral.sh/uv/), then run from the repository root.

```sh
uv python install 3.12
uv sync --locked
uv run --locked pytest -q
```

Copy `.env.example` to `.env` and set `EE_PROJECT_ID` to an Earth Engine–registered Google Cloud project with the Earth Engine API enabled and for which you have permission to run computations. The workflow uses existing Earth Engine credentials or opens the standard interactive authentication flow. Refresh expired credentials with `uv run --locked earthengine authenticate --force`. See the [Earth Engine authentication guide](https://developers.google.com/earth-engine/guides/auth).

## Run the analysis

Dates are inclusive at the start and exclusive at the end. The Sentinel-1 search uses UTC intervals and joins readings by fixed Mountain Standard Time (UTC−07:00).

```sh
uv run --locked lake-mead scenes --start 2022-07-01 --end 2022-09-01
uv run --locked lake-mead run --start 2022-07-07 --end 2022-07-20 --track 173 --monitor-window overton --output outputs/overton-pilot
uv run --locked lake-mead run --start 2022-07-01 --end 2022-09-01 --output outputs/2022-summer
uv run --locked lake-mead gauge --start 2022-07-01 --end 2022-09-01 --output outputs/gauge.csv
```

Use `--track` to hold a known relative orbit fixed across date ranges and `--polarization VH` for a separate sensitivity run. A `--monitor-window` pilot estimates both area and elevation within one basin. Use `--domains` to restrict shoreline sampling while keeping the full monitoring area. Inspect the acquisition coverage and QC fields before using the area series. Use a distinct output directory for each analysis. The CLI writes acquisition and terrain QC, shoreline samples, elevations, run metadata, gauge matches, validation metrics and interactive Plotly HTML charts when there are eligible values. Keep the shared `plotly.min.js` file alongside the HTML when moving the charts. See [methods and output interpretation](docs/methods.md) for estimator choice, scenario limits, the gauge CSV schema and datum provenance.

## Open the geemap notebook

```sh
uv run --locked jupyter lab notebooks/01_lake_mead_analysis.ipynb
```

Set the date interval and run the cells in order. The map includes basin windows, historical water corridor, GEM-15 DTM and hillshade, terrain gaps, DSM variability, Sentinel-1 backscatter, classified water, shoreline and sample locations. The notebook also renders observed change, a connected terrain scenario, a four-panel Plotly map figure and the plots supported by the results.

For high-resolution PNGs alongside the HTML, install the optional `static` extra with `uv sync --locked --extra static`. Use `uv run --locked --extra static ...` when starting the CLI or JupyterLab. Static export uses Kaleido and needs a compatible local Chrome or Chromium installation. See [Plotly static image export](https://plotly.com/python/static-image-export/).

## Data and attribution

| Product | Role |
| --- | --- |
| [Copernicus Sentinel-1 GRD](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S1_GRD) | SAR backscatter and observation geometry |
| [Google GEM-15 v1](https://developers.google.com/earth-engine/datasets/catalog/projects_climate-and-sustainability_assets_gem-15_v1) | 15 m DTM and DSM diagnostics, CC BY 4.0. This dataset is produced by Google. |
| [JRC Global Surface Water v1.4](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_4_GlobalSurfaceWater) | Historical monitoring corridor and reservoir seed, Landsat-derived |
| [Reclamation RISE 6123](https://data.usbr.gov/catalog/4370/item/6123) | Provisional daily observed Hoover Dam pool elevations |
| [Reclamation 2009 area and capacity tables](https://www.usbr.gov/lc/region/g4000/LM_AreaCapacityTables2009.pdf) | Optional gauge-based storage interpolation |

The MIT license covers project code. Data products retain their source terms.

## Repository

- `src/lake_mead/` contains the terrain adapter, Earth Engine workflow, validation, geemap views and CLI.
- `notebooks/` contains the interactive research workflow.
- `docs/` documents assumptions, sources, reproducibility and verification.
- `tests/` contains statistical tests and credential-free Earth Engine graph checks.

The live Overton Arm pilots yielded three eligible gauge matches across four dates. The spatial median ran high in both periods on the raw cross-datum comparison. See [verification](docs/verification.md) for the measured errors, area changes and terrain artifact. Establish a local independent datum tie and inspect shoreline terrain gaps before treating the estimates as absolute reservoir levels.
