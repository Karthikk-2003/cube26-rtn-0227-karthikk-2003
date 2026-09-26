"""Immutable internal types. No grades, observations or confidence are inferred."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .observations import ObservationBatch


class ValidationError(ValueError):
    """Malformed or unsupported input; caller must correct it."""


class TenantMismatch(PermissionError):
    """Input does not belong to the caller's trusted context."""


def validate_unicode_scalars(value: str) -> None:
    """Reject surrogate code points without replacing or normalizing input."""
    if not isinstance(value, str) or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise ValidationError("text containing only valid Unicode scalars required")


def identifier(value: str, name: str) -> str:
    if (not isinstance(value, str) or not value or value != value.strip()
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValidationError(f"{name}: nonempty text without edge whitespace/control characters required")
    validate_unicode_scalars(value)
    return value


class Verdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNCERTAIN = "UNCERTAIN"


class Disposition(str, Enum):
    RESTOCK = "restock"
    REFURBISH = "refurbish"
    LIQUIDATE = "liquidate"
    DISPOSE = "dispose"
    PENDING_REVIEW = "pending_review"


@dataclass(frozen=True)
class TenantContext:
    # Must come from trusted caller configuration, never from a submitted row.
    organization_id: str
    client_id: str | None = None

    def __post_init__(self):
        identifier(self.organization_id, "organization_id")
        if self.client_id is not None:
            identifier(self.client_id, "client_id")


@dataclass(frozen=True)
class Unit:
    unit_id: str

    def __post_init__(self):
        identifier(self.unit_id, "unit_id")


@dataclass(frozen=True)
class OrderContext:
    order_id: str
    ordered_sku: str
    ordered_asin: str

    def __post_init__(self):
        for name in ("order_id", "ordered_sku", "ordered_asin"):
            identifier(getattr(self, name), name)


@dataclass(frozen=True)
class Component:
    raw: str
    name: str
    quantity: int | None

    def __post_init__(self):
        identifier(self.raw, "component.raw")
        identifier(self.name, "component.name")
        if self.quantity is not None and (type(self.quantity) is not int or self.quantity <= 0):
            raise ValidationError("component.quantity: positive integer or unknown required")


@dataclass(frozen=True)
class ProductReference:
    ordered_sku: str
    ordered_asin: str
    components: tuple[Component, ...]
    # The CSV is not an authoritative catalogue, even when it lists parts.
    status: str = field(default="unverified_synthetic_reference", init=False)


@dataclass(frozen=True)
class EvidenceReference:
    reference: str
    # No loader or image-serving API exists in Phase 1. Never dereference input paths.
    status: str = field(default="unavailable", init=False)
    reason: str = field(default="synthetic_csv_placeholder_not_image_evidence", init=False)

    def __post_init__(self):
        identifier(self.reference, "photo_refs")


@dataclass(frozen=True)
class SourceLineage:
    source_name: str
    source_sha256: str
    row_number: int
    kind: str = field(default="synthetic_test_fixture", init=False)

    def __post_init__(self):
        identifier(self.source_name, "source_name")
        if (not isinstance(self.source_sha256, str) or len(self.source_sha256) != 64
                or any(c not in "0123456789abcdef" for c in self.source_sha256)):
            raise ValidationError("source_sha256: lowercase SHA-256 digest required")
        if type(self.row_number) is not int or self.row_number < 2:
            raise ValidationError("row_number: CSV data line (>=2) required")


@dataclass(frozen=True)
class Capture:
    record_id: str
    tenant: TenantContext
    unit: Unit
    order: OrderContext
    reference: ProductReference
    operator_id: str
    captured_at: str
    images: tuple[EvidenceReference, ...]
    source: SourceLineage
    # Exact CSV values (including historical labels) are lineage only.
    raw_fields: tuple[tuple[str, str], ...]
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class ObservationPlaceholder:
    reason: str = "observation_not_available"
    status: str = field(default="unavailable", init=False)

    def __post_init__(self):
        identifier(self.reason, "observation.reason")


@dataclass(frozen=True)
class IdentityResult:
    reasons: tuple[str, ...]
    verdict: Verdict = field(default=Verdict.UNCERTAIN, init=False)
    confidence: None = field(default=None, init=False)
    evidence: tuple = field(default=(), init=False)


@dataclass(frozen=True)
class CompletenessResult:
    unknown_components: tuple[str, ...]
    reasons: tuple[str, ...]
    verdict: Verdict = field(default=Verdict.UNCERTAIN, init=False)
    missing_components: tuple = field(default=(), init=False)
    confidence: None = field(default=None, init=False)
    evidence: tuple = field(default=(), init=False)


@dataclass(frozen=True)
class ConditionResult:
    reasons: tuple[str, ...]
    verdict: Verdict = field(default=Verdict.UNCERTAIN, init=False)
    grade: None = field(default=None, init=False)
    confidence: None = field(default=None, init=False)
    evidence: tuple = field(default=(), init=False)


@dataclass(frozen=True)
class DispositionResult:
    decision: Disposition
    reasons: tuple[str, ...]

    def __post_init__(self):
        try:
            object.__setattr__(self, "decision", Disposition(self.decision))
        except (ValueError, TypeError) as exc:
            raise ValidationError("unsupported disposition") from exc


@dataclass(frozen=True)
class ReviewState:
    reasons: tuple[str, ...]
    status: str = field(default="pending_review", init=False)


@dataclass(frozen=True)
class Assessment:
    identity: IdentityResult
    completeness: CompletenessResult
    condition: ConditionResult
    disposition: DispositionResult
    review: ReviewState
    observation: ObservationPlaceholder | ObservationBatch
    rule_version: str = field(default="phase1-missing-evidence-1", init=False)
    format_notice: str = field(default="internal_only_not_official_wire_contract", init=False)
