"""Harness regression checks using source data and labelled engineering faults only.

No visual golden labels, images, or model outputs are created by these tests.
"""

import copy
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

PARTICIPANT = Path(__file__).resolve().parents[1]
ROOT = PARTICIPANT.parents[1]
SAMPLE = ROOT / "data" / "returns_sample.csv"
sys.path.insert(0, str(PARTICIPANT / "agent"))

from returns_manager import evaluation
from returns_manager.domain import TenantContext, ValidationError
from returns_manager.evaluation_data import reference_inventory, scenario_cases, SCENARIOS
from returns_manager.validation import read_csv


class EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_bytes = SAMPLE.read_bytes()
        cls.report = evaluation.evaluate_dataset(SAMPLE, ROOT)

    def setUp(self):
        self.row, self.source = read_csv(SAMPLE)[0]
        self.context = TenantContext(self.row["org_id"])
        self.case = evaluation.EvaluationCase("TEST-case", "safe_review", self.row, self.source, self.context)

    def test_inventory_counts_measured_source_and_missing_paths(self):
        rows = read_csv(SAMPLE)
        dataset = self.report["dataset"]
        self.assertEqual(dataset["rows"], len(rows))
        self.assertEqual(dataset["unique_units"], len({row["unit_id"] for row, _ in rows}))
        self.assertEqual(set(dataset["organizations"]), {row["org_id"] for row, _ in rows})
        refs = [ref for row, _ in rows for ref in row["photo_refs"].split(";") if ref]
        self.assertEqual(dataset["image_references"], len(refs))
        for unit in dataset["units"]:
            for image in unit["images"]:
                self.assertEqual(image["status"], "missing")
                self.assertFalse(image["present_paths"])
                self.assertTrue(image["checked_paths"])
        self.assertEqual(dataset["condition_annotations_blank"], 24)
        self.assertEqual(dataset["identity_annotations"], {"yes": 24})

    def test_visual_scenarios_are_blocked_not_counted_as_passes(self):
        cases = [c for c in self.report["cases"] if c["category"] == "visual_scenario"]
        self.assertEqual({c["scenario"] for c in cases}, {name for _, name in SCENARIOS})
        for case in cases:
            self.assertEqual(case["status"], "BLOCKED")
            self.assertIsNone(case["expected"])
            self.assertIsNone(case["actual"])
            self.assertFalse(case["final_business_decision_evaluable"])
            self.assertTrue(case["blocked_reason"])
        self.assertEqual(self.report["summary"]["BLOCKED"], 10)

    def test_candidate_annotations_do_not_become_genuine_scenario_coverage(self):
        scenarios = {c["case_id"]: c for c in scenario_cases(self.report["dataset"])}
        self.assertEqual(scenarios["scenario:correct_product"]["annotation_candidate_count"], 24)
        self.assertEqual(scenarios["scenario:wrong_product"]["annotation_candidate_count"], 0)
        self.assertEqual(scenarios["scenario:multiple_missing"]["annotation_candidate_count"], 0)
        self.assertEqual(scenarios["scenario:heavily_damaged"]["annotation_candidate_count"], 0)
        self.assertEqual(scenarios["scenario:similar_products"]["annotation_candidate_count"], 0)
        self.assertTrue(all(c["ground_truth"] == "unavailable" for c in scenarios.values()))

    def test_repeat_run_is_byte_reproducible(self):
        second = evaluation.evaluate_dataset(SAMPLE, ROOT)
        self.assertEqual(evaluation.serialize(self.report), evaluation.serialize(second))

    def test_no_source_evidence_mutation(self):
        self.assertEqual(SAMPLE.read_bytes(), self.source_bytes)
        self.assertEqual(self.report["source"]["sha256"], hashlib.sha256(self.source_bytes).hexdigest())
        self.assertTrue(self.report["source"]["unchanged_after_run"])
        before = copy.deepcopy(self.row)
        evaluation.run_case(replace(self.case, kind="duplicate_reference"))
        self.assertEqual(self.row, before)

    def test_every_source_case_keeps_ids_references_lineage(self):
        records = {(r["org_id"], r["record_id"]): (r, s) for r, s in read_csv(SAMPLE)}
        for case in self.report["cases"]:
            if case["scenario"] != "safe_review":
                continue
            row, source = records[case["organization_id"], case["record_id"]]
            self.assertEqual(case["unit_id"], row["unit_id"])
            self.assertEqual(case["input_reference"]["source_sha256"], source.source_sha256)
            self.assertEqual(case["input_reference"]["row_number"], source.row_number)
            self.assertEqual([e["reference"] for e in case["evidence"]], row["photo_refs"].split(";"))
            self.assertEqual(case["review"]["organization_id"], row["org_id"])
            self.assertIsNone(case["review"]["client_id"])

    def test_uncertainty_can_pass_contract_without_passing_visual_benchmark(self):
        case = evaluation.run_case(self.case)
        self.assertEqual(case["status"], "PASS")
        self.assertEqual(case["system_state"], "UNCERTAIN/REVIEW")
        self.assertEqual(case["actual"]["identity"], "UNCERTAIN")
        self.assertIsNone(case["actual"]["grade"])
        self.assertTrue(case["uncertainty"])
        self.assertEqual(case["actual"]["disposition"], "pending_review")

    def test_expected_actual_comparison_detects_missing_values_and_types(self):
        self.assertEqual(evaluation.compare({"a": 1}, {"a": 1}), [])
        self.assertEqual(evaluation.compare({"a": None}, {})[0]["missing"], True)
        self.assertTrue(evaluation.compare({"a": True}, {"a": 1}))
        mismatch = evaluation.compare({"identity": "UNCERTAIN"}, {"identity": "PASS"})
        self.assertEqual(mismatch[0]["actual"], "PASS")

    def test_injected_wrong_actual_result_fails_with_explanation(self):
        original = evaluation._review_case
        def changed(*args):
            expected, actual, view = original(*args)
            actual["disposition"] = "restock"  # TEST intentionally incorrect output to test comparator.
            return expected, actual, view
        with patch.object(evaluation, "_review_case", side_effect=changed):
            case = evaluation.run_case(self.case)
        self.assertEqual(case["status"], "FAIL")
        self.assertEqual(case["failure_reason"][0]["check"], "disposition")
        self.assertEqual(case["failure_reason"][0]["expected"], "pending_review")

    def test_case_failure_does_not_contaminate_next_case(self):
        with patch.object(evaluation, "ingest", side_effect=RuntimeError("TEST sensitive failure")):
            broken = evaluation.run_case(self.case)
        good = evaluation.run_case(self.case)
        self.assertEqual(broken["status"], "FAIL")
        self.assertNotIn("sensitive", evaluation.serialize(broken))
        self.assertEqual(good["status"], "PASS")
        self.assertEqual(good["actual"]["capture_count"], 1)
        self.assertEqual(good["actual"]["review_event_count"], 1)

    def test_malformed_internal_cases_fail_safely(self):
        for case in (None, {}, replace(self.case, kind="TEST-unknown"), replace(self.case, row={}),
                     replace(self.case, context=TenantContext("org_demo_alpha") if self.context.organization_id != "org_demo_alpha"
                             else TenantContext("org_demo_bravo"))):
            with self.subTest(case_type=type(case).__name__):
                result = evaluation.run_case(case)
                self.assertEqual(result["status"], "FAIL")
                self.assertIsNotNone(result["failure_reason"])
                json.loads(evaluation.serialize(result))

    def test_case_isolation_uses_fresh_store_for_repeated_identifiers(self):
        first, second = evaluation.run_case(self.case), evaluation.run_case(self.case)
        self.assertEqual(first, second)
        self.assertEqual(first["actual"]["capture_count"], 1)
        self.assertEqual(first["actual"]["review_event_count"], 1)

    def test_malformed_case_retains_available_valid_identifiers(self):
        row = dict(self.row)
        del row["order_id"]
        result = evaluation.run_case(replace(self.case, row=row))
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["case_id"], self.case.case_id)
        self.assertEqual(result["record_id"], self.row["record_id"])
        self.assertEqual(result["unit_id"], self.row["unit_id"])
        self.assertEqual(result["organization_id"], self.context.organization_id)

    def test_controls_cover_each_available_tenant_and_are_labelled(self):
        controls = [c for c in self.report["cases"] if c["scenario"] in evaluation.CONTROL_KINDS]
        self.assertEqual(len(controls), len(evaluation.CONTROL_KINDS) * len(self.report["dataset"]["organizations"]))
        self.assertTrue(all(c["status"] == "PASS" for c in controls))
        self.assertTrue(all("Controlled engineering" in c["probe_notice"] for c in controls))
        for case in controls:
            if case["scenario"] == "tenant_isolation":
                self.assertEqual(case["actual"]["foreign_queue"], [])
                self.assertTrue(case["actual"]["foreign_history_rejected"])
                self.assertTrue(case["actual"]["foreign_override_rejected"])
            elif case["scenario"] == "persistence_failure":
                self.assertEqual(case["actual"]["partial_events"], 0)
                self.assertTrue(case["actual"]["capture_preserved"])

    def test_accuracy_metrics_are_blocked_not_zero_or_synthetic_percentages(self):
        for metric in self.report["summary"]["metrics"]["blocked_metrics"].values():
            self.assertEqual(metric["status"], "BLOCKED")
            self.assertIsNone(metric["value"])
        summary = self.report["summary"]
        self.assertEqual(summary["total_cases"], summary["PASS"] + summary["FAIL"] + summary["BLOCKED"])
        self.assertEqual(summary["metrics"]["sample_case_denominator"], self.report["dataset"]["rows"])
        self.assertEqual(summary["metrics"]["sample_verdict_distributions"]["identity"], {"UNCERTAIN": 24})
        failures = evaluation.summarize([evaluation.run_case(None), evaluation.run_case(replace(self.case, row={}))])
        self.assertEqual(failures["FAIL"], 2)
        self.assertEqual(failures["metrics"]["sample_cases_with_outputs"], 0)

    def test_inventory_does_not_fetch_remote_or_escape_repository(self):
        for ref in ("../outside.jpg", "https://example.invalid/photo.jpg", "C:/outside.jpg", "\\\\server\\share\\photo.jpg"):
            with self.subTest(ref=ref):
                self.assertEqual(reference_inventory(ref, ROOT, SAMPLE.parent)["status"], "unsafe_reference")
        # A real text file is deliberately NOT classified as genuine image evidence.
        found = reference_inventory("data/README.md", ROOT, SAMPLE.parent)
        self.assertEqual(found["status"], "present_unverified")

    def test_empty_and_duplicate_source_records_are_rejected(self):
        with patch.object(evaluation, "read_csv", return_value=[]), self.assertRaises(ValidationError):
            evaluation.evaluate_dataset(SAMPLE, ROOT)
        with patch.object(evaluation, "read_csv", return_value=[(self.row, self.source)] * 2), self.assertRaises(ValidationError):
            evaluation.evaluate_dataset(SAMPLE, ROOT)

    def test_malformed_dataset_cli_reports_structured_failure(self):
        error = io.StringIO()
        with redirect_stderr(error):
            code = evaluation.main(["--csv", str(ROOT / "data" / "README.md")])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(error.getvalue())["status"], "FAIL")

    def test_output_cannot_overwrite_evidence_or_outside_directory(self):
        for path in (SAMPLE, ROOT / "TEST-forbidden.json", PARTICIPANT / "agent" / "TEST-forbidden.json"):
            with self.subTest(path=path), redirect_stderr(io.StringIO()), patch.object(Path, "write_text") as write:
                self.assertEqual(evaluation.main(["--output", str(path)]), 2)
                write.assert_not_called()

    def test_cli_stdout_report_exit_does_not_claim_blocked_scenarios_passed(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = evaluation.main([])
        report = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)  # No engineering failures; visual readiness is separately BLOCKED.
        self.assertEqual(report["summary"]["BLOCKED"], 10)
        self.assertEqual(report, self.report)


if __name__ == "__main__":
    unittest.main()
