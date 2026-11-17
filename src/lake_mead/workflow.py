"""Build and run the acquisition-level workflow."""
from dataclasses import asdict, dataclass
from datetime import date
import logging
from typing import Callable

import ee
import pandas as pd

from . import dem, elevation, gee, sentinel1, shoreline, water_detection
from .config import LOCAL_ZONE, Settings

LOG = logging.getLogger(__name__)


@dataclass
class Analysis:
    settings: Settings
    bounds: ee.Geometry
    corridor: ee.Image
    anchors: ee.Image
    domains: dict[str, ee.Geometry]
    terrain: dem.Terrain

    @classmethod
    def create(cls, settings: Settings, terrain_loader: Callable = dem.load,
               monitor_window: str | None = None) -> "Analysis":
        bounds, corridor, anchors = gee.study_area(settings)
        domains = gee.windows()
        if monitor_window is not None:
            bounds = domains[monitor_window]
            corridor = corridor.clip(bounds)
            anchors = anchors.clip(bounds)
            domains = {monitor_window: bounds}
        return cls(settings, bounds, corridor, anchors, domains, terrain_loader(bounds))

    def classify(self, scene: sentinel1.Scene) -> water_detection.Water:
        db = sentinel1.backscatter(scene, self.settings)
        return water_detection.classify(db, self.terrain, self.bounds, self.corridor,
                                        self.anchors, self.settings)

    def run(self, start: date, end: date, limit: int | None = None,
            names: tuple[str, ...] | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        scenes = sentinel1.scenes(start, end, self.bounds, self.settings)
        if not scenes:
            raise ValueError("No Sentinel-1 acquisitions matched the filters")
        track = sentinel1.choose_track(scenes)
        scenes = [scene for scene in scenes if scene.track == track]
        acquisitions, estimates, samples = [], [], []
        names = names or tuple(self.domains)
        for scene in scenes[:limit]:
            timestamp = pd.Timestamp(scene.time_ms, unit="ms", tz="UTC")
            metadata = {**asdict(scene), "utc": timestamp.isoformat(),
                        "date": timestamp.tz_convert(LOCAL_ZONE).date().isoformat()}
            LOG.info("Processing %s, track %s", scene.index, track)
            try:
                water = self.classify(scene)
            except water_detection.ClassificationError as error:
                acquisitions.append(dict(metadata, qc=str(error)))
                continue
            LOG.info("Threshold %.2f dB, separation %.2f", water.threshold, water.separation)
            area = water_detection.areas(water, self.corridor, self.bounds, self.settings)
            if not area.get("domain_m2"):
                raise ValueError("The historical monitoring corridor contains no valid pixels")
            coverage = (area["covered_m2"] or 0) / area["domain_m2"]
            qc = "pass" if coverage >= self.settings.min_coverage else "partial_coverage"
            if not area["water_m2"]:
                qc = "no_classified_water"
            acquisitions.append(dict(metadata, **area, coverage=coverage, qc=qc,
                                     threshold_db=water.threshold, separation=water.separation))
            if qc != "pass":
                LOG.info("Acquisition excluded: %s (coverage %.1f%%)", qc, 100 * coverage)
                continue
            sample_stack = shoreline.sample_image(water, self.terrain, self.settings)
            for name in names:
                LOG.info("Sampling valid terrain in %s", name)
                frame, valid_fraction = shoreline.sample(
                    sample_stack, self.domains[name], self.settings, self.terrain
                )
                result = elevation.estimate(frame, self.settings)
                screened = self.terrain.screen(frame, self.settings)
                alternative = elevation.estimate(screened, self.settings)
                estimates.append(dict(
                    metadata, domain=name, **result, valid_terrain_fraction=valid_fraction,
                    screened_samples=len(screened), screened_qc=alternative["qc"],
                    screened_elevation_m=alternative.get("elevation_m"),
                ))
                samples.append(frame.assign(index=scene.index, date=metadata["date"], domain=name))
        return (pd.DataFrame(acquisitions), pd.DataFrame(estimates),
                pd.concat(samples, ignore_index=True) if samples else pd.DataFrame())
