"""Synthetic engineering fixtures only; no photos, model outputs or evaluation labels."""

import csv
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from contextlib import closing
from unittest.mock import patch

PARTICIPANT = Path(__file__).resolve().parents[1]
ROOT = PARTICIPANT.parents[1]
sys.path.insert(0, str(PARTICIPANT / "agent"))

from returns_manager.domain import (
    Component, Disposition, DispositionResult, ObservationPlaceholder,
    TenantContext, TenantMismatch, ValidationError, Verdict,
)
from returns_manager.rules import assess
from returns_manager.service import ingest
from returns_manager.storage import ConflictError, Store
from returns_manager.validation import FIELDS, parse_record, read_csv

SAMPLE = ROOT / "data" / "returns_sample.csv"
ALPHA = TenantContext("org_demo_alpha")
BRAVO = TenantContext("org_demo_bravo")


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.records = read_csv(SAMPLE)
        self.row, self.source = next((dict(r), s) for r, s in self.records if r["org_id"] == ALPHA.organization_id)
        self.capture = parse_record(self.row, ALPHA, self.source)
        scratch = PARTICIPANT / ".test-tmp"
        scratch.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.tmp.cleanup)
        self.database = Path(self.tmp.name) / "test.sqlite3"

    def test_all_24_units_and_both_organizations_preserved(self):
        before = SAMPLE.read_bytes()
        with SAMPLE.open(newline="", encoding="utf-8-sig") as f:
            raw = list(csv.DictReader(f))
        captures = [parse_record(r, TenantContext(r["org_id"]), s) for r, s in self.records]
        self.assertEqual(len(captures), 24)
        self.assertEqual({c.unit.unit_id for c in captures}, {r["unit_id"] for r in raw})
        self.assertEqual(len({c.unit.unit_id for c in captures}), 24)
        self.assertEqual({c.tenant.organization_id for c in captures}, {ALPHA.organization_id, BRAVO.organization_id})
        self.assertEqual(SAMPLE.read_bytes(), before)

    def test_all_lineage_fields_preserved(self):
        for row, source in self.records:
            with self.subTest(record=row["record_id"]):
                capture = parse_record(row, TenantContext(row["org_id"]), source)
                self.assertEqual(dict(capture.raw_fields), row)
                self.assertEqual(capture.record_id, row["record_id"])
                self.assertEqual(capture.order.order_id, row["order_id"])
                self.assertEqual(capture.order.ordered_sku, row["ordered_sku"])
                self.assertEqual(capture.order.ordered_asin, row["ordered_asin"])
                self.assertEqual(capture.operator_id, row["operator_id"])
                self.assertEqual(capture.captured_at, row["captured_at"])
                self.assertEqual([i.reference for i in capture.images], row["photo_refs"].split(";"))
                self.assertEqual(source.source_sha256, hashlib.sha256(SAMPLE.read_bytes()).hexdigest())
                self.assertEqual(source.kind, "synthetic_test_fixture")

    def test_missing_client_remains_none_and_blocks_review(self):
        self.assertIsNone(self.capture.tenant.client_id)
        self.assertIn("client_context_missing", self.capture.blockers)

    def test_invalid_identifiers(self):
        for field in ("record_id", "unit_id", "org_id", "order_id", "ordered_sku", "ordered_asin", "operator_id"):
            for value in ("", " ", " padded", "bad\nvalue", None, 42):
                with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                    parse_record({**self.row, field: value}, ALPHA, self.source)

    def test_missing_and_unknown_fields_rejected(self):
        bad = dict(self.row)
        del bad["unit_id"]
        for row in (bad, {**self.row, "unknown_field": "x"}, []):
            with self.subTest(row=row), self.assertRaises(ValidationError):
                parse_record(row, ALPHA, self.source)

    def test_invalid_tenant_context(self):
        for value in ("", " ", None):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                TenantContext(value)
        with self.assertRaises(ValidationError):
            TenantContext(ALPHA.organization_id, "")
        with self.assertRaises(ValidationError):
            parse_record(self.row, None, self.source)

    def test_cross_tenant_input_rejected(self):
        with self.assertRaises(TenantMismatch):
            parse_record(self.row, BRAVO, self.source)

    def test_timestamps_must_be_valid_utc(self):
        for value in ("not-a-date", "2026-09-26", "2026-09-26T09:00:00", "2026-09-26T09:00:00+05:30"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                parse_record({**self.row, "captured_at": value}, ALPHA, self.source)

    def test_component_quantities_are_not_guessed(self):
        row = {**self.row, "parts_list": "mug x2;puzzle pieces;manual", "parts_missing": ""}
        capture = parse_record(row, ALPHA, self.source)
        self.assertEqual([c.quantity for c in capture.reference.components], [2, None, None])

    def test_invalid_component_data_rejected(self):
        for value in ("mug x0", "mug x-2", "mug x1.5", "mug xmany", "mug;;manual", "mug;mug", "mug x2;mug x3"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                parse_record({**self.row, "parts_list": value, "parts_missing": ""}, ALPHA, self.source)
        for quantity in (0, -1, True, "2"):
            with self.subTest(quantity=quantity), self.assertRaises(ValidationError):
                Component("mug", "mug", quantity)

    def test_missing_part_not_in_reference_rejected(self):
        with self.assertRaises(ValidationError):
            parse_record({**self.row, "parts_missing": "TEST-UNKNOWN-PART"}, ALPHA, self.source)

    def test_missing_reference_preserved_for_review(self):
        capture = parse_record({**self.row, "parts_list": "", "parts_missing": ""}, ALPHA, self.source)
        self.assertIn("parts_reference_missing", capture.blockers)
        self.assertEqual(assess(capture, ObservationPlaceholder()).completeness.verdict, Verdict.UNCERTAIN)

    def test_unverified_reference_cannot_produce_decision(self):
        self.assertEqual(self.capture.reference.status, "unverified_synthetic_reference")
        result = assess(self.capture, ObservationPlaceholder())
        self.assertIn("catalogue_reference_unverified", result.review.reasons)
        self.assertIn("disposition_policy_unavailable", result.disposition.reasons)

    def test_missing_image_list_is_pending(self):
        capture = parse_record({**self.row, "photo_refs": ""}, ALPHA, self.source)
        self.assertEqual(capture.images, ())
        self.assertIn("image_evidence_unavailable", assess(capture, ObservationPlaceholder()).review.reasons)

    def test_all_72_image_references_unavailable(self):
        images = [image for row, source in self.records
                  for image in parse_record(row, TenantContext(row["org_id"]), source).images]
        self.assertEqual(len(images), 72)
        self.assertTrue(all(i.status == "unavailable" for i in images))

    def test_paths_and_urls_are_not_opened_as_evidence(self):
        for ref in ("../../private.txt", "https://example.invalid/image.jpg", str(SAMPLE)):
            with self.subTest(ref=ref), patch("builtins.open", side_effect=AssertionError("must not open")):
                capture = parse_record({**self.row, "photo_refs": ref}, ALPHA, self.source)
                self.assertEqual(capture.images[0].status, "unavailable")
                self.assertEqual(assess(capture, ObservationPlaceholder()).identity.evidence, ())

    def test_malformed_image_list_rejected(self):
        for value in ("a.jpg;;b.jpg", "a.jpg;a.jpg"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                parse_record({**self.row, "photo_refs": value}, ALPHA, self.source)

    def test_dispositions_validate_authorized_values_only(self):
        for value in Disposition:
            self.assertEqual(DispositionResult(value.value, ()).decision, value)
        for value in ("sell", "UNKNOWN", "RESTOCK", "", None):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                DispositionResult(value, ())

    def test_invalid_historical_disposition_rejected(self):
        with self.assertRaises(ValidationError):
            parse_record({**self.row, "operator_disposition": "sell"}, ALPHA, self.source)

    def test_history_is_not_prediction_or_ground_truth(self):
        for label in ("yes", "no", "uncertain"):
            capture = parse_record({**self.row, "identity_match": label, "amazon_condition": "TEST-UNSUPPORTED-GRADE",
                                    "operator_disposition": "restock"}, ALPHA, self.source)
            result = assess(capture, ObservationPlaceholder())
            self.assertEqual(result.identity.verdict, Verdict.UNCERTAIN)
            self.assertIsNone(result.condition.grade)
            self.assertEqual(result.disposition.decision, Disposition.PENDING_REVIEW)

    def test_four_layers_remain_separate_without_fabrication(self):
        result = assess(self.capture, ObservationPlaceholder())
        self.assertEqual(len({type(result.identity), type(result.completeness), type(result.condition), type(result.disposition)}), 4)
        for check in (result.identity, result.completeness, result.condition):
            self.assertEqual(check.verdict, Verdict.UNCERTAIN)
            self.assertIsNone(check.confidence)
            self.assertEqual(check.evidence, ())
        self.assertIsNone(result.condition.grade)
        self.assertEqual(result.completeness.missing_components, ())
        self.assertEqual(result.review.status, "pending_review")
        self.assertEqual(result, assess(self.capture, ObservationPlaceholder()))

    def test_rules_reject_unvalidated_or_forged_input(self):
        for capture in (self.row, replace(self.capture, record_id="TEST-FORGED")):
            with self.subTest(capture=type(capture)), self.assertRaises(ValidationError):
                assess(capture, ObservationPlaceholder())
        with self.assertRaises(ValidationError):
            assess(self.capture, {"identity": "PASS"})

    def test_capture_survives_restart(self):
        with Store(self.database, ALPHA) as store:
            original = ingest(self.row, self.source, store)
        with Store(self.database, ALPHA) as store:
            self.assertEqual(store.get(self.row["record_id"]), original)

    def test_other_organization_cannot_lookup_record_unit_or_evidence(self):
        with Store(self.database, ALPHA) as store:
            ingest(self.row, self.source, store)
        with Store(self.database, BRAVO) as store:
            self.assertIsNone(store.get(self.row["record_id"]))
            self.assertEqual(store.for_unit(self.row["unit_id"]), [])
            self.assertIsNone(store.evidence_reference(self.row["record_id"], self.capture.images[0].reference))
            with self.assertRaises(TenantMismatch):
                store.save_capture(self.capture)

    def test_identical_ids_can_exist_in_different_tenants(self):
        with Store(self.database, ALPHA) as store:
            ingest(self.row, self.source, store)
        other = {**self.row, "org_id": BRAVO.organization_id, "operator_id": "TEST-SYNTHETIC-OPERATOR"}
        with Store(self.database, BRAVO) as store:
            ingest(other, self.source, store)
            self.assertEqual(store.get(other["record_id"])["capture"]["operator_id"], other["operator_id"])
        with Store(self.database, ALPHA) as store:
            self.assertEqual(store.get(self.row["record_id"])["capture"]["operator_id"], self.row["operator_id"])

    def test_missing_client_is_persisted_as_null_without_inventing_id(self):
        with Store(self.database, ALPHA) as store:
            record = ingest(self.row, self.source, store)
            self.assertIsNone(record["capture"]["tenant"]["client_id"])
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute("SELECT client_scope FROM captures").fetchall(), [("null",)])

    def test_all_24_records_persist_with_bidirectional_tenant_isolation(self):
        for context in (ALPHA, BRAVO):
            with Store(self.database, context) as store:
                for row, source in self.records:
                    if row["org_id"] == context.organization_id:
                        ingest(row, source, store)
        for context in (ALPHA, BRAVO):
            with Store(self.database, context) as store:
                found = []
                for row, _ in self.records:
                    record = store.get(row["record_id"])
                    if row["org_id"] != context.organization_id:
                        self.assertIsNone(record)
                    else:
                        found.append(record["capture"]["unit"]["unit_id"])
                self.assertEqual(set(found), {r["unit_id"] for r, _ in self.records if r["org_id"] == context.organization_id})
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM captures").fetchone()[0], 24)

    def test_duplicate_ingestion_is_idempotent(self):
        with Store(self.database, ALPHA) as store:
            first = ingest(self.row, self.source, store)
            with patch("returns_manager.service.assess", side_effect=AssertionError("duplicate must not rerun")):
                self.assertEqual(ingest(self.row, self.source, store), first)
            self.assertEqual(len(store.for_unit(self.row["unit_id"])), 1)

    def test_conflicting_duplicate_does_not_overwrite(self):
        with Store(self.database, ALPHA) as store:
            first = ingest(self.row, self.source, store)
            with self.assertRaises(ConflictError):
                ingest({**self.row, "operator_id": "TEST-CHANGED"}, self.source, store)
            self.assertEqual(store.get(self.row["record_id"]), first)

    def test_failure_preserves_capture_pending_and_retry_can_resume(self):
        with Store(self.database, ALPHA) as store:
            with patch("returns_manager.service.assess", side_effect=TimeoutError("TEST-INJECTED")):
                with self.assertRaises(TimeoutError):
                    ingest(self.row, self.source, store)
            saved = store.get(self.row["record_id"])
            self.assertEqual(saved["status"], "pending_review")
            self.assertIsNone(saved["assessment"])
            self.assertEqual(saved["processing_error"], "TimeoutError")
            self.assertEqual(dict(saved["capture"]["raw_fields"]), self.row)
            recovered = ingest(self.row, self.source, store)
            self.assertIsNone(recovered["processing_error"])
            self.assertEqual(recovered["assessment"]["identity"]["verdict"], "UNCERTAIN")

    def test_fabricated_assessment_cannot_be_persisted(self):
        result = assess(self.capture, ObservationPlaceholder())
        result = replace(result, disposition=DispositionResult(Disposition.RESTOCK, ()))
        with Store(self.database, ALPHA) as store:
            with self.assertRaises(ValidationError):
                store.save_assessment(self.capture, result)
            self.assertIsNone(store.get(self.capture.record_id))

    def test_lookup_does_not_interpret_sql(self):
        with Store(self.database, ALPHA) as store:
            ingest(self.row, self.source, store)
            self.assertIsNone(store.get("' OR 1=1 --"))
            self.assertEqual(store.for_unit("' OR 1=1 --"), [])

    def test_csv_structural_errors(self):
        path = Path(self.tmp.name) / "synthetic-malformed.csv"
        for text in ("bad,header\nx,y\n", ",".join(FIELDS) + "\nshort,row\n",
                     ",".join((*FIELDS, "unit_id")) + "\n",
                     ",".join(FIELDS) + '\n"unterminated'):
            path.write_text(text, encoding="utf-8")
            with self.subTest(text=text), self.assertRaises(ValidationError):
                read_csv(path)

    def test_cli_imports_only_explicit_organization(self):
        env = {**os.environ, "PYTHONPATH": str(PARTICIPANT / "agent"), "PYTHONDONTWRITEBYTECODE": "1"}
        command = [sys.executable, "-m", "returns_manager", "--csv", str(SAMPLE),
                   "--organization", ALPHA.organization_id, "--database", str(self.database)]
        completed = subprocess.run(command, cwd=PARTICIPANT, env=env, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        records = [json.loads(line) for line in completed.stdout.splitlines()]
        self.assertEqual(len(records), 11)
        self.assertTrue(all(r["capture"]["tenant"]["organization_id"] == ALPHA.organization_id for r in records))
        self.assertTrue(all(r["assessment"]["disposition"]["decision"] == "pending_review" for r in records))

    def test_cli_rejects_database_outside_participant_directory(self):
        env = {**os.environ, "PYTHONPATH": str(PARTICIPANT / "agent"), "PYTHONDONTWRITEBYTECODE": "1"}
        completed = subprocess.run(
            [sys.executable, "-m", "returns_manager", "--csv", str(SAMPLE),
             "--organization", ALPHA.organization_id, "--database", str(ROOT / "forbidden.sqlite3")],
            cwd=PARTICIPANT, env=env, capture_output=True, text=True,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("database must be inside", completed.stderr)
        self.assertEqual(completed.stdout, "")


if __name__ == "__main__":
    unittest.main()
