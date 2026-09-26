"""Synthetic regression inputs only; no image, model or evaluation evidence."""

import copy
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

PARTICIPANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PARTICIPANT / "agent"))

from returns_manager.domain import TenantContext, TenantMismatch, ValidationError, identifier
from returns_manager.observations import text
from returns_manager.review import ReviewerContext
from returns_manager.review_storage import ReviewWorkflow
from returns_manager.service import ingest, inspect_capture
from returns_manager.storage import Store
from returns_manager.validation import FIELDS, parse_record, read_csv


class InputBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.row, self.source = next((r, s) for r, s in read_csv(
            PARTICIPANT.parents[1] / "data" / "returns_sample.csv") if r["org_id"] == "org_demo_alpha")
        self.context = TenantContext("org_demo_alpha")

    def assert_round_trip(self, row, source=None):
        source = source or self.source
        with Store(":memory:", self.context) as store:
            workflow = ReviewWorkflow(store)
            first = ingest(row, source, store)
            self.assertEqual(ingest(row, source, store), first)
            self.assertEqual(dict(first["capture"]["raw_fields"]), row)
            self.assertEqual(store.get(row["record_id"]), first)
            self.assertEqual(store.for_unit(row["unit_id"]), [first])
            review = workflow.route(row["record_id"], row["unit_id"])
            self.assertEqual(workflow.route(row["record_id"], row["unit_id"]), review)
            item = workflow.get(review, row["record_id"], row["unit_id"])
            self.assertEqual((item["record_id"], item["unit_id"]), (row["record_id"], row["unit_id"]))
            self.assertEqual(item["capture"], first["capture"])
            self.assertEqual(workflow.queue(), [item])
            args = dict(reviewer=ReviewerContext(self.context, "TEST-reviewer"), command_id="TEST-start",
                        expected_revision=1, status="in_review", reason="TEST boundary review")
            event = workflow.transition(review, row["record_id"], row["unit_id"], **args)
            self.assertEqual(workflow.transition(review, row["record_id"], row["unit_id"], **args), event)
            self.assertEqual(len(workflow.history(review, row["record_id"], row["unit_id"])), 2)
            # Scope identifiers also survive the existing observation-attempt path.
            attempt = inspect_capture(row, source, store, (), None)
            vision_review = workflow.route(row["record_id"], row["unit_id"], attempt_id=attempt)
            self.assertEqual(workflow.get(vision_review, row["record_id"], row["unit_id"])["capture"], first["capture"])
            self.assertEqual(store._db.execute("SELECT COUNT(*) FROM captures").fetchone()[0], 1)

    def test_long_record_id_round_trips_routes_and_retries(self):
        # Boundary is the pre-existing observation-text limit, not an identifier rule.
        for length in (8191, 8192, 8193, 8197):
            with self.subTest(length=length):
                self.assert_round_trip({**self.row, "record_id": "TEST-" + "x" * (length - 5)})

    def test_long_unit_id_round_trips_routes_and_retries(self):
        for length in (8191, 8192, 8193, 8197):
            with self.subTest(length=length):
                self.assert_round_trip({**self.row, "unit_id": "TEST-" + "x" * (length - 5)})

    def test_short_identifiers_keep_existing_behavior(self):
        self.assert_round_trip(self.row)

    def test_long_identifiers_preserve_tenant_isolation(self):
        row = {**self.row, "record_id": "TEST-record-" + "x" * 8192, "unit_id": "TEST-unit-" + "y" * 8192}
        root = PARTICIPANT / ".test-tmp"
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory:
            database = Path(directory) / "boundaries.sqlite3"
            contexts = (self.context, TenantContext("org_demo_bravo"))
            review_ids = []
            for context in contexts:
                with Store(database, context) as store:
                    ingest({**row, "org_id": context.organization_id}, self.source, store)
                    review_ids.append(ReviewWorkflow(store).route(row["record_id"], row["unit_id"]))
            for n, context in enumerate(contexts):
                with Store(database, context) as store:
                    workflow = ReviewWorkflow(store)
                    self.assertEqual([i["review_id"] for i in workflow.queue()], [review_ids[n]])
                    self.assertEqual(store.get(row["record_id"])["capture"]["tenant"]["organization_id"], context.organization_id)
                    self.assertEqual(len(store.for_unit(row["unit_id"])), 1)
                    for action in (
                        lambda: workflow.get(review_ids[1-n], row["record_id"], row["unit_id"]),
                        lambda: workflow.history(review_ids[1-n], row["record_id"], row["unit_id"]),
                        lambda: workflow.transition(review_ids[1-n], row["record_id"], row["unit_id"],
                            reviewer=ReviewerContext(context, "TEST-reviewer"), command_id="TEST-forbidden",
                            expected_revision=1, status="in_review", reason="TEST foreign access"),
                    ):
                        with self.assertRaises(TenantMismatch):
                            action()

    def test_observation_text_limit_is_unchanged(self):
        self.assertEqual(text("x" * 8192), "x" * 8192)
        with self.assertRaises(ValidationError):
            text("x" * 8193)
        self.assertEqual(identifier("x" * 8193, "record_id"), "x" * 8193)

    def assert_rejected_before_storage(self, row, source=None):
        with Store(":memory:", self.context) as store:
            workflow = ReviewWorkflow(store)
            # Both service entry points must reject before invoking persistence.
            for operation in (lambda: ingest(row, source or self.source, store),
                              lambda: inspect_capture(row, source or self.source, store, (), None)):
                for _ in range(2):
                    with patch.object(store, "save_capture", wraps=store.save_capture) as save:
                        with self.assertRaises(ValidationError):
                            operation()
                        save.assert_not_called()
            self.assertEqual(store._db.execute("SELECT COUNT(*) FROM captures").fetchone()[0], 0)
            self.assertEqual(store._db.execute("SELECT COUNT(*) FROM vision_attempts").fetchone()[0], 0)
            self.assertEqual(store._db.execute("SELECT COUNT(*) FROM review_events").fetchone()[0], 0)
            self.assertEqual(workflow.queue(), [])
            # Corrected retry succeeds normally without duplicate captures.
            accepted = ingest(self.row, self.source, store)
            self.assertEqual(ingest(self.row, self.source, store), accepted)
            self.assertEqual(store._db.execute("SELECT COUNT(*) FROM captures").fetchone()[0], 1)

    def test_invalid_unicode_operator_rejected_before_persistence(self):
        for scalar in ("\ud800", "\udfff"):
            with self.subTest(scalar=ascii(scalar)):
                self.assert_rejected_before_storage({**self.row, "operator_id": scalar})

    def test_invalid_unicode_all_other_persisted_row_fields_rejected(self):
        # Includes IDs, component/photo refs, historical/free text and timestamp.
        for field in FIELDS:
            if field == "operator_id":
                continue
            for scalar in ("\ud800", "\udfff"):
                with self.subTest(field=field, scalar=ascii(scalar)):
                    self.assert_rejected_before_storage({**self.row, field: scalar})

    def test_invalid_unicode_context_and_lineage_rejected(self):
        for scalar in ("\ud800", "\udfff"):
            with self.subTest(scalar=ascii(scalar)):
                with self.assertRaises(ValidationError):
                    TenantContext(scalar)
                with self.assertRaises(ValidationError):
                    TenantContext(self.context.organization_id, scalar)
                with self.assertRaises(ValidationError):
                    replace(self.source, source_name=scalar)
                # A manually forged lineage object must be checked again at ingress.
                forged = copy.copy(self.source)
                object.__setattr__(forged, "source_name", scalar)
                self.assert_rejected_before_storage(self.row, forged)

    def test_storage_revalidates_manually_forged_capture_unicode(self):
        raw = {**self.row, "amazon_condition": "\ud800"}
        capture = replace(parse_record(self.row, self.context, self.source), raw_fields=tuple(sorted(raw.items())))
        with Store(":memory:", self.context) as store:
            statements = []
            store._db.set_trace_callback(statements.append)
            with self.assertRaises(ValidationError):
                store.save_capture(capture)
            self.assertEqual(statements, [])
            self.assertEqual(store._db.execute("SELECT COUNT(*) FROM captures").fetchone()[0], 0)

    def test_valid_unicode_preserved_without_normalization(self):
        value = "TEST-caf\u00e9-e\u0301-\U0001f50d-\u5546\u54c1"
        row = {**self.row, **{field: value for field in (
            "record_id", "unit_id", "order_id", "ordered_sku", "ordered_asin", "operator_id", "photo_refs")},
            "parts_list": value, "parts_missing": "", "amazon_condition": value + "\nTEST historical text"}
        source = replace(self.source, source_name=value + ".csv")
        self.assert_round_trip(row, source)
        self.assertEqual(parse_record(row, self.context, source).source.source_name, source.source_name)

    def test_malformed_identifiers_still_rejected(self):
        with Store(":memory:", self.context) as store:
            workflow = ReviewWorkflow(store)
            ingest(self.row, self.source, store)
            review = workflow.route(self.row["record_id"], self.row["unit_id"])
            for value in ("", " leading", "trailing ", "TEST\n", "TEST\x00", None, 1, "\ud800"):
                for field in ("record_id", "unit_id"):
                    with self.subTest(value=repr(value), field=field):
                        row = {**self.row, field: value}
                        with self.assertRaises(ValidationError):
                            ingest(row, self.source, store)
                        with self.assertRaises(ValidationError):
                            workflow.route(row["record_id"], row["unit_id"])
                        with self.assertRaises(ValidationError):
                            workflow.get(review, row["record_id"], row["unit_id"])
            self.assertEqual(len(workflow.history(review, self.row["record_id"], self.row["unit_id"])), 1)


if __name__ == "__main__":
    unittest.main()
