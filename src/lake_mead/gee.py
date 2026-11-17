"""Earth Engine initialization and lightweight study-area graphs."""
import os
import ee
from dotenv import load_dotenv

from .config import CRS, MONITOR_BOUNDS, SEED_BOUNDS, SHORE_WINDOWS, Settings


def initialize(authenticate: bool = True) -> None:
    """Use persistent credentials or initiate standard Earth Engine authentication."""
    load_dotenv()
    project = os.getenv("EE_PROJECT_ID") or None
    try:
        ee.Initialize(project=project)
    except ee.EEException as error:
        if not authenticate or "Please authorize access" not in str(error):
            raise
        ee.Authenticate()
        ee.Initialize(project=project)


def rectangle(bounds: tuple[float, ...]) -> ee.Geometry:
    return ee.Geometry.Rectangle(list(bounds), geodesic=False)


def study_area(settings: Settings) -> tuple[ee.Geometry, ee.Image, ee.Image]:
    """Use historically mapped water to bound classification around the reservoir."""
    bounds = rectangle(MONITOR_BOUNDS)
    history = ee.Image("JRC/GSW1_4/GlobalSurfaceWater")
    maximum = history.select("max_extent").unmask(0).clip(bounds).reproject(CRS, scale=30)
    permanent = history.select("occurrence").unmask(0).gte(90).clip(bounds)
    core = permanent.clip(rectangle(SEED_BOUNDS))
    historical = connected(coarsen_water(maximum, 60), core, bounds, 220_000, 60)
    corridor = historical.unmask(0, False).clip(bounds).focalMax(
        radius=settings.corridor_m, units="meters"
    ).selfMask().clip(bounds).rename("corridor")
    return bounds, corridor, permanent.updateMask(historical).selfMask()


def connected(
    candidates: ee.Image, seed: ee.Image, bounds: ee.Geometry, distance_m: int, scale: int
) -> ee.Image:
    """Keep pixels reachable from seed through a traversable raster."""
    area = candidates.selfMask().clip(bounds)
    source = seed.unmask(0, False).clip(bounds).updateMask(area).selfMask().toByte()
    cost = area.multiply(0).add(1).toFloat()
    return (cost.cumulativeCost(source, distance_m, False).reproject(CRS, scale=scale)
            .mask().selfMask().rename("connected"))


def coarsen_water(image: ee.Image, scale: int) -> ee.Image:
    """Preserve narrow candidate routes when tracing connectivity at a coarser scale."""
    return image.reduceResolution(ee.Reducer.max(), maxPixels=16).reproject(CRS, scale=scale)


def windows() -> dict[str, ee.Geometry]:
    return {name: rectangle(bounds) for name, bounds in SHORE_WINDOWS.items()}
