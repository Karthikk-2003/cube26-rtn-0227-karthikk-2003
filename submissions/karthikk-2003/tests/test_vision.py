"""Synthetic JSON/metadata fixtures only. No genuine photos or model outputs.

Fixture IDs and assertions below exist solely to exercise plumbing and validation.
They are not observations of the repository's products or evaluation evidence.
"""

from contextlib import closing
from dataclasses import asdict, replace
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

PARTICIPANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PARTICIPANT / "agent"))

from returns_manager.domain import TenantContext, TenantMismatch, ValidationError
from returns_manager.observations import EvidenceMismatch, ProviderResponse, parse_response, validate_batch, validate_response
from returns_manager.rules import assess
from returns_manager.service import ingest, inspect_capture
from returns_manager.storage import Store
from returns_manager.validation import parse_record, read_csv
from returns_manager.vision import (
    FixtureProvider, ImageInput, ObservationScope, ProviderUnavailable,
    image_availability, observe, prepare_request, validate_run,
)


class VisionTests(unittest.TestCase):
    def setUp(self):
        records = read_csv(PARTICIPANT.parents[1] / "data" / "returns_sample.csv")
        self.row, self.source = next((r, s) for r, s in records if r["org_id"] == "org_demo_alpha")
        self.context = TenantContext(self.row["org_id"])
        self.capture = parse_record(self.row, self.context, self.source)
        self.scope = ObservationScope.from_capture(self.capture)
        self.images = tuple(ImageInput(self.scope, f"fixture-image-{n}", f"fixture-evidence-{n}",
                                      ref.reference, "returned_product", "fixture")
                            for n, ref in enumerate(self.capture.images[:2], 1))
        self.descriptors = prepare_request(self.capture, self.images, "fixture").images
        self.payload = {"scope": asdict(self.scope), "identity": [], "components": [], "condition": [],
                        "limitations": ["Synthetic fixture only; no image analyzed"]}

    def identity(self, **changes):
        return {"field": "model", "state": "observed", "values": ["TEST-VARIANT-X"],
                "evidence_refs": ["fixture-evidence-1"], "limitations": [], **changes}

    def component(self, **changes):
        return {"component": "usb cable", "presence": "present", "visibility": "visible", "quantity": 1,
                "quantity_reliable": True, "absence_basis": None, "evidence_refs": ["fixture-evidence-1"],
                "limitations": [], **changes}

    def condition(self, **changes):
        return {"feature": "scratches", "state": "observed", "description": "Synthetic scratch assertion",
                "evidence_refs": ["fixture-evidence-1"], "limitations": [], **changes}

    def parse(self, payload=None):
        return parse_response(self.capture, self.descriptors,
                              ProviderResponse(json.dumps(self.payload if payload is None else payload), "fixture-json", "fixture"))

    def run_provider(self, payload=None):
        return observe(self.capture, self.images, FixtureProvider(json.dumps(self.payload if payload is None else payload)))

    def database(self):
        root = PARTICIPANT / ".test-tmp"
        root.mkdir(exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=root)
        self.addCleanup(temp.cleanup)
        return Path(temp.name) / "vision.sqlite3"

    def test_valid_fixture_response_keeps_raw_separate(self):
        self.payload["identity"] = [self.identity()]
        run = self.run_provider()
        self.assertEqual(run.status, "validated")
        self.assertIsInstance(run.raw_response.text, str)
        self.assertEqual(run.observations.identity[0].values, ("TEST-VARIANT-X",))
        self.assertEqual(run.provider_mode, "fixture")
        self.assertIsNone(run.raw_response.model_version)
        self.assertIsNone(run.raw_response.request_id)
        self.assertIsNone(run.raw_response.latency_ms)
        self.assertIsNone(run.raw_response.token_usage)

    def test_malformed_json_is_unavailable(self):
        for text in ("{", '```json\n{}\n```', '[]', '{"scope":1,"scope":2}', '{"value":NaN}'):
            with self.subTest(text=text):
                run = observe(self.capture, self.images, FixtureProvider(text))
                self.assertEqual(run.error_code, "invalid_response")
                self.assertIsNone(run.observations)
                self.assertIsNone(run.raw_response)

    def test_empty_response_is_explicit(self):
        for text in ("", "   "):
            run = observe(self.capture, self.images, FixtureProvider(text))
            self.assertEqual(run.error_code, "empty_response")

    def test_invalid_unicode_identity_persists_only_safe_failure(self):
        with Store(self.database(), self.context) as store:
            for value in ("\ud800", "\udfff"):
                for escaped in (True, False):
                    with self.subTest(scalar=ascii(value), escaped=escaped):
                        self.payload["identity"] = [self.identity(values=[value])]
                        raw_text = json.dumps(self.payload, ensure_ascii=escaped)
                        raw = ProviderResponse(raw_text, "fixture-json", "fixture")
                        with self.assertRaises(ValidationError):
                            parse_response(self.capture, self.descriptors, raw)
                        attempt = inspect_capture(self.row, self.source, store, self.images, FixtureProvider(raw_text))
                        entry = store.vision_attempts(self.capture.record_id)[-1]
                        self.assertEqual(entry["attempt_id"], attempt)
                        self.assertEqual(entry["run"]["status"], "unavailable")
                        self.assertEqual(entry["run"]["error_code"], "invalid_response")
                        self.assertIsNone(entry["run"]["raw_response"])
                        self.assertIsNone(entry["run"]["observations"])
                        self.assertEqual(entry["assessment"]["identity"]["verdict"], "UNCERTAIN")
                        self.assertEqual(entry["assessment"]["review"]["status"], "pending_review")
                        self.assertEqual(entry["assessment"]["disposition"]["decision"], "pending_review")
                        self.assertIsNone(entry["assessment"]["condition"]["grade"])

    def test_invalid_unicode_provider_metadata_is_rejected(self):
        for field in ("provider_name", "model_version", "request_id"):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                validate_response(replace(ProviderResponse("{}", "TEST-adapter", "real"), **{field: "\ud800"}))

    def test_valid_unicode_round_trips_without_sanitizing(self):
        value = "TEST-caf\u00e9-\U0001f50d"
        self.payload["identity"] = [self.identity(values=[value])]
        with Store(self.database(), self.context) as store:
            for escaped in (True, False):
                with self.subTest(escaped=escaped):
                    raw_text = json.dumps(self.payload, ensure_ascii=escaped)
                    inspect_capture(self.row, self.source, store, self.images, FixtureProvider(raw_text))
                    run = store.vision_attempts(self.capture.record_id)[-1]["run"]
                    self.assertEqual(run["status"], "validated")
                    self.assertEqual(run["raw_response"]["text"], raw_text)
                    self.assertEqual(run["observations"]["identity"][0]["values"], [value])

    def test_oversized_latency_persists_safe_unavailable_state(self):
        oversized = 10**1000
        # Validate the numeric guard independently of the fixture telemetry ban.
        with self.assertRaises(ValidationError):
            validate_response(ProviderResponse("{}", "TEST-adapter", "real", latency_ms=oversized))
        raw = ProviderResponse(json.dumps(self.payload), "fixture-json", "fixture", latency_ms=oversized)
        with Store(self.database(), self.context) as store:
            with patch.object(FixtureProvider, "observe", return_value=raw):
                attempt = inspect_capture(self.row, self.source, store, self.images, FixtureProvider("{}"))
            entry = store.vision_attempts(self.capture.record_id)[0]
            self.assertEqual(entry["attempt_id"], attempt)
            self.assertEqual(entry["run"]["status"], "unavailable")
            self.assertEqual(entry["run"]["error_code"], "invalid_response")
            self.assertIsNone(entry["run"]["raw_response"])
            self.assertIsNone(entry["run"]["observations"])
            self.assertEqual(entry["assessment"]["review"]["status"], "pending_review")
            self.assertEqual(entry["assessment"]["disposition"]["decision"], "pending_review")
            self.assertIsNone(entry["assessment"]["identity"]["confidence"])

    def test_unconfigured_provider_is_unavailable(self):
        run = observe(self.capture, (), None)
        self.assertEqual(run.error_code, "provider_unavailable")
        self.assertEqual(run.provider_mode, "unconfigured")
        self.assertIsNone(run.observations)

    def test_provider_exception_is_unavailable_without_sensitive_text(self):
        with patch.object(FixtureProvider, "observe", side_effect=RuntimeError("TEST-sensitive-message")):
            run = self.run_provider()
        self.assertEqual(run.error_code, "provider_failure")
        self.assertNotIn("TEST-sensitive-message", str(run))

    def test_provider_unavailable_exception(self):
        with patch.object(FixtureProvider, "observe", side_effect=ProviderUnavailable()):
            self.assertEqual(self.run_provider().error_code, "provider_unavailable")

    def test_provider_timeout_is_explicit(self):
        with patch.object(FixtureProvider, "observe", side_effect=TimeoutError()):
            self.assertEqual(self.run_provider().error_code, "provider_timeout")

    def test_provider_wrong_response_type(self):
        with patch.object(FixtureProvider, "observe", return_value={"identity": "PASS"}):
            self.assertEqual(self.run_provider().error_code, "invalid_response")

    def test_provider_metadata_cannot_impersonate_another_adapter(self):
        with patch.object(FixtureProvider, "observe", return_value=ProviderResponse("{}", "TEST-other", "real")):
            self.assertEqual(self.run_provider().error_code, "provider_metadata_mismatch")

    def test_fixture_provider_cannot_claim_model_telemetry(self):
        for field, value in (("latency_ms", 123), ("model_version", "TEST-model"),
                             ("request_id", "TEST-request"), ("token_usage", 4)):
            with self.subTest(field=field):
                raw = replace(ProviderResponse(json.dumps(self.payload), "fixture-json", "fixture"), **{field: value})
                with self.assertRaises(ValidationError):
                    parse_response(self.capture, self.descriptors, raw)

    def test_visible_identity_fields_and_ocr_are_preserved_only_as_supplied(self):
        from returns_manager.observations import IDENTITY_FIELDS
        self.payload["identity"] = [self.identity(field=name, values=["TEST-provided-text"]) for name in sorted(IDENTITY_FIELDS)]
        batch = self.parse()
        self.assertEqual({i.field for i in batch.identity}, IDENTITY_FIELDS)
        self.assertTrue(all(i.values == ("TEST-provided-text",) for i in batch.identity))
        self.assertFalse(hasattr(batch, "condition_grade"))

    def test_unknown_identity_can_have_no_evidence(self):
        self.payload["identity"] = [self.identity(state="unknown", values=[], evidence_refs=[], limitations=["No identity view supplied"])]
        result = self.parse().identity[0]
        self.assertEqual(result.state, "unknown")
        self.assertEqual(result.values, ())

    def test_not_visible_identity_has_no_invented_values(self):
        self.payload["identity"] = [self.identity(state="not_visible", values=[], limitations=["Label occluded"])]
        self.assertEqual(self.parse().identity[0].values, ())

    def test_ambiguous_identity_preserves_alternatives(self):
        self.payload["identity"] = [self.identity(state="conflicting", values=["TEST-X", "TEST-Y"],
                                                  evidence_refs=["fixture-evidence-1", "fixture-evidence-2"],
                                                  limitations=["Similar variants; unresolved"])]
        batch = self.parse()
        self.assertEqual(batch.identity[0].values, ("TEST-X", "TEST-Y"))
        self.assertIn("identity:model", batch.conflicts)

    def test_conflicting_identity_across_images_not_overwritten(self):
        self.payload["identity"] = [self.identity(), self.identity(values=["TEST-Y"], evidence_refs=["fixture-evidence-2"])]
        batch = self.parse()
        self.assertEqual(len(batch.identity), 2)
        self.assertIn("identity:model", batch.conflicts)

    def test_conflicting_positive_and_negative_identity_preserved(self):
        self.payload["identity"] = [self.identity(), self.identity(state="not_observed", values=[],
                evidence_refs=["fixture-evidence-2"], limitations=["Marking not seen in second view"])]
        self.assertIn("identity:model", self.parse().conflicts)

    def test_unsupported_identity_states_and_structures_rejected(self):
        for changes in ({"state": "matched"}, {"field": "business_decision"}, {"values": "TEST-X"},
                        {"state": "unknown", "values": ["TEST-guessed"], "limitations": ["Unknown"]}):
            self.payload["identity"] = [self.identity(**changes)]
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.parse()

    def test_component_present_reliable_quantity(self):
        self.payload["components"] = [self.component()]
        item = self.parse().components[0]
        self.assertEqual((item.presence, item.quantity), ("present", 1))

    def test_component_absence_requires_coverage_basis(self):
        self.payload["components"] = [self.component(presence="absent", quantity=0,
                absence_basis="full_expected_area_visible", limitations=["TEST complete inspection area visible; no cable found"])]
        batch = self.parse()
        self.assertEqual(batch.components[0].presence, "absent")
        # A provider absence assertion is NOT automatically a business missing-parts verdict.
        self.assertEqual(assess(self.capture, batch).completeness.missing_components, ())

    def test_unjustified_component_absence_rejected(self):
        for changes in ({"absence_basis": None}, {"visibility": "occluded"}, {"evidence_refs": []}, {"quantity": None, "quantity_reliable": False}):
            item = self.component(presence="absent", quantity=0, absence_basis="full_expected_area_visible", limitations=["TEST coverage"])
            self.payload["components"] = [{**item, **changes}]
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.parse()

    def test_unknown_and_occluded_components_are_not_absent(self):
        for visibility in ("unknown", "occluded", "partial", "not_visible"):
            self.payload["components"] = [self.component(presence="unknown", visibility=visibility, quantity=None,
                                                         quantity_reliable=False, limitations=["Insufficient angle"])]
            item = self.parse().components[0]
            self.assertEqual(item.presence, "unknown")
            self.assertIsNone(item.quantity)

    def test_invalid_quantity_types_and_reliability(self):
        for changes in ({"quantity": -1}, {"quantity": True}, {"quantity": 1.5}, {"quantity": "1"},
                        {"quantity_reliable": False}, {"quantity_reliable": "yes"}, {"visibility": "partial"}):
            self.payload["components"] = [self.component(**changes)]
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.parse()

    def test_multiple_components_and_image_citations(self):
        self.payload["components"] = [self.component(), self.component(component="manual", evidence_refs=["fixture-evidence-1", "fixture-evidence-2"])]
        batch = self.parse()
        self.assertEqual(len(batch.components), 2)
        self.assertEqual(batch.components[1].evidence_refs, ("fixture-evidence-1", "fixture-evidence-2"))
        self.assertEqual(len(batch.images), 2)

    def test_conflicting_components_preserved(self):
        self.payload["components"] = [self.component(), self.component(quantity=2, evidence_refs=["fixture-evidence-2"])]
        batch = self.parse()
        self.assertEqual([c.quantity for c in batch.components], [1, 2])
        self.assertIn("component:usb cable", batch.conflicts)

    def test_visible_scratches_and_damage_remain_observations(self):
        self.payload["condition"] = [self.condition(), self.condition(feature="cracks", description="Synthetic crack assertion")]
        batch = self.parse()
        self.assertEqual(len(batch.condition), 2)
        result = assess(self.capture, batch)
        self.assertIsNone(result.condition.grade)
        self.assertEqual(result.condition.verdict.value, "UNCERTAIN")
        self.assertEqual(result.disposition.decision.value, "pending_review")

    def test_no_visible_damage_is_scoped_negative_not_condition_grade(self):
        self.payload["condition"] = [self.condition(state="not_observed", description="No scratches seen on exposed face",
                                                    limitations=["Only the exposed face was visible"])]
        batch = self.parse()
        self.assertEqual(batch.condition[0].state, "not_observed")
        self.assertIsNone(assess(self.capture, batch).condition.grade)

    def test_visibility_limitations_preserved(self):
        self.payload["limitations"] = ["blur", "glare", "occlusion", "poor lighting", "insufficient angle"]
        self.payload["condition"] = [self.condition(state="not_visible", description=None, limitations=["glare"])]
        batch = self.parse()
        self.assertEqual(batch.limitations, tuple(self.payload["limitations"]))
        self.assertIsNone(batch.condition[0].description)

    def test_ambiguous_condition_has_no_finding(self):
        self.payload["condition"] = [self.condition(state="unknown", description=None, evidence_refs=[], limitations=["Cannot distinguish scratch from reflection"])]
        self.assertIsNone(self.parse().condition[0].description)

    def test_conflicting_condition_preserved(self):
        self.payload["condition"] = [self.condition(), self.condition(state="not_observed", description="Not visible in second view",
                                    evidence_refs=["fixture-evidence-2"], limitations=["Second angle only"])]
        self.assertIn("condition:scratches", self.parse().conflicts)

    def test_invented_grade_or_disposition_field_rejected(self):
        for field in ("condition_grade", "amazon_condition", "outcome", "disposition", "confidence", "bounding_box"):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.parse({**self.payload, field: "TEST-unsupported"})
        self.payload["condition"] = [self.condition(feature="Used - Good")]
        with self.assertRaises(ValidationError):
            self.parse()

    def test_substantive_findings_require_supplied_evidence(self):
        for section, item in (("identity", self.identity(evidence_refs=[])),
                              ("components", self.component(evidence_refs=[])), ("condition", self.condition(evidence_refs=[]))):
            payload = {**self.payload, section: [item]}
            with self.subTest(section=section), self.assertRaises(EvidenceMismatch):
                self.parse(payload)

    def test_unknown_evidence_reference_rejected(self):
        self.payload["identity"] = [self.identity(evidence_refs=["TEST-NOT-IN-INPUT"])]
        with self.assertRaises(EvidenceMismatch):
            self.parse()

    def test_missing_and_duplicate_image_ids_rejected(self):
        for inputs in ((replace(self.images[0], image_id=""),), (self.images[0], self.images[0])):
            with self.subTest(inputs=inputs), self.assertRaises(ValidationError):
                prepare_request(self.capture, inputs, "fixture")

    def test_unknown_input_reference_rejected_before_provider(self):
        with patch.object(FixtureProvider, "observe") as provider_call:
            with self.assertRaises(EvidenceMismatch):
                observe(self.capture, (replace(self.images[0], reference="TEST-not-in-capture"),), FixtureProvider("{}"))
            provider_call.assert_not_called()

    def test_missing_image_stops_provider(self):
        missing = replace(self.images[0], kind="genuine", content=None)
        with patch.object(FixtureProvider, "observe") as provider_call:
            run = observe(self.capture, (missing,), FixtureProvider("{}"))
            self.assertEqual(run.error_code, "missing_image")
            provider_call.assert_not_called()

    def test_corrupt_image_stops_provider_without_inventing_damage(self):
        corrupt = replace(self.images[0], kind="genuine", content=b"TEST deliberately non-image bytes")
        with patch.object(FixtureProvider, "observe") as provider_call:
            run = observe(self.capture, (corrupt,), FixtureProvider("{}"))
            self.assertEqual(run.error_code, "unreadable_image")
            self.assertIsNone(run.observations)
            provider_call.assert_not_called()

    def test_truncated_image_never_becomes_available(self):
        self.assertIn(image_availability(b"\x89PNG\r\n\x1a\n"), {"unreadable", "decoder_unavailable"})

    def test_absent_optional_decoder_is_explicit(self):
        with patch.dict(sys.modules, {"PIL": None}):
            self.assertEqual(image_availability(b"\x89PNG\r\n\x1a\n"), "decoder_unavailable")

    def test_no_images_stops_provider(self):
        with patch.object(FixtureProvider, "observe") as provider_call:
            self.assertEqual(observe(self.capture, (), FixtureProvider("{}")).error_code, "missing_image")
            provider_call.assert_not_called()

    def test_fixture_input_cannot_be_passed_to_real_adapter(self):
        with self.assertRaises(ValidationError):
            prepare_request(self.capture, self.images, "real")

    def test_raw_response_scope_cannot_cross_organization_unit_or_record(self):
        for scope in (replace(self.scope, tenant=TenantContext("org_demo_bravo")),
                      replace(self.scope, unit_id="TEST-other-unit"), replace(self.scope, record_id="TEST-other-record")):
            with self.subTest(scope=scope):
                payload = {**self.payload, "scope": asdict(scope)}
                run = self.run_provider(payload)
                self.assertEqual(run.error_code, "response_scope_mismatch")
                self.assertIsNone(run.raw_response)
                self.assertIsNone(run.observations)

    def test_input_scope_cannot_cross_organization_unit_or_record(self):
        for scope in (replace(self.scope, tenant=TenantContext("org_demo_bravo")),
                      replace(self.scope, unit_id="TEST-other-unit"), replace(self.scope, record_id="TEST-other-record")):
            with self.subTest(scope=scope), patch.object(FixtureProvider, "observe") as provider_call:
                with self.assertRaises(TenantMismatch):
                    observe(self.capture, (replace(self.images[0], scope=scope),), FixtureProvider("{}"))
                provider_call.assert_not_called()

    def test_validated_observations_flow_to_deterministic_rules(self):
        self.payload["identity"] = [self.identity()]
        batch = self.parse()
        first = assess(self.capture, batch)
        self.assertEqual(first, assess(self.capture, batch))
        self.assertEqual(first.observation, batch)
        self.assertEqual(first.identity.verdict.value, "UNCERTAIN")
        self.assertEqual(first.disposition.decision.value, "pending_review")

    def test_tampered_normalized_observations_cannot_bypass_rules(self):
        self.payload["identity"] = [self.identity()]
        batch = self.parse()
        forged = replace(batch, identity=(replace(batch.identity[0], evidence_refs=("TEST-foreign",)),))
        with self.assertRaises(ValidationError):
            assess(self.capture, forged)

    def test_cross_unit_batch_cannot_bypass_rules(self):
        batch = replace(self.parse(), scope=replace(self.scope, unit_id="TEST-other-unit"))
        with self.assertRaises(TenantMismatch):
            assess(self.capture, batch)

    def test_run_raw_and_normalized_must_agree(self):
        run = self.run_provider()
        forged = replace(run, observations=replace(run.observations, limitations=("TEST-tampered",)))
        with self.assertRaises(ValidationError):
            validate_run(self.capture, forged)

    def test_vision_result_cannot_bypass_raw_response_storage(self):
        result = assess(self.capture, self.parse())
        with Store(self.database(), self.context) as store:
            with self.assertRaises(ValidationError):
                store.save_assessment(self.capture, result)

    def test_unconfigured_provider_persists_review(self):
        with Store(self.database(), self.context) as store:
            inspect_capture(self.row, self.source, store, (), None)
            entry = store.vision_attempts(self.capture.record_id)[0]
            self.assertEqual(entry["run"]["provider_mode"], "unconfigured")
            self.assertEqual(entry["assessment"]["review"]["status"], "pending_review")

    def test_failed_run_cannot_carry_valid_observations(self):
        run = replace(self.run_provider(), status="unavailable", error_code="provider_timeout")
        with self.assertRaises(ValidationError):
            validate_run(self.capture, run)

    def test_integration_persists_raw_observations_and_preserves_phase1(self):
        database = self.database()
        with Store(database, self.context) as store:
            original = ingest(self.row, self.source, store)
            attempt = inspect_capture(self.row, self.source, store, self.images, FixtureProvider(json.dumps(self.payload)))
            entries = store.vision_attempts(self.capture.record_id)
            self.assertEqual(entries[0]["attempt_id"], attempt)
            self.assertEqual(entries[0]["run"]["status"], "validated")
            self.assertEqual(entries[0]["run"]["raw_response"]["text"], json.dumps(self.payload))
            self.assertEqual(entries[0]["assessment"]["review"]["status"], "pending_review")
            self.assertEqual(store.get(self.capture.record_id), original)
        with Store(database, self.context) as store:
            self.assertEqual(len(store.vision_attempts(self.capture.record_id)), 1)

    def test_provider_failure_persists_explicit_review_without_false_conclusions(self):
        with Store(self.database(), self.context) as store:
            with patch.object(FixtureProvider, "observe", side_effect=TimeoutError()):
                inspect_capture(self.row, self.source, store, self.images, FixtureProvider("{}"))
            entry = store.vision_attempts(self.capture.record_id)[0]
            self.assertEqual(entry["run"]["error_code"], "provider_timeout")
            self.assertEqual(entry["assessment"]["identity"]["verdict"], "UNCERTAIN")
            self.assertEqual(entry["assessment"]["completeness"]["missing_components"], [])
            self.assertIsNone(entry["assessment"]["condition"]["grade"])
            self.assertEqual(entry["assessment"]["disposition"]["decision"], "pending_review")

    def test_repeated_explicit_attempts_preserve_history(self):
        with Store(self.database(), self.context) as store:
            for _ in range(2):
                inspect_capture(self.row, self.source, store, self.images, FixtureProvider(json.dumps(self.payload)))
            entries = store.vision_attempts(self.capture.record_id)
            self.assertEqual(len(entries), 2)
            self.assertNotEqual(entries[0]["attempt_id"], entries[1]["attempt_id"])

    def test_other_organization_cannot_read_or_write_observations(self):
        database = self.database()
        with Store(database, self.context) as store:
            inspect_capture(self.row, self.source, store, self.images, FixtureProvider(json.dumps(self.payload)))
        run = self.run_provider()
        with Store(database, TenantContext("org_demo_bravo")) as store:
            self.assertEqual(store.vision_attempts(self.capture.record_id), [])
            with self.assertRaises(TenantMismatch):
                store.save_vision_attempt(self.capture, run, assess(self.capture, run.observations))

    def test_other_record_cannot_read_observations(self):
        with Store(self.database(), self.context) as store:
            inspect_capture(self.row, self.source, store, self.images, FixtureProvider(json.dumps(self.payload)))
            self.assertEqual(store.vision_attempts("TEST-other-record"), [])

    def test_scoped_failure_does_not_persist_foreign_response_text(self):
        foreign = {**self.payload, "scope": asdict(replace(self.scope, unit_id="TEST-foreign-unit"))}
        with Store(self.database(), self.context) as store:
            inspect_capture(self.row, self.source, store, self.images, FixtureProvider(json.dumps(foreign)))
            entry = store.vision_attempts(self.capture.record_id)[0]
            self.assertEqual(entry["run"]["error_code"], "response_scope_mismatch")
            self.assertNotIn("TEST-foreign-unit", json.dumps(entry))

    def test_missing_fields_and_invalid_collection_types(self):
        payload = dict(self.payload)
        del payload["identity"]
        with self.assertRaises(ValidationError):
            self.parse(payload)
        for value in (None, {}, "observations", 7):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.parse({**self.payload, "components": value})

    def test_phase1_database_accepts_additive_vision_table(self):
        database = self.database()
        with closing(sqlite3.connect(database)) as db:
            db.execute("CREATE TABLE captures (organization_id TEXT, client_scope TEXT, record_id TEXT, unit_id TEXT, "
                       "payload TEXT, assessment TEXT, processing_error TEXT, PRIMARY KEY (organization_id, client_scope, record_id))")
            db.commit()
        with Store(database, self.context) as store:
            ingest(self.row, self.source, store)
            inspect_capture(self.row, self.source, store, self.images, FixtureProvider(json.dumps(self.payload)))
            self.assertEqual(len(store.vision_attempts(self.capture.record_id)), 1)


if __name__ == "__main__":
    unittest.main()
