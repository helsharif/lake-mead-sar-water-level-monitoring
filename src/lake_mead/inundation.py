"""Observed change and restricted connected terrain scenarios."""
import ee

from .config import CRS, Settings
from .dem import Terrain
from .gee import connected
from .water_detection import Water, reduce


def changes(before: Water, after: Water) -> ee.Image:
    """-1 exposed, 0 stable, +1 inundated, only where both SAR masks are valid."""
    return after.mask.toInt8().subtract(before.mask.toInt8()).rename("observed_change")


def change_areas(before: Water, after: Water, bounds: ee.Geometry, settings: Settings) -> dict:
    """Summarize gain, loss and support within the common valid footprint."""
    difference = changes(before, after)
    area = ee.Image.pixelArea()
    bands = (difference.eq(1).multiply(area).rename("newly_inundated_m2")
             .addBands(difference.eq(-1).multiply(area).rename("newly_exposed_m2"))
             .addBands(area.updateMask(difference.mask()).rename("common_coverage_m2")))
    return reduce(bands, ee.Reducer.sum(), bounds, settings.scale).getInfo()


def scenario(reference: Water, terrain: Terrain, level_m: float, corridor: ee.Image,
             bounds: ee.Geometry, settings: Settings) -> ee.Image:
    """Return connected newly inundatable land for a rise from observed baseline."""
    wet = reference.mask.selfMask()
    land = (terrain.elevation.gte(settings.terrain_min_m).And(terrain.elevation.lte(level_m))
            .And(reference.mask.eq(0)).selfMask())
    traversable = wet.unmask(0, False).Or(land.unmask(0, False)).updateMask(corridor)
    routing_scale = 45
    coarse = traversable.reproject(CRS, scale=routing_scale)
    reach = connected(coarse, wet, bounds, 8_000, routing_scale)
    return land.updateMask(reach).rename("modeled_gain")
