"""Explicit project-local demonstration captures; never benchmark/order truth."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid

from .domain import SourceLineage, ValidationError, TenantMismatch, DecisionReference
from .validation import FIELDS, parse_record, parse_components, validate_decision_reference
from .vision import ImageInput, ObservationScope, FixtureProvider, image_availability

PARTICIPANT = Path(__file__).resolve().parents[2]


def load_demo_case(case, paths, tenant):
    """One fixed synthetic package. No arbitrary file paths, network or observations."""
    if case != "headphones":
        raise ValidationError("unsupported demo case")
    source = PARTICIPANT / "demo" / "headphones-reference.json"
    if not source.resolve().is_relative_to(PARTICIPANT) or source.stat().st_size > 8192:
        raise ValidationError("bounded project-local demo source required")
    snapshot = source.read_bytes().decode("utf-8")
    try:
        data = json.loads(snapshot)
    except ValueError:
        raise ValidationError("invalid demo reference JSON") from None
    if (type(data) is not dict or data.get("reference_status") != "synthetic_demo"
            or data.get("label") != "DEMO / SYNTHETIC REFERENCE DATA"
            or data.get("image_reference") != "runtime/demo-images/headphones_smoke.png.png"
            or data.get("parts_list_complete") is not True):
        raise ValidationError("explicit synthetic headphones reference required")
    if (tenant.organization_id, tenant.client_id) != (data.get("organization_id"), data.get("client_id")):
        raise TenantMismatch("demo reference tenant mismatch")
    expected = local_image(PARTICIPANT / data["image_reference"])
    if tuple(Path(p).resolve() for p in paths) != (expected,):
        raise ValidationError("headphones case requires only its bound image")
    content = expected.read_bytes()
    if hashlib.sha256(content).hexdigest() != data.get("image_sha256") or image_availability(content) != "available":
        raise ValidationError("demo image missing, unreadable or changed")
    parse_components(data.get("parts_list", ""))
    return data, snapshot


def demo_reference(capture, case):
    data, snapshot = load_demo_case(case, tuple(PARTICIPANT / i.reference for i in capture.images), capture.tenant)
    reference = DecisionReference(capture.tenant, capture.record_id, capture.unit.unit_id,
        data["order_id"], data["ordered_sku"], data["ordered_asin"], parse_components(data["parts_list"]), True,
        "demo/headphones-reference.json - DEMO / SYNTHETIC REFERENCE DATA", snapshot,
        capture.operator_id, capture.captured_at, reference_status="synthetic_demo")
    validate_decision_reference(capture, reference)
    return reference


def local_image(path):
    path = Path(path).resolve()
    if not path.is_relative_to(PARTICIPANT) or path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
        raise ValidationError("demo images must be participant-local JPEG/PNG files")
    if not path.is_file() or path.stat().st_size > 10_000_000:
        raise ValidationError("demo image missing or oversized")
    return path


def prepare_demo(paths, tenant, operator, command_id, *, fixture=False, case=None):
    try:
        if str(uuid.UUID(command_id)) != command_id:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise ValidationError("canonical demo command UUID required") from None
    if not 1 <= len(paths) <= 4 or len(set(paths)) != len(paths):
        raise ValidationError("one to four distinct demo images required")
    paths = tuple(local_image(p) for p in paths)
    references = tuple(p.relative_to(PARTICIPANT).as_posix() for p in paths)
    if any(";" in ref for ref in references):
        raise ValidationError("demo reference cannot contain separator")
    row = {key: "" for key in FIELDS}
    row.update(record_id="DEMO-" + command_id, unit_id="DEMO-" + command_id,
        org_id=tenant.organization_id, operator_id=operator,
        order_id="DEMO_NOT_A_REAL_ORDER", ordered_sku="DEMO_UNKNOWN_SKU", ordered_asin="DEMO_UNKNOWN_ASIN",
        captured_at=datetime.now(timezone.utc).isoformat(), photo_refs=";".join(references))
    if case is not None:
        data, _ = load_demo_case(case, paths, tenant)
        row.update({key: data[key] for key in ("order_id", "ordered_sku", "ordered_asin", "parts_list")})
    source = SourceLineage("DEMO_in_memory_context_not_benchmark", hashlib.sha256(
        json.dumps(row, sort_keys=True).encode()).hexdigest(), 2)
    capture = parse_record(row, tenant, source)
    scope = ObservationScope.from_capture(capture)
    images = tuple(ImageInput(scope, f"DEMO-image-{i}", f"DEMO-evidence-{i}", ref,
        "returned_product", "fixture" if fixture else "genuine", None if fixture else path.read_bytes())
        for i, (path, ref) in enumerate(zip(paths, references)))
    return row, source, capture, images


def select_provider(name, capture=None):
    if name == "gemini":
        from .gemini import GeminiVisionProvider
        return GeminiVisionProvider()
    if name == "ollama":
        from .ollama import OllamaVisionProvider
        return OllamaVisionProvider()
    if name == "fixture" and capture is not None:
        from dataclasses import asdict
        return FixtureProvider(json.dumps({"scope": asdict(ObservationScope.from_capture(capture)),
            "identity": [], "components": [], "condition": [],
            "limitations": ["DEMO synthetic fixture only; no image inference or visual findings"]}))
    raise ValidationError("explicit supported provider required")
