"""Derive water edges and sample confidently dry terrain on its own grid."""
from dataclasses import dataclass

import ee
import pandas as pd

from .config import CRS, Settings
from .dem import Terrain
from .water_detection import Water, reduce

SAMPLE_COLUMNS = ["elevation_m", "slope", "x", "y", "lon", "lat"]


@dataclass
class SampleStack:
    candidates: ee.Image
    pixels: ee.Image


def shoreline(water: Water, settings: Settings) -> ee.Image:
    observed_land = water.mask.eq(0).unmask(0, False)
    near_land = observed_land.focalMax(radius=settings.scale, units="meters")
    return water.mask.And(near_land).selfMask().rename("water_edge")


def sample_image(water: Water, terrain: Terrain, settings: Settings) -> SampleStack:
    """Restrict the sample to a landward strip outside the uncertain SAR transition."""
    wet = water.mask.unmask(0, False)
    far_enough = wet.focalMax(radius=settings.land_min_m, units="meters").Not()
    near_water = wet.focalMax(radius=settings.land_max_m, units="meters")
    dry = water.mask.eq(0).And(water.db.gte(water.threshold + settings.margin_db))
    candidate = dry.And(far_enough).And(near_water).selfMask().rename("candidate")
    plausible = terrain.elevation.gte(settings.terrain_min_m).And(
        terrain.elevation.lte(settings.terrain_max_m)
    )
    sampling_mask = candidate.And(terrain.slope.lte(settings.sample_slope_max)).And(plausible)
    projection = ee.Projection(CRS).atScale(terrain.scale)
    xy = ee.Image.pixelCoordinates(projection).multiply(terrain.scale).rename(["x", "y"])
    pixels = (terrain.elevation.addBands(terrain.slope).addBands(xy)
              .addBands(ee.Image.pixelLonLat().rename(["lon", "lat"]))
              .addBands(terrain.quality.unmask(-9999, False))
              .updateMask(sampling_mask).setDefaultProjection(projection))
    return SampleStack(candidate, pixels)


def sample(stack: SampleStack, domain: ee.Geometry, settings: Settings,
           terrain: Terrain) -> tuple[pd.DataFrame, float | None]:
    availability = stack.candidates.addBands(
        stack.candidates.updateMask(terrain.elevation.mask()).rename("terrain_valid")
    )
    counts = reduce(availability, ee.Reducer.count(), domain, terrain.scale).getInfo()
    fraction = ((counts.get("terrain_valid") or 0) / counts["candidate"]
                if counts.get("candidate") else None)
    eligible = stack.pixels.select("elevation_m").multiply(0).add(1).toByte().rename("eligible")
    features = stack.pixels.addBands(eligible).stratifiedSample(
        numPoints=settings.samples_per_domain, classBand="eligible", region=domain,
        projection=ee.Projection(CRS), scale=terrain.scale, seed=11, tileScale=4,
        geometries=False,
    )
    result = ee.data.computeFeatures({"expression": features, "fileFormat": "PANDAS_DATAFRAME"})
    columns = [*SAMPLE_COLUMNS, *terrain.quality_bands]
    result = result.reindex(columns=columns).dropna(subset=SAMPLE_COLUMNS).replace(-9999, float("nan"))
    return result, fraction
