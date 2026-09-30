"""Synthetic transport/parser tests only; no live server or image/model evidence.

Successful-path tests explicitly mock the existing decoder with labelled TEST bytes.
Missing/corrupt-image tests use the actual image boundary. No fake image files exist.
"""

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

PARTICIPANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PARTICIPANT / "agent"))

from returns_manager.domain import TenantContext, TenantMismatch, ValidationError
from returns_manager.ollama import OllamaConfig, OllamaVisionProvider, MAX_RESPONSE_BYTES, post_json, _NoRedirect
from returns_manager.review_storage import ReviewWorkflow
from returns_manager.service import inspect_capture
from returns_manager.storage import Store
from returns_manager.validation import parse_record, read_csv
from returns_manager.vision import ImageInput, ObservationScope, ProviderUnavailable, observe, prepare_request


class OllamaTests(unittest.TestCase):
    def setUp(self):
        self.row, self.source = next((r, s) for r, s in read_csv(PARTICIPANT.parents[1] / "data/returns_sample.csv")
                                     if r["org_id"] == "org_demo_alpha")
        self.tenant = TenantContext("org_demo_alpha")
        self.capture = parse_record(self.row, self.tenant, self.source)
        self.scope = ObservationScope.from_capture(self.capture)
        self.content = b"TEST ONLY bytes; successful decoder is explicitly mocked"
        self.images = tuple(ImageInput(self.scope, f"TEST-image-{i}", f"TEST-evidence-{i}", image.reference,
                                      "returned_product", "genuine", self.content + bytes([i]))
                            for i, image in enumerate(self.capture.images[:2]))
        self.payload = {"scope": asdict(self.scope), "identity": [], "components": [], "condition": [],
                        "limitations": ["TEST synthetic response; no real inference"]}
        self.transport = Mock(side_effect=lambda *args: self.envelope())
        self.provider = OllamaVisionProvider(OllamaConfig(), transport=self.transport)

    def envelope(self, content=None, **changes):
        return json.dumps({"model": "TEST-returned-model-tag", "done": True, "done_reason": "stop",
            "message": {"role": "assistant", "content": json.dumps(self.payload) if content is None else content},
            **changes}).encode()

    def run_model(self):
        with patch("returns_manager.vision.image_availability", return_value="available"):
            return observe(self.capture, self.images, self.provider)

    def identity(self, value="TEST model A", evidence="TEST-evidence-0"):
        return {"field": "model", "state": "observed", "values": [value],
                "evidence_refs": [evidence], "limitations": ["TEST fixture"]}

    def test_defaults_and_environment_are_opt_in(self):
        with patch.dict("os.environ", {}, clear=True):
            config = OllamaConfig.from_env()
        self.assertEqual((config.base_url, config.model, config.timeout_seconds),
                         ("http://localhost:11434", "qwen2.5vl:3b", 240))
        with patch.dict("os.environ", {"OLLAMA_BASE_URL": "http://[::1]:11435/",
                                      "OLLAMA_MODEL": "TEST-local-model", "OLLAMA_TIMEOUT_SECONDS": "300.5"}):
            provider = OllamaVisionProvider(transport=self.transport)
        self.assertEqual(provider.config.endpoint, "http://[::1]:11435/api/chat")
        self.assertEqual(provider.config.timeout_seconds, 300.5)
        self.transport.assert_not_called()

    def test_invalid_configuration_rejected_before_network(self):
        for url in ("https://localhost:11434", "http://example.com", "http://0.0.0.0:11434",
                    "http://user:secret@localhost:11434", "http://localhost:11434/api/chat",
                    "http://localhost:11434?x=1", "http://localhost:11434/#x", "http://localhost:0", "http://localhost:bad"):
            with self.subTest(url=url), self.assertRaises(ValidationError):
                OllamaConfig(base_url=url)
        for timeout in (True, 0, -1, float("inf"), float("nan"), 10**1000, 86401, "240"):
            with self.subTest(timeout_type=type(timeout).__name__), self.assertRaises(ValidationError):
                OllamaConfig(timeout_seconds=timeout)
        for model in ("", "TEST:cloud", "TEST-cloud", "with whitespace"):
            with self.subTest(model=model), self.assertRaises(ValidationError):
                OllamaConfig(model=model)
        with patch.dict("os.environ", {"OLLAMA_TIMEOUT_SECONDS": "invalid"}), self.assertRaises(ValidationError):
            OllamaConfig.from_env()

    def test_success_keeps_raw_text_and_evidence_order(self):
        self.payload["identity"] = [self.identity()]
        raw = json.dumps(self.payload, indent=2)
        self.transport.side_effect = None
        self.transport.return_value = self.envelope(raw)
        run = self.run_model()
        self.assertEqual(run.status, "validated")
        self.assertEqual(run.raw_response.text, raw)
        self.assertEqual(run.observations.identity[0].values, ("TEST model A",))
        self.assertEqual(run.observations.identity[0].evidence_refs, ("TEST-evidence-0",))
        url, body, timeout = self.transport.call_args.args
        self.assertEqual(url, "http://127.0.0.1:11434/api/chat")
        self.assertEqual(timeout, 240)
        self.assertFalse(body["stream"])
        self.assertEqual(body["model"], "qwen2.5vl:3b")
        self.assertEqual([base64.b64decode(i) for i in body["messages"][1]["images"]], [i.content for i in self.images])
        for supplied, descriptor in zip(self.images, run.images):
            self.assertEqual(descriptor.scope, self.scope)
            self.assertEqual(descriptor.reference, supplied.reference)
            self.assertEqual(descriptor.sha256, hashlib.sha256(supplied.content).hexdigest())
        self.assertIsNone(run.raw_response.request_id)
        self.assertIsNone(run.raw_response.latency_ms)
        self.assertIsNone(run.raw_response.token_usage)

    def test_schema_and_prompt_cannot_supply_business_fields(self):
        self.run_model()
        body = self.transport.call_args.args[1]
        schema = body["format"]
        self.assertEqual(set(schema["properties"]), {"scope", "identity", "components", "condition", "limitations"})
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["scope"]["properties"]["unit_id"]["const"], self.scope.unit_id)
        component = schema["properties"]["components"]["items"]["properties"]
        self.assertIn("occluded", component["visibility"]["enum"])
        self.assertNotIn("missing", component["presence"]["enum"])
        self.assertEqual(component["evidence_refs"]["items"]["enum"], ["TEST-evidence-0", "TEST-evidence-1"])
        self.assertNotIn("grade", schema["properties"]["condition"]["items"]["properties"])
        prompt = body["messages"][0]["content"]
        self.assertIn("untrusted data", prompt)
        self.assertIn("does NOT mean absent", prompt)
        self.assertNotIn(self.row["ordered_sku"], body["messages"][1]["content"])
        self.assertNotIn("operator_disposition", body["messages"][1]["content"])

    def test_generation_schema_omits_max_length_but_keeps_min_length(self):
        self.assertEqual(self.run_model().status, "validated")
        schema = self.transport.call_args.args[1]["format"]
        bounded_strings = []

        def check(node):
            if isinstance(node, dict):
                self.assertNotIn("maxLength", node)
                if "minLength" in node:
                    self.assertEqual(node["minLength"], 1)
                    bounded_strings.append(node)
                for value in node.values():
                    check(value)
            elif isinstance(node, list):
                for value in node:
                    check(value)

        check(schema)
        self.assertTrue(bounded_strings)

    def test_compact_generation_still_enforces_application_array_limit(self):
        self.assertEqual(self.run_model().status, "validated")
        body = self.transport.call_args.args[1]
        self.assertNotIn('"maxItems"', json.dumps(body["format"]))
        self.assertNotIn('"properties"', body["messages"][1]["content"])
        self.assertEqual(body["options"]["num_predict"], 1024)
        self.payload["identity"] = [self.identity()] * 201
        run = self.run_model()
        self.assertEqual(run.error_code, "invalid_response")
        self.assertIsNone(run.observations)
        self.assertIsNone(run.raw_response)

    def test_application_observation_length_limit_still_enforced(self):
        for length, expected in ((8192, "validated"), (8193, "unavailable")):
            with self.subTest(length=length):
                self.payload["identity"] = [self.identity("T" * length)]
                run = self.run_model()
                self.assertEqual(run.status, expected)
                if length == 8192:
                    self.assertIsNone(run.error_code)
                    self.assertEqual(run.observations.identity[0].values, ("T" * length,))
                else:
                    self.assertEqual(run.error_code, "invalid_response")
                    self.assertIsNone(run.raw_response)
                    self.assertIsNone(run.observations)

    def test_malformed_model_json_rejected_without_repair(self):
        for content in ("{", "[]", "```json\n{}\n```", '{"scope":1,"scope":2}', '{"x":NaN}'):
            with self.subTest(content=content):
                self.transport.side_effect = None
                self.transport.return_value = self.envelope(content)
                run = self.run_model()
                self.assertEqual(run.error_code, "invalid_response")
                self.assertIsNone(run.raw_response)
                self.assertIsNone(run.observations)

    def test_business_fields_and_unknown_evidence_fail_validation(self):
        invalid = []
        for field in ("grade", "disposition", "confidence", "coordinates"):
            invalid.append({**self.payload, field: "RESTOCK"})
        invalid += [{**self.payload, "identity": [self.identity(evidence="TEST-foreign")]},
                    {**self.payload, "condition": [{"feature": "new", "state": "observed", "description": "TEST",
                                                   "evidence_refs": ["TEST-evidence-0"], "limitations": []}]}]
        for payload in invalid:
            with self.subTest(payload=payload):
                self.payload = payload
                self.assertEqual(self.run_model().error_code, "invalid_response")

    def test_uncertainty_visibility_and_conflicts_preserved(self):
        self.payload["identity"] = [self.identity(), self.identity("TEST model B", "TEST-evidence-1")]
        self.payload["components"] = [{"component": "TEST cable", "presence": "unknown", "visibility": "occluded",
            "quantity": None, "quantity_reliable": False, "absence_basis": None,
            "evidence_refs": ["TEST-evidence-0"], "limitations": ["TEST obscured area"]}]
        run = self.run_model()
        self.assertEqual(run.status, "validated")
        self.assertEqual(run.observations.conflicts, ("identity:model",))
        self.assertEqual(len(run.observations.identity), 2)
        self.assertEqual(run.observations.components[0].presence, "unknown")
        self.assertEqual(run.observations.components[0].visibility, "occluded")
        self.assertIsNone(run.observations.components[0].quantity)

    def test_model_wrong_scope_is_not_rebound(self):
        for key, value in (("unit_id", "TEST-other-unit"), ("record_id", "TEST-other-record"),
                           ("tenant", {"organization_id": "org_demo_bravo", "client_id": None})):
            with self.subTest(key=key):
                self.payload["scope"] = {**asdict(self.scope), key: value}
                run = self.run_model()
                self.assertEqual(run.error_code, "response_scope_mismatch")
                self.assertIsNone(run.raw_response)

    def test_foreign_input_never_reaches_transport(self):
        for scope in (replace(self.scope, tenant=TenantContext("org_demo_bravo")),
                      replace(self.scope, unit_id="TEST-other"), replace(self.scope, record_id="TEST-other")):
            with self.subTest(scope=scope), self.assertRaises(TenantMismatch):
                observe(self.capture, (replace(self.images[0], scope=scope),), self.provider)
        self.transport.assert_not_called()

    def test_missing_corrupt_and_decoder_unavailable_never_call_provider(self):
        for content, expected in ((None, "missing_image"), (b"", "missing_image"), (b"TEST-not-image", "unreadable_image")):
            with self.subTest(content=content):
                run = observe(self.capture, (replace(self.images[0], content=content),), self.provider)
                self.assertEqual(run.error_code, expected)
        with patch("returns_manager.vision.image_availability", return_value="decoder_unavailable"):
            self.assertEqual(observe(self.capture, self.images, self.provider).error_code, "image_decoder_unavailable")
        self.transport.assert_not_called()

    def test_timeout_unavailable_and_unexpected_failure_are_safe(self):
        for error, code in ((TimeoutError(), "provider_timeout"), (ProviderUnavailable(), "provider_unavailable"),
                            (RuntimeError("TEST secret"), "provider_failure")):
            with self.subTest(code=code):
                self.transport.side_effect = error
                run = self.run_model()
                self.assertEqual(run.error_code, code)
                self.assertIsNone(run.observations)
                self.assertIsNone(run.raw_response)

    def test_malformed_incomplete_and_tool_envelopes_fail(self):
        for raw in (b"{", b"\xff", b"[]", b'{"done":true,"done":false}', self.envelope(done=False),
                    self.envelope(done_reason="length"), self.envelope(error="TEST failure"),
                    self.envelope(message={"role": "assistant", "content": "{}", "tool_calls": [{"name": "TEST"}]}),
                    b"x" * (MAX_RESPONSE_BYTES + 1)):
            with self.subTest(length=len(raw)):
                self.transport.side_effect = None
                self.transport.return_value = raw
                run = self.run_model()
                self.assertEqual(run.error_code, "provider_failure")
                self.assertIsNone(run.observations)

    def test_actual_metadata_only_and_overflow_rejection(self):
        self.transport.side_effect = None
        self.transport.return_value = self.envelope(total_duration=123456789, prompt_eval_count=10, eval_count=20)
        raw = self.run_model().raw_response
        self.assertEqual(raw.model_version, "TEST-returned-model-tag")
        self.assertEqual(raw.latency_ms, 123.456789)
        self.assertEqual(raw.token_usage, 30)
        for key, value in (("total_duration", 10**1000), ("total_duration", -1), ("eval_count", True),
                           ("prompt_eval_count", "10")):
            self.transport.return_value = self.envelope(**{key: value})
            self.assertEqual(self.run_model().error_code, "provider_failure")
        self.transport.return_value = self.envelope(model=None, eval_count=20)
        raw = self.run_model().raw_response
        self.assertIsNone(raw.model_version)
        self.assertIsNone(raw.token_usage)

    def test_unicode_and_empty_model_text_remain_safe(self):
        for value, expected in (("", "empty_response"), ("\ud800", "invalid_response")):
            self.transport.side_effect = None
            self.transport.return_value = self.envelope(value)
            self.assertEqual(self.run_model().error_code, expected)
        self.transport.return_value = self.envelope(model="\ud800")
        self.assertEqual(self.run_model().error_code, "invalid_response")

    def test_storage_review_and_lineage_keep_original_capture(self):
        with Store(Path(":memory:"), self.tenant) as store:
            with patch("returns_manager.vision.image_availability", return_value="available"):
                attempt = inspect_capture(self.row, self.source, store, self.images, self.provider)
            workflow = ReviewWorkflow(store)
            review = workflow.route(self.row["record_id"], self.row["unit_id"], attempt_id=attempt)
            item = workflow.get(review, self.row["record_id"], self.row["unit_id"])
            self.assertEqual(item["capture"]["source"], asdict(self.source))
            self.assertEqual(item["raw_response"]["text"], json.dumps(self.payload))
            self.assertEqual(item["observations"]["scope"], asdict(self.scope))
            self.assertEqual(item["business_status"], "pending_review")
            self.assertIsNone(item["automated_assessment"]["condition"]["grade"])
            self.assertEqual(item["automated_assessment"]["completeness"]["missing_components"], [])
            self.assertTrue(all(item["automated_assessment"][d]["verdict"] == "UNCERTAIN"
                                for d in ("identity", "completeness", "condition")))
            # Read the same database snapshot through the other actual tenant's public APIs.
            with Store(Path(":memory:"), TenantContext("org_demo_bravo")) as bravo:
                store._db.backup(bravo._db)
                self.assertEqual(bravo.vision_attempts(self.row["record_id"]), [])
                self.assertEqual(ReviewWorkflow(bravo).queue(), [])

    def test_failure_attempts_persist_and_route_uncertainty(self):
        with Store(Path(":memory:"), self.tenant) as store:
            for error, code in ((TimeoutError(), "provider_timeout"), (ProviderUnavailable(), "provider_unavailable")):
                self.transport.side_effect = error
                with patch("returns_manager.vision.image_availability", return_value="available"):
                    attempt = inspect_capture(self.row, self.source, store, self.images, self.provider)
                entry = store.vision_attempts(self.row["record_id"])[-1]
                self.assertEqual(entry["run"]["error_code"], code)
                self.assertIsNone(entry["run"]["raw_response"])
                wf = ReviewWorkflow(store)
                rid = wf.route(self.row["record_id"], self.row["unit_id"], attempt_id=attempt)
                item = wf.get(rid, self.row["record_id"], self.row["unit_id"])
                self.assertIn(code, [reason["code"] for reason in item["uncertainty"]])
                self.assertEqual(item["business_status"], "pending_review")

    def test_direct_provider_rejects_misbound_or_changed_bytes(self):
        with patch("returns_manager.vision.image_availability", return_value="available"):
            request = prepare_request(self.capture, self.images, "real")
        with self.assertRaises(ValidationError):
            self.provider.observe(replace(request, image_contents=(b"TEST changed", b"TEST changed")))
        with self.assertRaises(TenantMismatch):
            self.provider.observe(replace(request, scope=replace(self.scope, unit_id="TEST-other")))
        self.transport.assert_not_called()

    def test_http_transport_bounds_bytes_and_passes_timeout(self):
        response = Mock(status=200)
        response.read.return_value = b'{"TEST":"envelope"}'
        opener = Mock()
        opener.open.return_value.__enter__ = Mock(return_value=response)
        opener.open.return_value.__exit__ = Mock(return_value=False)
        with patch("returns_manager.ollama.build_opener", return_value=opener) as factory:
            self.assertEqual(post_json("http://127.0.0.1:11434/api/chat", {"TEST": 1}, 241), response.read.return_value)
        self.assertEqual(factory.call_args.args[0].proxies, {})
        self.assertIsInstance(factory.call_args.args[1], _NoRedirect)
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 241)
        self.assertEqual(opener.open.call_args.args[0].method, "POST")
        response.read.assert_called_once_with(MAX_RESPONSE_BYTES + 1)

    def test_http_connection_errors_and_redirects_are_not_followed(self):
        for error, expected in ((URLError("TEST offline"), ProviderUnavailable),
                                (URLError(TimeoutError()), TimeoutError), (TimeoutError(), TimeoutError),
                                (HTTPError("TEST", 404, "TEST missing model", {}, io.BytesIO()), ProviderUnavailable)):
            opener = Mock()
            opener.open.side_effect = error
            with patch("returns_manager.ollama.build_opener", return_value=opener), self.assertRaises(expected):
                post_json("http://127.0.0.1:11434/api/chat", {}, 240)
        with self.assertRaises(ProviderUnavailable):
            _NoRedirect().redirect_request(None, None, 302, "TEST", {}, "https://external.invalid")


if __name__ == "__main__":
    unittest.main()
