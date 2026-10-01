"""Read-only adapter for existing automated assessments; never selects review overrides.

Stored capture/run/reference are revalidated and rules recomputed offline. No provider
is constructed or called. An explicit attempt is required; never choose 'latest'.
"""
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sqlite3

from ..domain import (Assessment, Component, DecisionReference, ObservationPlaceholder, TenantMismatch,
                      SourceLineage, TenantContext, ValidationError, Verdict, lineage_from_dict)
from ..observations import ImageDescriptor, ObservationScope, ProviderResponse, parse_response
from ..rules import assess
from ..validation import parse_record
from ..vision import VisionRun, validate_run
from .ingestion import MAX_BYTES, PARTICIPANT, digest, scoped_path
from .models import canonical, strict_json


@dataclass(frozen=True)
class Dimension:
    state: str  # decisive / uncertain / not_comparable
    label: str | None
    reason: str


@dataclass(frozen=True)
class SystemOutput:
    available: bool
    provider_available: bool | None
    dimensions: dict[str, Dimension]
    error_code: str | None
    provenance: dict


def unavailable(code, provenance=None):
    return SystemOutput(False, None, {}, code, provenance or {})


def adapt_assessment(assessment, provenance, provider_available=None):
    """Exact domain enum adapter. Human condition taxonomy is not application policy."""
    if not isinstance(assessment, Assessment):
        return unavailable("assessment_unavailable", provenance)
    dimensions = {}
    for name in ("identity", "completeness"):
        verdict = getattr(assessment, name).verdict
        if not isinstance(verdict, Verdict):
            raise ValidationError("actual Verdict enum required")
        dimensions[name] = (Dimension("uncertain", None, "system_uncertain") if verdict == Verdict.UNCERTAIN
                            else Dimension("decisive", "yes" if verdict == Verdict.PASS else "no", "exact_verdict_adapter"))
    condition = assessment.condition
    if condition.verdict == Verdict.UNCERTAIN or condition.grade is None:
        dimensions["condition"] = Dimension("uncertain", None, "application_condition_unresolved")
    else:
        # Future incompatible policy grades cannot silently acquire evaluation semantics.
        dimensions["condition"] = Dimension("not_comparable", None, "no_authorized_condition_taxonomy_adapter")
    return SystemOutput(True, provider_available, dimensions, None, provenance)


def _capture(payload, tenant):
    if payload["tenant"] != asdict(tenant):
        raise ValidationError("capture tenant mismatch")
    source = payload["source"]
    capture = parse_record(dict(payload["raw_fields"]), tenant,
        lineage_from_dict(source))
    if canonical(asdict(capture)) != canonical(payload):
        raise ValidationError("capture lineage mismatch")
    return capture


def _scope(value):
    return ObservationScope(TenantContext(**value["tenant"]), value["unit_id"], value["record_id"])


def _reference(value):
    if value is None:
        return None
    fields = dict(value)
    expected = fields.pop("source_sha256")
    fields["tenant"] = TenantContext(**fields["tenant"])
    fields["components"] = tuple(Component(**c) for c in fields["components"])
    reference = DecisionReference(**fields)
    if expected != reference.source_sha256:
        raise ValidationError("reference snapshot hash mismatch")
    return reference


def _run(capture, value):
    scope = _scope(value["scope"])
    images = tuple(ImageDescriptor(**{**img, "scope": _scope(img["scope"])}) for img in value["images"])
    raw = ProviderResponse(**value["raw_response"]) if value["raw_response"] is not None else None
    batch = parse_response(capture, images, raw) if raw is not None else None
    if canonical(asdict(batch) if batch is not None else None) != canonical(value["observations"]):
        raise ValidationError("stored observations differ from raw provider response")
    run = VisionRun(scope, images, value["provider_name"], value["provider_mode"],
                    value["status"], value["error_code"], raw, batch)
    validate_run(capture, run)
    if canonical(asdict(run)) != canonical(value):
        raise ValidationError("unexpected run fields")
    return run


class SystemReader:
    """Read-only SQLite snapshot, scoped by org, nullable client, record AND unit."""
    def __init__(self, path, tenant, root=PARTICIPANT):
        self.path = scoped_path(path, root, (".sqlite3", ".sqlite", ".db"))
        self.tenant = TenantContext(tenant.organization_id, tenant.client_id)
        self.db = None

    def __enter__(self):
        self.db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
        try:
            self.db.execute("PRAGMA query_only=ON")
            self.db.execute("BEGIN")
        except sqlite3.Error:
            self.db.close()
            raise
        return self

    def __exit__(self, *args):
        if self.db is not None:
            self.db.close()

    def read(self, case):
        binding = case.binding
        if binding is None:
            return unavailable("system_binding_absent")
        params = (self.tenant.organization_id, json.dumps(self.tenant.client_id), binding.record_id, binding.unit_id)
        row = self.db.execute("SELECT payload, assessment, processing_error FROM captures WHERE "
            "organization_id=? AND client_scope=? AND record_id=? AND unit_id=?", params).fetchone()
        if row is None:
            return unavailable("scoped_record_unavailable")
        provenance = {"tenant": asdict(self.tenant), "binding": asdict(binding), "source": "automated_assessment"}
        try:
            if any(isinstance(v, str) and len(v) > MAX_BYTES for v in row):
                raise ValidationError("stored payload too large")
            capture = _capture(strict_json(row[0]), self.tenant)
            provenance["capture_sha256"] = digest(row[0].encode("utf-8"))
            if capture.record_id != binding.record_id or capture.unit.unit_id != binding.unit_id:
                raise ValidationError("capture scope mismatch")
            provenance["capture_source"] = asdict(capture.source)
            for key, actual in (("sku", capture.order.ordered_sku), ("asin", capture.order.ordered_asin)):
                expected = getattr(case.reference, key)
                if expected != "UNKNOWN" and expected != actual:
                    return unavailable("reference_order_mismatch", provenance)
            captured_refs = {image.reference for image in capture.images}
            if not {image.reference for image in case.reference.images}.issubset(captured_refs):
                return unavailable("reference_image_mismatch", provenance)
            run = None
            stored = row[1]
            if binding.attempt_id is not None:
                attempt = self.db.execute("SELECT payload, assessment FROM vision_attempts WHERE "
                    "organization_id=? AND client_scope=? AND record_id=? AND unit_id=? AND attempt_id=?",
                    (*params, binding.attempt_id)).fetchone()
                if attempt is None:
                    return unavailable("scoped_attempt_unavailable", provenance)
                if any(len(v) > MAX_BYTES for v in attempt):
                    raise ValidationError("stored attempt too large")
                run = _run(capture, strict_json(attempt[0]))
                stored = attempt[1]
                provenance.update(run_sha256=digest(attempt[0].encode("utf-8")), provider_name=run.provider_name,
                    provider_mode=run.provider_mode, provider_error=run.error_code,
                    images=[asdict(image) for image in run.images])
                if run.raw_response is not None:
                    provenance["provider_metadata"] = {k: v for k, v in asdict(run.raw_response).items() if k != "text"}
                hashes = {image.reference: image.sha256 for image in run.images}
                if any(image.sha256 is not None and hashes.get(image.reference) != image.sha256
                       for image in case.reference.images):
                    return unavailable("reference_image_hash_mismatch", provenance)
            elif any(image.sha256 is not None for image in case.reference.images):
                return unavailable("image_hash_not_verifiable_without_attempt", provenance)
            if stored is None:
                return unavailable("assessment_unavailable", provenance)
            original = strict_json(stored)
            observation = (run.observations or ObservationPlaceholder(run.error_code)) if run else ObservationPlaceholder(
                original["observation"]["reason"])
            result = assess(capture, observation, _reference(original.get("decision_reference")))
            if canonical(asdict(result)) != canonical(original):
                raise ValidationError("stored assessment differs from deterministic rules")
            provenance.update(assessment_sha256=digest(stored.encode("utf-8")), rule_version=result.rule_version,
                              condition_policy_status=result.condition.policy_status)
            if run and run.status == "unavailable":
                return SystemOutput(False, False, {}, run.error_code, provenance)
            return adapt_assessment(result, provenance, run.status == "validated" if run else None)
        except (ValidationError, TenantMismatch, ValueError, TypeError, KeyError, AttributeError, RecursionError):
            # Do not leak raw DB/provider text or foreign scope through diagnostics.
            return unavailable("stored_output_invalid", {"source": "automated_assessment"})
