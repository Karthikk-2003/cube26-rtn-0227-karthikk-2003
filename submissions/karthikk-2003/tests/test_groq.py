"""Synthetic mocked Groq transport tests; no real API keys or inference."""
import base64
from dataclasses import asdict, replace
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agent'))
from returns_manager.groq import GroqConfig, GroqVisionProvider, GroqHTTPFailure, ENDPOINT, post_json
from returns_manager.domain import SourceLineage, TenantContext, ValidationError
from returns_manager.validation import FIELDS, parse_record
from returns_manager.vision import ImageInput, ObservationScope, observe
from returns_manager.service import inspect_capture
from returns_manager.storage import Store
from returns_manager.review_storage import ReviewWorkflow


class GroqTests(unittest.TestCase):
    def setUp(self):
        self.row = dict.fromkeys(FIELDS, '')
        self.row.update(record_id='TEST-groq', unit_id='TEST-unit', org_id='org_demo_alpha',
            order_id='TEST-order', ordered_sku='UNKNOWN', ordered_asin='UNKNOWN', operator_id='TEST-operator',
            captured_at='2026-10-01T00:00:00Z', photo_refs='TEST/image.jpg')
        self.source = SourceLineage('SYNTHETIC TEST', hashlib.sha256(json.dumps(self.row).encode()).hexdigest(), 2)
        self.capture = parse_record(self.row, TenantContext('org_demo_alpha'), self.source)
        self.scope = ObservationScope.from_capture(self.capture)
        self.images = (ImageInput(self.scope, 'TEST-image', 'TEST-evidence', 'TEST/image.jpg',
            'returned_product', 'genuine', b'\xff\xd8\xffTEST synthetic; decoder mocked'),)
        self.batch = dict(scope=asdict(self.scope), identity=[], components=[], condition=[], limitations=['SYNTHETIC TEST'])
        self.transport = Mock(side_effect=lambda *args: (200, json.dumps({'model':'TEST-model', 'id':'TEST-request',
            'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':json.dumps(self.batch)}}]}).encode()))
        self.provider = GroqVisionProvider(GroqConfig('TEST_NOT_A_SECRET'), transport=self.transport)

    def run_model(self):
        with patch('returns_manager.vision.image_availability', return_value='available'):
            return observe(self.capture, self.images, self.provider)

    def test_data_uri_provenance_and_single_call(self):
        run = self.run_model()
        self.assertEqual(run.status, 'validated')
        self.transport.assert_called_once()
        url, payload, timeout, key = self.transport.call_args.args
        self.assertEqual(url, ENDPOINT)
        uri = payload['messages'][1]['content'][1]['image_url']['url']
        self.assertTrue(uri.startswith('data:image/jpeg;base64,'))
        self.assertEqual(base64.b64decode(uri.split(',')[1]), self.images[0].content)
        self.assertNotIn(key, json.dumps(payload))
        self.assertEqual(run.raw_response.model_version, 'TEST-model')
        self.assertEqual(run.raw_response.request_id, 'TEST-request')
        self.assertEqual(run.images[0].sha256, hashlib.sha256(self.images[0].content).hexdigest())

    def test_missing_key_and_invalid_config(self):
        self.provider = GroqVisionProvider(GroqConfig(), transport=self.transport)
        self.assertEqual(self.run_model().error_code, 'provider_unavailable')
        self.transport.assert_not_called()
        self.assertNotIn('TEST_NOT_A_SECRET', repr(GroqConfig('TEST_NOT_A_SECRET')))
        for changes in ({'api_key':'TEST\nHEADER'}, {'timeout_seconds':10**1000}):
            with self.assertRaises(ValidationError): GroqConfig(**changes)

    def test_transport_identifies_application_and_keeps_key_out_of_output(self):
        from contextlib import redirect_stdout, redirect_stderr
        from returns_manager.groq import USER_AGENT
        opener = Mock()
        # Explicit context manager mock; no actual network or credential.
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value = response
        response.status, response.read.return_value = 200, b'{}'
        opener.open.return_value = response
        out, err = io.StringIO(), io.StringIO()
        with patch('returns_manager.groq.build_opener', return_value=opener), redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(post_json(ENDPOINT, {'TEST':'payload'}, 30, 'TEST_NOT_A_SECRET'), (200,b'{}'))
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_header('User-agent'), USER_AGENT)
        self.assertEqual(USER_AGENT, 'cube-returns-manager/1.0')
        self.assertEqual(request.get_header('Authorization'), 'Bearer TEST_NOT_A_SECRET')
        self.assertNotIn('TEST_NOT_A_SECRET', request.full_url + request.data.decode() + repr(request) + out.getvalue() + err.getvalue())
        opener.open.assert_called_once()

    def test_invalid_json_schema_scope_and_business_fields_rejected(self):
        self.batch['disposition']='RESTOCK'
        self.assertEqual(self.run_model().error_code, 'invalid_response')
        del self.batch['disposition']
        self.batch['scope']['tenant']['organization_id']='org_demo_bravo'
        self.assertEqual(self.run_model().error_code, 'response_scope_mismatch')
        self.transport.side_effect=None
        self.transport.return_value=(200,b'not JSON')
        self.assertEqual(self.run_model().error_code, 'provider_failure')

    def test_http_failure_no_retry_and_timeout(self):
        opener = Mock()
        opener.open.side_effect = HTTPError(ENDPOINT,503,'TEST',{},io.BytesIO(b'TEST private error'))
        with patch('returns_manager.groq.build_opener', return_value=opener), self.assertRaises(GroqHTTPFailure) as error:
            post_json(ENDPOINT,{},90,'TEST')
        self.assertEqual(error.exception.status,503)
        self.assertEqual(str(error.exception),'groq_http_error')
        opener.open.assert_called_once()
        self.transport.side_effect=TimeoutError()
        self.assertEqual(self.run_model().error_code,'provider_timeout')

    def test_persistence_review_and_failed_attempt_not_negative(self):
        with Store(':memory:', self.capture.tenant) as store, patch('returns_manager.vision.image_availability', return_value='available'):
            for failed in (False,True):
                if failed:self.transport.side_effect=GroqHTTPFailure(429)
                attempt=inspect_capture(self.row,self.source,store,self.images,self.provider)
                workflow=ReviewWorkflow(store)
                review=workflow.route(self.capture.record_id,self.capture.unit.unit_id,attempt_id=attempt)
                detail=workflow.get(review,self.capture.record_id,self.capture.unit.unit_id)
                self.assertEqual(detail['business_status'],'pending_review')
                self.assertIsNone(detail['automated_assessment']['condition']['grade'])
                self.assertEqual(detail['automated_assessment']['identity']['verdict'],'UNCERTAIN')
                self.assertEqual(detail['observations'] is None,failed)
                self.assertEqual(self.provider.http_status,429 if failed else 200)

    def test_diagnostic_enum_and_unknown_fields_never_echo_provider_text(self):
        secret = 'TEST-sensitive-provider-value-not-for-diagnostics'
        self.batch['identity'] = [{'field':secret, 'state':'observed', 'values':['TEST'],
                                  'evidence_refs':['TEST-evidence'], 'limitations':[]}]
        self.assertEqual(self.run_model().error_code, 'invalid_response')
        diag = self.provider.validation_diagnostic
        self.assertEqual(diag['path'], '$.identity[0].field')
        self.assertEqual(diag['category'], 'enum')
        self.assertNotIn(secret, json.dumps(diag))
        self.batch['identity'][0]['field'] = 'brand'
        self.batch['identity'][0][secret] = secret
        self.assertEqual(self.run_model().error_code, 'invalid_response')
        self.assertEqual(self.provider.validation_diagnostic['unexpected_field_count'], 1)
        self.assertNotIn(secret, json.dumps(self.provider.validation_diagnostic))

    def test_diagnostic_semantic_quantity_rule_without_repair_or_persistence(self):
        self.batch['components'] = [{'component':'TEST', 'presence':'unknown', 'visibility':'occluded',
            'quantity':1, 'quantity_reliable':True, 'absence_basis':None, 'evidence_refs':['TEST-evidence'],
            'limitations':['TEST obscured']}]
        with Store(':memory:', self.capture.tenant) as store, patch('returns_manager.vision.image_availability', return_value='available'):
            attempt = inspect_capture(self.row,self.source,store,self.images,self.provider)
            actual = store.vision_attempts(self.capture.record_id)[0]['run']
            self.assertIsNone(actual['observations'])
            self.assertIsNone(actual['raw_response'])
            self.assertEqual(actual['error_code'],'invalid_response')
        diag = self.provider.validation_diagnostic
        self.assertEqual(diag['path'], '$.components[0].quantity')
        self.assertEqual(diag['expected'], 'quantity cannot be inferred from obscured/conflicting evidence')
        self.assertEqual(self.batch['components'][0]['quantity'],1)

    def test_diagnostic_missing_fields_and_reset_on_valid_response(self):
        self.batch['condition'] = [{'feature':'wear', 'state':'unknown', 'evidence_refs':[], 'limitations':['TEST']}]
        self.assertEqual(self.run_model().error_code,'invalid_response')
        self.assertEqual(self.provider.validation_diagnostic['missing_fields'],['description'])
        self.batch['condition'][0]['description'] = None
        self.assertEqual(self.run_model().status,'validated')
        self.assertIsNone(self.provider.validation_diagnostic)
