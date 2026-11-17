"""Serialize the main graph through Earth Engine's offline API fixtures."""
from unittest.mock import patch

import ee
from ee.apitestcase import ApiTestCase

from lake_mead.config import Settings
from lake_mead.inundation import changes, scenario
from lake_mead.sentinel1 import Scene
from lake_mead.shoreline import sample_image, shoreline
from lake_mead.water_detection import areas
from lake_mead.workflow import Analysis


class TestEarthEngineGraph(ApiTestCase):
    def test_workflow_expressions(self):
        analysis = Analysis.create(Settings())
        scene = Scene("offline-scene-A", 0, 7, "A", "DESCENDING", 12,
                      ("offline-scene-A", "offline-scene-B"), 1)
        self.assertIn("gem-15_v1", analysis.terrain.elevation.serialize())
        histogram = {"backscatter_db": {"bucketMeans": [-22, -8], "histogram": [10, 10]}}
        with patch.object(ee.Dictionary, "getInfo", return_value=histogram):
            water = analysis.classify(scene)
        stack = sample_image(water, analysis.terrain, analysis.settings)
        self.assertIn("dtm", stack.pixels.serialize())
        self.assertIn("dsm_percentile_95", stack.pixels.serialize())
        self.assertIn("cumulativeCost", shoreline(water, analysis.settings).serialize())
        self.assertIn("observed_change", changes(water, water).serialize())
        self.assertIn("modeled_gain", scenario(water, analysis.terrain, 325,
                                               analysis.corridor, analysis.bounds,
                                               analysis.settings).serialize())
        with patch.object(ee.Dictionary, "getInfo", return_value={"water_m2": 100}):
            self.assertEqual(areas(water, analysis.corridor, analysis.bounds,
                                   analysis.settings)["water_m2"], 100)
