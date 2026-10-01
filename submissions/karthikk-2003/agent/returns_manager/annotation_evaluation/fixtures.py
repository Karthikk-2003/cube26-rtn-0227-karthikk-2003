"""SYNTHETIC TEST FIXTURE workflow. Does not read photos or construct real providers."""
from dataclasses import asdict
from pathlib import Path
import tempfile

from ..domain import SourceLineage
from ..service import ingest, inspect_capture
from ..storage import Store
from ..validation import FIELDS, parse_record
from ..vision import FixtureProvider, ImageInput, ObservationScope
from .engine import evaluate
from .ingestion import PARTICIPANT, digest, load_json, persist, scoped_path
from .models import canonical, fail
from .system import SystemReader

FIXTURE_PATH = "evaluation/annotation-fixtures/synthetic.json"


def smoke(timestamp=None, root=PARTICIPANT):
    imported = load_json(FIXTURE_PATH, root)
    if imported.dataset.kind != "synthetic_test_fixture":
        fail("fixture", "kind", "offline smoke requires explicitly synthetic data")
    scratch = scoped_path(Path(root) / "evaluation/offline/TEST-scratch.sqlite3", root, (".sqlite3",)).parent
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="TEST-evaluation-", dir=scratch) as temporary:
        database = Path(temporary) / "TEST.sqlite3"
        with Store(database, imported.dataset.tenant) as store:
            for index, case in enumerate(imported.dataset.cases):
                if case.binding is None:
                    continue
                row = {key: "" for key in FIELDS}
                row.update(record_id=case.binding.record_id, unit_id=case.binding.unit_id,
                    org_id=imported.dataset.tenant.organization_id, order_id="TEST-order-" + str(index),
                    ordered_sku="UNKNOWN", ordered_asin="UNKNOWN", operator_id="TEST-operator",
                    captured_at="2026-09-30T00:00:00Z", photo_refs="TEST-only-metadata.png")
                source = SourceLineage("SYNTHETIC TEST FIXTURE", digest(canonical(row).encode()), index + 2)
                capture = parse_record(row, imported.dataset.tenant, source)
                ingest(row, source, store)
                if case.binding.attempt_id is not None:
                    scope = ObservationScope.from_capture(capture)
                    image = ImageInput(scope, "TEST-image", "TEST-evidence", "TEST-only-metadata.png",
                                       "returned_product", "fixture")
                    payload = canonical({"scope": asdict(scope), "identity": [], "components": [], "condition": [],
                                         "limitations": ["SYNTHETIC TEST FIXTURE; no visual inference"]})
                    # Second attempt proves the existing invalid-response review path.
                    if case.binding.attempt_id == 2:
                        payload = "{"
                    attempt = inspect_capture(row, source, store, (image,), FixtureProvider(payload))
                    if attempt != case.binding.attempt_id:
                        fail("fixture", "binding", "synthetic fixture attempt order changed")
        persisted = persist(imported, root)
        with SystemReader(database, imported.dataset.tenant, root) as reader:
            first = evaluate(imported, reader, timestamp)
            second = evaluate(imported, reader, first["evaluated_at"])
        if canonical(first) != canonical(second):
            fail("report", "reproducibility", "repeated offline evaluation differed")
    return first, persisted
