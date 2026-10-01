"""SYNTHETIC TEST FIXTURES ONLY. No human labels, images or model inference."""
import copy
import csv
from dataclasses import asdict, replace
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import closing, redirect_stdout, redirect_stderr
from unittest.mock import patch

PARTICIPANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PARTICIPANT / "agent"))
from returns_manager.annotation_evaluation import SCHEMA_VERSION
from returns_manager.annotation_evaluation.models import (AnnotationError, canonical, document, parse_dataset, strict_json)
from returns_manager.annotation_evaluation.ingestion import (CSV_FIELDS, load_csv, load_json, persist, read_import, scoped_path)
from returns_manager.annotation_evaluation.engine import Comparison, compare, evaluate, human_agreement, markdown
from returns_manager.annotation_evaluation.system import Dimension, SystemReader, adapt_assessment
from returns_manager.domain import ObservationPlaceholder, SourceLineage, TenantContext, Verdict
from returns_manager.validation import FIELDS, parse_record
from returns_manager.rules import assess
from returns_manager.storage import Store
from returns_manager.service import ingest, inspect_capture
from returns_manager.vision import FixtureProvider, ImageInput, ObservationScope
from returns_manager.annotation_evaluation.ingestion import digest


def fixture(count=1):
    """Fictional evaluation labels; never PRODUCT 01-50 or official ground truth."""
    cases = []
    for i in range(count):
        pid = f"SYNTHETIC-CASE-{i:03}"
        cases.append({"product_id": pid,
            "reference": {"title": "SYNTHETIC TEST FIXTURE", "brand": None, "model": "UNKNOWN",
                "variant": "", "sku": "UNKNOWN", "asin": "UNKNOWN", "expected_components": [], "images": []},
            "binding": None, "provenance": {"source_name": "SYNTHETIC TEST FIXTURE", "notes": None},
            "annotations": [{"product_id": pid, "annotator_id": a, "identity_label": "yes",
                "completeness_label": "not_sure", "condition_label": "not_sure", "notes": "SYNTHETIC TEST FIXTURE",
                "schema_version": SCHEMA_VERSION, "captured_at": None} for a in ("TEST-A", "TEST-B")]})
    return {"schema_version": SCHEMA_VERSION, "evaluation_set_id": "SYNTHETIC TEST FIXTURE",
        "dataset_version": "TEST-1", "kind": "synthetic_test_fixture",
        "tenant": {"organization_id": "org_demo_alpha", "client_id": None},
        "annotators": ["TEST-A", "TEST-B"], "cases": cases}


class AnnotationValidationTests(unittest.TestCase):
    def test_missing_and_duplicate_annotator_definitions(self):
        for annotators in ([], ["TEST-A"], ["TEST-A", "TEST-A"], ["TEST-A", "TEST-B", "TEST-C"]):
            data = fixture()
            data["annotators"] = annotators
            with self.assertRaises(AnnotationError):
                parse_dataset(data)

    def test_duplicate_binding_and_invalid_attempt_id(self):
        binding = {"record_id": "TEST-record", "unit_id": "TEST-unit", "attempt_id": 1}
        data = fixture(2)
        for c in data["cases"]:
            c["binding"] = binding
        with self.assertRaises(AnnotationError):
            parse_dataset(data)
        for value in (0, True, "1", -1):
            data = fixture()
            data["cases"][0]["binding"] = {**binding, "attempt_id": value}
            with self.assertRaises(AnnotationError):
                parse_dataset(data)

    def test_schema_is_machine_readable_with_explicit_taxonomy(self):
        from returns_manager.annotation_evaluation.models import SCHEMA
        schema = json.loads(canonical(SCHEMA))
        annotation = schema["properties"]["cases"]["items"]["properties"]["annotations"]["items"]
        self.assertEqual(annotation["properties"]["condition_label"]["enum"],
                         ["like_new", "very_good", "good", "acceptable", "not_sure"])
        self.assertFalse(annotation["additionalProperties"])
        self.assertNotIn("disposition", canonical(schema))

    def test_valid_utc_timestamp_and_non_ascii_text(self):
        data = fixture()
        data["cases"][0]["reference"]["title"] = "SYNTHETIC TEST FIXTURE — café"
        data["cases"][0]["annotations"][0]["captured_at"] = "2026-09-30T12:34:56Z"
        self.assertEqual(document(parse_dataset(data)), data)

    def test_unknown_and_optional_values_roundtrip(self):
        data = parse_dataset(fixture())
        self.assertEqual(document(data), fixture())
        self.assertEqual(data.cases[0].reference.sku, "UNKNOWN")
        self.assertEqual(data.cases[0].reference.asin, "UNKNOWN")
        self.assertEqual(data.cases[0].reference.model, "UNKNOWN")

    def test_empty_and_fifty_case_shapes(self):
        for n in (0, 1, 50):
            self.assertEqual(len(parse_dataset(fixture(n)).cases), n)

    def test_malformed_json_and_duplicate_keys(self):
        for raw in ("", "{", "[] garbage", '{"a":1,"a":2}', '{"a":NaN}'):
            with self.subTest(raw=raw), self.assertRaises(AnnotationError):
                strict_json(raw)

    def test_missing_fields(self):
        for field in ("product_id", "reference", "annotations", "binding", "provenance"):
            data = fixture()
            del data["cases"][0][field]
            with self.subTest(field=field), self.assertRaises(AnnotationError) as caught:
                parse_dataset(data)
            self.assertEqual(caught.exception.issues[0].record_index, 0)
            self.assertEqual(caught.exception.issues[0].code, "required")

    def test_unsupported_labels(self):
        for field in ("identity_label", "completeness_label", "condition_label"):
            for value in ("UNKNOWN", "not sure", "PASS", "RESTOCK", "Like New", "", None, 1, True):
                data = fixture()
                data["cases"][0]["annotations"][0][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(AnnotationError):
                    parse_dataset(data)

    def test_invalid_identifiers_and_controls(self):
        for value in ("", " x", "x ", "x\n", "x\x7f", "x\x85y", "x\x9by", "\ud800", 123, True, "x" * 257):
            data = fixture()
            data["cases"][0]["product_id"] = value
            with self.subTest(value=repr(value)), self.assertRaises(AnnotationError):
                parse_dataset(data)

    def test_duplicate_products_annotations_images_components(self):
        mutations = (
            lambda d: d["cases"].append(copy.deepcopy(d["cases"][0])),
            lambda d: d["cases"][0]["annotations"].__setitem__(1, d["cases"][0]["annotations"][0]),
            lambda d: d["cases"][0]["reference"].update(images=[{"reference": "TEST.png", "sha256": None}] * 2),
            lambda d: d["cases"][0]["reference"].update(expected_components=[{"name": "cable", "quantity": 1}] * 2),
        )
        for mutate in mutations:
            data = fixture()
            mutate(data)
            with self.assertRaises(AnnotationError):
                parse_dataset(data)

    def test_missing_reference_fields_and_bad_quantity(self):
        for field in ("images", "expected_components", "sku", "asin", "model"):
            data = fixture()
            del data["cases"][0]["reference"][field]
            with self.assertRaises(AnnotationError):
                parse_dataset(data)
        for qty in (0, -1, True, "1", 1.0):
            data = fixture()
            data["cases"][0]["reference"]["expected_components"] = [{"name": "TEST-part", "quantity": qty}]
            with self.assertRaises(AnnotationError):
                parse_dataset(data)

    def test_unknown_quantity_is_preserved(self):
        data = fixture()
        data["cases"][0]["reference"]["expected_components"] = [{"name": "TEST-part", "quantity": None}]
        self.assertIsNone(parse_dataset(data).cases[0].reference.expected_components[0].quantity)

    def test_annotation_scope(self):
        for field in ("product_id", "annotator_id"):
            data = fixture()
            data["cases"][0]["annotations"][0][field] = "TEST-foreign"
            with self.assertRaises(AnnotationError):
                parse_dataset(data)

    def test_missing_one_or_both_annotations_is_explicit(self):
        for n in (0, 1):
            data = fixture()
            data["cases"][0]["annotations"] = data["cases"][0]["annotations"][:n]
            self.assertEqual(len(parse_dataset(data).cases[0].annotations), n)

    def test_timestamp_and_strict_extra_fields(self):
        for stamp in ("yesterday", "2026-09-30", "2026-09-30T00:00:00+05:30"):
            data = fixture()
            data["cases"][0]["annotations"][0]["captured_at"] = stamp
            with self.assertRaises(AnnotationError):
                parse_dataset(data)
        data = fixture()
        data["cases"][0]["annotations"][0]["disposition"] = "restock"
        with self.assertRaises(AnnotationError):
            parse_dataset(data)


class FileTestCase(unittest.TestCase):
    def setUp(self):
        base = PARTICIPANT / ".test-tmp"
        base.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, content):
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path


class IngestionTests(FileTestCase):
    def test_bounded_input_and_invalid_utf8(self):
        from returns_manager.annotation_evaluation.ingestion import read_source
        path = self.root / "bad.json"
        path.write_bytes(b"\xff")
        with self.assertRaises(AnnotationError):
            read_source(path, self.root)
        path.write_bytes(b" " * 33)
        with patch("returns_manager.annotation_evaluation.ingestion.MAX_BYTES", 32), self.assertRaises(AnnotationError):
            read_source(path, self.root)

    def test_output_location_cannot_be_redirected(self):
        from returns_manager.annotation_evaluation.ingestion import immutable_artifact
        for folder in ("..", "../../agent", "imports/../.."):
            with self.assertRaises(AnnotationError):
                immutable_artifact(folder, b"TEST", ".json", self.root)
        with patch("pathlib.Path.resolve", return_value=self.root.parent):
            # Direct resolved containment checks are also exercised by outside-path test.
            with self.assertRaises(AnnotationError):
                scoped_path(self.root / "bad.py", self.root)

    def test_invalid_provenance_rejected_before_persistence(self):
        from returns_manager.annotation_evaluation.ingestion import ImportedDataset
        for source in ({"path": "test.json", "sha256": "wrong"},
                       {"path": "../foreign.json", "sha256": "a" * 64}):
            with self.assertRaises(AnnotationError):
                persist(ImportedDataset(parse_dataset(fixture()), (source,)), self.root)
        self.assertFalse((self.root / "evaluation").exists())

    def test_csv_duplicate_annotation_and_foreign_product(self):
        data = fixture()
        annotation = data["cases"][0]["annotations"][0]
        data["cases"][0]["annotations"] = []
        manifest = self.write("manifest.json", canonical(data))
        for rows in ((annotation, annotation), ({**annotation, "product_id": "TEST-foreign"},)):
            stream = io.StringIO(newline="")
            writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
            with self.assertRaises(AnnotationError):
                load_csv(self.write("labels.csv", stream.getvalue()), manifest, self.root)

    def test_csv_empty_optional_cells_and_header_only_dataset(self):
        data = fixture()
        data["cases"][0]["annotations"] = []
        manifest = self.write("manifest.json", canonical(data))
        loaded = load_csv(self.write("empty.csv", ",".join(CSV_FIELDS) + "\n"), manifest, self.root)
        self.assertEqual(len(loaded.dataset.cases[0].annotations), 0)
        # Empty file is invalid; header-only means explicitly no annotations.

    def test_csv_annotated_manifest_not_silently_merged(self):
        manifest = self.write("manifest.json", canonical(fixture()))
        with self.assertRaises(AnnotationError):
            load_csv(self.write("empty.csv", ",".join(CSV_FIELDS)), manifest, self.root)

    def test_import_twice_no_mutation_no_duplicate(self):
        path = self.write("input.json", canonical(fixture()))
        original = path.read_bytes()
        imported = load_json(path, self.root)
        first = persist(imported, self.root)
        second = persist(load_json(path, self.root), self.root)
        self.assertEqual(first, second)
        self.assertEqual(read_import(first, self.root), imported)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(len(list(first.parent.glob("*.json"))), 1)

    def test_partial_invalid_dataset_creates_nothing(self):
        data = fixture(2)
        data["cases"][1]["annotations"][0]["identity_label"] = "invalid"
        path = self.write("bad.json", canonical(data))
        with self.assertRaises(AnnotationError):
            persist(load_json(path, self.root), self.root)
        self.assertFalse((self.root / "evaluation").exists())

    def test_csv_thin_adapter(self):
        data = fixture()
        annotations = data["cases"][0]["annotations"]
        data["cases"][0]["annotations"] = []
        manifest = self.write("manifest.json", canonical(data))
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(annotations)
        path = self.write("labels.csv", stream.getvalue())
        loaded = load_csv(path, manifest, self.root)
        self.assertEqual(document(loaded.dataset), fixture())
        self.assertEqual(len(loaded.sources), 2)

    def test_invalid_csv_structure(self):
        data = fixture()
        data["cases"][0]["annotations"] = []
        manifest = self.write("manifest.json", canonical(data))
        for raw in ("", "product_id\nTEST\n", ",".join(CSV_FIELDS) + '\n"unfinished',
                    ",".join(CSV_FIELDS) + "\na,b\n"):
            path = self.write("bad.csv", raw)
            with self.subTest(raw=raw), self.assertRaises(AnnotationError):
                load_csv(path, manifest, self.root)

    def test_outside_hidden_and_bad_extension_rejected(self):
        for path in (self.root / "../outside.json", self.root / ".env.json", self.root / "data.py"):
            with self.assertRaises(AnnotationError):
                scoped_path(path, self.root)

    def test_import_tamper_rejected(self):
        path = persist(load_json(self.write("input.json", canonical(fixture())), self.root), self.root)
        envelope = json.loads(path.read_text())
        envelope["dataset"]["dataset_version"] = "TEST-tampered"
        path.write_text(canonical(envelope))
        with self.assertRaises(AnnotationError):
            read_import(path, self.root)


class ComparisonTests(unittest.TestCase):
    def test_metrics_counts_denominators_and_non_penalized_abstention(self):
        from returns_manager.annotation_evaluation.engine import evaluate_case, metrics
        from returns_manager.annotation_evaluation.system import SystemOutput, unavailable
        dataset = parse_dataset(fixture(4))
        outputs = [SystemOutput(True, True, {d: Dimension("decisive", "yes", "SYNTHETIC TEST FIXTURE")
                   for d in ("identity", "completeness", "condition")}, None, {}),
            SystemOutput(True, True, {d: Dimension("decisive", "no", "SYNTHETIC TEST FIXTURE")
                   for d in ("identity", "completeness", "condition")}, None, {}),
            SystemOutput(True, None, {d: Dimension("uncertain", None, "TEST uncertainty")
                   for d in ("identity", "completeness", "condition")}, None, {}), unavailable("TEST unavailable")]
        summary = metrics([evaluate_case(case, output, "2026-09-30T00:00:00Z") for case, output in zip(dataset.cases, outputs)])
        identity = summary["dimensions"]["identity"]
        self.assertEqual(identity["total_evaluated"], 8)
        self.assertEqual(identity["agreement_rate"], {"numerator": 2, "denominator": 4, "value": 0.5})
        self.assertEqual(identity["system_uncertainty_rate"]["denominator"], 3)
        self.assertEqual(summary["system_availability"]["value"], 0.75)
        self.assertEqual(summary["provider_availability"]["denominator"], 2)

    def test_every_comparison_category(self):
        for human, state, label, available, expected in (
            ("yes", "decisive", "yes", True, "MATCH"),
            ("no", "decisive", "no", True, "MATCH"),
            ("yes", "decisive", "no", True, "MISMATCH"),
            ("not_sure", "decisive", "yes", True, "HUMAN_UNCERTAIN"),
            ("yes", "uncertain", None, True, "SYSTEM_UNCERTAIN"),
            ("not_sure", "uncertain", None, True, "BOTH_UNCERTAIN"),
            ("yes", "decisive", "yes", False, "SYSTEM_UNAVAILABLE"),
            ("yes", "not_comparable", None, True, "NOT_COMPARABLE"),
        ):
            for dimension in ("identity", "completeness"):
                with self.subTest(expected=expected, dimension=dimension):
                    self.assertEqual(compare(human, Dimension(state, label, "TEST"), dimension, available), expected)

    def test_condition_direct_synthetic_comparison_without_policy_mapping(self):
        self.assertEqual(compare("good", Dimension("decisive", "good", "SYNTHETIC TEST FIXTURE"), "condition"), "MATCH")
        self.assertEqual(compare("good", Dimension("decisive", "acceptable", "SYNTHETIC TEST FIXTURE"), "condition"), "MISMATCH")
        self.assertEqual(compare("good", Dimension("decisive", "Used - Good", "TEST incompatible"), "condition"), "NOT_COMPARABLE")
        self.assertEqual(compare("good", Dimension("uncertain", None, "policy unresolved"), "condition"), "SYSTEM_UNCERTAIN")

    def test_unavailable_precedence_does_not_erase_human_uncertainty_rate(self):
        from returns_manager.annotation_evaluation.ingestion import ImportedDataset
        report = evaluate(ImportedDataset(parse_dataset(fixture()), ({"path": "TEST.json", "sha256": "a" * 64},)))
        metric = report["metrics"]["dimensions"]["completeness"]
        self.assertEqual(metric["counts"]["SYSTEM_UNAVAILABLE"], 2)
        self.assertEqual(metric["human_uncertainty_rate"], {"numerator": 2, "denominator": 2, "value": 1.0})
        self.assertIsNone(metric["agreement_rate"]["value"])

    def test_empty_metrics_all_rates_null(self):
        from returns_manager.annotation_evaluation.ingestion import ImportedDataset
        report = evaluate(ImportedDataset(parse_dataset(fixture(0)), ({"path": "TEST.json", "sha256": "a" * 64},)))
        self.assertEqual(report["case_count"], 0)
        self.assertIsNone(report["metrics"]["system_availability"]["value"])
        for dimension in ("identity", "completeness", "condition"):
            metric = report["metrics"]["dimensions"][dimension]
            self.assertEqual(metric["total_comparable"], 0)
            self.assertIsNone(metric["agreement_rate"]["value"])
        self.assertIn("N/A", markdown(report))

    def test_double_annotator_states_and_no_consensus(self):
        data = fixture(5)
        cases = data["cases"]
        cases[1]["annotations"][1]["identity_label"] = "no"
        for a in cases[2]["annotations"]:
            a["identity_label"] = "not_sure"
        cases[3]["annotations"] = cases[3]["annotations"][:1]
        cases[4]["annotations"][1]["identity_label"] = "not_sure"
        dataset = parse_dataset(data)
        result = human_agreement(dataset, "identity")
        self.assertEqual(set(result["states"].values()), {1})
        self.assertEqual(result["raw_agreement_including_not_sure"]["denominator"], 4)
        self.assertEqual(result["decisive_agreement"]["denominator"], 2)
        self.assertEqual(len(dataset.cases[1].annotations), 2)
        self.assertEqual(dataset.cases[1].annotations[1].identity_label, "no")

    def test_kappa_known_non_degenerate_example(self):
        data = fixture(4)
        for case, (left, right) in zip(data["cases"], (("yes", "yes"), ("yes", "no"), ("no", "no"), ("no", "yes"))):
            case["annotations"][0]["identity_label"] = left
            case["annotations"][1]["identity_label"] = right
        result = human_agreement(parse_dataset(data), "identity")
        self.assertEqual(result["cohens_kappa"]["value"], 0.0)
        self.assertEqual(result["raw_agreement_including_not_sure"]["value"], 0.5)

    def test_kappa_null_for_single_degenerate_or_uncertain_pairs(self):
        for n in (0, 1, 4):
            result = human_agreement(parse_dataset(fixture(n)), "identity")
            self.assertIsNone(result["cohens_kappa"]["value"])
        result = human_agreement(parse_dataset(fixture(4)), "condition")
        self.assertEqual(result["cohens_kappa"]["denominator"], 0)
        self.assertIsNone(result["cohens_kappa"]["value"])


class SystemSafetyChecks:
    def test_dataset_reader_tenant_mismatch_rejected_even_with_same_identifiers(self):
        with SystemReader(self.dbpath, TenantContext("org_demo_bravo"), self.root) as reader:
            with self.assertRaises(AnnotationError):
                evaluate(self.imported, reader)

    def test_raw_scope_tamper_cannot_cross_tenant(self):
        import sqlite3
        self.fixture_attempt()
        with closing(sqlite3.connect(self.dbpath)) as db, db:
            value = json.loads(db.execute("SELECT payload FROM vision_attempts").fetchone()[0])
            value["scope"]["tenant"]["organization_id"] = "org_demo_bravo"
            db.execute("UPDATE vision_attempts SET payload=?", (json.dumps(value),))
        result = self.output()
        self.assertFalse(result.available)
        self.assertNotIn("org_demo_bravo", canonical(asdict(result)))

    def test_reference_image_and_hash_mismatches_are_unavailable(self):
        self.fixture_attempt()
        for ref, sha in (("TEST-foreign.png", None), ("TEST-evaluation.png", "a" * 64)):
            data = document(self.imported.dataset)
            data["cases"][0]["reference"]["images"] = [{"reference": ref, "sha256": sha}]
            self.input.write_text(canonical(data))
            result = self.output(load_json(self.input, self.root))
            self.assertFalse(result.available)
            self.assertIn("mismatch", result.error_code)

    def test_missing_database_not_created(self):
        import sqlite3
        missing = self.root / "missing.sqlite3"
        with self.assertRaises(sqlite3.OperationalError):
            with SystemReader(missing, self.tenant, self.root):
                pass
        self.assertFalse(missing.exists())

    def test_references_are_not_dereferenced_or_promoted_into_rules(self):
        data = document(self.imported.dataset)
        data["cases"][0]["reference"]["images"] = [{"reference": "../../secret.png", "sha256": None}]
        data["cases"][0]["reference"]["expected_components"] = [{"name": "TEST-unknown", "quantity": 1}]
        self.input.write_text(canonical(data))
        with patch("pathlib.Path.open", side_effect=AssertionError("no image reads")):
            from returns_manager.annotation_evaluation.ingestion import ImportedDataset
            result = self.output(ImportedDataset(parse_dataset(data), self.imported.sources))
        self.assertFalse(result.available)
        self.assertEqual(result.error_code, "reference_image_mismatch")

    def test_fifty_cases_evaluate_without_real_data(self):
        from returns_manager.annotation_evaluation.ingestion import ImportedDataset
        imported = ImportedDataset(parse_dataset(fixture(50)), self.imported.sources)
        report = evaluate(imported, timestamp="2026-09-30T00:00:00Z")
        self.assertEqual(report["case_count"], 50)
        self.assertEqual(report["annotation_count"], 100)
        self.assertEqual(report["metrics"]["system_availability"]["denominator"], 50)
        self.assertIsNone(report["metrics"]["dimensions"]["identity"]["agreement_rate"]["value"])


class CLITests(FileTestCase):
    def cli(self, args):
        from returns_manager.annotation_evaluation.__main__ import main
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = main(args, root=self.root)
        return result, stdout.getvalue(), stderr.getvalue()

    def test_validate_import_evaluate_commands_twice(self):
        self.write("input.json", canonical(fixture()))
        code, output, error = self.cli(["validate", "input.json"])
        self.assertEqual(code, 0, error)
        self.assertFalse((self.root / "evaluation").exists())
        code, output, error = self.cli(["import", "input.json"])
        self.assertEqual(code, 0, error)
        imported = json.loads(output)["imported"]
        args = ["evaluate", imported, "--timestamp", "2026-09-30T00:00:00Z"]
        first = self.cli(args)
        second = self.cli(args)
        self.assertEqual(first, second)
        self.assertEqual(first[0], 0, first[2])
        result = json.loads(first[1])
        report = json.loads((self.root / result["reports"]["json"]).read_text())
        self.assertEqual(report["unavailable_cases"], ["SYNTHETIC-CASE-000"])
        self.assertEqual(len(list((self.root / "evaluation/offline/reports").iterdir())), 2)

    def test_actionable_failure_no_raw_input_or_debug_leak(self):
        self.write("bad.json", '{"sensitive":"TEST-secret-do-not-log",')
        code, output, error = self.cli(["validate", "bad.json"])
        self.assertEqual(code, 2)
        self.assertEqual(output, "")
        self.assertNotIn("TEST-secret-do-not-log", error)
        self.assertNotIn("Traceback", error)
        self.assertEqual(json.loads(error)["issues"][0]["code"], "invalid_json")

    def test_synthetic_cli_without_network_and_repeat_reproducibility(self):
        destination = self.root / "evaluation/annotation-fixtures"
        destination.mkdir(parents=True)
        source = PARTICIPANT / "evaluation/annotation-fixtures/synthetic.json"
        (destination / "synthetic.json").write_bytes(source.read_bytes())
        with patch("urllib.request.urlopen", side_effect=AssertionError("NO NETWORK")), \
             patch("socket.create_connection", side_effect=AssertionError("NO NETWORK")):
            first = self.cli(["synthetic", "--timestamp", "2026-09-30T00:00:00Z"])
            second = self.cli(["synthetic", "--timestamp", "2026-09-30T00:00:00Z"])
        self.assertEqual(first[0], 0, first[2])
        self.assertEqual(first, second)
        result = json.loads(first[1])
        self.assertTrue(result["repeated_evaluation_identical"])
        self.assertEqual(result["case_count"], 4)
        self.assertFalse(list((self.root / "evaluation/offline").glob("TEST-evaluation-*")))

    def test_schema_command(self):
        code, output, error = self.cli(["schema"])
        self.assertEqual(code, 0, error)
        self.assertEqual(json.loads(output)["$schema"], "https://json-schema.org/draft/2020-12/schema")


class SystemIntegrationTests(SystemSafetyChecks, FileTestCase):
    def setUp(self):
        super().setUp()
        self.tenant = TenantContext("org_demo_alpha")
        self.dbpath = self.root / "TEST.sqlite3"
        self.row = {k: "" for k in FIELDS}
        self.row.update(record_id="TEST-record", unit_id="TEST-unit", org_id="org_demo_alpha",
            order_id="TEST-order", ordered_sku="UNKNOWN", ordered_asin="UNKNOWN", operator_id="TEST-operator",
            captured_at="2026-09-30T00:00:00Z", photo_refs="TEST-evaluation.png")
        self.source = SourceLineage("SYNTHETIC TEST FIXTURE", digest(b"SYNTHETIC TEST FIXTURE"), 2)
        self.capture = parse_record(self.row, self.tenant, self.source)
        with Store(self.dbpath, self.tenant) as store:
            ingest(self.row, self.source, store)
        data = fixture()
        data["cases"][0]["binding"] = {"record_id": "TEST-record", "unit_id": "TEST-unit", "attempt_id": None}
        self.input = self.write("input.json", canonical(data))
        self.imported = load_json(self.input, self.root)

    def output(self, imported=None, tenant=None):
        with SystemReader(self.dbpath, tenant or self.tenant, self.root) as reader:
            return reader.read((imported or self.imported).dataset.cases[0])

    def fixture_attempt(self, provider=None):
        scope = ObservationScope.from_capture(self.capture)
        image = ImageInput(scope, "TEST-image", "TEST-evidence", "TEST-evaluation.png", "returned_product", "fixture")
        payload = {"scope": asdict(scope), "identity": [], "components": [], "condition": [],
                   "limitations": ["SYNTHETIC TEST FIXTURE; no inference"]}
        with Store(self.dbpath, self.tenant) as store:
            attempt = inspect_capture(self.row, self.source, store, (image,), provider or FixtureProvider(json.dumps(payload)))
        data = document(self.imported.dataset)
        data["cases"][0]["binding"]["attempt_id"] = attempt
        self.input.write_text(canonical(data))
        self.imported = load_json(self.input, self.root)
        return attempt

    def test_actual_assessment_adapter_retains_uncertainty_no_disposition(self):
        result = self.output()
        self.assertTrue(result.available)
        self.assertEqual(set(d.state for d in result.dimensions.values()), {"uncertain"})
        self.assertNotIn("disposition", result.dimensions)
        self.assertIsNone(result.provider_available)
        assessment = assess(self.capture, ObservationPlaceholder())
        for verdict, label in ((Verdict.PASS, "yes"), (Verdict.FAIL, "no")):
            test_assessment = replace(assessment, identity=replace(assessment.identity, verdict=verdict))
            self.assertEqual(adapt_assessment(test_assessment, {"kind": "SYNTHETIC TEST FIXTURE"}).dimensions["identity"].label, label)

    def test_fixture_run_lineage_is_validated(self):
        self.fixture_attempt()
        result = self.output()
        self.assertTrue(result.available, result.error_code)
        self.assertTrue(result.provider_available)
        self.assertEqual(result.provenance["provider_mode"], "fixture")
        self.assertEqual(result.provenance["images"][0]["reference"], "TEST-evaluation.png")
        self.assertIn("run_sha256", result.provenance)

    def test_unavailable_provider_is_not_mismatch(self):
        class Failure:
            name, mode = "TEST-provider", "fixture"
            def observe(self, request):
                raise TimeoutError("SYNTHETIC TEST FIXTURE")
        self.fixture_attempt(Failure())
        result = self.output()
        self.assertFalse(result.available)
        self.assertFalse(result.provider_available)
        self.assertEqual(result.error_code, "provider_timeout")

    def test_other_org_client_unit_record_and_attempt_are_inaccessible(self):
        for tenant in (TenantContext("org_demo_bravo"), TenantContext("org_demo_alpha", "TEST-foreign-client")):
            self.assertFalse(self.output(tenant=tenant).available)
        for field, value in (("record_id", "TEST-foreign"), ("unit_id", "TEST-foreign"), ("attempt_id", 999)):
            data = document(self.imported.dataset)
            data["cases"][0]["binding"][field] = value
            self.input.write_text(canonical(data))
            self.assertFalse(self.output(load_json(self.input, self.root)).available)

    def test_tampered_result_rejected_without_debug_leakage(self):
        import sqlite3
        from contextlib import closing
        with closing(sqlite3.connect(self.dbpath)) as db, db:
            payload = json.loads(db.execute("SELECT assessment FROM captures").fetchone()[0])
            payload["identity"]["verdict"] = "PASS"
            db.execute("UPDATE captures SET assessment=?", (json.dumps(payload),))
        result = self.output()
        self.assertFalse(result.available)
        self.assertEqual(result.error_code, "stored_output_invalid")
        self.assertEqual(result.provenance, {"source": "automated_assessment"})

    def test_database_open_is_readonly(self):
        import sqlite3
        original = self.dbpath.read_bytes()
        with SystemReader(self.dbpath, self.tenant, self.root) as reader:
            with self.assertRaises(sqlite3.OperationalError):
                reader.db.execute("DELETE FROM captures")
        self.assertEqual(self.dbpath.read_bytes(), original)

    def test_end_to_end_twice_sources_immutable_reports_equivalent(self):
        self.fixture_attempt()
        original = self.input.read_bytes()
        db_original = self.dbpath.read_bytes()
        outputs = []
        for _ in range(2):
            imported = read_import(persist(load_json(self.input, self.root), self.root), self.root)
            with SystemReader(self.dbpath, self.tenant, self.root) as reader:
                outputs.append(evaluate(imported, reader, "2026-09-30T00:00:00Z"))
        self.assertEqual(canonical(outputs[0]), canonical(outputs[1]))
        self.assertEqual(markdown(outputs[0]), markdown(outputs[1]))
        self.assertIn("NO REAL EVALUATION DATA LOADED", outputs[0]["notice"])
        self.assertEqual(outputs[0]["metrics"]["dimensions"]["identity"]["counts"]["SYSTEM_UNCERTAIN"], 2)
        self.assertEqual(self.input.read_bytes(), original)
        self.assertEqual(self.dbpath.read_bytes(), db_original)
        self.assertEqual(len(list((self.root / "evaluation/offline/imports").glob("*.json"))), 1)
        self.assertNotIn("api_key", canonical(outputs[0]).lower())
