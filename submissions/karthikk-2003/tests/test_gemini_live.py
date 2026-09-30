"""Opt-in genuine project-local image smoke. No product database or benchmark claim."""
import os
from pathlib import Path
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from returns_manager.demo import prepare_demo
from returns_manager.domain import TenantContext
from returns_manager.gemini import GeminiVisionProvider
from returns_manager.vision import observe


@unittest.skipUnless(os.environ.get("GEMINI_LIVE_TEST") == "1", "live Gemini test is opt-in")
class GeminiLiveTests(unittest.TestCase):
    def test_project_image(self):
        if not os.environ.get("GEMINI_API_KEY"):
            self.skipTest("GEMINI_API_KEY missing")
        if os.environ.get("GEMINI_FREE_TIER_CONFIRMED") != "1":
            self.skipTest("Free-tier confirmation required")
        path = os.environ.get("GEMINI_LIVE_IMAGE")
        if not path:
            self.skipTest("set GEMINI_LIVE_IMAGE to a participant-local product photo")
        _, _, capture, images = prepare_demo((Path(path),), TenantContext("LOCAL_SMOKE_TEST_ORGANIZATION"),
            "LOCAL_SMOKE_TEST_OPERATOR", str(uuid.uuid4()))
        provider = GeminiVisionProvider()
        run = observe(capture, images, provider)
        self.assertEqual(run.status, "validated", (run.error_code, provider.last_error))
        self.assertEqual(run.observations.scope, run.scope)
        self.assertEqual(run.images[0].reference, images[0].reference)
        self.assertIsNotNone(run.images[0].sha256)
        self.assertFalse(hasattr(run.observations, "disposition"))
        self.assertFalse(hasattr(run.observations, "grade"))
        print(f"Live Gemini: model={run.raw_response.model_version}; latency_ms={run.raw_response.latency_ms:.1f}; validated")
