"""Pure Phase 1 rule scaffolding: no I/O, model, grades or business-policy guesses."""

from .domain import (
    Assessment, Capture, CompletenessResult, ConditionResult, Disposition,
    DispositionResult, IdentityResult, ObservationPlaceholder, ReviewState,
    ValidationError,
)
from .validation import validate_capture
from .observations import ObservationBatch, validate_batch


def assess(capture: Capture, observation: ObservationPlaceholder | ObservationBatch) -> Assessment:
    validate_capture(capture)
    if isinstance(observation, ObservationBatch):
        validate_batch(capture, observation)
        reason = "visual_observations_are_not_business_verdicts"
        extra = ("fixture_observations_only",) if observation.provider_mode == "fixture" else ()
        extra += tuple("conflict:" + c for c in observation.conflicts)
        extra += ("observation_limitations_present",) if observation.limitations else ()
    elif isinstance(observation, ObservationPlaceholder):
        reason, extra = observation.reason, ()
    else:
        raise ValidationError("validated observations or unavailable placeholder required")
    identity = IdentityResult((reason, "catalogue_reference_unverified"))
    completeness = CompletenessResult(
        tuple(c.raw for c in capture.reference.components),
        (reason, "parts_reference_unverified"),
    )
    condition = ConditionResult((reason, "condition_policy_unavailable"))
    blockers = capture.blockers
    if isinstance(observation, ObservationBatch) and observation.provider_mode == "real" and observation.images:
        if all(i.availability == "available" for i in observation.images):
            blockers = tuple(b for b in blockers if b != "image_evidence_unavailable")
    reasons = tuple(dict.fromkeys((*blockers, reason, *extra)))
    disposition = DispositionResult(Disposition.PENDING_REVIEW, reasons)
    return Assessment(identity, completeness, condition, disposition, ReviewState(reasons), observation)
