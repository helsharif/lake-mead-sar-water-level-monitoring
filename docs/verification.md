# Verification

## Terrain source and local artifact

The live Earth Engine query found eight GEM-15 images intersecting the study search window using the catalog ID `projects/climate-and-sustainability/assets/gem-15_v1`. The supplied slash-form ID returned an asset-not-found response. Earth Engine reported `dtm`, `dsm`, `dsm_std`, and `dsm_percentile_5/50/95`. The first intersecting tile returned a 15 m transform in UTM 12N. The public COG sampled separately below is in UTM 11N. The elevation adapter harmonizes both to a 15 m UTM 11N grid without filling producer no-data. [Google Earth Engine catalog](https://developers.google.com/earth-engine/datasets/catalog/projects_climate-and-sustainability_assets_gem-15_v1)

A public Google COG window check used tile `wm115s36`, band 1 of the DTM and 15 m pixel counts over windows transformed to UTM bounding rectangles. It found 49.12% non-masked DTM cells over the Boulder Basin core search window (`[-114.84,36.04,-114.72,36.13]`) and 82.20% in the Overton check window (`[-114.53,36.30,-114.35,36.45]`). The percentages describe entire rectangles, including open water, and differ from the shoreline availability fraction in the workflow.

The Overton rectangle contained 460 unmasked cells below 250 m. The lowest cell, at approximately 114.347815° W, 36.416390° N, reported 118.62 m in the DTM, 300.71 m in the DSM, 3.92 m DSM standard deviation and 9.82 m DSM P95–P05. USGS EPQS returned approximately 329.55 m from a 1 m elevation source. The USGS value is interpolated and the source elevations refer to different acquisition periods and datums. These figures identify a gross suspect DTM value and illustrate how both the broad terrain range and the separate DSM-based screen would flag it. The point was selected from the terrain raster and was not established as a valid SAR shoreline sample. [Google tile metadata and public COG links](https://storage.googleapis.com/climate-and-sustainability/gem-15/stac/gem-15/p30_m120/wm115s36/wm115s36.json) · [USGS elevation point service](https://www.usgs.gov/faqs/how-accurate-are-elevations-generated-elevation-point-query-service-national-map)

## Reclamation observations

The CLI retrieved 62 daily observations from RISE item 6123 for July–August 2022, from 1,040.58 to 1,044.29 feet USGS 1912. Gauge readings are independent of the SAR classification and the terrain quality thresholds. [Reclamation item 6123](https://data.usbr.gov/catalog/4370/item/6123)

## Software and pilot checks

The locked environment passed 16 tests covering statistics, data quality, Earth Engine expression construction and Plotly exports. The authenticated Sentinel-1 catalog query returned ten acquisitions across tracks 100 and 173 in July–August 2022. Track 173 had the greater search-window footprint. The Overton geemap view initialized 15 live layers with both dates, change classes and a modeled scenario.

An initial pilot with a historical footprint and minimum patch size allowed small detached dark areas to contribute candidate shorelines. The two July 2022 estimates both failed the spatial-dispersion screen, with block IQRs of 14.87 m and 13.07 m. The current workflow checks connectivity to historical persistent water and samples from the eligible terrain class. The pilot data and Plotly HTML and PNG figures are kept in local output directories.

With persistent-water anchors enabled, the live July 7–19 Overton comparison classified 2.388 km² of gain and 0.926 km² of loss over 152.623 km² of common corridor coverage. Reclamation's gauge fell from 1,042.35 to 1,041.04 ft over the same dates. Treat the mapped changes as differences between classifications and check them against independent near-date imagery before interpreting the net gain physically. The four-panel map and threshold figure were exported to Plotly HTML and Kaleido PNG.

The updated Overton pilot measured 30.008 km² on July 7 and 31.471 km² on July 19. Each date returned 1,500 eligible terrain samples, and the DTM had values at 60.1% and 62.2% of candidate landward cells before slope and plausibility screening. July 7 passed internal QC with a 6.52 m block IQR. The 337.68 m EGM96 estimate was 19.97 m above the gauge after unit conversion alone. The lower-quartile estimate was 18.13 m above the gauge and the DSM-screened estimate was 20.03 m above. July 19 failed internal QC with a 14.35 m block IQR. For this one matched date, MAE, RMSE and signed bias of the median all equal 19.97 m on the unharmonized basis, and R² is undefined. The discrepancy shows why spatial consistency alone is insufficient to establish accuracy. The pilot provides no basis for adopting Overton alone as a reservoir-wide water-level estimator.

An independent higher-pool comparison used July 5 and July 11, 2020, on the same descending relative orbit (173). Both passed internal QC, with terrain block IQRs of 4.28 m and 4.62 m and classified water areas of 42.062 km² and 41.539 km². The spatial median had MAE 7.33 m, RMSE 7.34 m and bias +7.33 m on the unharmonized basis. The predictive R² of −6,228.16 reflects two readings separated by just 0.19 m, so it gives little information about generalization. The block lower quartile had raw MAE 5.77 m, and the DSM-screened median had raw MAE 7.32 m. The small samples and unresolved datum tie leave estimator ranking provisional.

The contrast map for July 5, 2020, and July 7, 2022, showed 14.416 km² classified as exposed and 2.362 km² classified as inundated, a net decline of 12.054 km² in classified water within common Overton coverage. The later panel includes a reproducible display subsample of the extracted shoreline terrain locations.

### Higher-pool pilot command

```sh
uv run --locked lake-mead run --start 2020-07-01 --end 2020-08-01 --track 173 --limit 2 --monitor-window overton --output outputs/overton-2020
```
