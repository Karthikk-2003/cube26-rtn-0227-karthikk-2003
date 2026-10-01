"""Evaluation-only dataclasses and strict, dependency-free JSON Schema validation."""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import json
import re
from ..domain import TenantContext, ValidationError
from . import SCHEMA_VERSION


@dataclass(frozen=True)
class Issue:
    record_index: int | None
    product_id: str | None
    field: str
    code: str
    message: str


class AnnotationError(ValidationError):
    def __init__(self, issues):
        self.issues = tuple(issues)
        super().__init__("evaluation input rejected; inspect structured issues")


def fail(field, code, message, index=None, product=None):
    raise AnnotationError((Issue(index, product, field, code, message),))


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                      separators=(",", ":")) + "\n"


def strict_json(raw):
    def pairs(entries):
        result = {}
        for key, value in entries:
            if key in result:
                fail("$", "duplicate_key", "JSON keys must be unique")
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs,
            parse_constant=lambda _: fail("$", "nonfinite", "finite JSON numbers required"))
    except (ValueError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, AnnotationError):
            raise
        fail("$", "invalid_json", "bounded valid UTF-8 JSON required")


TEXT = {"type": "string", "minLength": 1, "maxLength": 8192,
        "pattern": r"^[^\x00-\x1f\x7f-\x9f\ud800-\udfff]+$"}
ID = {**TEXT, "maxLength": 256}
NULL_TEXT = {**TEXT, "type": ["string", "null"], "minLength": 0,
             "pattern": r"^[^\x00-\x1f\x7f-\x9f\ud800-\udfff]*$"}
STAMP = {**TEXT, "type": ["string", "null"], "format": "date-time"}
HASH = {"type": ["string", "null"], "pattern": "^[0-9a-f]{64}$"}
BINARY = {"type": "string", "enum": ["yes", "no", "not_sure"]}
CONDITION = {"type": "string", "enum": ["like_new", "very_good", "good", "acceptable", "not_sure"]}


def obj(properties, optional=()):
    return {"type": "object", "properties": properties,
            "required": [k for k in properties if k not in optional], "additionalProperties": False}


def array(items, maximum=1000, minimum=0):
    return {"type": "array", "items": items, "maxItems": maximum, "minItems": minimum}


ANNOTATION = obj({"product_id": ID, "annotator_id": ID, "identity_label": BINARY,
    "completeness_label": BINARY, "condition_label": CONDITION, "notes": NULL_TEXT,
    "captured_at": STAMP, "schema_version": {"const": SCHEMA_VERSION}}, ("notes", "captured_at"))
REFERENCE = obj({"title": TEXT, "brand": NULL_TEXT, "model": TEXT, "variant": NULL_TEXT,
    "sku": TEXT, "asin": TEXT,
    "expected_components": array(obj({"name": TEXT, "quantity": {"type": ["integer", "null"], "minimum": 1}}), 200),
    "images": array(obj({"reference": TEXT, "sha256": HASH}), 20)}, ("brand", "variant"))
BINDING = obj({"record_id": ID, "unit_id": ID, "attempt_id": {"type": ["integer", "null"], "minimum": 1}})
BINDING["type"] = ["object", "null"]
CASE = obj({"product_id": ID, "reference": REFERENCE, "binding": BINDING,
    "annotations": array(ANNOTATION, 2), "provenance": obj({"source_name": TEXT, "notes": NULL_TEXT}, ("notes",))})
SCHEMA = {"$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Independent Human Evaluation Annotations (not official ground truth)",
    **obj({"schema_version": {"const": SCHEMA_VERSION}, "evaluation_set_id": ID, "dataset_version": ID,
    "kind": {"enum": ["synthetic_test_fixture", "independent_human_annotations"]},
    "tenant": obj({"organization_id": ID, "client_id": {**ID, "type": ["string", "null"]}}),
    "annotators": array(ID, 2, 2), "cases": array(CASE)})}


def validate_shape(value, schema, path="$", index=None, product=None):
    """Validate precisely the keywords used by SCHEMA; cross-field checks follow."""
    if "const" in schema and value != schema["const"]:
        fail(path, "version", "unsupported schema version", index, product)
    types = schema.get("type", [])
    types = [types] if isinstance(types, str) else types
    actual = {str: "string", dict: "object", list: "array", int: "integer", type(None): "null"}.get(type(value))
    if types and actual not in types:
        fail(path, "type", "incorrect value type", index, product)
    if "enum" in schema and value not in schema["enum"]:
        fail(path, "enum", "unsupported label; use documented exact values", index, product)
    if value is None:
        return
    if actual == "object":
        properties = schema["properties"]
        if set(value) - set(properties):
            fail(path, "unknown_field", "unexpected field", index, product)
        for name in schema["required"]:
            if name not in value:
                fail(path + "." + name, "required", "required field absent", index, product)
        for name, item in value.items():
            validate_shape(item, properties[name], path + "." + name, index, product)
    elif actual == "array":
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", 1000):
            fail(path, "length", "array size outside contract", index, product)
        for i, item in enumerate(value):
            is_case = path == "$.cases"
            pid = item.get("product_id") if is_case and isinstance(item, dict) else product
            if not isinstance(pid, str) or not re.fullmatch(r"[A-Za-z0-9_. -]{1,256}", pid):
                pid = None
            validate_shape(item, schema["items"], f"{path}[{i}]", i if is_case else index, pid)
    elif actual == "string":
        if not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 8192):
            fail(path, "length", "text length outside contract", index, product)
        if "pattern" in schema and not re.fullmatch(schema["pattern"], value):
            fail(path, "text", "invalid characters or format", index, product)
        if value and value.strip() != value:
            fail(path, "whitespace", "leading/trailing whitespace is not normalized", index, product)
        if schema.get("format") == "date-time":
            try:
                stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if "T" not in value or stamp.utcoffset() != timedelta(0):
                    raise ValueError()
            except ValueError:
                fail(path, "timestamp", "ISO-8601 UTC timestamp required", index, product)
    elif actual == "integer" and value < schema.get("minimum", value):
        fail(path, "range", "positive integer required", index, product)


@dataclass(frozen=True)
class HumanAnnotation:
    product_id: str
    annotator_id: str
    identity_label: str
    completeness_label: str
    condition_label: str
    schema_version: str
    notes: str | None = None
    captured_at: str | None = None


@dataclass(frozen=True)
class ReferenceComponent:
    name: str
    quantity: int | None


@dataclass(frozen=True)
class ImageReference:
    reference: str
    sha256: str | None


@dataclass(frozen=True)
class ReferenceProduct:
    title: str
    model: str
    sku: str
    asin: str
    expected_components: tuple[ReferenceComponent, ...]
    images: tuple[ImageReference, ...]
    brand: str | None = None
    variant: str | None = None


@dataclass(frozen=True)
class Binding:
    record_id: str
    unit_id: str
    attempt_id: int | None


@dataclass(frozen=True)
class Provenance:
    source_name: str
    notes: str | None = None


@dataclass(frozen=True)
class EvaluationCase:
    product_id: str
    reference: ReferenceProduct
    binding: Binding | None
    annotations: tuple[HumanAnnotation, ...]
    provenance: Provenance


@dataclass(frozen=True)
class Dataset:
    schema_version: str
    evaluation_set_id: str
    dataset_version: str
    kind: str
    tenant: TenantContext
    annotators: tuple[str, str]
    cases: tuple[EvaluationCase, ...]


def document(dataset):
    return strict_json(canonical(asdict(dataset)))


def parse_dataset(value):
    validate_shape(value, SCHEMA)
    if len(set(value["annotators"])) != 2:
        fail("$.annotators", "duplicate", "two distinct annotator identifiers required")
    cases, seen, bindings = [], set(), set()
    for i, case in enumerate(value["cases"]):
        pid = case["product_id"]
        def reject(field, code, message):
            fail(f"$.cases[{i}].{field}", code, message, i, pid)
        if pid in seen:
            reject("product_id", "duplicate", "duplicate product ID")
        seen.add(pid)
        ref = case["reference"]
        for field, key in (("expected_components", "name"), ("images", "reference")):
            names = [v[key].casefold() for v in ref[field]]
            if len(set(names)) != len(names):
                reject("reference." + field, "duplicate", "duplicate reference entries")
        annotations = case["annotations"]
        if len({a["annotator_id"] for a in annotations}) != len(annotations):
            reject("annotations", "duplicate", "duplicate annotator for product")
        for a in annotations:
            if a["product_id"] != pid or a["annotator_id"] not in value["annotators"]:
                reject("annotations", "scope", "annotation product/annotator binding mismatch")
        binding = Binding(**case["binding"]) if case["binding"] is not None else None
        if binding:
            if binding in bindings:
                reject("binding", "duplicate", "one system record/attempt cannot represent two products")
            bindings.add(binding)
        reference = ReferenceProduct(**{k: v for k, v in ref.items() if k not in ("images", "expected_components")},
            images=tuple(ImageReference(**v) for v in ref["images"]),
            expected_components=tuple(ReferenceComponent(**v) for v in ref["expected_components"]))
        cases.append(EvaluationCase(pid, reference, binding,
            tuple(sorted((HumanAnnotation(**a) for a in annotations), key=lambda a: a.annotator_id)),
            Provenance(**case["provenance"])))
    return Dataset(value["schema_version"], value["evaluation_set_id"], value["dataset_version"],
        value["kind"], TenantContext(**value["tenant"]), tuple(sorted(value["annotators"])),
        tuple(sorted(cases, key=lambda c: c.product_id)))
