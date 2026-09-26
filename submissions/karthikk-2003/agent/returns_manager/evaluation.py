"""Deterministic engineering evaluation of the repository sample; not a visual benchmark.

Each case uses fresh in-memory SQLite. Controlled mutations/faults are explicitly
engineering probes, never product observations or ground-truth labels.
"""

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

from .domain import TenantContext, TenantMismatch, ValidationError, SourceLineage, ObservationPlaceholder, identifier
from .evaluation_data import inventory, scenario_cases
from .review import ReviewerContext
from .review_storage import ReviewWorkflow
from .rules import assess
from .service import ingest, inspect_capture
from .storage import Store
from .validation import parse_record, read_csv
from .vision import FixtureProvider, ImageInput, ObservationScope


CONTROL_KINDS = ("missing_required", "invalid_unicode", "duplicate_reference", "unsupported_disposition",
                 "missing_images", "invalid_image", "malformed_provider", "provider_timeout",
                 "persistence_failure", "tenant_isolation")


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    kind: str
    row: dict
    source: SourceLineage
    context: TenantContext
    other_context: TenantContext | None = None


def compare(expected: dict, actual: dict) -> list[dict]:
    """Compare explicit contract assertions, including types; no scores/thresholds."""
    return [{"check": key, "expected": value, "actual": actual.get(key), "missing": key not in actual}
            for key, value in expected.items()
            if key not in actual or type(actual[key]) is not type(value) or actual[key] != value]


def _count(store, table):
    # Table names are internal constants, never supplied by a report/input case.
    if table not in {"captures", "vision_attempts", "review_items", "review_events"}:
        raise ValidationError("unsupported evaluation table")
    return store._db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]


def _review_projection(item):
    # Runtime timestamps remain in original review history; omit them from the
    # deterministic evaluation projection, never replace them with invented times.
    return {key: item[key] for key in ("organization_id", "client_id", "unit_id", "record_id", "source_key",
            "status", "business_status", "uncertainty", "unresolved_decisions", "evidence",
            "observations", "raw_response", "automated_assessment")}


class _TimeoutFixture:
    name, mode = "TEST-injected-timeout", "fixture"

    def observe(self, request):
        raise TimeoutError("TEST fault injection; no network or model")


def _review_case(case, store, workflow):
    row = dict(case.row)
    if case.kind == "missing_images":
        row["photo_refs"] = ""
    capture = parse_record(row, case.context, case.source)
    first = ingest(row, case.source, store)
    retry = ingest(row, case.source, store)
    images, provider = (), None
    expected_error = "provider_unavailable"
    if case.kind in {"invalid_image", "malformed_provider", "provider_timeout"}:
        if not capture.images:
            raise ValidationError("fault probe requires an existing sample photo reference")
        images = (ImageInput(ObservationScope.from_capture(capture), "TEST-eval-image", "TEST-eval-evidence",
                             capture.images[0].reference, "returned_product",
                             "genuine" if case.kind == "invalid_image" else "fixture",
                             b"TEST intentionally invalid non-image bytes" if case.kind == "invalid_image" else None),)
        provider = _TimeoutFixture() if case.kind == "provider_timeout" else FixtureProvider("{")
        expected_error = {"invalid_image": "unreadable_image", "malformed_provider": "invalid_response",
                          "provider_timeout": "provider_timeout"}[case.kind]
    attempt = inspect_capture(row, case.source, store, images, provider)
    entry = store.vision_attempts(capture.record_id)[0]
    review = workflow.route(capture.record_id, capture.unit.unit_id, attempt_id=attempt)
    item = workflow.get(review, capture.record_id, capture.unit.unit_id)
    result = entry["assessment"]
    actual = {
        "identity": result["identity"]["verdict"], "completeness": result["completeness"]["verdict"],
        "condition": result["condition"]["verdict"], "grade": result["condition"]["grade"],
        "disposition": result["disposition"]["decision"], "review_status": item["status"],
        "missing_components": result["completeness"]["missing_components"],
        "confidence_unavailable": all(result[d]["confidence"] is None for d in ("identity", "completeness", "condition")),
        "client_id": item["client_id"], "provider_error": entry["run"]["error_code"],
        "observations": entry["run"]["observations"], "raw_response": entry["run"]["raw_response"],
        "input_preserved": dict(first["capture"]["raw_fields"]) == row,
        "source_preserved": first["capture"]["source"] == asdict(case.source),
        "identifiers_preserved": (item["organization_id"], item["unit_id"], item["record_id"]) ==
                                 (case.context.organization_id, row["unit_id"], row["record_id"]),
        "reference_lineage_preserved": [i["reference"] for i in item["evidence"]] == [i.reference for i in capture.images],
        "original_assessment_preserved": store.get(capture.record_id) == first,
        "ingest_retry_identical": retry == first, "capture_count": _count(store, "captures"),
        "review_retry_identical": workflow.route(capture.record_id, capture.unit.unit_id, attempt_id=attempt) == review,
        "review_event_count": len(workflow.history(review, capture.record_id, capture.unit.unit_id)),
        "deterministic_rules": assess(capture, ObservationPlaceholder()) == assess(capture, ObservationPlaceholder()),
    }
    expected = {"identity": "UNCERTAIN", "completeness": "UNCERTAIN", "condition": "UNCERTAIN", "grade": None,
                "disposition": "pending_review", "review_status": "pending_review", "missing_components": [],
                "confidence_unavailable": True, "client_id": None, "provider_error": expected_error,
                "observations": None, "raw_response": None,
                **{key: True for key in ("input_preserved", "source_preserved", "identifiers_preserved",
                   "reference_lineage_preserved", "original_assessment_preserved", "ingest_retry_identical",
                   "review_retry_identical", "deterministic_rules")}, "capture_count": 1, "review_event_count": 1}
    return expected, actual, _review_projection(item)


def _rejection_case(case, store):
    row = dict(case.row)
    if case.kind == "missing_required":
        del row["order_id"]
    elif case.kind == "invalid_unicode":
        row["operator_id"] = "\ud800"
    elif case.kind == "unsupported_disposition":
        row["operator_disposition"] = "TEST-unsupported"
    else:
        reference = row["photo_refs"].split(";")[0]
        if not reference:
            raise ValidationError("duplicate-reference probe requires sample reference")
        row["photo_refs"] = reference + ";" + reference
    errors = []
    for _ in range(2):
        try:
            ingest(row, case.source, store)
            errors.append(None)
        except ValidationError:
            errors.append("ValidationError")
    actual = {"rejections": errors, **{table: _count(store, table) for table in
                                     ("captures", "vision_attempts", "review_items", "review_events")}}
    expected = {"rejections": ["ValidationError", "ValidationError"],
                "captures": 0, "vision_attempts": 0, "review_items": 0, "review_events": 0}
    return expected, actual, None


def _persistence_case(case, store, workflow):
    record = ingest(case.row, case.source, store)
    store._db.execute("CREATE TEMP TRIGGER TEST_fail_event BEFORE INSERT ON review_events "
                      "BEGIN SELECT RAISE(ABORT, 'TEST evaluation persistence fault'); END")
    error = None
    try:
        workflow.route(case.row["record_id"], case.row["unit_id"])
    except sqlite3.IntegrityError:
        error = "IntegrityError"
    actual = {"error": error, "partial_cases": _count(store, "review_items"),
              "partial_events": _count(store, "review_events"),
              "capture_preserved": store.get(case.row["record_id"]) == record}
    store._db.execute("DROP TRIGGER TEST_fail_event")
    review = workflow.route(case.row["record_id"], case.row["unit_id"])
    retry = workflow.route(case.row["record_id"], case.row["unit_id"])
    actual.update({"retry_same_case": review == retry, "cases_after_retry": _count(store, "review_items"),
                   "events_after_retry": _count(store, "review_events")})
    expected = {"error": "IntegrityError", "partial_cases": 0, "partial_events": 0, "capture_preserved": True,
                "retry_same_case": True, "cases_after_retry": 1, "events_after_retry": 1}
    return expected, actual, _review_projection(workflow.get(review, case.row["record_id"], case.row["unit_id"]))


def _isolation_case(case, store, workflow):
    if case.other_context is None or case.other_context == case.context:
        raise ValidationError("distinct existing sample tenant required")
    capture = parse_record(case.row, case.context, case.source)
    ingest(case.row, case.source, store)
    attempt = inspect_capture(case.row, case.source, store, (), None)
    review = workflow.route(capture.record_id, capture.unit.unit_id, attempt_id=attempt)
    actual = {}
    # Clone the same populated SQLite image in memory, then access it through a
    # different scoped Store. This tests predicates without persistent artifacts.
    with Store(":memory:", case.other_context) as foreign:
        store._db.backup(foreign._db)
        other = ReviewWorkflow(foreign)
        actual.update({"foreign_record": foreign.get(capture.record_id), "foreign_unit": foreign.for_unit(capture.unit.unit_id),
                       "foreign_attempts": foreign.vision_attempts(capture.record_id), "foreign_queue": other.queue(),
                       "foreign_evidence": foreign.evidence_reference(capture.record_id, capture.images[0].reference) if capture.images else None})
        for name, action in (
            ("foreign_history_rejected", lambda: other.history(review, capture.record_id, capture.unit.unit_id)),
            ("foreign_review_rejected", lambda: other.get(review, capture.record_id, capture.unit.unit_id)),
            ("foreign_route_rejected", lambda: other.route(capture.record_id, capture.unit.unit_id, attempt_id=attempt)),
            ("foreign_write_rejected", lambda: foreign.save_capture(capture)),
            ("foreign_override_rejected", lambda: other.transition(review, capture.record_id, capture.unit.unit_id,
                reviewer=ReviewerContext(case.other_context, capture.operator_id), command_id="TEST-foreign-update",
                expected_revision=1, status="in_review", reason="TEST unauthorized scope probe")),
        ):
            try:
                action()
                actual[name] = False
            except TenantMismatch:
                actual[name] = True
    for dimension in ("unit_id", "record_id"):
        identifiers = {"unit_id": capture.unit.unit_id, "record_id": capture.record_id}
        identifiers[dimension] = "TEST-invalid-scope"
        try:
            workflow.get(review, **identifiers)
            actual[dimension + "_mismatch_rejected"] = False
        except TenantMismatch:
            actual[dimension + "_mismatch_rejected"] = True
    expected = {"foreign_record": None, "foreign_unit": [], "foreign_attempts": [], "foreign_queue": [],
                "foreign_evidence": None, **{key: True for key in (
                    "foreign_history_rejected", "foreign_review_rejected", "foreign_route_rejected", "foreign_write_rejected", "foreign_override_rejected",
                    "unit_id_mismatch_rejected", "record_id_mismatch_rejected")}}
    return expected, actual, None


def run_case(case: EvaluationCase) -> dict:
    result = {"case_id": None, "category": "engineering_contract", "scenario": None,
              "organization_id": None, "unit_id": None, "record_id": None, "input_reference": None,
              "expected": None, "actual": None, "status": "FAIL", "system_state": "NOT_RUN",
              "evidence": [], "uncertainty": [], "failure_reason": None}
    try:
        if not isinstance(case, EvaluationCase):
            raise ValidationError("unsupported internal evaluation case")
        identifier(case.case_id, "case_id")
        result["case_id"] = case.case_id
        if case.kind not in ("safe_review", *CONTROL_KINDS):
            raise ValidationError("unsupported internal evaluation kind")
        result["scenario"] = case.kind
        if isinstance(case.context, TenantContext):
            result["organization_id"] = case.context.organization_id
        if type(case.row) is dict and case.row.get("org_id") == result["organization_id"]:
            for key in ("unit_id", "record_id"):
                try:
                    result[key] = identifier(case.row.get(key), key)
                except ValidationError:
                    pass
        capture = parse_record(case.row, case.context, case.source)
        result.update({"case_id": case.case_id, "scenario": case.kind, "organization_id": case.context.organization_id,
                       "unit_id": capture.unit.unit_id, "record_id": capture.record_id,
                       "input_reference": asdict(case.source), "evidence": [asdict(i) for i in capture.images],
                       "probe_notice": "Unmodified synthetic repository row" if case.kind == "safe_review" else
                           "Controlled engineering mutation/fault derived from this row; not visual evidence or benchmark labels",
                       "expectation_basis": ["README.md: UNCERTAIN/fail-open", "RULES.md: isolation and evidence integrity",
                                             "data/README.md: synthetic placeholders", "participant internal Phase 1-3 validation/review contract"]})
        with Store(":memory:", case.context) as store:
            workflow = ReviewWorkflow(store)
            if case.kind in CONTROL_KINDS[:4]:
                expected, actual, view = _rejection_case(case, store)
                result["system_state"] = "REJECTED" if actual["rejections"] == ["ValidationError"] * 2 else "UNEXPECTED_ACCEPTANCE"
            elif case.kind == "persistence_failure":
                expected, actual, view = _persistence_case(case, store, workflow)
            elif case.kind == "tenant_isolation":
                expected, actual, view = _isolation_case(case, store, workflow)
                result["system_state"] = "ISOLATION_CHECK"
            else:
                expected, actual, view = _review_case(case, store, workflow)
            mismatches = compare(expected, actual)
            result.update({"expected": expected, "actual": actual, "status": "FAIL" if mismatches else "PASS",
                           "failure_reason": mismatches or None})
            if view is not None:
                result["review"] = view
                result["evidence"] = view["evidence"]
                result["uncertainty"] = view["uncertainty"]
                result["system_state"] = "UNCERTAIN/REVIEW" if view["business_status"] == "pending_review" else view["business_status"]
    except Exception as exc:
        # One broken case must not abort the remainder. Keep exception class only;
        # do not echo potentially invalid Unicode, foreign data or provider text.
        result.update({"status": "FAIL", "failure_reason": {"exception_type": type(exc).__name__}})
    return result


def summarize(cases):
    counts = Counter(case["status"] for case in cases)
    baseline = [case for case in cases if case["scenario"] == "safe_review"]
    observed = [case for case in baseline if "review" in case]
    reasons = Counter((r["code"], r["dimension"]) for case in observed for r in case["uncertainty"])
    metrics = {"sample_cases_with_outputs": len(observed), "sample_case_denominator": len(baseline),
               "sample_uncertain_review_count": sum(c["system_state"] == "UNCERTAIN/REVIEW" for c in observed),
               "sample_verdict_distributions": {dimension: dict(sorted(Counter(
                   case["review"]["automated_assessment"][dimension]["verdict"] for case in observed).items()))
                   for dimension in ("identity", "completeness", "condition")},
               "sample_disposition_distribution": dict(sorted(Counter(
                   case["review"]["automated_assessment"]["disposition"]["decision"] for case in observed).items())),
               "sample_review_reason_distribution": [{"code": code, "dimension": dimension, "count": count}
                                                       for (code, dimension), count in sorted(reasons.items())],
               "engineering_failures_by_kind": dict(sorted(Counter(c["scenario"] or "invalid_case" for c in cases
                   if c["category"] == "engineering_contract" and c["status"] == "FAIL").items())),
               "blocked_metrics": {name: {"status": "BLOCKED", "value": None,
                                          "reason": "insufficient authoritative ground truth and genuine image/reference evidence"}
                                   for name in ("identity_accuracy", "component_detection_accuracy", "condition_grade_accuracy",
                                                "physical_observation_accuracy", "disposition_accuracy", "review_precision_recall")}}
    return {"total_cases": len(cases), **{key: counts[key] for key in ("PASS", "FAIL", "BLOCKED")},
            "UNCERTAIN/REVIEW": sum(c["system_state"] == "UNCERTAIN/REVIEW" for c in cases),
            "count_notice": "UNCERTAIN/REVIEW is an observed state overlapping case PASS/FAIL, not a fourth additive status. "
                            "Engineering passes do not count as visual scenario coverage.", "metrics": metrics}


def evaluate_dataset(csv_path: Path, root: Path) -> dict:
    root, csv_path = root.resolve(), csv_path.resolve()
    if not csv_path.is_relative_to(root):
        raise ValidationError("evaluation input must be inside the repository")
    before = csv_path.read_bytes()
    records = read_csv(csv_path)
    if not records:
        raise ValidationError("evaluation requires source records")
    if len({(row["org_id"], row["record_id"]) for row, _ in records}) != len(records):
        raise ValidationError("duplicate scoped source record IDs")
    dataset = inventory(records, root, csv_path)
    records = sorted(records, key=lambda entry: (entry[0]["org_id"], entry[0]["record_id"], entry[1].row_number))
    cases, representatives = [], {}
    for row, source in records:
        context = TenantContext(row["org_id"])
        key = f"sample:{row['org_id']}:{row['record_id']}:{source.row_number}"
        cases.append(run_case(EvaluationCase(key, "safe_review", row, source, context)))
        representatives.setdefault(row["org_id"], (row, source))
    for organization, (row, source) in representatives.items():
        for kind in CONTROL_KINDS:
            other = next((org for org in representatives if org != organization), None)
            if kind == "tenant_isolation" and other is None:
                continue  # Report the unavailable coverage explicitly below.
            cases.append(run_case(EvaluationCase(f"control:{organization}:{kind}", kind, row, source,
                        TenantContext(organization), TenantContext(other) if other else None)))
    cases.extend(scenario_cases(dataset))
    integrity = before == csv_path.read_bytes()
    if not integrity:
        raise ValidationError("source dataset changed during evaluation")
    code_hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                   for path in sorted(Path(__file__).parent.glob("*.py"))}
    return {"schema_version": "internal-evaluation-1", "format_notice": "not_official_wire_contract_or_visual_benchmark",
            "source": {"path": csv_path.relative_to(root).as_posix(), "sha256": hashlib.sha256(before).hexdigest(),
                       "unchanged_after_run": integrity}, "code_sha256": code_hashes, "dataset": dataset,
            "configuration": {"real_provider": None, "client_id": None, "stores": "fresh_in_memory_per_case",
                              "timestamps": "omitted_from_evaluation_projection_only", "metrics_are_ground_truth_accuracy": False},
            "isolation_coverage": "two_existing_sample_organizations" if len(representatives) >= 2 else "BLOCKED: second tenant unavailable",
            "cases": cases, "summary": summarize(cases)}


def serialize(report):
    return json.dumps(report, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + "\n"


def main(argv=None):
    participant = Path(__file__).resolve().parents[2]
    root = participant.parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=root / "data" / "returns_sample.csv")
    parser.add_argument("--output", type=Path, help="Optional .json report under participant/evaluation; otherwise stdout")
    args = parser.parse_args(argv)
    try:
        output = args.output.resolve() if args.output else None
        if output is not None and (not output.is_relative_to(participant / "evaluation") or output.suffix != ".json"
                                   or output == args.csv.resolve()):
            raise ValidationError("report must be a .json inside participant/evaluation and cannot replace input")
        report = evaluate_dataset(args.csv, root)
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(serialize(report), encoding="utf-8", newline="\n")
            print(json.dumps(report["summary"], sort_keys=True))
        else:
            print(serialize(report), end="")
        return 1 if report["summary"]["FAIL"] else 0
    except (ValidationError, OSError, ValueError) as exc:
        print(json.dumps({"status": "FAIL", "stage": "dataset_or_output_validation", "exception_type": type(exc).__name__}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
