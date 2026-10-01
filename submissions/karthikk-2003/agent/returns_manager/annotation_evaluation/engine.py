"""Independent comparisons, explicit denominators and reproducible offline reports."""
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
import html
from pathlib import Path

from . import EVALUATOR_VERSION, SYNTHETIC_NOTICE
from .ingestion import digest
from .models import (BINARY, CONDITION, STAMP, canonical, document, fail, parse_dataset, validate_shape)
from .system import Dimension, SystemOutput, unavailable

DIMENSIONS = ("identity", "completeness", "condition")


class Comparison(str, Enum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    HUMAN_UNCERTAIN = "HUMAN_UNCERTAIN"
    SYSTEM_UNCERTAIN = "SYSTEM_UNCERTAIN"
    BOTH_UNCERTAIN = "BOTH_UNCERTAIN"
    SYSTEM_UNAVAILABLE = "SYSTEM_UNAVAILABLE"
    NOT_COMPARABLE = "NOT_COMPARABLE"


def compare(human, system, dimension, available=True):
    validate_shape(human, CONDITION if dimension == "condition" else BINARY)
    if dimension not in DIMENSIONS:
        fail("dimension", "enum", "unknown comparison dimension")
    if not available:
        return Comparison.SYSTEM_UNAVAILABLE
    if not isinstance(system, Dimension) or system.state not in ("decisive", "uncertain", "not_comparable"):
        fail("system", "structure", "validated system dimension required")
    if human == "not_sure":
        return Comparison.BOTH_UNCERTAIN if system.state == "uncertain" else Comparison.HUMAN_UNCERTAIN
    if system.state == "uncertain":
        return Comparison.SYSTEM_UNCERTAIN
    if system.state == "not_comparable":
        return Comparison.NOT_COMPARABLE
    labels = (CONDITION if dimension == "condition" else BINARY)["enum"]
    if system.label not in labels or system.label == "not_sure":
        return Comparison.NOT_COMPARABLE
    return Comparison.MATCH if human == system.label else Comparison.MISMATCH


def rate(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def human_agreement(dataset, dimension):
    counts = Counter()
    pairs = []
    per_case = {}
    for case in dataset.cases:
        labels = {a.annotator_id: getattr(a, dimension + "_label") for a in case.annotations}
        if len(labels) != 2:
            state = "incomplete_annotation"
        else:
            left, right = (labels[a] for a in dataset.annotators)
            if left == right == "not_sure":
                state = "both_uncertain"
            elif "not_sure" in (left, right):
                state = "one_uncertain"
            else:
                state = "human_agreement" if left == right else "human_disagreement"
                pairs.append((left, right))
        per_case[case.product_id] = state
        counts[state] += 1
    paired = sum(len(case.annotations) == 2 for case in dataset.cases)
    all_equal = counts["human_agreement"] + counts["both_uncertain"]
    n = len(pairs)
    decisive_equal = sum(a == b for a, b in pairs)
    kappa, reason = None, "fewer_than_two_decisive_pairs"
    if n >= 2:
        left, right = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
        expected_numerator = sum(left[k] * right[k] for k in set(left) | set(right))
        if expected_numerator == n * n:
            reason = "degenerate_marginals_expected_agreement_one"
        else:
            kappa = (decisive_equal * n - expected_numerator) / (n * n - expected_numerator)
            reason = None
    return {"states": {s: counts[s] for s in ("human_agreement", "human_disagreement", "both_uncertain",
        "one_uncertain", "incomplete_annotation")}, "cases": per_case,
        "raw_agreement_including_not_sure": rate(all_equal, paired),
        "decisive_agreement": rate(decisive_equal, n),
        "cohens_kappa": {"value": kappa, "denominator": n, "excluded_pairs": paired - n,
                         "unavailable_reason": reason, "policy": "two fixed annotators; exclude not_sure; at least two decisive pairs"}}


@dataclass(frozen=True)
class EvaluationResult:
    product_id: str
    comparisons: tuple[dict, ...]
    system_available: bool
    provider_available: bool | None
    error_code: str | None
    uncertainty: dict
    reference_limitations: tuple[str, ...]
    provenance: dict
    evaluator_version: str
    evaluated_at: str


def evaluate_case(case, output, timestamp):
    comparisons = tuple({"annotator_id": a.annotator_id,
        "human_labels": {d: getattr(a, d + "_label") for d in DIMENSIONS},
        "system_dimensions": {d: asdict(value) for d, value in output.dimensions.items()},
        "dimensions": {d: compare(getattr(a, d + "_label"), output.dimensions.get(d), d, output.available).value
                       for d in DIMENSIONS}} for a in case.annotations)
    limitations = []
    for field in ("sku", "asin", "model"):
        if getattr(case.reference, field) == "UNKNOWN":
            limitations.append(field + "_unknown")
    if not case.reference.expected_components:
        limitations.append("expected_components_empty_not_proof_of_completeness")
    elif any(c.quantity is None for c in case.reference.expected_components):
        limitations.append("component_quantities_unknown")
    if not case.reference.images:
        limitations.append("image_references_absent")
    elif any(i.sha256 is None for i in case.reference.images):
        limitations.append("image_hashes_unavailable")
    if output.provenance.get("provider_mode") == "fixture":
        limitations.append("fixture_provider_not_real_inference")
    if output.provenance.get("capture_source", {}).get("kind") == "synthetic_test_fixture":
        limitations.append("system_capture_uses_synthetic_source_adapter")
    uncertainty = {d: {"human_uncertain": sum(getattr(a, d + "_label") == "not_sure" for a in case.annotations),
                       "system_uncertain": output.available and output.dimensions[d].state == "uncertain"}
                   for d in DIMENSIONS}
    return EvaluationResult(case.product_id, comparisons, output.available, output.provider_available,
        output.error_code, uncertainty, tuple(limitations), {"reference_source": asdict(case.provenance),
        "system": output.provenance}, EVALUATOR_VERSION, timestamp)


def metrics(results):
    result = {}
    for dimension in DIMENSIONS:
        counts = Counter(c["dimensions"][dimension] for r in results for c in r.comparisons)
        count = sum(counts.values())
        eligible = counts["MATCH"] + counts["MISMATCH"]
        result[dimension] = {"total_evaluated": count, "total_comparable": eligible,
            "counts": {c.value: counts[c.value] for c in Comparison},
            "agreement_rate": rate(counts["MATCH"], eligible),
            "human_uncertainty_rate": rate(sum(r.uncertainty[dimension]["human_uncertain"] for r in results), count),
            "system_uncertainty_rate": rate(sum(r.uncertainty[dimension]["system_uncertain"] for r in results),
                                            sum(r.system_available for r in results))}
    return {"dimensions": result, "system_availability": rate(sum(r.system_available for r in results), len(results)),
        "provider_availability": rate(sum(r.provider_available is True for r in results),
                                      sum(r.provider_available is not None for r in results)),
        "provider_availability_unknown": sum(r.provider_available is None for r in results),
        "denominator_notice": "Comparison counts are independent annotation-dimension pairs (up to two per case), "
          "not independent products. System availability/uncertainty use cases. Agreement excludes all abstentions, "
          "unavailable and incompatible results; it is not overall accuracy."}


def evaluate(imported, reader=None, timestamp=None):
    dataset = parse_dataset(document(imported.dataset))
    if reader is not None and reader.tenant != dataset.tenant:
        fail("tenant", "scope", "system reader and evaluation dataset tenant must match")
    timestamp = timestamp or datetime.now(timezone.utc).isoformat()
    validate_shape(timestamp, {**STAMP, "type": "string"})
    results = [evaluate_case(case, reader.read(case) if reader else unavailable("no_system_database_selected"), timestamp)
               for case in dataset.cases]
    annotations = sum(len(c.annotations) for c in dataset.cases)
    notice = (SYNTHETIC_NOTICE if dataset.kind == "synthetic_test_fixture" or not annotations
              else "Independent Human Evaluation Annotations; not official CUBE ground truth")
    return {"evaluation_set_id": dataset.evaluation_set_id, "dataset_version": dataset.dataset_version,
        "evaluator_version": EVALUATOR_VERSION, "evaluated_at": timestamp, "kind": dataset.kind, "notice": notice,
        "tenant": asdict(dataset.tenant), "case_count": len(results), "annotation_count": annotations,
        "annotation_completeness": rate(annotations, 2 * len(results)), "annotators": list(dataset.annotators),
        "import_id": imported.import_id, "source_hashes": list(imported.sources),
        "dataset_sha256": digest(canonical(document(dataset)).encode("utf-8")),
        "evaluator_code_sha256": {p.name: digest(p.read_bytes()) for p in sorted(Path(__file__).parent.glob("*.py"))},
        "policy_notice": "Human condition labels are evaluation-only. No condition/disposition mapping. "
                         "Image references are metadata; no image files or providers are accessed by this evaluator.",
        "metrics": metrics(results), "human_agreement": {d: human_agreement(dataset, d) for d in DIMENSIONS},
        "system_disagreement_cases": [r.product_id for r in results if any(
            v == "MISMATCH" for c in r.comparisons for v in c["dimensions"].values())],
        "unavailable_cases": [r.product_id for r in results if not r.system_available],
        "cases": [asdict(r) for r in results]}


def markdown(report):
    def safe(value):
        return html.escape(str(value)).replace("`", "&#96;")
    lines = ["# Independent annotation evaluation", "", safe(report["notice"]), "",
        f"Set: {safe(report['evaluation_set_id'])}; version: {safe(report['dataset_version'])}",
        f"Evaluator: {safe(report['evaluator_version'])}; timestamp: {safe(report['evaluated_at'])}",
        f"Cases: {report['case_count']}; annotations: {report['annotation_count']}", "",
        report["metrics"]["denominator_notice"], "", report["policy_notice"], ""]
    for dimension in DIMENSIONS:
        metric = report["metrics"]["dimensions"][dimension]
        agreement = metric["agreement_rate"]
        display = "N/A" if agreement["value"] is None else f"{100 * agreement['value']:.2f}%"
        lines += [f"## {dimension.title()}", "", f"Decisive agreement: {display} "
            f"({agreement['numerator']}/{agreement['denominator']}); annotation comparisons: {metric['total_evaluated']}.",
            "Counts: " + ", ".join(f"{k}={v}" for k, v in metric["counts"].items()), "",
            "Human pair states: " + canonical(report["human_agreement"][dimension]["states"]).strip(), ""]
    lines += ["## Case trace", ""]
    for case in report["cases"]:
        lines.append(f"- {safe(case['product_id'])}: available={case['system_available']}; "
            f"error={safe(case['error_code'])}; limitations={safe(', '.join(case['reference_limitations']))}")
    lines += ["", "Full per-annotator comparisons, availability/uncertainty rates, kappa, provenance and hashes "
              "are retained in the companion JSON report.", "", f"Import SHA-256: {report['import_id']}", ""]
    return "\n".join(lines)
