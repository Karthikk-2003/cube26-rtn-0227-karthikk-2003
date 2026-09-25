"""Pure Phase 1 rule scaffolding: no I/O, model, grades or business-policy guesses."""

from .domain import (
    Assessment, Capture, CompletenessResult, ConditionResult, Disposition,
    DispositionResult, IdentityResult, ObservationPlaceholder, ReviewState,
    ValidationError,
)
from .validation import validate_capture


def assess(capture: Capture, observation: ObservationPlaceholder) -> Assessment:
    validate_capture(capture)
    if not isinstance(observation, ObservationPlaceholder):
        raise ValidationError("Phase 1 accepts only an unavailable observation placeholder")
    identity = IdentityResult((observation.reason, "catalogue_reference_unverified"))
    completeness = CompletenessResult(
        tuple(c.raw for c in capture.reference.components),
        (observation.reason, "parts_reference_unverified"),
    )
    condition = ConditionResult((observation.reason, "condition_policy_unavailable"))
    reasons = tuple(dict.fromkeys((*capture.blockers, observation.reason)))
    disposition = DispositionResult(Disposition.PENDING_REVIEW, reasons)
    return Assessment(identity, completeness, condition, disposition, ReviewState(reasons), observation)
