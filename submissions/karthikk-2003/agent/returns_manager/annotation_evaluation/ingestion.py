"""Bounded local imports and immutable content-addressed artifacts; no image reads."""
import csv
from dataclasses import dataclass
import hashlib
import io
from pathlib import Path

from .models import HASH, TEXT, Dataset, canonical, document, fail, obj, parse_dataset, strict_json, validate_shape

PARTICIPANT = Path(__file__).resolve().parents[3]
MAX_BYTES = 8 * 1024 * 1024
CSV_FIELDS = ("product_id", "annotator_id", "identity_label", "completeness_label",
              "condition_label", "notes", "captured_at", "schema_version")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def scoped_path(path, root=PARTICIPANT, suffixes=(".json", ".csv")):
    root = Path(root).resolve()
    path = Path(path)
    path = (path if path.is_absolute() else root / path).resolve()
    if not path.is_relative_to(root) or path.suffix.lower() not in suffixes:
        fail("path", "scope", "path must stay inside participant with an allowed extension")
    if any(p.startswith(".") for p in path.relative_to(root).parts):
        fail("path", "scope", "hidden/configuration paths are not evaluation inputs")
    return path


def read_source(path, root=PARTICIPANT):
    path = scoped_path(path, root)
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        fail("source", "size", "evaluation source exceeds 8 MiB limit")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError:
        fail("source", "encoding", "UTF-8 source required")
    return text, {"path": path.relative_to(Path(root).resolve()).as_posix(), "sha256": digest(raw)}


@dataclass(frozen=True)
class ImportedDataset:
    dataset: Dataset
    sources: tuple[dict, ...]

    def envelope(self):
        validate_sources(self.sources)
        return {"dataset": document(self.dataset), "sources": list(self.sources)}

    @property
    def import_id(self):
        return digest(canonical(self.envelope()).encode("utf-8"))


def validate_sources(sources, root=None):
    if not isinstance(sources, (list, tuple)) or not 1 <= len(sources) <= 2:
        fail("sources", "structure", "one JSON source or CSV plus manifest required")
    for source in sources:
        validate_shape(source, obj({"path": TEXT, "sha256": {**HASH, "type": "string"}}))
        if root is not None:
            scoped_path(source["path"], root)


def load_json(path, root=PARTICIPANT):
    text, source = read_source(path, root)
    return ImportedDataset(parse_dataset(strict_json(text)), (source,))


def load_csv(path, reference_manifest, root=PARTICIPANT):
    """Thin annotation adapter. JSON manifest holds reference/scope; labels stay exact."""
    manifest = load_json(reference_manifest, root)
    data = document(manifest.dataset)
    if any(c["annotations"] for c in data["cases"]):
        fail("manifest", "annotations_present", "CSV reference manifest must have empty annotations")
    text, source = read_source(path, root)
    reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
    cases = {c["product_id"]: c for c in data["cases"]}
    try:
        if reader.fieldnames is None or sorted(reader.fieldnames) != sorted(CSV_FIELDS):
            fail("csv", "columns", "CSV must have exactly the documented columns without duplicates")
        for i, row in enumerate(reader):
            if None in row or any(v is None for v in row.values()):
                fail("csv", "columns", "wrong column count", i)
            if row["product_id"] not in cases:
                fail("product_id", "scope", "CSV product missing from reference manifest", i)
            # CSV has no null type: empty optional cells mean unavailable, not a label.
            row["captured_at"] = row["captured_at"] or None
            row["notes"] = row["notes"] or None
            cases[row["product_id"]]["annotations"].append(row)
    except csv.Error:
        fail("csv", "invalid_csv", "malformed CSV quoting/structure")
    return ImportedDataset(parse_dataset(data), (*manifest.sources, source))


def immutable_artifact(folder, raw, extension, root=PARTICIPANT):
    """No user-controlled output filename; cannot overwrite source or production DB."""
    if folder not in ("imports", "reports") or extension not in (".json", ".md"):
        fail("output", "scope", "unsupported artifact kind")
    directory = Path(root).resolve() / "evaluation" / "offline" / folder
    path = scoped_path(directory / (digest(raw) + extension), root, (extension,))
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(raw)
    except FileExistsError:
        if path.read_bytes() != raw:
            fail("output", "conflict", "existing content-addressed artifact differs")
    return path


def persist(imported, root=PARTICIPANT):
    parse_dataset(document(imported.dataset))  # Revalidate complete input before any write.
    validate_sources(imported.sources, root)
    return immutable_artifact("imports", canonical(imported.envelope()).encode("utf-8"), ".json", root)


def read_import(path, root=PARTICIPANT):
    text, _ = read_source(path, root)
    envelope = strict_json(text)
    if not isinstance(envelope, dict) or set(envelope) != {"dataset", "sources"}:
        fail("import", "structure", "import envelope required")
    sources = envelope["sources"]
    validate_sources(sources, root)
    imported = ImportedDataset(parse_dataset(envelope["dataset"]), tuple(sources))
    if Path(path).stem != imported.import_id:
        fail("import", "integrity", "import filename must match canonical content hash")
    return imported
