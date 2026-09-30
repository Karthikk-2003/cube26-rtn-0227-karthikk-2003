"""Synthetic offline policy scenarios, not photographs, model output or eval labels."""
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

PARTICIPANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PARTICIPANT / 'agent'))
from returns_manager.domain import (Component, DecisionReference, Disposition, ObservationPlaceholder,
    SourceLineage, TenantContext, TenantMismatch, ValidationError, Verdict)
from returns_manager.observations import ObservationScope, ProviderResponse
from returns_manager.vision import FixtureProvider, ImageInput, observe, ProviderUnavailable
from returns_manager.validation import FIELDS, parse_record, validate_decision_reference
from returns_manager.rules import assess
from returns_manager.storage import Store
from returns_manager.service import inspect_capture
from returns_manager.review import HumanDecision, ReviewerContext
from returns_manager.review_storage import ReviewWorkflow
from returns_manager.ui import detail_projection


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.tenant = TenantContext('org_demo_alpha')
        self.row = {key: '' for key in FIELDS}
        self.row.update(record_id='TEST-record', unit_id='TEST-unit', org_id='org_demo_alpha',
            order_id='TEST-order', ordered_sku='TEST-SKU', ordered_asin='TEST-ASIN',
            operator_id='TEST-operator', captured_at='2026-09-30T00:00:00Z', photo_refs='TEST/a.png;TEST/b.png')
        self.source = SourceLineage('TEST synthetic capture', hashlib.sha256(b'TEST capture').hexdigest(), 2)
        self.capture = parse_record(self.row, self.tenant, self.source)
        self.scope = ObservationScope.from_capture(self.capture)
        self.reference = DecisionReference(self.tenant, 'TEST-record', 'TEST-unit', 'TEST-order',
            'TEST-SKU', 'TEST-ASIN', tuple(Component(n, n, 1) for n in ('case', 'cable', 'manual')), True,
            'TEST synthetic catalogue', 'TEST ONLY synthetic attestation for deterministic rule tests',
            'TEST-verifier', '2026-09-30T00:00:00Z')
        self.images = tuple(ImageInput(self.scope, f'TEST-image-{i}', f'TEST-evidence-{i}', img.reference,
            'returned_product', 'genuine', b'TEST synthetic bytes; decoder mocked' + bytes([i]))
            for i, img in enumerate(self.capture.images))
        self.payload = {'scope': asdict(self.scope), 'identity': [self.identity()],
            'components': [self.component(n) for n in ('case', 'cable', 'manual')], 'condition': [], 'limitations': []}
        self.provider = Mock()
        self.provider.name, self.provider.mode = 'TEST-mocked-provider', 'real'
        self.provider.observe.side_effect = lambda _: ProviderResponse(json.dumps(self.payload), self.provider.name,
            'real', model_version='TEST-model', request_id='TEST-request', latency_ms=17, token_usage=23)

    def identity(self, **changes):
        return {'field': 'sku', 'state': 'observed', 'values': ['TEST-SKU'],
            'evidence_refs': ['TEST-evidence-0'], 'limitations': [], **changes}

    def component(self, name, absent=False, **changes):
        return {'component': name, 'presence': 'absent' if absent else 'present', 'visibility': 'visible',
            'quantity': 0 if absent else 1, 'quantity_reliable': True,
            'absence_basis': 'full_expected_area_visible' if absent else None,
            'evidence_refs': ['TEST-evidence-0'],
            'limitations': ['TEST full expected area visible'] if absent else [], **changes}

    def run_observations(self):
        with patch('returns_manager.vision.image_availability', return_value='available'):
            return observe(self.capture, self.images, self.provider)

    def result(self):
        run = self.run_observations()
        self.assertEqual(run.status, 'validated')
        return assess(self.capture, run.observations, self.reference)

    def inspect(self, store):
        with patch('returns_manager.vision.image_availability', return_value='available'):
            return inspect_capture(self.row, self.source, store, self.images, self.provider, reference=self.reference)

    def test_correct_product_and_complete_parts_with_source_and_citations(self):
        result = self.result()
        self.assertEqual(result.identity.verdict, Verdict.PASS)
        self.assertEqual(result.completeness.verdict, Verdict.PASS)
        self.assertEqual(result.identity.evidence, ('TEST-evidence-0',))
        self.assertEqual(result.completeness.evidence, ('TEST-evidence-0',))
        self.assertEqual(result.decision_reference, self.reference)
        self.assertEqual(result.rule_version, 'scoped-reference-checks-2')
        self.assertEqual(result.decision_reference.source_sha256,
            hashlib.sha256(self.reference.source_document.encode()).hexdigest())
        self.assertIsNone(result.identity.confidence)
        self.assertIsNone(result.completeness.confidence)
        self.assertEqual(result.disposition.decision, Disposition.PENDING_REVIEW)

    def test_wrong_product_does_not_grade_its_accessories_against_order(self):
        self.payload['identity'] = [self.identity(values=['TEST-DIFFERENT-SKU'])]
        result = self.result()
        self.assertEqual(result.identity.verdict, Verdict.FAIL)
        self.assertEqual(result.completeness.verdict, Verdict.UNCERTAIN)
        self.assertFalse(result.completeness.missing_components)

    def test_similar_product_names_and_packaging_cannot_pass_identity(self):
        for item in (self.identity(field='product_name', values=['TEST-SKU']),
                     self.identity(field='packaging_identifiers', values=['TEST-SKU'])):
            self.payload['identity'] = [item]
            self.assertEqual(self.result().identity.verdict, Verdict.UNCERTAIN)
        self.payload['identity'] = [self.identity()]
        self.images = tuple(replace(i, image_role='returned_packaging') for i in self.images)
        self.assertEqual(self.result().identity.verdict, Verdict.UNCERTAIN)

    def test_exact_identifiers_are_not_fuzzy_or_case_normalized(self):
        self.payload['identity'] = [self.identity(values=['test-sku'])]
        self.assertEqual(self.result().identity.verdict, Verdict.UNCERTAIN)

    def test_disagreeing_sku_asin_and_multiview_identity_conflicts_stay_uncertain(self):
        for other in (self.identity(field='asin', values=['TEST-WRONG-ASIN']),
                      self.identity(values=['TEST-WRONG-SKU'], evidence_refs=['TEST-evidence-1'])):
            self.payload['identity'] = [self.identity(), other]
            self.assertEqual(self.result().identity.verdict, Verdict.UNCERTAIN)

    def test_ambiguous_identity_and_global_limits_prevent_pass(self):
        self.payload['identity'] = [self.identity(state='unknown', values=[], evidence_refs=[], limitations=['TEST blurred'])]
        self.assertEqual(self.result().identity.verdict, Verdict.UNCERTAIN)
        self.payload['identity'] = [self.identity(limitations=['TEST possibly obscured'])]
        self.assertEqual(self.result().identity.verdict, Verdict.UNCERTAIN)
        self.payload['identity'] = [self.identity()]
        self.payload['limitations'] = ['TEST overall low visibility']
        result = self.result()
        self.assertEqual(result.identity.verdict, Verdict.UNCERTAIN)
        self.assertEqual(result.completeness.verdict, Verdict.UNCERTAIN)

    def test_one_and_multiple_missing_components(self):
        for names in (('cable',), ('cable', 'manual')):
            self.payload['components'] = [self.component(n, n in names) for n in ('case', 'cable', 'manual')]
            result = self.result()
            self.assertEqual(result.completeness.verdict, Verdict.FAIL)
            self.assertEqual(result.completeness.missing_components, names)
            self.assertEqual(result.completeness.unknown_components, ())
            self.assertEqual(result.disposition.decision, Disposition.PENDING_REVIEW)

    def test_absence_without_full_coverage_is_rejected_by_existing_parser(self):
        self.payload['components'] = [self.component('cable', True, absence_basis=None)]
        run = self.run_observations()
        self.assertEqual(run.error_code, 'invalid_response')
        result = assess(self.capture, ObservationPlaceholder(run.error_code), self.reference)
        self.assertEqual(result.completeness.verdict, Verdict.UNCERTAIN)
        self.assertFalse(result.completeness.missing_components)

    def test_not_visible_occluded_and_unknown_do_not_become_missing(self):
        for visibility in ('not_visible', 'occluded', 'unknown', 'partial'):
            self.payload['components'] = [self.component('cable', presence='unknown', visibility=visibility,
                quantity=None, quantity_reliable=False, limitations=['TEST not enough coverage'])]
            result = self.result()
            self.assertEqual(result.completeness.verdict, Verdict.UNCERTAIN)
            self.assertFalse(result.completeness.missing_components)

    def test_known_missing_remains_traceable_with_other_unknown_parts(self):
        self.payload['components'] = [self.component('cable', True)]
        result = self.result()
        self.assertEqual(result.completeness.verdict, Verdict.FAIL)
        self.assertEqual(result.completeness.missing_components, ('cable',))
        self.assertEqual(result.completeness.unknown_components, ('case', 'manual'))

    def test_counts_not_summed_across_photos_and_partial_count_not_absence(self):
        self.reference = replace(self.reference, components=(Component('cable x2', 'cable', 2),))
        self.payload['components'] = [self.component('cable'), self.component('cable', evidence_refs=['TEST-evidence-1'])]
        result = self.result()
        self.assertEqual(result.completeness.verdict, Verdict.UNCERTAIN)
        self.assertFalse(result.completeness.missing_components)
        self.payload['components'] = [self.component('cable', quantity=2)]
        self.assertEqual(self.result().completeness.verdict, Verdict.PASS)

    def test_conflicting_component_counts_do_not_choose_a_winner(self):
        self.payload['components'] += [self.component('cable', True, evidence_refs=['TEST-evidence-1'])]
        result = self.result()
        self.assertEqual(result.completeness.verdict, Verdict.UNCERTAIN)
        self.assertFalse(result.completeness.missing_components)
        self.assertEqual(result.identity.verdict, Verdict.PASS)

    def test_incomplete_or_unquantified_reference_cannot_pass(self):
        for changes in ({'parts_list_complete': False}, {'components': ()},
                        {'components': (Component('cable', 'cable', None),)}):
            original = self.reference
            self.reference = replace(original, **changes)
            self.assertEqual(self.result().completeness.verdict, Verdict.UNCERTAIN)
            self.reference = original

    def test_csv_does_not_become_authoritative_without_reference(self):
        run = self.run_observations()
        result = assess(self.capture, run.observations)
        self.assertEqual(result.identity.verdict, Verdict.UNCERTAIN)
        self.assertEqual(result.completeness.verdict, Verdict.UNCERTAIN)
        self.assertIsNone(result.decision_reference)

    def test_fixture_observations_cannot_release_business_checks(self):
        images = tuple(replace(i, kind='fixture', content=None) for i in self.images)
        run = observe(self.capture, images, FixtureProvider(json.dumps(self.payload)))
        result = assess(self.capture, run.observations, self.reference)
        self.assertEqual(result.identity.verdict, Verdict.UNCERTAIN)
        self.assertEqual(result.completeness.verdict, Verdict.UNCERTAIN)

    def test_new_looking_used_damaged_and_heavily_damaged_do_not_invent_grade(self):
        for feature, description in (('surface_condition', 'TEST new-looking surface'), ('signs_of_use', 'TEST light wear'),
                                     ('cracks', 'TEST visible crack'), ('broken_parts', 'TEST extensive broken housing')):
            self.payload['condition'] = [{'feature': feature, 'state': 'observed', 'description': description,
                'evidence_refs': ['TEST-evidence-0'], 'limitations': []}]
            result = self.result()
            self.assertEqual(result.condition.verdict, Verdict.UNCERTAIN)
            self.assertIsNone(result.condition.grade)
            self.assertIsNone(result.condition.confidence)
            self.assertEqual(result.condition.evidence, ('TEST-evidence-0',))
            self.assertEqual(result.condition.policy_source, 'https://sell.amazon.com/blog/amazon-condition-guidelines')
            self.assertEqual(result.disposition.decision, Disposition.PENDING_REVIEW)

    def test_ambiguous_and_conflicting_condition_preserved(self):
        first = {'feature': 'scratches', 'state': 'observed', 'description': 'TEST line visible',
            'evidence_refs': ['TEST-evidence-0'], 'limitations': []}
        self.payload['condition'] = [first, {**first, 'state': 'not_observed', 'description': 'TEST reflection only',
            'evidence_refs': ['TEST-evidence-1'], 'limitations': ['TEST alternate angle']}]
        result = self.result()
        self.assertIn('conflicting_condition_observations', result.condition.reasons)
        self.assertEqual(result.condition.evidence, ('TEST-evidence-0', 'TEST-evidence-1'))
        self.assertIsNone(result.condition.grade)

    def test_all_four_historical_dispositions_are_not_policy(self):
        for decision in (Disposition.RESTOCK, Disposition.REFURBISH, Disposition.LIQUIDATE, Disposition.DISPOSE):
            capture = parse_record({**self.row, 'operator_disposition': decision.value,
                'amazon_condition': 'Used - Good'}, self.tenant, self.source)
            run = self.run_observations()
            result = assess(capture, run.observations, self.reference)
            self.assertEqual(result.disposition.decision, Disposition.PENDING_REVIEW)
            self.assertIsNone(result.condition.grade)

    def test_missing_unreadable_and_provider_failure_stay_uncertain(self):
        for content in (None, b'TEST not an image'):
            run = observe(self.capture, tuple(replace(i, content=content) for i in self.images), self.provider)
            result = assess(self.capture, ObservationPlaceholder(run.error_code), self.reference)
            self.assertEqual(result.identity.verdict, Verdict.UNCERTAIN)
        self.provider.observe.assert_not_called()
        for error in (ProviderUnavailable('TEST'), TimeoutError(), RuntimeError('TEST')):
            self.provider.observe.side_effect = error
            run = self.run_observations()
            result = assess(self.capture, ObservationPlaceholder(run.error_code), self.reference)
            self.assertEqual(result.completeness.verdict, Verdict.UNCERTAIN)
            self.assertIsNone(result.condition.grade)

    def test_reference_scope_and_order_checked_before_provider_or_storage(self):
        for changes in ({'tenant': TenantContext('org_demo_bravo')}, {'tenant': TenantContext('org_demo_alpha', 'TEST-client')},
                        {'record_id': 'TEST-other'}, {'unit_id': 'TEST-other'}, {'order_id': 'TEST-other'},
                        {'ordered_sku': 'TEST-other'}, {'ordered_asin': 'TEST-other'}):
            with Store(Path(':memory:'), self.tenant) as store:
                bad = replace(self.reference, **changes)
                with self.assertRaises((TenantMismatch, ValidationError)):
                    inspect_capture(self.row, self.source, store, self.images, self.provider, reference=bad)
                self.assertIsNone(store.get(self.capture.record_id))
        self.provider.observe.assert_not_called()

    def test_reference_malformed_and_duplicate_parts_rejected(self):
        for changes in ({'parts_list_complete': 'yes'}, {'source_document': ''}, {'source_document': '\ud800'},
                {'verified_by': ''}, {'verified_at': '2026-09-30T00:00:00'}, {'components': []},
                {'components': (Component('case', 'case', 1), Component('CASE', 'CASE', 1))}):
            with self.assertRaises(ValidationError):
                replace(self.reference, **changes)
        object.__setattr__(self.reference, 'source_sha256', '0' * 64)
        with self.assertRaises(ValidationError):
            validate_decision_reference(self.capture, self.reference)

    def test_rejected_citations_and_business_fields_never_reach_policy(self):
        for changes in ({'identity': [self.identity(evidence_refs=['TEST-foreign'])]}, {'disposition': 'RESTOCK'},
                        {'grade': 'Used - Good'}):
            original = self.payload
            self.payload = {**original, **changes}
            run = self.run_observations()
            self.assertEqual(run.status, 'unavailable')
            self.assertIsNone(run.observations)
            self.payload = original

    def test_persistence_raw_lineage_review_api_and_human_override(self):
        scratch = PARTICIPANT / '.test-tmp'
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            path = Path(directory) / 'TEST.sqlite3'
            with Store(path, self.tenant) as store:
                attempt = self.inspect(store)
                workflow = ReviewWorkflow(store)
                rid = workflow.route('TEST-record', 'TEST-unit', attempt_id=attempt)
                before = workflow.get(rid, 'TEST-record', 'TEST-unit')
                assessment = before['automated_assessment']
                self.assertEqual(assessment['identity']['verdict'], 'PASS')
                self.assertEqual(assessment['decision_reference']['source_sha256'], self.reference.source_sha256)
                self.assertEqual(before['raw_response']['text'], json.dumps(self.payload))
                self.assertEqual(before['raw_response']['latency_ms'], 17)
                self.assertEqual(before['raw_response']['model_version'], 'TEST-model')
                self.assertEqual(before['evidence'][0]['sha256'], hashlib.sha256(self.images[0].content).hexdigest())
                self.assertEqual(detail_projection(before)['automated_assessment'], assessment)
                self.assertNotIn({'code': 'unverified_reference', 'dimension': 'identity'}, before['uncertainty'])
                reviewer = ReviewerContext(self.tenant, 'TEST-reviewer')
                workflow.transition(rid, 'TEST-record', 'TEST-unit', reviewer=reviewer, command_id='TEST-start',
                    expected_revision=1, status='in_review', reason='TEST review')
                workflow.transition(rid, 'TEST-record', 'TEST-unit', reviewer=reviewer, command_id='TEST-finish',
                    expected_revision=2, status='reviewed', reason='TEST disagree',
                    decisions=(HumanDecision('identity', 'FAIL', ('TEST-evidence-0',)),))
                after = workflow.get(rid, 'TEST-record', 'TEST-unit')
                self.assertEqual(after['automated_assessment'], assessment)
                self.assertEqual(after['effective_results']['identity']['source'], 'human')
                self.assertEqual(after['business_status'], 'pending_review')
                self.assertEqual(len(workflow.history(rid, 'TEST-record', 'TEST-unit')), 3)
            with Store(path, self.tenant) as store:
                self.assertEqual(store.vision_attempts('TEST-record')[0]['assessment'], assessment)
            for tenant in (TenantContext('org_demo_bravo'), TenantContext('org_demo_alpha', 'TEST-client')):
                with Store(path, tenant) as store:
                    self.assertEqual(store.vision_attempts('TEST-record'), [])
                    self.assertEqual(ReviewWorkflow(store).queue(), [])

    def test_forged_result_or_reference_digest_rejected_at_storage(self):
        run = self.run_observations()
        result = assess(self.capture, run.observations, self.reference)
        with Store(Path(':memory:'), self.tenant) as store:
            for forged in (replace(result, identity=replace(result.identity, verdict=Verdict.FAIL)),
                           replace(result, disposition=replace(result.disposition, decision=Disposition.RESTOCK))):
                with self.assertRaises(ValidationError):
                    store.save_vision_attempt(self.capture, run, forged)
            self.assertEqual(store.vision_attempts('TEST-record'), [])

    def test_decision_is_pure_repeatable_and_reference_not_sent_to_provider(self):
        first, second = self.result(), self.result()
        self.assertEqual(first, second)
        request = self.provider.observe.call_args.args[0]
        self.assertNotIn(self.reference.source_document, repr(request))
        self.assertNotIn(self.reference.verified_by, repr(request))

    def test_source_snapshot_preserves_multiline_content_exactly(self):
        source = '\nTEST document\r\n\tTEST retained formatting\n'
        reference = replace(self.reference, source_document=source)
        validate_decision_reference(self.capture, reference)
        self.assertEqual(reference.source_document, source)
        self.assertEqual(reference.source_sha256, hashlib.sha256(source.encode('utf-8')).hexdigest())

    def test_packaging_view_cannot_establish_actual_accessories(self):
        self.images = (self.images[0], replace(self.images[1], image_role='returned_packaging'))
        self.payload['components'] = [self.component(n, evidence_refs=['TEST-evidence-1']) for n in ('case', 'cable', 'manual')]
        result = self.result()
        self.assertEqual(result.identity.verdict, Verdict.PASS)
        self.assertEqual(result.completeness.verdict, Verdict.UNCERTAIN)
        self.assertFalse(result.completeness.missing_components)
