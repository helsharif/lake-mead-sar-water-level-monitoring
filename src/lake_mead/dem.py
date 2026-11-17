"""Terrain source adapter for GEM-15 bare-earth elevation."""
from dataclasses import dataclass

import ee
import pandas as pd

from .config import CRS, Settings

GEM15_ASSET = "projects/climate-and-sustainability/assets/gem-15_v1"
QUALITY_BANDS = ("dsm_std_m", "dsm_p95_p05_m", "dsm_minus_dtm_m")


@dataclass
class Terrain:
    elevation: ee.Image
    slope: ee.Image
    hillshade: ee.Image
    quality: ee.Image
    source: str
    datum: str
    scale: int
    quality_bands: tuple[str, ...]

    def screen(self, frame: pd.DataFrame, settings: Settings) -> pd.DataFrame:
        """Sensitivity screen using within-cell roughness and surface-to-terrain relief."""
        limits = (settings.max_dsm_std_m, settings.max_dsm_spread_m, settings.max_surface_gap_m)
        if frame.empty or not self.quality_bands:
            return frame
        flags = pd.concat([frame[band].between(0, limit)
                           for band, limit in zip(self.quality_bands, limits, strict=True)], axis=1)
        return frame.loc[flags.all(axis=1)]


def load(bounds: ee.Geometry) -> Terrain:
    """Preserve the provider's water and no-data masks on a 15 m UTM grid."""
    bands = ["dtm", "dsm", "dsm_std", "dsm_percentile_5", "dsm_percentile_95"]
    mosaic = (ee.ImageCollection(GEM15_ASSET).filterBounds(bounds.buffer(300))
              .select(bands).sort("system:index").mosaic().reproject(CRS, scale=15))
    elevation = mosaic.select("dtm").rename("elevation_m")
    quality = mosaic.select("dsm_std").addBands(
        mosaic.select("dsm_percentile_95").subtract(mosaic.select("dsm_percentile_5"))
    ).addBands(mosaic.select("dsm").subtract(elevation)).rename(list(QUALITY_BANDS))
    products = ee.Terrain.products(elevation)
    return Terrain(elevation, products.select("slope"), products.select("hillshade"),
                   quality, GEM15_ASSET, "EGM96 (EPSG:5773)", 15, QUALITY_BANDS)
