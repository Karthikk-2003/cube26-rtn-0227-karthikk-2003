"""Explicit one-image collection inspection. No automatic retries or fallback."""
import argparse
from functools import partial
import json
import time

from .collection import DEFAULT_SOURCE, PARTICIPANT, source_root
from .collection_pipeline import database_path, image_inputs
from .demo import select_provider
from .domain import CollectionLineage, TenantContext, ValidationError, lineage_from_dict
from .review_storage import ReviewWorkflow
from .service import inspect_capture
from .storage import Store
from .validation import parse_record
from .ui import _collection_source_argument


def inspect_one(database, tenant, source, record_id, image_index, provider_name):
    if provider_name not in {"disabled", "ollama", "gemini", "groq"}:
        raise ValidationError("explicit collection provider required")
    root = source_root(source)
    path = database_path(database)
    if not path.is_file():
        raise ValidationError("prepare the collection database first")
    with Store(path, tenant) as store:
        record = store.get(record_id)
        if record is None:
            raise ValidationError("record unavailable in configured scope")
        payload = record["capture"]
        lineage = lineage_from_dict(payload["source"])
        if not isinstance(lineage, CollectionLineage):
            raise ValidationError("collection capture required")
        snapshot = json.loads(lineage.metadata_snapshot)
        if snapshot["source_dataset"] != root.name:
            raise ValidationError("collection source identity differs")
        if type(image_index) is not int or not 0 <= image_index < len(snapshot["images"]):
            raise ValidationError("valid stored image index required")
        row = dict(payload["raw_fields"])
        capture = parse_record(row, tenant, lineage)
        # Load only the chosen snapshot entry, preserving its original evidence ID/index.
        entry = snapshot["images"][image_index]
        image = image_inputs(capture, {"images": [entry]}, root)[0]
        from dataclasses import replace
        image = replace(image, image_id=f"collection-image-{image_index}",
                        evidence_id=f"collection-evidence-{image_index}")
        provider = None if provider_name == "disabled" else select_provider(provider_name)
        if provider_name == "gemini":
            from .gemini import post_json
            provider.transport = partial(post_json, max_attempts=1)
        started = time.perf_counter()
        attempt = inspect_capture(row, lineage, store, (image,), provider)
        elapsed = time.perf_counter() - started
        review = ReviewWorkflow(store).route(record_id, capture.unit.unit_id, attempt_id=attempt)
        actual = next(a for a in store.vision_attempts(record_id) if a["attempt_id"] == attempt)
        run = actual["run"]
        return {"record_id": record_id, "unit_id": capture.unit.unit_id, "attempt_id": attempt,
                "review_id": review, "selected_provider": provider_name, "status": run["status"],
                "error_code": run["error_code"], "diagnostic": getattr(provider, "last_error", None),
                "http_status": getattr(provider, "http_status", None),
                "response_json_parsed": getattr(provider, "response_json_parsed", None),
                "observation_json_parsed": getattr(provider, "observation_json_parsed", None),
                "validation_diagnostic": getattr(provider, "validation_diagnostic", None),
                "elapsed_seconds": elapsed, "validated_observation_persisted": run["observations"] is not None,
                "notice": "One explicit attempt; no retry/fallback. Inspect the new review; previous reviews are unchanged."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organization", required=True)
    parser.add_argument("--client", default=None)
    parser.add_argument("--provider", required=True, choices=("disabled", "ollama", "gemini", "groq"))
    parser.add_argument("--record", required=True)
    parser.add_argument("--image-index", type=int, required=True)
    parser.add_argument("--collection-source", type=_collection_source_argument, default=DEFAULT_SOURCE)
    parser.add_argument("--database", default=PARTICIPANT / "runtime/real-products.sqlite3")
    args = parser.parse_args(argv)
    try:
        result = inspect_one(args.database, TenantContext(args.organization, args.client), args.collection_source,
                             args.record, args.image_index, args.provider)
    except (ValidationError, OSError):
        print('{"error":"collection_inspection_rejected"}')
        return 2
    print(json.dumps(result, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
