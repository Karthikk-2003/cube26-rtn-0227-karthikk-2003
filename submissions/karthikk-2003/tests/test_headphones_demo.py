"""Local-photo package integration; fixture replay only, never a live model call."""
from dataclasses import replace, asdict
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch
from wsgiref.util import setup_testing_defaults

PARTICIPANT = Path(__file__).resolve().parents[1]
PHOTO = PARTICIPANT / 'runtime/demo-images/headphones_smoke.png.png'
sys.path.insert(0, str(PARTICIPANT / 'agent'))
from returns_manager.demo import prepare_demo, demo_reference, load_demo_case, select_provider
from returns_manager.domain import TenantContext, TenantMismatch, ValidationError, Verdict
from returns_manager.vision import prepare_request
from returns_manager.observations import parse_response, ProviderResponse
from returns_manager.rules import assess
from returns_manager.ui import UIConfig, create_app


@unittest.skipUnless(PHOTO.is_file() and importlib.util.find_spec('PIL'), 'Authorized local demo photo/Pillow not installed')
class HeadphonesDemoTests(unittest.TestCase):
    def setUp(self):
        scratch = PARTICIPANT / '.test-tmp'
        scratch.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.tmp.cleanup)
        self.tenant = TenantContext('org_demo_alpha')
        self.command = str(uuid.uuid4())
        self.config = UIConfig(Path(self.tmp.name) / 'TEST.sqlite3', self.tenant, 'TEST-package-verifier',
            provider='fixture', demo_images=(PHOTO,), demo_case='headphones')
        self.app = create_app(self.config)
        # Any unintended provider network access fails this offline integration test.
        for target in ('returns_manager.gemini.build_opener', 'returns_manager.ollama.build_opener'):
            blocker = patch(target, side_effect=AssertionError('No live requests authorized'))
            self.addCleanup(blocker.stop)
            blocker.start()

    def request(self, path, body=None, app=None):
        env = {}; setup_testing_defaults(env)
        raw = json.dumps(body).encode() if body is not None else b''
        env.update(PATH_INFO=path, REQUEST_METHOD='POST' if body is not None else 'GET',
            HTTP_HOST='127.0.0.1:8000', REMOTE_ADDR='127.0.0.1', HTTP_ORIGIN='http://127.0.0.1:8000',
            HTTP_X_RETURNS_REQUEST='1', CONTENT_LENGTH=str(len(raw)), CONTENT_TYPE='application/json')
        env['wsgi.input'] = io.BytesIO(raw)
        result = {}
        def start(status, headers): result['status'] = int(status.split()[0])
        result['data'] = json.loads(b''.join((app or self.app)(env, start)))
        return result

    def prepare(self, fixture=True):
        return prepare_demo((PHOTO,), self.tenant, 'TEST-package-verifier', self.command, fixture=fixture, case='headphones')

    def test_snapshot_hash_scope_and_synthetic_order_are_preserved(self):
        row, _, capture, images = self.prepare()
        reference = demo_reference(capture, 'headphones')
        data = json.loads(reference.source_document)
        self.assertEqual(reference.reference_status, 'synthetic_demo')
        self.assertEqual(reference.source_sha256, hashlib.sha256(reference.source_document.encode()).hexdigest())
        self.assertEqual(data['image_sha256'], hashlib.sha256(PHOTO.read_bytes()).hexdigest())
        self.assertEqual(reference.verified_by, 'TEST-package-verifier')
        self.assertEqual(reference.verified_at, capture.captured_at)
        self.assertEqual(reference.record_id, row['record_id'])
        self.assertEqual(reference.unit_id, capture.unit.unit_id)
        self.assertEqual([c.name for c in reference.components], ['headphones', 'carrying case', 'USB cable', 'manual'])
        self.assertTrue(all(c.quantity == 1 for c in reference.components))
        self.assertIsNone(reference.tenant.client_id)
        self.assertIsNone(images[0].content)

    def test_fixture_reference_to_assessment_review_and_history(self):
        created = self.request('/api/demo/inspect', {'command_id': self.command})
        self.assertEqual(created['status'], 200)
        self.assertEqual(created['data']['status'], 'validated')
        url = f"/api/reviews/{created['data']['review_id']}"
        item = self.request(url)['data']; assessment = item['automated_assessment']
        self.assertEqual(item['observations']['provider_mode'], 'fixture')
        self.assertEqual(item['evidence'][0]['availability'], 'fixture_only')
        self.assertIsNone(item['evidence'][0]['sha256'])
        self.assertEqual(assessment['decision_reference']['reference_status'], 'synthetic_demo')
        self.assertEqual(item['raw_response']['provider_name'], 'fixture-json')
        self.assertIsNone(item['raw_response']['latency_ms'])
        for dimension in ('identity', 'completeness', 'condition'):
            self.assertEqual(assessment[dimension]['verdict'], 'UNCERTAIN')
        self.assertEqual(assessment['completeness']['missing_components'], [])
        self.assertEqual(len(assessment['completeness']['unknown_components']), 4)
        self.assertIsNone(assessment['condition']['grade'])
        self.assertEqual(assessment['disposition']['decision'], 'pending_review')
        self.assertIn({'code': 'synthetic_reference', 'dimension': 'identity'}, item['uncertainty'])
        for revision, status in ((1, 'in_review'), (2, 'reviewed')):
            changed = self.request(url + '/transition', {'status': status, 'reason': 'TEST synthetic workflow rehearsal',
                'command_id': 'TEST-' + status, 'expected_revision': revision})
            self.assertEqual(changed['status'], 200)
        after = self.request(url)['data']
        self.assertEqual(after['automated_assessment'], assessment)
        self.assertEqual(after['business_status'], 'pending_review')
        self.assertEqual(len(self.request(url + '/history')['data']['events']), 3)
        reopened = create_app(self.config)
        self.assertEqual(self.request(url, app=reopened)['data']['automated_assessment'], assessment)

    def test_repeated_command_reuses_case(self):
        a = self.request('/api/demo/inspect', {'command_id': self.command})['data']
        b = self.request('/api/demo/inspect', {'command_id': self.command})['data']
        self.assertEqual(a['review_id'], b['review_id'])
        self.assertTrue(b['reused'])

    def test_real_input_preparation_ready_without_calling_provider(self):
        _, _, capture, images = self.prepare(fixture=False)
        request = prepare_request(capture, images, 'real')
        self.assertEqual(request.images[0].availability, 'available')
        self.assertEqual(request.images[0].sha256, hashlib.sha256(PHOTO.read_bytes()).hexdigest())
        self.assertEqual(request.image_contents[0], PHOTO.read_bytes())
        self.assertEqual(demo_reference(capture, 'headphones').reference_status, 'synthetic_demo')

    def test_synthetic_identifiers_cannot_be_promoted_by_model_echo(self):
        _, _, capture, images = self.prepare(fixture=False)
        request = prepare_request(capture, images, 'real')
        # Adversarial synthetic JSON, not a model result or image interpretation.
        payload = {'scope': asdict(request.scope), 'identity': [{'field': 'sku', 'state': 'observed',
            'values': [capture.order.ordered_sku], 'evidence_refs': ['DEMO-evidence-0'], 'limitations': []}],
            'components': [], 'condition': [], 'limitations': []}
        batch = parse_response(capture, request.images, ProviderResponse(json.dumps(payload), 'TEST-adversarial', 'real'))
        result = assess(capture, batch, demo_reference(capture, 'headphones'))
        self.assertEqual(result.identity.verdict, Verdict.UNCERTAIN)
        self.assertIn('synthetic_reference_not_real_catalogue', result.identity.reasons)

    def test_image_hash_change_rejected_without_modifying_photo(self):
        original = Path.read_bytes
        def read(path): return b'TEST changed bytes' if path == PHOTO else original(path)
        with patch.object(Path, 'read_bytes', read), self.assertRaises(ValidationError):
            self.prepare()

    def test_case_rejects_other_paths_tenants_and_clients(self):
        for tenant in (TenantContext('org_demo_bravo'), TenantContext('org_demo_alpha', 'TEST-client')):
            with self.assertRaises(TenantMismatch): load_demo_case('headphones', (PHOTO,), tenant)
        with self.assertRaises(ValidationError): load_demo_case('unknown', (PHOTO,), self.tenant)
        with self.assertRaises(ValidationError): load_demo_case('headphones', (PHOTO.parent / 'OTHER.png',), self.tenant)

    def test_ui_context_labels_case_and_foreign_retrieval_stays_isolated(self):
        self.assertEqual(self.request('/api/context')['data']['demo_case'], 'headphones')
        result = self.request('/api/demo/inspect', {'command_id': self.command})['data']
        foreign = create_app(replace(self.config, tenant=TenantContext('org_demo_bravo'), demo_case=None))
        self.assertEqual(self.request(f"/api/reviews/{result['review_id']}", app=foreign)['status'], 404)
        self.assertEqual(self.request('/api/reviews', app=foreign)['data']['reviews'], [])

    def test_reference_status_cannot_claim_external_verification(self):
        _, _, capture, _ = self.prepare()
        with self.assertRaises(ValidationError):
            replace(demo_reference(capture, 'headphones'), reference_status='externally_verified')
