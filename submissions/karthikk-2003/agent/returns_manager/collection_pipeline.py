"""Offline preparation into the existing Store/service/review pipeline; no model calls."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from .collection import DEFAULT_SOURCE, PARTICIPANT, canonical, inventory, save_inventory, sha, source_file, source_root
from .domain import CollectionLineage, TenantContext, ValidationError, identifier
from .review_storage import ReviewWorkflow
from .service import ingest, inspect_capture
from .storage import ConflictError, Store
from .validation import FIELDS, parse_record
from .vision import ImageInput, ObservationScope, ProviderUnavailable


class OfflineProvider:
    """Explicitly disabled inference. Real image preparation still runs normally."""
    name, mode = "offline-no-inference", "real"

    def observe(self, request):
        raise ProviderUnavailable("offline mode; no provider request attempted")


def database_path(path):
    path = Path(path).resolve()
    if not path.is_relative_to(PARTICIPANT / "runtime") or path.suffix != ".sqlite3":
        raise ValidationError("collection DB must be a .sqlite3 inside participant/runtime")
    return path


def prepare_product(product, report, tenant, operator, timestamp):
    data = product["metadata"]
    for key in ("case_id", "unit_id", "order_id", "product_name"):
        identifier(data[key], key)
    snapshot = canonical({**product, "source_dataset": report["source_dataset"], "collection_schema": report["schema_version"]})
    source = CollectionLineage(report["source_dataset"], sha(snapshot.encode()), product["number"] + 1, snapshot)
    row = {name: "" for name in FIELDS}
    # Missing SKU/ASIN use the contract's explicit UNKNOWN sentinel; originals stay in snapshot.
    row.update(record_id=data["case_id"], unit_id=data["unit_id"], org_id=tenant.organization_id,
        order_id=data["order_id"], ordered_sku=data["sku"] or "UNKNOWN", ordered_asin=data["asin"] or "UNKNOWN",
        operator_id=operator, captured_at=timestamp,
        photo_refs=";".join("collection/" + image["source_path"] for image in product["images"]))
    # Supplier/template parts and condition are retained in snapshot, never promoted into rules.
    capture = parse_record(row, tenant, source)
    return row, source, capture


def image_inputs(capture, product, root):
    scope = ObservationScope.from_capture(capture)
    inputs = []
    for index, image in enumerate(product["images"]):
        path = source_file(root, image["source_path"])
        raw = path.read_bytes()
        if sha(raw) != image["sha256"]:
            raise ConflictError("collection image changed since inventory")
        inputs.append(ImageInput(scope, f"collection-image-{index}", f"collection-evidence-{index}",
            "collection/" + image["source_path"], "returned_product", "genuine", raw))
    return tuple(inputs)


def prepare(source, database, tenant, operator):
    identifier(operator, "operator")
    root, database = source_root(source), database_path(database)
    report = inventory(root)
    products = [p for p in report["products"] if p["metadata_status"] == "populated_unverified" and not p["errors"]]
    if not products:
        raise ValidationError("no populated product metadata")
    timestamp = datetime.now(timezone.utc).isoformat()
    prepared = [prepare_product(p, report, tenant, operator, timestamp) for p in products]
    for key in ("record_id", "unit_id"):
        if len({row[key] for row, _, _ in prepared}) != len(prepared):
            raise ValidationError("duplicate collection capture identifiers")
    # Complete validation/hash checks before persisting any captures.
    inputs = [image_inputs(capture, product, root) for (_, _, capture), product in zip(prepared, products)]
    database.parent.mkdir(parents=True, exist_ok=True)
    outcomes = []
    with Store(database, tenant) as store:
        workflow = ReviewWorkflow(store)
        for row, source, _ in prepared:
            existing = store.get(row["record_id"])
            if existing and (existing["capture"]["source"] != asdict(source)
                             or existing["capture"]["unit"]["unit_id"] != row["unit_id"]):
                raise ConflictError("existing record differs; use a separate database for changed source")
        for (row, source, capture), product, images in zip(prepared, products, inputs):
            existing = store.get(row["record_id"])
            if existing:
                # Keep actual first ingestion provenance, not a newly invented capture time.
                row = dict(existing["capture"]["raw_fields"])
            ingest(row, source, store)
            attempts = store.vision_attempts(row["record_id"])
            if len(attempts) > 1:
                raise ConflictError("multiple attempts require explicit selection; offline importer will not choose latest")
            attempt_id = attempts[0]["attempt_id"] if attempts else inspect_capture(row, source, store, images, OfflineProvider())
            review_id = workflow.route(row["record_id"], row["unit_id"], attempt_id=attempt_id)
            actual = store.vision_attempts(row["record_id"])[0]
            outcomes.append({"product_id": product["product_id"], "record_id": row["record_id"], "unit_id": row["unit_id"],
                "attempt_id": attempt_id, "review_id": review_id, "provider": actual["run"]["provider_name"],
                "model_version": actual["run"]["raw_response"]["model_version"] if actual["run"]["raw_response"] else None,
                "status": actual["run"]["status"], "error_code": actual["run"]["error_code"],
                "assessment": actual["assessment"], "source_sha256": source.source_sha256})
    return {"schema_version": "collection-preparation-1", "tenant": asdict(tenant), "source_sha256": report["source_sha256"],
        "configuration": {"mode": "offline_only", "live_requests": 0, "automatic_fallback": False},
        "code_sha256": {name: sha((Path(__file__).parent / name).read_bytes()) for name in
            ("collection.py", "collection_pipeline.py", "domain.py", "validation.py", "vision.py", "rules.py", "service.py", "storage.py")},
        "inventory": save_inventory(report).relative_to(PARTICIPANT).as_posix(), "prepared": outcomes,
        "skipped_products": [p["product_id"] for p in report["products"] if p not in products],
        "human_evaluation": {"status": "BLOCKED", "reason": "independent human annotations and annotator identities not supplied",
                             "agreement": None, "accuracy": None},
        "notice": "Real source files; synthetic collection order labels; no AI inference attempted; all decisions pending review."}


def serve_image(root, capture, evidence):
    """Allow only snapshot-listed scoped real images; no browser filesystem paths."""
    from .domain import lineage_from_dict
    lineage = lineage_from_dict(capture["source"])
    if not isinstance(lineage, CollectionLineage) or evidence.get("availability") != "available" or evidence.get("kind") != "genuine":
        raise ValidationError("collection evidence unavailable")
    if not evidence["reference"].startswith("collection/"):
        raise ValidationError("not collection evidence")
    rel = evidence["reference"][len("collection/"):]
    snapshot = json.loads(lineage.metadata_snapshot)
    if snapshot["source_dataset"] != root.name:
        raise ValidationError("collection source name differs")
    entry = next((i for i in snapshot["images"] if i["source_path"] == rel), None)
    if entry is None or entry["sha256"] != evidence.get("sha256"):
        raise ValidationError("collection image not bound to capture")
    raw = source_file(root, rel).read_bytes()
    if sha(raw) != entry["sha256"] or entry["mime_type"] not in ("image/jpeg", "image/png"):
        raise ValidationError("changed or unsupported collection image")
    return entry["mime_type"], raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--database", type=Path, default=PARTICIPANT / "runtime/real-products.sqlite3")
    parser.add_argument("--organization", required=True)
    parser.add_argument("--client", default=None)
    parser.add_argument("--operator", required=True)
    args = parser.parse_args(argv)
    try:
        result = prepare(args.source, args.database, TenantContext(args.organization, args.client), args.operator)
        raw = canonical(result).encode()
        folder = PARTICIPANT / "evaluation/real-products"
        path = folder / (sha(raw) + ".json")
        if not path.exists():
            with path.open("xb") as stream:
                stream.write(raw)
        elif path.read_bytes() != raw:
            raise ConflictError("preparation artifact conflict")
        print(canonical({"prepared": len(result["prepared"]), "skipped": len(result["skipped_products"]),
            "report": path.relative_to(PARTICIPANT).as_posix(), "notice": result["notice"]}), end="")
        return 0
    except (ValidationError, ConflictError, OSError):
        print('{"error":"collection_preparation_rejected"}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
