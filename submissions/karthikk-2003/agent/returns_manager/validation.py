"""Strict synthetic CSV adapter. Source annotations never become observations."""

import csv
import hashlib
import io
import re
from datetime import datetime, timedelta
from pathlib import Path

from .domain import (
    Capture, Component, Disposition, EvidenceReference, OrderContext,
    ProductReference, SourceLineage, TenantContext, TenantMismatch, Unit,
    ValidationError, identifier, validate_unicode_scalars,
)

FIELDS = (
    "record_id", "unit_id", "org_id", "order_id", "ordered_sku", "ordered_asin",
    "identity_match", "parts_list", "parts_missing", "observed_state",
    "amazon_condition", "operator_disposition", "photo_refs", "operator_id", "captured_at",
)


def split_entries(value: str, field: str) -> tuple[str, ...]:
    if not value:
        return ()
    entries = tuple(value.split(";"))
    for entry in entries:
        identifier(entry, field)
    if len({s.casefold() for s in entries}) != len(entries):
        raise ValidationError(f"{field}: duplicate entries")
    return entries


def parse_components(value: str) -> tuple[Component, ...]:
    components = []
    for raw in split_entries(value, "parts_list"):
        match = re.fullmatch(r"(.+) x([0-9]+)", raw)
        if match:
            component = Component(raw, match[1], int(match[2]))
        elif re.search(r"\s[xX](?:\s|[+\-\d]|$)", raw) or re.search(r"\s[xX]\S*$", raw):
            raise ValidationError("parts_list: unsupported quantity syntax")
        else:
            # No guess that 'puzzle pieces' or a singular noun means quantity one.
            component = Component(raw, raw, None)
        components.append(component)
    if len({c.name.casefold() for c in components}) != len(components):
        raise ValidationError("parts_list: duplicate component names")
    return tuple(components)


def read_csv(path: Path) -> list[tuple[dict[str, str], SourceLineage]]:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
        if reader.fieldnames is None or sorted(reader.fieldnames) != sorted(FIELDS):
            raise ValidationError("CSV must have exactly the documented sample columns, without duplicates")
        records = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValidationError(f"CSV line {reader.line_num}: wrong column count")
            records.append((row, SourceLineage(path.name, digest, reader.line_num)))
        return records
    except (UnicodeError, csv.Error) as exc:
        raise ValidationError("malformed UTF-8 CSV") from exc


def parse_record(row: dict[str, str], context: TenantContext, source: SourceLineage) -> Capture:
    if not isinstance(context, TenantContext) or not isinstance(source, SourceLineage):
        raise ValidationError("trusted tenant context and source lineage required")
    # Recheck supplied context/lineage at the input boundary as well as construction.
    TenantContext(context.organization_id, context.client_id)
    SourceLineage(source.source_name, source.source_sha256, source.row_number)
    if not isinstance(row, dict) or set(row) != set(FIELDS):
        raise ValidationError("record must contain exactly the documented sample fields")
    if any(not isinstance(value, str) for value in row.values()):
        raise ValidationError("CSV values must be text")
    # Includes historical/free-text fields retained verbatim in raw_fields.
    for value in row.values():
        validate_unicode_scalars(value)
    for name in ("record_id", "unit_id", "org_id", "order_id", "ordered_sku",
                 "ordered_asin", "operator_id", "captured_at"):
        identifier(row[name], name)
    if row["org_id"] != context.organization_id:
        raise TenantMismatch("organization context mismatch")
    try:
        captured = datetime.fromisoformat(row["captured_at"].replace("Z", "+00:00"))
        if "T" not in row["captured_at"] or captured.utcoffset() != timedelta(0):
            raise ValueError("UTC timestamp required")
    except ValueError as exc:
        raise ValidationError("captured_at: ISO-8601 UTC timestamp required") from exc

    components = parse_components(row["parts_list"])
    missing = split_entries(row["parts_missing"], "parts_missing")
    if not set(missing).issubset({c.raw for c in components}):
        raise ValidationError("parts_missing: entry not in parts_list")
    if row["identity_match"] not in ("", "yes", "no", "uncertain"):
        raise ValidationError("identity_match: unsupported historical value")
    if row["observed_state"] not in ("", "factory_sealed", "opened_unused", "signs_of_use",
                                      "damaged", "empty_box", "uncertain"):
        raise ValidationError("observed_state: unsupported historical value")
    if row["operator_disposition"]:
        try:
            Disposition(row["operator_disposition"])
        except ValueError as exc:
            raise ValidationError("operator_disposition: unsupported historical value") from exc

    images = tuple(EvidenceReference(ref) for ref in split_entries(row["photo_refs"], "photo_refs"))
    blockers = ["image_evidence_unavailable", "catalogue_reference_unverified",
                "condition_policy_unavailable", "disposition_policy_unavailable"]
    if context.client_id is None:
        blockers.append("client_context_missing")
    if not components:
        blockers.append("parts_reference_missing")
    elif any(c.quantity is None for c in components):
        blockers.append("component_quantities_unverified")
    if row["amazon_condition"]:
        blockers.append("historical_condition_not_authoritative")
    return Capture(
        row["record_id"], context, Unit(row["unit_id"]),
        OrderContext(row["order_id"], row["ordered_sku"], row["ordered_asin"]),
        ProductReference(row["ordered_sku"], row["ordered_asin"], components),
        row["operator_id"], row["captured_at"], images, source,
        tuple(sorted(row.items())), tuple(blockers),
    )


def validate_capture(capture: Capture) -> None:
    """Revalidate at the persistence/rule boundary, including manually constructed types."""
    if not isinstance(capture, Capture):
        raise ValidationError("validated Capture required")
    rebuilt = parse_record(dict(capture.raw_fields), capture.tenant, capture.source)
    if rebuilt != capture:
        raise ValidationError("capture does not match validated source lineage")
