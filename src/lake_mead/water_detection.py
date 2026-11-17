"""Adaptive classification on a fixed metric grid."""
from dataclasses import dataclass
import ee
import numpy as np

from .config import CRS, Settings
from .dem import Terrain
from .gee import coarsen_water, connected


class ClassificationError(ValueError):
    """An acquisition could not support classification."""


def otsu(histogram: dict) -> tuple[float, float]:
    """Return a split between bin centers and the explained variance fraction."""
    centers = np.asarray(histogram.get("bucketMeans", []), dtype=float)
    counts = np.asarray(histogram.get("histogram", []), dtype=float)
    if centers.shape != counts.shape or not np.isfinite(centers).all() or not np.isfinite(counts).all():
        raise ClassificationError("Invalid backscatter histogram")
    keep = counts > 0
    centers, counts = centers[keep], counts[keep]
    if len(counts) < 2:
        raise ClassificationError("Backscatter histogram has fewer than two occupied bins")
    fractions = counts / counts.sum()
    weight = np.cumsum(fractions)[:-1]
    mean = np.dot(fractions, centers)
    between = (np.cumsum(fractions * (centers - mean))[:-1] ** 2
               / (weight * (1 - weight)))
    variance = np.dot(fractions, (centers - mean) ** 2)
    if variance <= 0:
        raise ClassificationError("Backscatter histogram has no spread")
    split = int(np.argmax(between))
    return float((centers[split] + centers[split + 1]) / 2), float(between[split] / variance)


@dataclass
class Water:
    mask: ee.Image
    db: ee.Image
    threshold: float
    separation: float
    histogram: dict


def reduce(image: ee.Image, reducer: ee.Reducer, bounds: ee.Geometry, scale: int) -> ee.Dictionary:
    return image.reduceRegion(reducer=reducer, geometry=bounds, crs=CRS, scale=scale,
                              maxPixels=120_000_000, tileScale=4)


def classify(db: ee.Image, terrain: Terrain, bounds: ee.Geometry, corridor: ee.Image,
             anchors: ee.Image, settings: Settings) -> Water:
    """Keep connected low-backscatter patches inside the historical corridor."""
    stats = reduce(db.updateMask(corridor), ee.Reducer.histogram(128, 0.25),
                   bounds, max(settings.scale, 40)).getInfo()
    histogram = stats.get("backscatter_db") or {}
    threshold, separation = otsu(histogram)
    if separation < settings.min_separation:
        raise ClassificationError(f"Weak histogram separation ({separation:.2f})")
    # Missing original-land slope is common on water. Connectivity supplies the prior there.
    gentle = terrain.slope.lte(settings.water_slope_max).unmask(1, False)
    candidate = db.lt(threshold).And(gentle).updateMask(corridor).selfMask()
    count = candidate.connectedPixelCount(settings.min_water_pixels, True)
    patches = candidate.updateMask(count.gte(settings.min_water_pixels))
    routing_scale = 2 * settings.scale
    reachable = connected(coarsen_water(patches, routing_scale), anchors, bounds,
                          settings.water_reach_m, routing_scale)
    wet = patches.updateMask(reachable)
    water = wet.unmask(0, False).updateMask(db.mask()).updateMask(corridor)
    return Water(water.toByte().rename("water"), db, threshold, separation, histogram)


def areas(water: Water, corridor: ee.Image, bounds: ee.Geometry, settings: Settings) -> dict:
    area = ee.Image.pixelArea().toFloat()
    image = (water.mask.multiply(area).rename("water_m2")
             .addBands(area.updateMask(water.mask.mask()).rename("covered_m2"))
             .addBands(area.updateMask(corridor).rename("domain_m2")))
    return reduce(image, ee.Reducer.sum(), bounds, settings.scale).getInfo()
