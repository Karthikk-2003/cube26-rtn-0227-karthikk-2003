"""Project-local UI integration with labelled synthetic bytes and injected providers."""
from dataclasses import replace, asdict
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from unittest.mock import Mock, patch
from wsgiref.util import setup_testing_defaults

PARTICIPANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PARTICIPANT / "agent"))
from returns_manager.ui import UIConfig, create_app
from returns_manager.domain import TenantContext, ValidationError
from returns_manager.observations import ProviderResponse
from returns_manager.demo import local_image, prepare_demo, select_provider


class DemoTests(unittest.TestCase):
    def setUp(self):
        scratch = PARTICIPANT / ".test-tmp"
        scratch.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.tmp.cleanup)
        self.image = Path(self.tmp.name) / "TEST-synthetic.png"
        self.image.write_bytes(b"TEST synthetic bytes; not a real image")
        self.config = UIConfig(Path(self.tmp.name) / "test.sqlite3", TenantContext("org_demo_alpha"),
            "TEST-reviewer", provider="gemini", demo_images=(self.image,))
        self.app = create_app(self.config)
        self.provider = Mock(name="TEST-provider")
        self.provider.name = "gemini"
        self.provider.mode = "real"
        self.provider.last_error = None
        self.provider.observe.side_effect = lambda r: ProviderResponse(json.dumps({"scope": asdict(r.scope),
            "identity": [], "components": [], "condition": [], "limitations": ["TEST synthetic provider output"]}),
            "gemini", "real", model_version="TEST-model", latency_ms=12)

    def request(self, path, body=None, app=None, origin="http://127.0.0.1:8000"):
        env = {}
        setup_testing_defaults(env)
        raw = json.dumps(body).encode() if body is not None else b""
        env.update(PATH_INFO=path, REQUEST_METHOD="POST" if body is not None else "GET",
            HTTP_HOST="127.0.0.1:8000", REMOTE_ADDR="127.0.0.1", HTTP_ORIGIN=origin,
            HTTP_X_RETURNS_REQUEST="1", CONTENT_LENGTH=str(len(raw)), CONTENT_TYPE="application/json")
        env["wsgi.input"] = io.BytesIO(raw)
        result = {}
        def start(status, headers):
            result.update(status=int(status.split()[0]), headers=dict(headers))
        raw = b"".join((app or self.app)(env, start))
        result["data"] = json.loads(raw) if result["headers"]["Content-Type"] == "application/json" else raw
        return result

    def inspect(self, command=None):
        with patch("returns_manager.ui.select_provider", return_value=self.provider), patch(
                "returns_manager.vision.image_availability", return_value="available"):
            return self.request("/api/demo/inspect", {"command_id": command or str(uuid.uuid4())})

    def test_inspection_persists_review_and_serves_only_scoped_hash_bound_image(self):
        result = self.inspect()
        self.assertEqual(result["status"], 200)
        rid = result["data"]["review_id"]
        detail = self.request(f"/api/reviews/{rid}")["data"]
        self.assertEqual(detail["raw_response"]["model_version"], "TEST-model")
        self.assertEqual(detail["business_status"], "pending_review")
        self.assertIsNone(detail["automated_assessment"]["condition"]["grade"])
        image_path = f"/api/reviews/{rid}/images/0"
        self.assertEqual(self.request(image_path)["data"], self.image.read_bytes())
        bravo = create_app(replace(self.config, tenant=TenantContext("org_demo_bravo")))
        self.assertEqual(self.request(image_path, app=bravo)["status"], 404)
        self.image.write_bytes(b"TEST changed bytes")
        self.assertEqual(self.request(image_path)["status"], 404)

    def test_retry_same_command_does_not_call_provider_twice(self):
        command = str(uuid.uuid4())
        first = self.inspect(command)
        second = self.inspect(command)
        self.assertEqual(first["data"]["review_id"], second["data"]["review_id"])
        self.assertTrue(second["data"]["reused"])
        self.provider.observe.assert_called_once()

    def test_boundary_disabled_and_no_browser_paths(self):
        self.assertEqual(self.request("/api/demo/inspect", {"command_id": str(uuid.uuid4())}, origin="https://evil.example")["status"], 403)
        self.assertEqual(self.request("/api/demo/inspect", {"command_id": "bad", "image": "../secret"})["status"], 422)
        disabled = create_app(replace(self.config, provider="disabled"))
        self.assertEqual(self.request("/api/demo/inspect", {"command_id": str(uuid.uuid4())}, app=disabled)["status"], 422)
        self.provider.observe.assert_not_called()

    def test_unavailable_provider_still_routes_review(self):
        self.provider.observe.side_effect = TimeoutError()
        result = self.inspect()["data"]
        self.assertEqual(result["error_code"], "provider_timeout")
        item = self.request(f"/api/reviews/{result['review_id']}")["data"]
        self.assertIsNone(item["observations"])
        self.assertEqual(item["business_status"], "pending_review")

    def test_outside_path_rejected_without_read(self):
        with self.assertRaises(ValidationError):
            local_image(PARTICIPANT.parent / "OUTSIDE_TEST.png")

    def test_fixture_is_explicit_and_never_live(self):
        app = create_app(replace(self.config, provider="fixture"))
        result = self.request("/api/demo/inspect", {"command_id": str(uuid.uuid4())}, app=app)
        item = self.request(f"/api/reviews/{result['data']['review_id']}", app=app)["data"]
        self.assertEqual(item["observations"]["provider_mode"], "fixture")
        self.assertEqual(item["evidence"][0]["availability"], "fixture_only")
        self.assertEqual(self.request(f"/api/reviews/{result['data']['review_id']}/images/0", app=app)["status"], 404)

    def test_explicit_provider_selection_and_context_never_infers(self):
        _, _, capture, _ = prepare_demo((self.image,), self.config.tenant, "TEST-reviewer", str(uuid.uuid4()), fixture=True)
        with patch("returns_manager.gemini.build_opener") as gemini_http, patch("returns_manager.ollama.build_opener") as ollama_http:
            for name in ("gemini", "ollama", "fixture"):
                with self.subTest(provider=name), patch.dict("os.environ", {}, clear=True):
                    provider = select_provider(name, capture)
                    self.assertEqual(provider.name, "fixture-json" if name == "fixture" else name)
                    app = create_app(replace(self.config, provider=name))
                    context = self.request("/api/context", app=app)["data"]
                    self.assertEqual(context["ai_provider"], name)
                    self.assertTrue(context["demo_enabled"])
            gemini_http.assert_not_called()
            ollama_http.assert_not_called()
        with self.assertRaises(ValidationError):
            select_provider("automatic", capture)

    def test_fixture_demo_can_be_reviewed_with_history_without_ai(self):
        app = create_app(replace(self.config, provider="fixture"))
        with patch("returns_manager.gemini.build_opener") as gemini, patch("returns_manager.ollama.build_opener") as ollama:
            result = self.request("/api/demo/inspect", {"command_id": str(uuid.uuid4())}, app=app)
            url = f"/api/reviews/{result['data']['review_id']}"
            before = self.request(url, app=app)["data"]
            for revision, status in ((1, "in_review"), (2, "reviewed")):
                changed = self.request(url + "/transition", {"command_id": f"TEST-review-{revision}",
                    "status": status, "expected_revision": revision, "reason": "TEST fixture review only",
                    "decisions": [{"dimension": "identity", "verdict": "UNCERTAIN", "evidence_refs": []}] if status == "reviewed" else []}, app=app)
                self.assertEqual(changed["status"], 200)
            after = self.request(url, app=app)["data"]
            self.assertEqual(after["status"], "reviewed")
            self.assertEqual(after["business_status"], "pending_review")
            self.assertEqual(after["observations"], before["observations"])
            self.assertIsNone(after["raw_response"]["latency_ms"])
            self.assertEqual(len(self.request(url + "/history", app=app)["data"]["events"]), 3)
            gemini.assert_not_called()
            ollama.assert_not_called()

    def test_ollama_demo_uses_existing_parser_store_review_and_actual_metadata(self):
        from returns_manager.ollama import OllamaConfig, OllamaVisionProvider
        transport = Mock(side_effect=lambda url, body, timeout: json.dumps({"done": True, "done_reason": "stop",
            "model": "TEST-mocked-ollama", "total_duration": 12000000,
            "message": {"role": "assistant", "content": json.dumps({
                "scope": json.loads(body["messages"][1]["content"].split("\n")[0])["scope"],
                "identity": [], "components": [], "condition": [], "limitations": ["TEST mocked Ollama only"]})}}).encode())
        self.provider = OllamaVisionProvider(OllamaConfig(), transport=transport)
        self.app = create_app(replace(self.config, provider="ollama"))
        with patch("returns_manager.gemini.build_opener") as gemini:
            result = self.inspect()["data"]
        self.assertEqual(result["status"], "validated")
        detail = self.request(f"/api/reviews/{result['review_id']}")["data"]
        self.assertEqual(detail["observations"]["provider_name"], "ollama")
        self.assertEqual(detail["raw_response"]["latency_ms"], 12)
        self.assertEqual(detail["business_status"], "pending_review")
        self.assertEqual(self.request(f"/api/reviews/{result['review_id']}/images/0")["data"], self.image.read_bytes())
        transport.assert_called_once()
        gemini.assert_not_called()

    def test_real_gemini_http_503_path_routes_review_without_fallback(self):
        from urllib.error import HTTPError
        from returns_manager.gemini import GeminiConfig, GeminiVisionProvider
        self.provider = GeminiVisionProvider(GeminiConfig(api_key="TEST", free_tier_confirmed=True))
        # Explicit synthetic PNG signature, with decoder mocked by inspect().
        self.image.write_bytes(b"\x89PNG\r\n\x1a\nTEST synthetic bytes, not image evidence")
        opener = Mock()
        opener.open.side_effect = lambda *a, **kw: (_ for _ in ()).throw(
            HTTPError("TEST", 503, "TEST", {}, io.BytesIO(b"TEST secret provider body")))
        with patch("returns_manager.gemini.build_opener", return_value=opener), patch(
                "returns_manager.gemini.time.sleep"), patch("returns_manager.ollama.OllamaVisionProvider") as fallback:
            command = str(uuid.uuid4())
            result = self.inspect(command)["data"]
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual(result["diagnostic"], "gemini_overloaded")
            self.assertEqual(result["error_code"], "provider_unavailable")
            self.assertEqual(opener.open.call_count, 3)
            self.assertTrue(self.inspect(command)["data"]["reused"])
            self.assertEqual(opener.open.call_count, 3)
            fallback.assert_not_called()
        item = self.request(f"/api/reviews/{result['review_id']}")["data"]
        self.assertIsNone(item["observations"])
        self.assertIsNone(item["raw_response"])
        self.assertEqual(item["business_status"], "pending_review")
        self.assertIsNone(item["automated_assessment"]["condition"]["grade"])
        self.assertNotIn("TEST secret provider body", json.dumps(item))
