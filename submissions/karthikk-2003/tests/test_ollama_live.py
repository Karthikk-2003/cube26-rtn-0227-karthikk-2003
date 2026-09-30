"""Explicitly opt-in local smoke test; no benchmark or persisted product findings."""

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

PARTICIPANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PARTICIPANT / "agent"))

from returns_manager.domain import SourceLineage, TenantContext
from returns_manager.ollama import OllamaVisionProvider
from returns_manager.validation import parse_record, read_csv
from returns_manager.vision import ImageInput, ObservationScope, image_availability, observe


@unittest.skipUnless(os.environ.get("OLLAMA_LIVE_TEST") == "1", "live Ollama smoke is opt-in")
class OllamaLiveTests(unittest.TestCase):
    def test_operator_supplied_image_returns_validated_observations(self):
        supplied = os.environ.get("OLLAMA_LIVE_IMAGE")
        if not supplied or not Path(supplied).is_file():
            self.skipTest("supply an existing genuine JPEG/PNG through OLLAMA_LIVE_IMAGE")
        image_path = Path(supplied)
        if image_path.stat().st_size > 10_000_000:
            self.skipTest("image exceeds the existing byte limit")
        content = image_path.read_bytes()
        availability = image_availability(content)
        if availability != "available":
            self.skipTest("genuine image decoder/input unavailable: " + availability)
        # Test-only context, explicitly unrelated to any real product/order identification.
        row, _ = next((r, s) for r, s in read_csv(PARTICIPANT.parents[1] / "data/returns_sample.csv")
                      if r["org_id"] == "org_demo_alpha")
        row = {**row, "record_id": "TEST-OLLAMA-LIVE", "unit_id": "TEST-OLLAMA-LIVE",
               "parts_list": "", "parts_missing": "", "photo_refs": str(image_path)}
        source = SourceLineage("TEST-live-smoke-context", hashlib.sha256(json.dumps(row).encode()).hexdigest(), 2)
        capture = parse_record(row, TenantContext("org_demo_alpha"), source)
        scope = ObservationScope.from_capture(capture)
        image = ImageInput(scope, "TEST-live-image", "TEST-live-evidence", str(image_path), "returned_product", "genuine", content)
        run = observe(capture, (image,), OllamaVisionProvider())
        if run.error_code in {"provider_unavailable", "provider_timeout"}:
            self.skipTest(run.error_code)
        self.assertEqual(run.status, "validated", run.error_code)
        self.assertEqual(asdict(run.observations.scope), asdict(scope))
        self.assertEqual(run.images[0].sha256, hashlib.sha256(content).hexdigest())
        # No observation accuracy assertion; nothing is written to a product database.


if __name__ == "__main__":
    unittest.main()
