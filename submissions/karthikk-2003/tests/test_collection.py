"""Explicit synthetic metadata/image fixtures for collection boundary tests; no model calls."""
from contextlib import ExitStack
from dataclasses import asdict
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from xml.sax.saxutils import escape

PARTICIPANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PARTICIPANT / "agent"))
from returns_manager import collection, collection_pipeline as pipeline
from returns_manager.domain import CollectionLineage, TenantContext, ValidationError, lineage_from_dict
from returns_manager.storage import Store, ConflictError
from returns_manager.review_storage import ReviewWorkflow
from returns_manager.review import ReviewerContext
from returns_manager.ui import UIConfig, create_app


def fixture_lines(number=1, populated=True):
    return [f"Case ID: RTN-{number:03}", f"Unit ID: UNIT-{number:03}", f"Order ID: ORD-{number:03}",
        "Name: TEST-person-not-for-export", "Product Name:" + ("SYNTHETIC TEST FIXTURE" if populated else ""),
        "Brand: TEST", "Exact Model: UNKNOWN", "Variant / Storage / Size / Colour:", "SKU: UNKNOWN", "ASIN:",
        "What normally belongs with this product?", "List the components/accessories you know are normally included.",
        "Example:", "TEST-cable", "What are you actually providing?", "List exactly what you are providing photographs of.",
        "Is anything missing?", "YES / NO / NOT SURE", "If yes, what is missing?", "D. VISIBLE PHYSICAL CONDITION",
        "Visible condition:", "No visible damage", "Minor visible wear", "Visible damage", "Significant visible damage",
        "Not sure", "Describe only what is physically visible."]


class CollectionTests(unittest.TestCase):
    def setUp(self):
        base = PARTICIPANT / ".test-tmp"
        base.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "TEST-collection"
        self.source.mkdir()
        self.folder = self.source / "01 — PRODUCT 01"
        self.doc = self.folder / "01 — PRODUCT DETAILS/PRODUCT DETAILS.docx"
        self.write_doc(self.doc, fixture_lines())
        self.photo = self.folder / "02 — PHOTOS/01 — FRONT/TEST.png"
        self.photo.parent.mkdir(parents=True)
        # Deliberately synthetic 1x1 test pixel, never copied to demo/evaluation evidence.
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("optional existing Pillow decoder required for collection integration fixtures")
        image = Image.new("RGB", (1, 1), "white")
        with io.BytesIO() as output:
            image.save(output, "PNG")
            self.photo.write_bytes(output.getvalue())
        self.context = TenantContext("org_demo_alpha")
        self.database = self.root / "runtime/TEST.sqlite3"
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for module in (collection, pipeline):
            self.stack.enter_context(patch.object(module, "PARTICIPANT", self.root))
        self.stack.enter_context(patch("returns_manager.ui.PARTICIPANT", self.root))

    def write_doc(self, path, lines):
        path.parent.mkdir(parents=True, exist_ok=True)
        xml = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
        xml += ''.join('<w:p><w:r><w:t>' + escape(line) + '</w:t></w:r></w:p>' for line in lines)
        xml += '</w:body></w:document>'
        with zipfile.ZipFile(path, "w") as doc:
            doc.writestr("word/document.xml", xml)

    def prepare(self):
        return pipeline.prepare(self.source, self.database, self.context, "TEST-ingestion-operator")

    def detail(self):
        with Store(self.database, self.context) as store:
            workflow = ReviewWorkflow(store)
            item = workflow.queue()[0]
            return workflow.get(item["review_id"], item["record_id"], item["unit_id"])

    def request(self, app, path):
        status = []
        body = b"".join(app({"REQUEST_METHOD": "GET", "PATH_INFO": path, "QUERY_STRING": "",
            "HTTP_HOST": "127.0.0.1:8765", "wsgi.url_scheme": "http", "SERVER_NAME": "127.0.0.1",
            "SERVER_PORT": "8765", "REMOTE_ADDR": "127.0.0.1", "wsgi.input": io.BytesIO()}, lambda s, h: status.append(s)))
        return status[0], body

    def test_inventory_hashes_mime_dimensions_and_no_pii(self):
        report = collection.inventory(self.source)
        self.assertEqual(report["summary"]["images"], 1)
        image = report["products"][0]["images"][0]
        self.assertEqual((image["width"], image["height"], image["mime_type"]), (1, 1, "image/png"))
        self.assertEqual(image["sha256"], collection.sha(self.photo.read_bytes()))
        self.assertNotIn("TEST-person-not-for-export", collection.canonical(report))

    def test_unknown_and_blank_not_invented(self):
        data = collection.inventory(self.source)["products"][0]["metadata"]
        self.assertEqual(data["sku"], "UNKNOWN")
        self.assertIsNone(data["asin"])
        self.assertEqual(data["model"], "UNKNOWN")

    def test_capture_cannot_rebind_source_ids_or_promote_supplier_labels(self):
        from returns_manager.validation import parse_record
        report = collection.inventory(self.source)
        row, source, _ = pipeline.prepare_product(report["products"][0], report, self.context,
                                                  "TEST-operator", "2026-09-30T00:00:00Z")
        for key, value in (("record_id", "TEST-foreign"), ("unit_id", "TEST-foreign"),
                           ("order_id", "TEST-foreign"), ("photo_refs", "foreign.png"),
                           ("parts_list", "TEST-part"), ("identity_match", "yes")):
            with self.subTest(key=key), self.assertRaises(ValidationError):
                parse_record({**row, key: value}, self.context, source)

    def test_template_examples_not_confirmed_parts_or_condition(self):
        data = collection.metadata(fixture_lines())
        self.assertEqual(data["expected_components_status"], "ambiguous_template_examples")
        self.assertIsNone(data["missing_statement"])
        self.assertEqual(data["physical_condition_statements"], [])
        self.assertEqual(data["provided_component_statements"], [])

    def test_explicit_supplier_statements_retained_not_human_annotations(self):
        lines = fixture_lines()
        lines[lines.index("YES / NO / NOT SURE")] = "No"
        data = collection.metadata(lines)
        self.assertEqual(data["missing_statement"], ["No"])
        self.assertEqual(data["independent_annotations"], "not_supplied")

    def test_duplicate_images_and_mismatched_extension(self):
        duplicate = self.photo.with_suffix(".jpg")
        duplicate.write_bytes(self.photo.read_bytes())
        report = collection.inventory(self.source)
        self.assertEqual(report["summary"]["duplicate_copies"], 1)
        self.assertEqual(report["summary"]["extension_mismatches"], 1)
        self.assertTrue(all(i["duplicate_paths"] for i in report["products"][0]["images"]))

    def test_corrupt_image_safely_unavailable(self):
        self.photo.write_bytes(b"SYNTHETIC deliberately malformed image")
        report = collection.inventory(self.source)
        self.assertEqual(report["summary"]["unreadable_images"], 1)
        prepared = self.prepare()
        self.assertEqual(prepared["prepared"][0]["error_code"], "unreadable_image")

    def test_malformed_metadata_and_missing_fields_reported(self):
        for raw in (b"not a ZIP",):
            self.doc.write_bytes(raw)
            report = collection.inventory(self.source)
            self.assertEqual(report["summary"]["metadata_errors"], 1)
            with self.assertRaises(ValidationError):
                self.prepare()
        self.write_doc(self.doc, fixture_lines()[1:])
        self.assertEqual(collection.inventory(self.source)["summary"]["metadata_errors"], 1)

    def test_conflicting_metadata_documents_not_silently_selected(self):
        lines = fixture_lines()
        lines[4] = "Product Name: OTHER TEST"
        self.write_doc(self.doc.with_name("PRODUCT DETAILS(1).docx"), lines)
        self.assertIn("conflicting_metadata_documents", collection.inventory(self.source)["products"][0]["errors"])

    def test_missing_images_are_not_missing_components(self):
        self.photo.unlink()
        self.prepare()
        detail = self.detail()
        self.assertEqual(detail["automated_assessment"]["completeness"]["missing_components"], [])
        self.assertIsNone(detail["automated_assessment"]["condition"]["grade"])
        self.assertEqual(detail["automated_assessment"]["disposition"]["decision"], "pending_review")

    def test_template_only_products_skipped(self):
        self.write_doc(self.source / "02 — PRODUCT 02/01 — PRODUCT DETAILS/PRODUCT DETAILS.docx", fixture_lines(2, False))
        result = self.prepare()
        self.assertEqual(result["skipped_products"], ["PRODUCT 02"])

    def test_repeated_import_preserves_source_records_attempts_and_history(self):
        before = {p: p.read_bytes() for p in self.source.rglob("*") if p.is_file()}
        first, second = self.prepare(), self.prepare()
        self.assertEqual(first, second)
        with Store(self.database, self.context) as store:
            self.assertEqual(len(store.vision_attempts("RTN-001")), 1)
            workflow = ReviewWorkflow(store)
            self.assertEqual(len(workflow.queue()), 1)
            self.assertEqual(len(workflow.history(first["prepared"][0]["review_id"], "RTN-001", "UNIT-001")), 1)
        self.assertTrue(all(path.read_bytes() == data for path, data in before.items()))

    def test_no_network_and_real_lineage_no_fake_observations(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("NO NETWORK")):
            result = self.prepare()
        detail = self.detail()
        self.assertEqual(detail["capture"]["source"]["kind"], "real_product_collection")
        self.assertEqual(detail["capture"]["source"]["timestamp_kind"], "ingested_at_not_photographed_at")
        self.assertIsNone(detail["observations"])
        self.assertIsNone(detail["raw_response"])
        self.assertEqual(detail["evidence"][0]["availability"], "available")
        self.assertEqual(result["prepared"][0]["provider"], "offline-no-inference")
        self.assertIsNone(result["human_evaluation"]["accuracy"])

    def test_cross_tenant_records_inaccessible(self):
        self.prepare()
        for tenant in (TenantContext("org_demo_bravo"), TenantContext("org_demo_alpha", "TEST-other-client")):
            with Store(self.database, tenant) as store:
                self.assertIsNone(store.get("RTN-001"))
                self.assertEqual(ReviewWorkflow(store).queue(), [])

    def test_changed_source_reimport_conflict_preserves_original(self):
        self.prepare()
        self.write_doc(self.doc, [x.replace("Brand: TEST", "Brand: changed TEST") for x in fixture_lines()])
        with self.assertRaises(ConflictError):
            self.prepare()
        self.assertIn('"brand":"TEST"', self.detail()["capture"]["source"]["metadata_snapshot"])

    def test_image_serving_requires_hash_scope_and_local_allowlist(self):
        self.prepare()
        config = UIConfig(self.database, self.context, "TEST-reviewer", 8765, collection_source=self.source)
        app = create_app(config)
        review_id = self.detail()["review_id"]
        status, raw = self.request(app, f"/api/reviews/{review_id}/images/0")
        self.assertTrue(status.startswith("200"), raw)
        self.assertEqual(raw, self.photo.read_bytes())
        foreign = create_app(UIConfig(self.database, TenantContext("org_demo_bravo"), "TEST-reviewer", 8765, collection_source=self.source))
        self.assertTrue(self.request(foreign, f"/api/reviews/{review_id}/images/0")[0].startswith("404"))
        self.photo.write_bytes(b"changed")
        self.assertTrue(self.request(app, f"/api/reviews/{review_id}/images/0")[0].startswith("404"))

    def test_path_traversal_and_source_snapshot_tampering(self):
        with self.assertRaises(ValidationError):
            collection.source_file(self.source, "../outside.png")
        with self.assertRaises(ValidationError):
            pipeline.database_path(self.root / "outside.sqlite3")
        self.prepare()
        detail = self.detail()
        bad = dict(detail["capture"]["source"])
        bad["metadata_snapshot"] += " "
        with self.assertRaises(ValidationError):
            lineage_from_dict(bad)

    def test_collection_image_missing_index_root_and_absolute_path_rejected(self):
        self.prepare()
        app = create_app(UIConfig(self.database, self.context, "TEST-reviewer", 8765, collection_source=self.source))
        detail = self.detail()
        url = f"/api/reviews/{detail['review_id']}/images/"
        mime, raw = pipeline.serve_image(self.source, detail['capture'], detail['evidence'][0])
        self.assertEqual(mime, 'image/png')
        self.assertTrue(raw)
        self.assertTrue(self.request(app, url + '99')[0].startswith('404'))
        wrong = create_app(UIConfig(self.database, self.context, "TEST-reviewer", 8765, collection_source=self.root))
        self.assertTrue(self.request(wrong, url + '0')[0].startswith('404'))
        for path in (str(self.photo.resolve()), '../outside.png'):
            with self.subTest(path=path), self.assertRaises(ValidationError):
                collection.source_file(self.source, path)
        self.photo.unlink()
        self.assertTrue(self.request(app, url + '0')[0].startswith('404'))

    def test_review_transition_history_and_stale_revision(self):
        result = self.prepare()
        review = result["prepared"][0]["review_id"]
        with Store(self.database, self.context) as store:
            workflow = ReviewWorkflow(store)
            event = workflow.transition(review, "RTN-001", "UNIT-001", reviewer=ReviewerContext(self.context, "TEST-reviewer"),
                status="in_review", reason="SYNTHETIC TEST workflow only", expected_revision=1,
                command_id="TEST-collection-review", decisions=())
            self.assertEqual(event["revision"], 2)
            with self.assertRaises(ConflictError):
                workflow.transition(review, "RTN-001", "UNIT-001", reviewer=ReviewerContext(self.context, "TEST-reviewer"),
                    status="in_review", reason="TEST stale", expected_revision=1, command_id="TEST-other-command", decisions=())

    def test_evaluator_rehydrates_real_collection_lineage(self):
        from returns_manager.annotation_evaluation.system import SystemReader
        from returns_manager.annotation_evaluation.models import EvaluationCase, ReferenceProduct, Binding, Provenance
        result = self.prepare()
        case = EvaluationCase("TEST-product", ReferenceProduct("TEST", "UNKNOWN", "UNKNOWN", "UNKNOWN", (), ()),
            Binding("RTN-001", "UNIT-001", result["prepared"][0]["attempt_id"]), (), Provenance("SYNTHETIC TEST"))
        with SystemReader(self.database, self.context, self.root) as reader:
            output = reader.read(case)
        self.assertEqual(output.error_code, "provider_unavailable")
        self.assertEqual(output.provenance["capture_source"]["kind"], "real_product_collection")

    def test_explicit_collection_inspection_validated_persistence_and_ui_provenance(self):
        from returns_manager.collection_inspect import inspect_one
        from returns_manager.ollama import OllamaVisionProvider, OllamaConfig
        self.prepare()
        def transport(url, body, timeout):
            context = json.loads(body['messages'][1]['content'].split('\n')[0])
            batch = {'scope': context['scope'], 'identity': [], 'components': [], 'condition': [],
                     'limitations': ['SYNTHETIC TEST output; no visual findings']}
            return json.dumps({'done': True, 'model': 'TEST-model', 'message': {'role': 'assistant',
                               'content': json.dumps(batch)}}).encode()
        with patch('returns_manager.collection_inspect.select_provider', return_value=OllamaVisionProvider(OllamaConfig(), transport=transport)):
            result = inspect_one(self.database, self.context, self.source, 'RTN-001', 0, 'ollama')
        self.assertTrue(result['validated_observation_persisted'])
        app = create_app(UIConfig(self.database, self.context, 'TEST-reviewer', 8765, collection_source=self.source))
        status, raw = self.request(app, f"/api/reviews/{result['review_id']}")
        detail = json.loads(raw)
        self.assertTrue(status.startswith('200'))
        self.assertEqual(detail['provider_attempt']['provider'], 'ollama')
        self.assertEqual(detail['provider_attempt']['model'], 'TEST-model')
        self.assertTrue(detail['provider_attempt']['validated_observation_persisted'])
        self.assertIsNone(detail['automated_assessment']['condition']['grade'])
        self.assertEqual(detail['business_status'], 'pending_review')

    def test_collection_inspection_disabled_failures_and_scope(self):
        from returns_manager.collection_inspect import inspect_one
        from returns_manager.vision import ProviderUnavailable
        from unittest.mock import Mock
        self.prepare()
        with patch('returns_manager.collection_inspect.select_provider') as select:
            result = inspect_one(self.database, self.context, self.source, 'RTN-001', 0, 'disabled')
            select.assert_not_called()
            self.assertFalse(result['validated_observation_persisted'])
        for error in (TimeoutError(), ProviderUnavailable('TEST unavailable')):
            provider = Mock(name='TEST-provider')
            provider.name, provider.mode, provider.last_error = 'ollama', 'real', None
            provider.observe.side_effect = error
            with patch('returns_manager.collection_inspect.select_provider', return_value=provider):
                result = inspect_one(self.database, self.context, self.source, 'RTN-001', 0, 'ollama')
            self.assertFalse(result['validated_observation_persisted'])
            self.assertIn(result['error_code'], ('provider_timeout', 'provider_unavailable'))
        for tenant, name, index in ((TenantContext('org_demo_bravo'), 'ollama', 0),
                                   (self.context, 'unknown', 0), (self.context, 'ollama', 99)):
            with self.assertRaises(ValidationError), patch('returns_manager.collection_inspect.select_provider') as select:
                inspect_one(self.database, tenant, self.source, 'RTN-001', index, name)
            select.assert_not_called()
