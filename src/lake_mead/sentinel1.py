"""Group single-geometry Sentinel-1 slices and filter backscatter."""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
import math

import ee

from .config import CRS, Settings

COLLECTION = "COPERNICUS/S1_GRD"


@dataclass(frozen=True)
class Scene:
    index: str
    time_ms: int
    track: int
    platform: str
    direction: str
    absolute_orbit: int
    slices: tuple[str, ...]
    footprint_fraction: float


def scenes(start: date, end: date, bounds: ee.Geometry, settings: Settings) -> list[Scene]:
    if end <= start:
        raise ValueError("End date must follow the start date (end is exclusive)")
    collection = (ee.ImageCollection(COLLECTION).filterBounds(bounds)
                  .filterDate(start.isoformat(), end.isoformat())
                  .filter(ee.Filter.eq("instrumentMode", "IW"))
                  .filter(ee.Filter.eq("resolution_meters", 10))
                  .filter(ee.Filter.eq("orbitProperties_pass", settings.orbit_pass))
                  .filter(ee.Filter.listContains("transmitterReceiverPolarisation",
                                                 settings.polarization)))
    if settings.track is not None:
        collection = collection.filter(ee.Filter.eq("relativeOrbitNumber_start", settings.track))
    def tag(im: ee.Image) -> ee.Image:
        key = ee.String(im.get("platform_number")).cat(
            ee.Number(im.get("orbitNumber_start")).format("%d")
        )
        return im.set("lake_orbit", key)

    collection = collection.map(tag)
    seeds = collection.distinct(["lake_orbit"])
    def row(im: ee.Image) -> ee.Image:
        group = collection.filter(ee.Filter.eq("lake_orbit", im.get("lake_orbit")))
        fraction = group.geometry(120).intersection(bounds, 120).area(120).divide(bounds.area(120))
        return im.set("lake_meta", ee.List([
            group.aggregate_min("system:time_start"), im.get("relativeOrbitNumber_start"),
            im.get("platform_number"), im.get("orbitProperties_pass"), im.get("orbitNumber_start"),
            group.aggregate_array("system:index").sort(), fraction,
        ]))
    rows = seeds.map(row).aggregate_array("lake_meta").getInfo()
    return sorted([Scene(items[0], stamp, track, platform, direction, orbit, tuple(items), fraction)
                   for stamp, track, platform, direction, orbit, items, fraction in rows],
                  key=lambda scene: (scene.time_ms, scene.index))


def choose_track(acquisitions: list[Scene]) -> int:
    """Prefer tracks with the largest typical fraction of the search window."""
    from statistics import median

    coverage = defaultdict(list)
    for scene in acquisitions:
        coverage[scene.track].append(scene.footprint_fraction)
    return max(coverage, key=lambda track: (median(coverage[track]), len(coverage[track]), -track))


def backscatter(scene: Scene, settings: Settings) -> ee.Image:
    def gamma(index: str) -> ee.Image:
        image = ee.Image(f"{COLLECTION}/{index}")
        angle = image.select("angle")
        db = image.select(settings.polarization)
        valid = angle.gte(settings.angle_min).And(angle.lte(settings.angle_max)).And(db.mask())
        # Approximate flat-surface gamma nought, preserving invalid data.
        correction = angle.multiply(math.pi / 180).cos().log10().multiply(10)
        return db.subtract(correction).toFloat().updateMask(valid)

    image = ee.ImageCollection.fromImages([gamma(index) for index in scene.slices]).mosaic()
    image = image.reproject(CRS, scale=settings.scale)
    return image.focalMedian(radius=settings.speckle_m, units="meters").updateMask(
        image.mask()
    ).rename("backscatter_db")
