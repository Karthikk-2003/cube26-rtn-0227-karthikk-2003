"""Read-only local collection audit. Supplier statements are not model/human labels."""
import argparse
from collections import Counter, defaultdict
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import warnings
import xml.etree.ElementTree as ET
import zipfile

from .domain import ValidationError

PARTICIPANT = Path(__file__).resolve().parents[2]
REPOSITORY = PARTICIPANT.parents[1]
COLLECTION_NAME = "CUBE 2026 — RTN PRODUCT COLLECTION-20260930T161737Z-1-001"
DEFAULT_SOURCE = REPOSITORY / COLLECTION_NAME
VERSION = "collection-audit-1"
CATEGORIES = ("FRONT", "BACK", "IDENTIFICATION", "ACCESSORIES", "CONDITION")
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def source_root(path=DEFAULT_SOURCE):
    path = Path(path).resolve()
    # Explicit launch-time local source. No URLs, arbitrary parent traversal or broad repository roots.
    if not path.is_dir() or path == REPOSITORY or not path.is_relative_to(REPOSITORY):
        raise ValidationError("collection must be an explicit directory inside this repository")
    return path


def source_file(root, relative):
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValidationError("relative collection path required")
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValidationError("source file outside collection or unavailable")
    return path


def paragraphs(raw):
    if len(raw) > 2_000_000:
        raise ValidationError("metadata document too large")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > 2_000_000:
                raise ValidationError("expanded metadata too large")
            xml = archive.read(info)
        if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
            raise ValidationError("XML entities are unsupported")
        tree = ET.fromstring(xml)
        return ["".join(t.text or "" for t in p.findall(".//w:t", NS)).strip() for p in tree.findall(".//w:p", NS)]
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        raise ValidationError("malformed product DOCX") from exc


def metadata(lines):
    """Parse only explicit known labels/sections. Never retain supplier name/relationship."""
    labels = {"case_id": "Case ID:", "unit_id": "Unit ID:", "order_id": "Order ID:",
        "product_name": "Product Name:", "brand": "Brand:", "model": "Exact Model:",
        "variant": "Variant / Storage / Size / Colour:", "sku": "SKU:", "asin": "ASIN:"}
    result = {}
    for key, label in labels.items():
        matches = [line[len(label):].strip() for line in lines if line.startswith(label)]
        if len(matches) != 1:
            raise ValidationError("missing or duplicate metadata field: " + key)
        result[key] = matches[0] or None
    def section(start, end, omit=()):
        try:
            a, b = lines.index(start), lines.index(end)
        except ValueError:
            raise ValidationError("unrecognized collection section") from None
        return [s for s in lines[a + 1:b] if s and not s.startswith("---") and s not in omit]
    expected = section("What normally belongs with this product?", "What are you actually providing?",
                       ("List the components/accessories you know are normally included.",))
    result["expected_component_statements"] = [s for s in expected if s != "Example:"]
    result["expected_components_status"] = "ambiguous_template_examples" if "Example:" in expected else "supplier_statement_unverified"
    result["provided_component_statements"] = section("What are you actually providing?", "Is anything missing?",
        ("List exactly what you are providing photographs of.",))
    missing = section("Is anything missing?", "If yes, what is missing?")
    result["missing_statement"] = None if missing == ["YES / NO / NOT SURE"] or not missing else missing
    result["missing_component_statements"] = section("If yes, what is missing?", "D. VISIBLE PHYSICAL CONDITION")
    condition = section("Visible condition:", "Describe only what is physically visible.")
    options = ["No visible damage", "Minor visible wear", "Visible damage", "Significant visible damage", "Not sure"]
    result["physical_condition_statements"] = [] if condition == options else condition
    result["condition_statement_status"] = "unanswered_options" if condition == options else "supplier_statement_not_grade"
    result["order_context"] = "synthetic_collection_label_not_verified_customer_order"
    result["independent_annotations"] = "not_supplied"
    return result


def image_info(raw, path):
    info = {"filename": path.name, "extension": path.suffix.lower(), "size_bytes": len(raw),
            "sha256": sha(raw), "mime_type": None, "format": None, "width": None, "height": None,
            "readable": False, "extension_mismatch": None, "error_code": None}
    try:
        from PIL import Image
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                info.update(format=image.format, mime_type=Image.MIME.get(image.format), width=image.width, height=image.height)
                if image.width * image.height > 20_000_000 or len(raw) > 10_000_000:
                    raise ValidationError("image exceeds provider boundary")
                image.verify()
            with Image.open(io.BytesIO(raw)) as image:
                image.load()
        info["readable"] = True
        info["extension_mismatch"] = info["format"] not in {".jpg": ("JPEG",), ".jpeg": ("JPEG",),
            ".png": ("PNG",), ".webp": ("WEBP",)}.get(path.suffix.lower(), ())
    except ImportError:
        info["error_code"] = "image_decoder_unavailable"
    except Exception:
        info["error_code"] = "unreadable_or_unsupported_image"
    return info


def inventory(path=DEFAULT_SOURCE):
    root = source_root(path)
    candidates = [root] + [p for p in root.iterdir() if p.is_dir()]
    folder_sets = [(p, sorted(q for q in p.iterdir() if q.is_dir() and re.fullmatch(r"\d{2} — PRODUCT \d{2}", q.name)))
                   for p in candidates]
    sets = [(p, folders) for p, folders in folder_sets if folders]
    if len(sets) != 1:
        raise ValidationError("one collection with numbered product folders required")
    parent, folders = sets[0]
    products, hashes, documents = [], defaultdict(list), []
    # Hash every source file, including readme/status, without retaining personal text.
    source_hashes, document_inventory = {}, []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        checked = source_file(root, rel)
        with checked.open("rb") as stream:
            source_hashes[rel] = hashlib.file_digest(stream, "sha256").hexdigest()
        if path.suffix.lower() == ".docx":
            state = "readable"
            try:
                if path.stat().st_size > 2_000_000:
                    raise ValidationError("metadata too large")
                paragraphs(checked.read_bytes())
            except (ValidationError, OSError):
                state = "unreadable"
            document_inventory.append({"source_path": rel, "sha256": source_hashes[rel], "status": state})
    for folder in folders:
        number = int(folder.name[:2])
        if not 1 <= number <= 50 or not folder.name.endswith(f"{number:02}"):
            raise ValidationError("product folder numbering mismatch")
        details = sorted(folder.glob("01 */PRODUCT DETAILS*.docx"))
        variants, errors = [], []
        for doc in details:
            rel = doc.relative_to(root).as_posix()
            raw = source_file(root, rel).read_bytes()
            record = {"path": rel, "sha256": sha(raw)}
            try:
                record["metadata"] = metadata(paragraphs(raw))
                variants.append(record["metadata"])
            except ValidationError:
                record["error_code"] = "invalid_product_metadata"
                errors.append("invalid_product_metadata")
            documents.append(record)
        data = variants[0] if variants and all(v == variants[0] for v in variants) else None
        if variants and data is None:
            errors.append("conflicting_metadata_documents")
        if not details:
            errors.append("missing_metadata_document")
        images = []
        for image in sorted(folder.rglob("*")):
            if not image.is_file() or image.suffix.lower() == ".docx":
                continue
            rel = image.relative_to(root).as_posix()
            raw = source_file(root, rel).read_bytes()
            category = next((c for c in CATEGORIES if c in image.parent.name), "UNCATEGORIZED")
            item = {"source_path": rel, "category": category, **image_info(raw, image)}
            hashes[item["sha256"]].append(rel)
            images.append(item)
        populated = bool(data and data["product_name"])
        products.append({"product_id": f"PRODUCT {number:02}", "number": number,
            "folder": folder.relative_to(root).as_posix(), "metadata": data,
            "metadata_documents": [{k: v for k, v in d.items() if k != "metadata"} for d in documents if d["path"].startswith(folder.relative_to(root).as_posix() + "/")],
            "metadata_status": "populated_unverified" if populated else "incomplete_or_template",
            "errors": sorted(set(errors)), "images": images,
            "missing_photo_categories": [c for c in CATEGORIES if c not in {i["category"] for i in images}],
            "photo_notice": "Condition photo may legitimately be absent; folder absence is not proof of product damage or missing parts."})
    for product in products:
        for image in product["images"]:
            image["duplicate_paths"] = hashes[image["sha256"]] if len(hashes[image["sha256"]]) > 1 else []
    all_images = [i for p in products for i in p["images"]]
    return {"schema_version": VERSION, "source_dataset": root.name, "source_sha256": sha(canonical(source_hashes).encode()),
        "source_files": source_hashes, "documents": document_inventory, "products": products,
        "summary": {"products": len(products), "missing_product_numbers": sorted(set(range(1, 51)) - {p["number"] for p in products}),
            "populated_products": sum(p["metadata_status"] == "populated_unverified" for p in products),
            "products_with_images": sum(bool(p["images"]) for p in products), "images": len(all_images),
            "unique_image_hashes": len(hashes), "duplicate_copies": len(all_images) - len(hashes),
            "unreadable_images": sum(not i["readable"] for i in all_images),
            "extension_mismatches": sum(i["extension_mismatch"] is True for i in all_images),
            "metadata_errors": sum(bool(p["errors"]) for p in products),
            "unreadable_documents": sum(d["status"] != "readable" for d in document_inventory)},
        "annotation_status": "Independent human annotations not supplied; comparison and accuracy unavailable.",
        "privacy": "Supplier names/relationships omitted. Original files hashed, never changed or copied."}


def save_inventory(report):
    directory = (PARTICIPANT / "evaluation" / "real-products").resolve()
    if not directory.is_relative_to(PARTICIPANT.resolve()):
        raise ValidationError("inventory output escaped participant directory")
    directory.mkdir(parents=True, exist_ok=True)
    raw = canonical(report).encode()
    path = directory / (sha(raw) + ".json")
    try:
        with path.open("xb") as stream:
            stream.write(raw)
    except FileExistsError:
        if path.read_bytes() != raw:
            raise ValidationError("inventory artifact conflict")
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args(argv)
    try:
        report = inventory(args.source)
        path = save_inventory(report)
        print(canonical({"inventory": str(path.relative_to(PARTICIPANT)), **report["summary"]}), end="")
        return 0
    except (ValidationError, OSError):
        print('{"error":"collection_unavailable_or_invalid"}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
