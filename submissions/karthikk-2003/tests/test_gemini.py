"""Offline synthetic transport tests; never real model/evaluation evidence."""
import base64
from dataclasses import asdict, replace
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from returns_manager.domain import SourceLineage, TenantContext, TenantMismatch, ValidationError
from returns_manager.validation import FIELDS, parse_record
from returns_manager.vision import ImageInput, ObservationScope, observe, prepare_request, ProviderUnavailable
from returns_manager.gemini import GeminiConfig, GeminiVisionProvider, post_json, NoRedirect, MAX_RESPONSE_BYTES
from returns_manager.storage import Store
from returns_manager.service import inspect_capture
from returns_manager.review_storage import ReviewWorkflow


class GeminiTests(unittest.TestCase):
    def setUp(self):
        sleeper = patch("returns_manager.gemini.time.sleep")
        self.sleep = sleeper.start()
        self.addCleanup(sleeper.stop)
        self.row = {k: "" for k in FIELDS}
        self.row.update(record_id="TEST-record", unit_id="TEST-unit", org_id="org_demo_alpha",
            order_id="TEST-order", ordered_sku="TEST-sku", ordered_asin="TEST-asin", operator_id="TEST-operator",
            captured_at="2026-09-30T00:00:00Z", photo_refs="TEST/image.png")
        self.source = SourceLineage("TEST-synthetic", hashlib.sha256(json.dumps(self.row).encode()).hexdigest(), 2)
        self.capture = parse_record(self.row, TenantContext("org_demo_alpha"), self.source)
        self.scope = ObservationScope.from_capture(self.capture)
        self.images = (ImageInput(self.scope, "TEST-image", "TEST-evidence", "TEST/image.png", "returned_product",
            "genuine", b"\x89PNG\r\n\x1a\nTEST not a real image; decoder explicitly mocked"),)
        self.payload = {"scope": asdict(self.scope), "identity": [], "components": [], "condition": [],
            "limitations": ["TEST synthetic response"]}
        self.transport = Mock(side_effect=lambda *args: self.envelope())
        self.provider = GeminiVisionProvider(GeminiConfig("TEST_NOT_A_SECRET", free_tier_confirmed=True), transport=self.transport)

    def envelope(self, **changes):
        return json.dumps({"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(self.payload)}]}}],
            "modelVersion": "TEST-model", "responseId": "TEST-response", "usageMetadata": {"totalTokenCount": 42}, **changes}).encode()

    def run_model(self):
        with patch("returns_manager.vision.image_availability", return_value="available"):
            return observe(self.capture, self.images, self.provider)

    def test_environment_and_secret_safe_repr(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "TEST_NOT_A_SECRET", "GEMINI_MODEL": "gemini-3.8-flash",
                "GEMINI_TIMEOUT_SECONDS": "45", "GEMINI_FREE_TIER_CONFIRMED": "1"}, clear=True):
            config = GeminiConfig.from_env()
        self.assertEqual(config.timeout_seconds, 45)
        self.assertNotIn("TEST_NOT_A_SECRET", repr(config))
        self.assertTrue(config.free_tier_confirmed)

    def test_invalid_config(self):
        for kwargs in ({"model": "../evil"}, {"timeout_seconds": 10**1000}, {"timeout_seconds": True},
                {"timeout_seconds": 0}, {"api_key": "TEST\nHEADER"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValidationError):
                GeminiConfig(**kwargs)

    def test_missing_key_or_tier_confirmation_no_network(self):
        for config in (GeminiConfig(), GeminiConfig("TEST")):
            self.provider = GeminiVisionProvider(config, transport=self.transport)
            self.assertEqual(self.run_model().error_code, "provider_unavailable")
        self.transport.assert_not_called()

    def test_request_and_success_lineage(self):
        run = self.run_model()
        self.assertEqual(run.status, "validated")
        url, body, timeout, key = self.transport.call_args.args
        self.assertEqual(url, "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent")
        self.assertNotIn(key, url + json.dumps(body))
        part = body["contents"][0]["parts"][1]["inlineData"]
        self.assertEqual(base64.b64decode(part["data"]), self.images[0].content)
        self.assertEqual(part["mimeType"], "image/png")
        self.assertEqual(body["generationConfig"]["responseMimeType"], "application/json")
        self.assertNotIn("tools", body)
        self.assertNotIn("JSON schema", body["contents"][0]["parts"][0]["text"])
        self.assertEqual(run.raw_response.text, json.dumps(self.payload))
        self.assertEqual(run.raw_response.token_usage, 42)
        self.assertGreaterEqual(run.raw_response.latency_ms, 0)
        self.assertEqual(run.images[0].reference, self.images[0].reference)
        self.assertEqual(run.images[0].sha256, hashlib.sha256(self.images[0].content).hexdigest())
        self.assertEqual(run.observations.scope, self.scope)

    def test_scope_and_evidence_and_decision_leakage(self):
        original = self.payload.copy()
        for changes, code in (({"scope": {**asdict(self.scope), "unit_id": "TEST-foreign"}}, "response_scope_mismatch"),
                ({"disposition": "restock"}, "invalid_response"), ({"grade": "new"}, "invalid_response"),
                ({"identity": [{"field": "model", "state": "observed", "values": ["TEST"],
                    "evidence_refs": ["FOREIGN"], "limitations": []}]}, "invalid_response")):
            with self.subTest(changes=changes):
                self.payload = {**original, **changes}
                run = self.run_model()
                self.assertEqual(run.error_code, code)
                self.assertIsNone(run.observations)
                self.assertIsNone(run.raw_response)

    def test_input_isolation_no_network(self):
        for scope in (replace(self.scope, tenant=TenantContext("org_demo_bravo")), replace(self.scope, unit_id="other"),
                replace(self.scope, record_id="other")):
            with self.assertRaises(TenantMismatch):
                observe(self.capture, (replace(self.images[0], scope=scope),), self.provider)
        self.transport.assert_not_called()

    def test_missing_corrupt_images_no_network(self):
        for content in (None, b"not an image"):
            run = observe(self.capture, (replace(self.images[0], content=content),), self.provider)
            self.assertEqual(run.status, "unavailable")
        self.transport.assert_not_called()

    def test_malformed_blocked_empty_and_truncated(self):
        for raw in (b"{", b"[]", self.envelope(promptFeedback={"blockReason": "SAFETY"}),
                self.envelope(candidates=[]), self.envelope(candidates=[{"finishReason": "MAX_TOKENS"}]),
                self.envelope(candidates=[{"finishReason": "STOP", "content": {"parts": [{"text": ""}]}}]),
                self.envelope(candidates=[{"finishReason": "STOP", "content": {"parts": [{"text": "not json"}]}}])):
            self.transport.side_effect = None
            self.transport.return_value = raw
            run = self.run_model()
            self.assertEqual(run.status, "unavailable")
            self.assertIsNone(run.observations)

    def test_unknown_not_visible_remains_unknown(self):
        self.payload["components"] = [{"component": "TEST cable", "presence": "unknown", "visibility": "not_visible",
            "quantity": None, "quantity_reliable": False, "absence_basis": None,
            "evidence_refs": [], "limitations": ["TEST not visible"]}]
        run = self.run_model()
        self.assertEqual(run.observations.components[0].presence, "unknown")

    def test_timeout_and_safe_errors(self):
        for exc, code in ((TimeoutError(), "provider_timeout"), (ProviderUnavailable("gemini_rate_limited"), "provider_unavailable"),
                (RuntimeError("TEST"), "provider_failure")):
            self.transport.side_effect = exc
            self.assertEqual(self.run_model().error_code, code)

    def test_telemetry_and_application_limits(self):
        for token in (-1, True, 10**1000):
            self.transport.side_effect = None
            self.transport.return_value = self.envelope(usageMetadata={"totalTokenCount": token})
            self.assertEqual(self.run_model().status, "unavailable")
        self.transport.side_effect = lambda *args: self.envelope()
        self.payload["limitations"] = ["T" * 8193]
        self.assertEqual(self.run_model().error_code, "invalid_response")

    def test_storage_review_preserves_real_provider_and_uncertainty(self):
        with Store(Path(":memory:"), self.capture.tenant) as store:
            with patch("returns_manager.vision.image_availability", return_value="available"):
                attempt = inspect_capture(self.row, self.source, store, self.images, self.provider)
            workflow = ReviewWorkflow(store)
            rid = workflow.route(self.row["record_id"], self.row["unit_id"], attempt_id=attempt)
            item = workflow.get(rid, self.row["record_id"], self.row["unit_id"])
            self.assertEqual(item["observations"]["provider_name"], "gemini")
            self.assertEqual(item["business_status"], "pending_review")
            self.assertIsNone(item["automated_assessment"]["condition"]["grade"])

    def test_http_errors_never_expose_response_or_key(self):
        for status, code in ((401, "gemini_authentication_failed"), (403, "gemini_authentication_failed"),
                (429, "gemini_rate_limited"), (500, "gemini_http_error"), (400, "gemini_request_rejected"),
                (404, "gemini_model_unavailable"), (503, "gemini_overloaded")):
            opener = Mock()
            opener.open.side_effect = HTTPError("TEST", status, "SECRET", {}, io.BytesIO(b"SECRET"))
            with patch("returns_manager.gemini.build_opener", return_value=opener), self.assertRaises(ProviderUnavailable) as caught:
                post_json(self.provider.config.endpoint, {}, 1, "TEST")
            self.assertEqual(str(caught.exception), code)

    def test_transport_headers_redirects_and_bounds(self):
        response = Mock(status=200)
        response.read.return_value = b"{}"
        opener = Mock()
        opener.open.return_value.__enter__ = Mock(return_value=response)
        opener.open.return_value.__exit__ = Mock(return_value=False)
        with patch("returns_manager.gemini.build_opener", return_value=opener) as factory:
            post_json(self.provider.config.endpoint, {}, 5, "TEST")
        self.assertEqual(factory.call_args.args[0].proxies, {})
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_header("X-goog-api-key"), "TEST")
        self.assertNotIn("TEST", request.full_url)
        response.read.assert_called_once_with(MAX_RESPONSE_BYTES + 1)
        with self.assertRaises(ProviderUnavailable):
            NoRedirect().redirect_request(None)
        with self.assertRaises(ValidationError):
            post_json("https://example.com", {}, 5, "TEST")

    def test_transport_request_and_response_size_limits(self):
        with patch("returns_manager.gemini.MAX_REQUEST_BYTES", 10), patch("returns_manager.gemini.build_opener") as factory:
            with self.assertRaises(ValidationError):
                post_json(self.provider.config.endpoint, {"TEST": "too long"}, 5, "TEST")
            factory.assert_not_called()
        self.transport.side_effect = None
        with patch("returns_manager.gemini.MAX_RESPONSE_BYTES", 10):
            self.transport.return_value = b"T" * 11
            self.assertEqual(self.run_model().error_code, "provider_failure")

    def test_direct_provider_rejects_changed_bytes_and_scope(self):
        with patch("returns_manager.vision.image_availability", return_value="available"):
            request = prepare_request(self.capture, self.images, "real")
        with self.assertRaises(TenantMismatch):
            self.provider.observe(replace(request, scope=replace(self.scope, unit_id="TEST-other")))
        with self.assertRaises(ValidationError):
            self.provider.observe(replace(request, image_contents=(b"TEST changed",)))
        self.transport.assert_not_called()

    def test_transport_network_and_timeout_errors(self):
        for error, expected in ((URLError("TEST network"), ProviderUnavailable),
                (URLError(TimeoutError()), TimeoutError), (TimeoutError(), TimeoutError)):
            opener = Mock()
            opener.open.side_effect = error
            with patch("returns_manager.gemini.build_opener", return_value=opener), self.assertRaises(expected):
                post_json(self.provider.config.endpoint, {}, 1, "TEST")

    def test_transient_http_retries_are_bounded_with_exponential_jitter(self):
        for status in (429, 500, 502, 503, 504):
            with self.subTest(status=status):
                self.sleep.reset_mock()
                opener = Mock()
                opener.open.side_effect = lambda *a, **kw: (_ for _ in ()).throw(HTTPError("TEST", status, "TEST", {}, io.BytesIO()))
                with patch("returns_manager.gemini.build_opener", return_value=opener), patch(
                        "returns_manager.gemini.random.uniform", return_value=0.75), self.assertRaises(ProviderUnavailable):
                    post_json(self.provider.config.endpoint, {}, 90, "TEST")
                self.assertEqual(opener.open.call_count, 3)
                self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [0.75, 1.5])

    def test_controlled_single_http_attempt_stops_on_503(self):
        opener = Mock()
        opener.open.side_effect = HTTPError('TEST', 503, 'TEST', {}, io.BytesIO())
        self.sleep.reset_mock()
        with patch('returns_manager.gemini.build_opener', return_value=opener), self.assertRaises(ProviderUnavailable):
            post_json(self.provider.config.endpoint, {}, 90, 'TEST', max_attempts=1)
        opener.open.assert_called_once()
        self.sleep.assert_not_called()
        for count in (0, 4, True):
            with self.assertRaises(ValidationError):
                post_json(self.provider.config.endpoint, {}, 90, 'TEST', max_attempts=count)

    def test_retry_after_and_permanent_failures_stop(self):
        for status, headers in ((401, {}), (400, {}), (501, {}), (429, {"Retry-After": "120"}), (503, {"Retry-After": "invalid"})):
            opener = Mock()
            opener.open.side_effect = HTTPError("TEST", status, "TEST", headers, io.BytesIO())
            self.sleep.reset_mock()
            with patch("returns_manager.gemini.build_opener", return_value=opener), self.assertRaises(ProviderUnavailable):
                post_json(self.provider.config.endpoint, {}, 90, "TEST")
            self.assertEqual(opener.open.call_count, 1)
            self.sleep.assert_not_called()

    def test_retry_success_and_server_delay(self):
        response = Mock(status=200)
        response.read.return_value = b"{}"
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.side_effect = [HTTPError("TEST", 503, "TEST", {"Retry-After": "3"}, io.BytesIO()), context]
        with patch("returns_manager.gemini.build_opener", return_value=opener):
            self.assertEqual(post_json(self.provider.config.endpoint, {}, 90, "TEST"), b"{}")
        self.sleep.assert_called_once_with(3)
        self.assertEqual(opener.open.call_count, 2)

    def test_retry_budget_stops_before_another_request(self):
        opener = Mock()
        opener.open.side_effect = HTTPError("TEST", 503, "TEST", {}, io.BytesIO())
        with patch("returns_manager.gemini.build_opener", return_value=opener), patch(
                "returns_manager.gemini.time.monotonic", side_effect=[0, 0, 89.9]), patch(
                "returns_manager.gemini.random.uniform", return_value=0.75), self.assertRaises(ProviderUnavailable):
            post_json(self.provider.config.endpoint, {}, 90, "TEST")
        opener.open.assert_called_once()
        self.sleep.assert_not_called()
