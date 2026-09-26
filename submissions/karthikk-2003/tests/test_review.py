"""Synthetic engineering fixtures only; no images, model results or evaluation evidence."""

from dataclasses import asdict, replace
import json
import sqlite3
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

PARTICIPANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PARTICIPANT / "agent"))

from returns_manager.domain import TenantContext, TenantMismatch, ValidationError
from returns_manager.review import HumanDecision, ReviewerContext, route_reasons
from returns_manager.review_storage import ReviewWorkflow
from returns_manager.service import ingest, inspect_capture
from returns_manager.storage import Store, ConflictError
from returns_manager.validation import parse_record, read_csv
from returns_manager.vision import FixtureProvider, ImageInput, ObservationScope


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.context = TenantContext("org_demo_alpha")
        records = read_csv(PARTICIPANT.parents[1] / "data" / "returns_sample.csv")
        self.row, self.source = next((r, s) for r, s in records if r["org_id"] == self.context.organization_id)
        self.capture = parse_record(self.row, self.context, self.source)
        self.record, self.unit = self.capture.record_id, self.capture.unit.unit_id
        self.store = Store(":memory:", self.context)
        self.addCleanup(self.store.close)
        self.workflow = ReviewWorkflow(self.store)
        ingest(self.row, self.source, self.store)
        self.scope = ObservationScope.from_capture(self.capture)
        self.images = tuple(ImageInput(self.scope, f"TEST-image-{n}", f"TEST-evidence-{n}",
                                       image.reference, "returned_product", "fixture")
                            for n, image in enumerate(self.capture.images))
        self.payload = {"scope": asdict(self.scope), "identity": [], "components": [], "condition": [],
                        "limitations": ["TEST fixture only; no actual inspection"]}
        self.reviewer = ReviewerContext(self.context, "TEST-reviewer")

    def vision_case(self, provider=None, images=None):
        if provider is None:
            provider = FixtureProvider(json.dumps(self.payload))
        attempt = inspect_capture(self.row, self.source, self.store,
                                  self.images if images is None else images, provider)
        review = self.workflow.route(self.record, self.unit, attempt_id=attempt)
        return review, attempt

    def item(self, review):
        return self.workflow.get(review, self.record, self.unit)

    def codes(self, review):
        return {r["code"] for r in self.item(review)["uncertainty"]}

    def change(self, review, **changes):
        args = dict(reviewer=self.reviewer, command_id="TEST-start", expected_revision=1,
                    status="in_review", reason="TEST human review")
        args.update(changes)
        return self.workflow.transition(review, self.record, self.unit, **args)

    def test_capture_missing_evidence_routes_to_review(self):
        review = self.workflow.route(self.record, self.unit)
        item = self.item(review)
        self.assertEqual(item["status"], "pending_review")
        self.assertIn("missing_evidence", self.codes(review))
        self.assertTrue(all(e["availability"] == "missing" for e in item["evidence"]))
        self.assertIsNone(item["raw_response"])
        self.assertEqual(item["unresolved_decisions"], ["identity", "completeness", "condition", "disposition"])

    def test_missing_client_and_policy_remain_explicit(self):
        review, _ = self.vision_case()
        self.assertIn("missing_client_context", self.codes(review))
        self.assertIsNone(self.item(review)["client_id"])
        policy = {r["dimension"] for r in self.item(review)["uncertainty"] if r["code"] == "unresolved_policy"}
        self.assertEqual(policy, {"condition", "disposition"})

    def test_raw_and_normalized_lineage_matches_persisted_attempt(self):
        self.payload["identity"] = [{"field": "model", "state": "observed", "values": ["TEST-model"],
                                     "evidence_refs": ["TEST-evidence-0"], "limitations": []}]
        review, attempt = self.vision_case()
        item = self.item(review)
        source = self.store.vision_attempts(self.record)[0]
        self.assertEqual(item["source_key"], f"vision:{attempt}")
        self.assertEqual(item["raw_response"], source["run"]["raw_response"])
        self.assertEqual(item["observations"], source["run"]["observations"])
        self.assertEqual(item["automated_assessment"], source["assessment"])
        self.assertEqual(item["capture"], self.store.get(self.record)["capture"])
        self.assertEqual(item["observations"]["identity"][0]["evidence_refs"], [item["evidence"][0]["evidence_id"]])
        self.assertEqual(item["observations"]["scope"], asdict(self.scope))

    def test_partial_image_submission_exposes_missing_reference(self):
        review, _ = self.vision_case(images=self.images[:1])
        self.assertIn("missing_evidence", self.codes(review))
        self.assertEqual(len(self.item(review)["evidence"]), len(self.capture.images))
        self.assertEqual(self.item(review)["evidence"][1]["availability"], "missing")

    def test_missing_and_unreadable_images_route_safely(self):
        for content, code in ((None, "missing_evidence"), (b"TEST-not-image", "unreadable_image")):
            with self.subTest(code=code):
                review, _ = self.vision_case(images=(replace(self.images[0], kind="genuine", content=content),))
                self.assertIn(code, self.codes(review))
                self.assertIsNone(self.item(review)["observations"])

    def test_provider_failures_route_without_losing_capture(self):
        for error, code in ((TimeoutError(), "provider_timeout"), (RuntimeError(), "provider_failure")):
            with self.subTest(code=code), patch.object(FixtureProvider, "observe", side_effect=error):
                review, _ = self.vision_case()
                self.assertIn(code, self.codes(review))
                self.assertEqual(self.item(review)["capture"]["record_id"], self.record)
                self.assertIsNone(self.item(review)["raw_response"])

    def test_unconfigured_provider_is_explicit(self):
        attempt = inspect_capture(self.row, self.source, self.store, (), None)
        review = self.workflow.route(self.record, self.unit, attempt_id=attempt)
        self.assertIn("provider_unavailable", self.codes(review))

    def test_invalid_response_routes_without_retaining_foreign_text(self):
        review, _ = self.vision_case(FixtureProvider('{"TEST-foreign":true}'))
        self.assertIn("invalid_response", self.codes(review))
        self.assertNotIn("TEST-foreign", json.dumps(self.item(review)))

    def test_identity_conflicts_are_preserved_in_review(self):
        self.payload["identity"] = [
            {"field": "model", "state": "observed", "values": [value],
             "evidence_refs": [f"TEST-evidence-{n}"], "limitations": []}
            for n, value in enumerate(("TEST-A", "TEST-B"))]
        review, _ = self.vision_case()
        self.assertIn("conflicting_identity", self.codes(review))
        self.assertEqual(len(self.item(review)["observations"]["identity"]), 2)

    def test_component_conflicts_are_preserved_in_review(self):
        self.payload["components"] = [
            {"component": "TEST-cable", "presence": "present", "visibility": "visible", "quantity": n + 1,
             "quantity_reliable": True, "absence_basis": None, "evidence_refs": [f"TEST-evidence-{n}"], "limitations": []}
            for n in range(2)]
        review, _ = self.vision_case()
        self.assertIn("conflicting_component", self.codes(review))
        self.assertEqual(len(self.item(review)["observations"]["components"]), 2)

    def test_condition_conflicts_are_preserved_in_review(self):
        self.payload["condition"] = [
            {"feature": "scratches", "state": state, "description": "TEST assertion",
             "evidence_refs": [f"TEST-evidence-{n}"], "limitations": ["TEST limited view"]}
            for n, state in enumerate(("observed", "not_observed"))]
        review, _ = self.vision_case()
        self.assertIn("conflicting_condition", self.codes(review))
        self.assertEqual(len(self.item(review)["observations"]["condition"]), 2)

    def test_ambiguous_identity_components_condition_stay_uncertain(self):
        self.payload["identity"] = [{"field": "model", "state": "unknown", "values": [],
                                     "evidence_refs": [], "limitations": ["TEST obscured"]}]
        self.payload["components"] = [{"component": "TEST-cable", "presence": "unknown", "visibility": "occluded",
            "quantity": None, "quantity_reliable": False, "absence_basis": None,
            "evidence_refs": [], "limitations": ["TEST obscured"]}]
        self.payload["condition"] = [{"feature": "scratches", "state": "unknown", "description": None,
                                      "evidence_refs": [], "limitations": ["TEST glare"]}]
        review, _ = self.vision_case()
        self.assertTrue({"ambiguous_identity", "ambiguous_component", "insufficient_condition_evidence",
                         "insufficient_image_coverage"}.issubset(self.codes(review)))
        assessment = self.item(review)["automated_assessment"]
        self.assertEqual(assessment["completeness"]["missing_components"], [])
        self.assertIsNone(assessment["condition"]["grade"])

    def test_routing_is_deterministic(self):
        review, _ = self.vision_case()
        source = self.store.vision_attempts(self.record)[0]
        args = (self.item(review)["capture"], source["assessment"], source["run"])
        self.assertEqual(route_reasons(*args), route_reasons(*args))
        self.assertEqual(route_reasons(*args), self.item(review)["uncertainty"])

    def test_route_retries_do_not_duplicate_or_reset_state(self):
        review, attempt = self.vision_case()
        self.change(review)
        for _ in range(3):
            self.assertEqual(self.workflow.route(self.record, self.unit, attempt_id=attempt), review)
        self.assertEqual(len(self.workflow.queue()), 1)
        self.assertEqual(self.item(review)["status"], "in_review")
        self.assertEqual(len(self.workflow.history(review, self.record, self.unit)), 2)

    def test_distinct_attempts_have_distinct_cases(self):
        first, _ = self.vision_case()
        second, _ = self.vision_case()
        self.assertNotEqual(first, second)
        self.assertEqual(len(self.workflow.queue()), 2)

    def test_status_history_records_previous_new_actor_reason_timestamp(self):
        review = self.workflow.route(self.record, self.unit)
        self.change(review)
        self.change(review, command_id="TEST-finish", expected_revision=2, status="reviewed")
        history = self.workflow.history(review, self.record, self.unit)
        self.assertEqual([e["revision"] for e in history], [1, 2, 3])
        for previous, current in zip(history, history[1:]):
            self.assertEqual(previous["new_state"], current["previous_state"])
            self.assertEqual(current["actor_id"], "TEST-reviewer")
            self.assertTrue(current["timestamp"].endswith("+00:00"))
            self.assertEqual(current["reason"], "TEST human review")
        self.assertEqual(self.item(review)["business_status"], "pending_review")
        self.assertEqual(len(self.workflow.queue(status="reviewed")), 1)

    def test_human_override_preserves_automated_source_and_reasons(self):
        review, _ = self.vision_case()
        before = self.item(review)
        source = self.store.vision_attempts(self.record)
        self.change(review)
        self.change(review, command_id="TEST-override", expected_revision=2, status="reviewed",
                    decisions=(HumanDecision("identity", "FAIL", ("TEST-evidence-0",)),))
        after = self.item(review)
        self.assertEqual(after["effective_results"]["identity"], {"value": "FAIL", "source": "human", "revision": 3})
        for field in ("uncertainty", "raw_response", "observations", "automated_assessment"):
            self.assertEqual(after[field], before[field])
        self.assertEqual(self.store.vision_attempts(self.record), source)
        self.assertEqual(after["human_decisions"]["identity"]["reviewer_id"], "TEST-reviewer")
        self.assertEqual(after["automated_assessment"]["identity"]["verdict"], "UNCERTAIN")
        self.assertIn("fixture_only_evidence", self.codes(review))

    def test_reopen_and_revise_human_override_preserves_prior_decision(self):
        review, _ = self.vision_case()
        self.change(review)
        self.change(review, command_id="TEST-first", expected_revision=2, status="reviewed",
                    decisions=(HumanDecision("identity", "FAIL", ("TEST-evidence-0",)),))
        self.change(review, command_id="TEST-reopen", expected_revision=3)
        event = self.change(review, command_id="TEST-second", expected_revision=4,
                            decisions=(HumanDecision("identity", "UNCERTAIN"),))
        self.assertEqual(event["overrides"][0]["previous_result"]["value"], "FAIL")
        self.assertEqual(event["previous_state"]["human_decisions"]["identity"]["verdict"], "FAIL")
        self.assertEqual(self.item(review)["effective_results"]["identity"]["value"], "UNCERTAIN")

    def test_decision_dimensions_stay_separate(self):
        review, _ = self.vision_case()
        self.change(review)
        self.change(review, command_id="TEST-both", expected_revision=2,
                    decisions=(HumanDecision("identity", "PASS", ("TEST-evidence-0",)),
                               HumanDecision("completeness", "FAIL", ("TEST-evidence-1",))))
        item = self.item(review)
        self.assertEqual(item["effective_results"]["identity"]["value"], "PASS")
        self.assertEqual(item["effective_results"]["completeness"]["value"], "FAIL")
        self.assertEqual(item["unresolved_decisions"], ["condition", "disposition"])

    def test_transition_retry_returns_original_event_without_duplicate(self):
        review, _ = self.vision_case()
        first = self.change(review)
        self.change(review, command_id="TEST-finish", expected_revision=2, status="reviewed")
        self.assertEqual(self.change(review), first)
        self.assertEqual(len(self.workflow.history(review, self.record, self.unit)), 3)

    def test_reused_command_with_changed_payload_is_rejected(self):
        review, _ = self.vision_case()
        self.change(review)
        with self.assertRaises(ConflictError):
            self.change(review, reason="TEST changed")
        self.assertEqual(self.item(review)["revision"], 2)

    def test_stale_update_is_rejected(self):
        review, _ = self.vision_case()
        self.change(review)
        with self.assertRaises(ConflictError):
            self.change(review, command_id="TEST-other-worker")

    def test_invalid_transitions_rejected_without_history_entry(self):
        review, _ = self.vision_case()
        for status in ("reviewed", "pending_review", "resolved", "restock"):
            with self.subTest(status=status), self.assertRaises(ValidationError):
                self.change(review, status=status)
        self.assertEqual(len(self.workflow.history(review, self.record, self.unit)), 1)

    def test_missing_review_identity_reason_and_invalid_unicode_rejected(self):
        for identity in ("", " bad", "bad\n", "\ud800", None):
            with self.subTest(identity=repr(identity)), self.assertRaises(ValidationError):
                ReviewerContext(self.context, identity)
        review, _ = self.vision_case()
        for changes in ({"reason": ""}, {"reason": "\ud800"}, {"reviewer": {"reviewer_id": "forged"}},
                        {"command_id": "system:route"}, {"expected_revision": True}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.change(review, **changes)

    def test_forged_evidence_and_observation_input_rejected(self):
        review, _ = self.vision_case()
        self.change(review)
        for decisions in ((HumanDecision("identity", "PASS", ("TEST-forged-evidence",)),),
                          ({"dimension": "identity", "verdict": "PASS", "ocr": "invented"},),
                          (HumanDecision("identity", "UNCERTAIN"), HumanDecision("identity", "UNCERTAIN"))):
            with self.subTest(decisions=decisions), self.assertRaises(ValidationError):
                self.change(review, command_id="TEST-invalid", expected_revision=2, decisions=decisions)
        self.assertEqual(self.item(review)["revision"], 2)

    def test_unavailable_evidence_cannot_support_human_verdict(self):
        review = self.workflow.route(self.record, self.unit)
        self.change(review)
        with self.assertRaises(ValidationError):
            self.change(review, command_id="TEST-invalid", expected_revision=2,
                        decisions=(HumanDecision("identity", "PASS", (self.capture.images[0].reference,)),))
        with self.assertRaises(ValidationError):
            HumanDecision("identity", "PASS")

    def test_condition_and_disposition_policy_cannot_be_bypassed(self):
        for dimension, verdict in (("condition", "Used - Good"), ("disposition", "restock"),
                                   ("disposition", "dispose"), ("identity", "MATCH")):
            with self.subTest(dimension=dimension), self.assertRaises(ValidationError):
                HumanDecision(dimension, verdict, ("TEST-evidence-0",))

    def test_foreign_reviewer_rejected(self):
        review, _ = self.vision_case()
        with self.assertRaises(TenantMismatch):
            self.change(review, reviewer=ReviewerContext(TenantContext("org_demo_bravo"), "TEST-reviewer"))

    def test_cross_unit_and_record_access_rejected_on_all_paths(self):
        review, attempt = self.vision_case()
        for record, unit in ((self.record, "TEST-other-unit"), ("TEST-other-record", self.unit)):
            for action in (
                lambda: self.workflow.get(review, record, unit),
                lambda: self.workflow.history(review, record, unit),
                lambda: self.workflow.route(record, unit, attempt_id=attempt),
                lambda: self.workflow.transition(review, record, unit, reviewer=self.reviewer,
                    command_id="TEST-forged", expected_revision=1, status="in_review", reason="TEST"),
            ):
                with self.subTest(record=record, unit=unit), self.assertRaises(TenantMismatch):
                    action()

    def test_attempt_from_other_record_cannot_be_routed(self):
        _, attempt = self.vision_case()
        other = {**self.row, "record_id": "TEST-other-record"}
        ingest(other, self.source, self.store)
        with self.assertRaises(TenantMismatch):
            self.workflow.route(other["record_id"], self.unit, attempt_id=attempt)

    def test_persisted_history_and_bidirectional_tenant_isolation(self):
        root = PARTICIPANT / ".test-tmp"
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory:
            path = Path(directory) / "reviews.sqlite3"
            contexts = (self.context, TenantContext("org_demo_bravo"))
            ids = []
            attempts = []
            for context in contexts:
                with Store(path, context) as store:
                    row = {**self.row, "org_id": context.organization_id}
                    ingest(row, self.source, store)
                    workflow = ReviewWorkflow(store)
                    review = workflow.route(self.record, self.unit)
                    ids.append(review)
                    attempts.append(inspect_capture(row, self.source, store, (), None))
            for n, context in enumerate(contexts):
                with Store(path, context) as store:
                    workflow = ReviewWorkflow(store)
                    self.assertEqual([i["review_id"] for i in workflow.queue()], [ids[n]])
                    own_history = workflow.history(ids[n], self.record, self.unit)
                    self.assertEqual(len(own_history), 1)
                    with self.assertRaises(TenantMismatch):
                        workflow.route(self.record, self.unit, attempt_id=attempts[1-n])
                    for action in (
                        lambda: workflow.get(ids[1-n], self.record, self.unit),
                        lambda: workflow.history(ids[1-n], self.record, self.unit),
                        lambda: workflow.transition(ids[1-n], self.record, self.unit,
                            reviewer=ReviewerContext(context, "TEST-reviewer"), command_id="TEST-forged",
                            expected_revision=1, status="in_review", reason="TEST"),
                    ):
                        with self.assertRaises(TenantMismatch):
                            action()

    def test_interrupted_assessment_is_reviewable_and_later_retry_does_not_rewrite_context(self):
        row = {**self.row, "record_id": "TEST-interrupted"}
        capture = parse_record(row, self.context, self.source)
        self.store.save_capture(capture)
        self.store.record_failure(capture, "TimeoutError")
        review = self.workflow.route(row["record_id"], self.unit)
        before = self.workflow.get(review, row["record_id"], self.unit)
        self.assertIsNone(before["automated_assessment"])
        self.assertEqual(before["processing_error_at_routing"], "TimeoutError")
        self.assertIn({"code": "assessment_unavailable", "dimension": "assessment"}, before["uncertainty"])
        ingest(row, self.source, self.store)
        self.assertEqual(self.workflow.get(review, row["record_id"], self.unit), before)

    def test_returned_data_mutation_does_not_change_history(self):
        review, _ = self.vision_case()
        item = self.item(review)
        item["status"] = "resolved"
        history = self.workflow.history(review, self.record, self.unit)
        history[0]["new_state"]["status"] = "resolved"
        self.assertEqual(self.item(review)["status"], "pending_review")
        self.assertEqual(self.workflow.history(review, self.record, self.unit)[0]["new_state"]["status"], "pending_review")

    def test_invalid_ids_and_sql_like_identifiers_cannot_bypass_scope(self):
        review, _ = self.vision_case()
        for value in (True, 0, -1, "1", 10**1000):
            with self.subTest(value=type(value)), self.assertRaises(ValidationError):
                self.workflow.get(value, self.record, self.unit)
            with self.assertRaises(ValidationError):
                self.workflow.route(self.record, self.unit, attempt_id=value)
        with self.assertRaises(TenantMismatch):
            self.workflow.get(review, "' OR 1=1 --", self.unit)

    def test_event_write_failure_rolls_back_entire_case_creation(self):
        self.store._db.execute("CREATE TEMP TRIGGER fail_review_event BEFORE INSERT ON review_events "
                               "BEGIN SELECT RAISE(ABORT, 'TEST injected failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.workflow.route(self.record, self.unit)
        self.assertEqual(self.workflow.queue(), [])
        self.assertIsNotNone(self.store.get(self.record))
        self.store._db.execute("DROP TRIGGER fail_review_event")
        review = self.workflow.route(self.record, self.unit)
        self.assertEqual(len(self.workflow.history(review, self.record, self.unit)), 1)

    def test_two_connections_retry_and_stale_update_survive_restart(self):
        root = PARTICIPANT / ".test-tmp"
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory:
            path = Path(directory) / "concurrent.sqlite3"
            with Store(path, self.context) as first, Store(path, self.context) as second:
                ingest(self.row, self.source, first)
                one, two = ReviewWorkflow(first), ReviewWorkflow(second)
                review = one.route(self.record, self.unit)
                self.assertEqual(two.route(self.record, self.unit), review)
                command = dict(reviewer=self.reviewer, command_id="TEST-worker-one", expected_revision=1,
                               status="in_review", reason="TEST review started")
                event = one.transition(review, self.record, self.unit, **command)
                self.assertEqual(two.transition(review, self.record, self.unit, **command), event)
                with self.assertRaises(ConflictError):
                    two.transition(review, self.record, self.unit, **{**command, "command_id": "TEST-worker-two"})
            with Store(path, self.context) as reopened:
                workflow = ReviewWorkflow(reopened)
                self.assertEqual(workflow.history(review, self.record, self.unit)[1], event)
                self.assertEqual(workflow.get(review, self.record, self.unit)["revision"], 2)


if __name__ == "__main__":
    unittest.main()
