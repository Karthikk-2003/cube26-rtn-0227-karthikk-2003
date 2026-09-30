# Returns Manager architecture and policy resolution

Current implementation, 2026-09-30. Internal contracts only; this is not the organiser's finalized wire schema.

## Authority and policy findings

The supplied Returns Manager challenge and the 18-page CUBE handbook are the CUBE requirements. The handbook's sections 9-10 require traceable checks, uncertainty and held-out evaluation; it contains no condition definitions or disposition decision table. Its submission list requires an architecture document. The challenge's headphones example is one scenario, not a universal rule.

The repository's data/README.md explicitly says to use Amazon's published condition scale. The Verity 6-Pager (page 3) and One-Pager agree, but are product context, not CUBE judging specifications. Their disposition wording explicitly refers to customer rules. The Working Document leaves rubric ownership open (DEC-005) and references BRD/technical-spec files that were not supplied. The Customer Letter describes itself as a synthesized hypothesis; none of its claims becomes mandatory policy here. Its business metrics and Verity's 500-unit targets are not CUBE evaluation results or substituted requirements.

External source checked 2026-09-30: [Amazon's published condition guidance](https://sell.amazon.com/blog/amazon-condition-guidelines), published 2025-09-26. It distinguishes general condition categories and category-specific requirements. Several descriptions require working condition or qualified inspection, so cosmetic photographs alone cannot establish those criteria. Implementation: ConditionResult records this source, keeps physical-observation citations, and returns no grade while applicable category, marketplace and nonvisual checks remain unresolved. Ambiguity: the general article is not a complete executable rubric for every product/category. The linked [Seller Central condition guidelines](https://sellercentral.amazon.com/help/hub/reference/external/G200339950?locale=en-US) returned a JavaScript/login shell in this check; no hidden policy was inferred from it. No external condition-to-disposition rule was established or implemented.

Allowed final business recommendations remain restock, refurbish, liquidate and dispose (the existing internal serialization is lowercase). The repository also authorizes pending_review. No supplied source establishes an exhaustive mapping, recovery-value calculation, repairability threshold or customer-specific rule table. All automated dispositions therefore remain pending_review. In particular, Used - Good does not imply refurbish, visible damage does not imply dispose, and an Amazon listing restriction does not establish zero recoverable value.

## Existing data flow

Configured image bytes -> prepare_request -> explicit VisionProvider -> raw ProviderResponse -> strict parse_response -> ObservationBatch -> deterministic assess -> scoped SQLite vision attempt -> review routing -> local HTTP/UI -> append-only human review events.

FixtureProvider (actual class name), OllamaVisionProvider and GeminiVisionProvider retain their existing contracts. Fixture mode is synthetic/test-only. Real adapters never grade or recommend disposition. Explicit provider selection and bounded Gemini transport retries are unchanged by this policy work; no automatic provider fallback exists.

The image boundary validates JPEG/PNG content, scope, reference membership and actual SHA-256. The parser rejects unknown fields, foreign scope, malformed telemetry, invalid Unicode, unsupported decisions and invented evidence IDs. It preserves uncertainty and conflicting assertions. Validation establishes structure and lineage, not the factual accuracy of a model's interpretation of pixels.

## Deterministic checks implemented

An optional DecisionReference is supplied by a trusted local caller, separately from model output. It records organization/client, record/unit, original order/SKU/ASIN, required components and quantities, explicit parts-list completeness, verifier identity/time, source name and exact source text. Its SHA-256 is calculated from that text. Scope/order mismatches are rejected before provider invocation or persistence. A hash proves byte identity, not source authenticity; the operator must actually verify the order/catalogue. No CSV flag, model response or browser body can create this attestation automatically.

The following are conservative engineering predicates implementing CUBE's identity/completeness checks, not claimed external resale policies:

- Identity uses exact SKU/ASIN observations on returned-product images against the attested order. Consistent matching identifiers yield PASS; consistent explicit mismatches yield FAIL. Disagreeing identifiers, multiple interpretations, uncertainty, per-identifier limitations or missing identifiers yield UNCERTAIN. Names, brand resemblance and packaging-only identifiers cannot establish identity. Case-only differences remain uncertain; no fuzzy normalization or catalogue-specific alias rule is assumed.
- Completeness requires established product identity and a nonempty, explicitly complete expected-parts list. Each part is compared by exact name, without guessed aliases. Visible reliable counts meeting the expected quantity establish presence. Explicit absence requires the existing parser's full_expected_area_visible basis, zero quantity, citations and coverage explanation. One or more such absent required parts yields FAIL and a missing-components list, while other unresolved parts remain separately listed.
- Not-visible/occluded/unknown is never missing. A smaller visible quantity remains unresolved because other units may be off-camera. Counts are never summed across photos. Contradictory counts remain uncertain. Packaging-only views cannot establish actual accessories.
- Global observation limitations, fixture mode or unavailable images prevent decisive checks. Without a supplied reference, the legacy synthetic-input path still returns UNCERTAIN. The caller's source snapshot is not sent to the model and does not become an observation.
- Condition observations retain evidence citations but never imply functionality, usage history, authenticity, grade or value. Condition classification and all final dispositions remain unresolved. No confidence value is manufactured.

## Integration and persistence

`assess(capture, observations, reference=None)` remains pure. `inspect_capture(row, source, store, images, provider, reference=reference)` validates the optional reference before calling the provider. `Store.save_vision_attempt` reparses the raw response, recomputes the deterministic assessment with its bound reference, and rejects tampered results. Each new assessment records rule_version=scoped-reference-checks-2 and its complete reference snapshot.

No SQL migration or data rewrite is required: the optional reference is embedded in the existing assessment JSON. Old records and assessments remain unchanged and readable. New attempts append; review changes never replace automated evidence. Cross-organization/client/unit/record checks continue at the existing boundaries. unit_id remains the cross-stage join key. Null client context is retained and flagged, never replaced with an invented client identifier.

The review adapter projects the stored assessment. The workstation displays separate automated/human results, reasons and evidence citations, confirmed missing versus unresolved parts, source attestation, condition-policy gaps and actual provider telemetry. A human identity/completeness assertion remains attributed and does not release the pending business disposition. No condition/disposition override was added.

## Supplying a real reference

The separate synthetic headphones package (`demo/README.md`) uses this same contract with `reference_status=synthetic_demo`, selected explicitly by `--demo-case headphones`. Its source, image hash and operator preparation identity are retained, but it cannot release automated identity/completeness. Existing real-reference callers default to operator_attested. The fixed demo case is not a general browser catalogue upload or a new reference store.

This is an optional library integration, not a new browser upload API. After obtaining an actual order/catalogue document and verifying it, the trusted caller constructs:

```python
from returns_manager.domain import DecisionReference
from returns_manager.service import inspect_capture

reference = DecisionReference(
    tenant=capture.tenant,
    record_id=capture.record_id,
    unit_id=capture.unit.unit_id,
    order_id=capture.order.order_id,
    ordered_sku=capture.order.ordered_sku,
    ordered_asin=capture.order.ordered_asin,
    components=verified_components,  # tuple[Component]; quantities explicit or None
    parts_list_complete=verified_parts_list_is_complete,
    source_name=actual_reference_name,
    source_document=actual_reference_text,  # exact text, max 8192 characters
    verified_by=actual_verifier,
    verified_at=actual_verification_utc,
)
attempt_id = inspect_capture(row, source, store, images, provider, reference=reference)
```

The variables above are deliberately not populated with fake customer/catalogue data. Merely copying the synthetic row into this object would not verify it. No actual order/catalogue reference was supplied with the demo photo, so the existing browser demo continues to show unknown identity/completeness. Creating a library reference cannot finalize condition/disposition or bypass image validation. Automated retrieval/authentication of catalogue documents, product-name/identifier aliases and category-specific grading inputs remain future integrations.

## Reproducible verification and limits

Run the offline suite using the README command, with GEMINI_LIVE_TEST=0 and OLLAMA_LIVE_TEST=0. tests/test_policy.py contains explicitly synthetic structured scenarios and mocked decoder/provider outputs; they are not real photographs, generated visual evidence or benchmark labels. Existing provider, failure, isolation, review, UI and evaluation tests remain in place. See build-log.md for exact executed counts.

The evaluation harness's historical report covers synthetic engineering checks and blocked visual scenarios. It was not regenerated or reinterpreted as a new benchmark. Genuine 50-unit held-out visual evaluation, two independent human labels, category-specific condition validation and disposition accuracy remain blocked. Provider raw text/model/version/latency/token lineage is retained when actually supplied; no successful live inference, cost or accuracy is claimed by offline tests.

See README.md for explicit Gemini/Ollama/Fixture launch commands. Gemini live verification remains paused; this task made no inference requests. Ollama remains limited by the previously observed local memory/timeouts. Fixture mode supports reliable workflow rehearsal without pretending that AI inspected a photo. Further business decisions require an approved applicable condition rubric, nonvisual inspection evidence and customer disposition rules; they cannot be supplied by a more confident prompt.
