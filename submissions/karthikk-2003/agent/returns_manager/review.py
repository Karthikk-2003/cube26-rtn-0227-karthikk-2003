"""Internal deterministic review contracts. No model calls or business policy.

Human decisions are attributed assertions, never replacement visual observations.
The caller must obtain ReviewerContext from trusted operator configuration/auth.
"""

from dataclasses import dataclass

from .domain import TenantContext, ValidationError
from .observations import text, choice


STATUSES = frozenset({"pending_review", "in_review", "reviewed"})
TRANSITIONS = {
    "pending_review": {"in_review"},
    "in_review": {"in_review", "pending_review", "reviewed"},
    "reviewed": {"in_review"},
}


@dataclass(frozen=True)
class ReviewerContext:
    tenant: TenantContext
    reviewer_id: str

    def __post_init__(self):
        if not isinstance(self.tenant, TenantContext):
            raise ValidationError("trusted reviewer tenant required")
        text(self.reviewer_id)


@dataclass(frozen=True)
class HumanDecision:
    # Condition grades and disposition decisions await an authoritative policy.
    dimension: str
    verdict: str
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self):
        choice(self.dimension, {"identity", "completeness"})
        choice(self.verdict, {"PASS", "FAIL", "UNCERTAIN"})
        if type(self.evidence_refs) is not tuple or len(self.evidence_refs) > 20:
            raise ValidationError("bounded tuple of evidence IDs required")
        for reference in self.evidence_refs:
            text(reference)
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValidationError("duplicate evidence citation")
        if self.verdict != "UNCERTAIN" and not self.evidence_refs:
            raise ValidationError("decisive human assertion requires existing evidence citations")


def route_reasons(capture: dict, assessment: dict | None, run: dict | None) -> list[dict]:
    """Pure routing over persisted source data; reasons are internal codes.

    Storage obtains these inputs itself, never accepts a caller-supplied assessment.
    Free-text provider limitations are retained as data, not interpreted as policy.
    """
    reasons = set()

    def add(code, dimension="evidence"):
        reasons.add((code, dimension))

    if capture["tenant"]["client_id"] is None:
        add("missing_client_context", "context")
    # These policies/references remain unavailable in the current implementation.
    for dimension in ("condition", "disposition"):
        add("unresolved_policy", dimension)
    reference = assessment.get("decision_reference") if assessment else None
    if not reference:
        add("unverified_reference", "identity")
        add("unverified_reference", "completeness")
    elif reference.get("reference_status") == "synthetic_demo":
        add("synthetic_reference", "identity")
        add("synthetic_reference", "completeness")
    elif not reference["parts_list_complete"] or not reference["components"]:
        add("unverified_reference", "completeness")
    images = run["images"] if run else []
    supplied = {image["reference"] for image in images}
    if not capture["images"] or any(i["reference"] not in supplied for i in capture["images"]):
        add("missing_evidence")
    for image in images:
        availability = image["availability"]
        if availability == "missing":
            add("missing_evidence")
        elif availability == "unreadable":
            add("unreadable_image")
        elif availability == "decoder_unavailable":
            add("evidence_unavailable")
        elif availability == "fixture_only":
            add("fixture_only_evidence")
    if run and run["error_code"]:
        code = run["error_code"]
        add(code, "provider" if code.startswith("provider_") else "evidence")
    batch = run["observations"] if run else None
    if batch is None:
        add("observations_unavailable")
    else:
        for conflict in batch["conflicts"]:
            kind = conflict.split(":", 1)[0]
            add("conflicting_" + kind, {"component": "completeness"}.get(kind, kind))
        if not batch["identity"] or any(i["state"] != "observed" for i in batch["identity"]):
            add("ambiguous_identity", "identity")
        expected = {c["name"] for c in (reference or capture["reference"])["components"]}
        observed = {c["component"] for c in batch["components"]}
        if not expected or not expected.issubset(observed) or any(
            c["presence"] in {"unknown", "conflicting"} or c["visibility"] != "visible"
            for c in batch["components"]
        ):
            add("ambiguous_component", "completeness")
        # Visible cosmetic findings alone do not establish complete condition coverage.
        add("insufficient_condition_evidence", "condition")
        if batch["limitations"] or any(
            item["limitations"] for section in ("identity", "components", "condition")
            for item in batch[section]
        ):
            add("insufficient_image_coverage")
    if assessment is None:
        add("assessment_unavailable", "assessment")
    for dimension in ("identity", "completeness", "condition", "disposition"):
        result = assessment[dimension] if assessment else {}
        if result.get("verdict", result.get("decision")) in (None, "UNCERTAIN", "pending_review"):
            add("insufficient_evidence_for_decision", dimension)
    return [{"code": code, "dimension": dimension} for code, dimension in sorted(reasons)]
