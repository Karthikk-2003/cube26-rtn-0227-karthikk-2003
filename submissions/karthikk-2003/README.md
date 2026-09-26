# karthikk-2003 - Returns Manager

Participant: Karthik Karunakaran (@Karthikk-2003, supplied handoff).

Status: Phase 1 foundation, Phase 2 observation layer, Phase 3 backend evidence/review workflow and Phase 4 engineering evaluation foundation implemented. Visual benchmarking remains blocked by missing genuine evidence, authoritative labels and policies. No real multimodal API call, UI, authoritative grading/disposition policy, official wire-contract implementation or deployment exists.

This index is adapted from [submissions/_TEMPLATE/README.md](../_TEMPLATE/README.md), which requests a participant README. Current [RULES](../../RULES.md) and [GitHub guide](../../GITHUB-GUIDE.md) instead describe an own-fork workflow without requiring participant folders or organiser PRs. This directory follows the user's requested boundary and is compatible with the retained guard's path rule; it does not imply a PR is required.

## Current documentation

- [Build brief](build-brief.md): source-backed repository findings, proposed architecture, data/evidence contract, evaluation methodology, roadmap and open questions.
- [Build log](build-log.md): audit, implementation history and actual engineering test results.
- [Evaluation contract/discovery](evaluation/README.md) and [executed JSON report](evaluation/results.json): reproducible engineering checks and explicitly blocked visual scenarios.

## Implemented structure

- `agent/returns_manager/domain.py`: immutable internal tenant, unit, order, reference, capture, observation placeholder and separate result types.
- `agent/returns_manager/validation.py`: strict synthetic CSV adapter, source digest/row lineage and input/reference checks.
- `agent/returns_manager/rules.py`: pure missing-evidence rule scaffolding; no model calls or business-policy mappings.
- `agent/returns_manager/storage.py`: tenant-bound SQLite capture/result persistence and scoped record/unit/evidence-reference lookups.
- `agent/returns_manager/service.py`: persist capture before assessment, preserve failures, resume unfinished ingestion and reject conflicting duplicates.
- `agent/returns_manager/__main__.py` and `__init__.py`: local CLI and package entry.
- `tests/test_foundation.py`: explicitly synthetic engineering tests; no image generation or model output fixtures.
- `agent/returns_manager/observations.py`: observation dataclasses, strict raw JSON parser, evidence/scope validation and conflict detection.
- `agent/returns_manager/vision.py`: image-input boundary, provider protocol, fixture replay provider and failure-safe observation pipeline.
- `tests/test_vision.py`: synthetic observation/metadata fixtures, provider failures, isolation and integration tests.
- `agent/returns_manager/review.py`: internal human decision contracts and pure deterministic uncertainty routing.
- `agent/returns_manager/review_storage.py`: scoped evidence view, retry-safe review cases and append-only review events over an existing Store.
- `tests/test_review.py`: synthetic review, lineage, isolation, override and persistence tests.
- `agent/returns_manager/evaluation.py` and `evaluation_data.py`: isolated engineering cases, repository-data inventory, blocked scenarios and structured results.
- `tests/test_evaluation.py`: evaluation harness regression tests; no visual golden labels.
- `requirements-images.txt`: optional Pillow dependency for validation of genuine image bytes; not needed for fixture tests or the Phase 1 CLI.
- `.gitignore`: excludes local runtime databases and temporary test directories within this directory.

## Setup, run and test

Requires Python 3.10+ with standard-library SQLite; tested here with Python 3.13.4. The existing CSV CLI and fixture tests require no pip dependencies, API keys or network access. Run the following PowerShell commands from this participant directory:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'agent'
python -B -m returns_manager --csv ../../data/returns_sample.csv --organization org_demo_alpha
python -B -m returns_manager --csv ../../data/returns_sample.csv --organization org_demo_bravo
python -B -m unittest discover -s tests -v
```

The CLI deliberately selects only rows belonging to the explicit organization, validates that selected batch and writes one internal JSON object per selected record to stdout. The sample contains 11 alpha and 13 bravo rows. It persists to `runtime/returns.sqlite3` under this participant directory; `--database` may select another path inside this directory only. The sample CSV is read-only. Tests create and clean their own databases under `.test-tmp/`; test execution does not need PYTHONPATH set.

For other shells, set PYTHONPATH to the absolute `agent` directory before running the same Python commands. Do not redirect output into repository root files. CLI validation/storage errors exit with code 2; a successful import exits 0. Unexpected processing errors propagate, leaving already accepted captures pending in storage. Imports are per-record durable, not an all-or-nothing batch transaction.

## What the foundation does and does not establish

All current input goes through an explicitly **synthetic CSV fixture adapter**. Historical annotations are retained under `capture.raw_fields`, never used as inferred identity, missing parts, condition or disposition. The adapter preserves record_id, unit_id, original org_id, order/SKU/ASIN, operator, exact capture timestamp, photo references, source filename, SHA-256 and row number. The source digest identifies bytes read; it is not an official content_hash or an immutability claim.

The adapter requires exactly the documented CSV columns and valid nonempty identifiers/UTC timestamps. It rejects wrong tenant context, malformed rows, duplicate/invalid components, unsupported historical dispositions and inconsistent missing-part lists. Empty parts/photo lists are retained with review blockers. Explicit `xN` quantities are parsed; unspecified quantities stay unknown. The sample's parts list is unverified reference context, not an authoritative catalogue.

The CSV adapter still marks every photo reference **unavailable**. Input paths and URLs are never opened, fetched or served, even if a file happens to exist. The Phase 1 CLI retains its unavailable observation placeholder. The separate Phase 2 library API accepts explicitly supplied image inputs and returns either validated observations or an explicit unavailable state. Identity, completeness and condition remain separate UNCERTAIN business results with null confidence, no assigned grade and no fabricated missing-component claims. Disposition remains `pending_review`. Future decisive checks require validated evidence/policies and a subsequent implementation phase.

SQLite lookups require a Store bound to an explicit trusted TenantContext and include organization and client scope in every query. Missing client_id remains JSON null and is an exact scope, not a wildcard or generated identifier. `--client` is only for a real trusted client context if one becomes available; the supplied data has none. No client IDs are invented in the implementation or tests. Actual client-level authorization remains unverified until real context is supplied.

This local CLI trusts the operator's organization argument; it is **not an authentication service**. Database file access is not protected against its local owner. A future server must derive tenant context from authentication rather than user-submitted fields and protect storage at the host level. Phase 1 prevents accidental cross-tenant application lookups and never serves image bytes.

Repeated ingestion of identical scoped record ID and full lineage returns the stored result without another assessment. Changed data or source lineage under the same scoped record ID raises ConflictError and does not overwrite prior input. Distinct organizations may use identical record/unit IDs safely. A processing exception preserves the committed capture, pending state and exception type (not sensitive exception text); an exact retry can resume when no assessment exists. Existing assessments cannot be silently replaced. Phase 3 stores human decisions in separate review history.

The JSON output is labelled `internal_only_not_official_wire_contract`; it is not a Recovery Manager interoperability claim. Exact official schema, condition rules and disposition policy remain unresolved. See the build brief for details.

## Phase 2 observation layer

Flow: capture-bound image inputs -> VisionProvider -> raw ProviderResponse -> strict parser/validator -> ObservationBatch -> existing deterministic rules -> stored observation attempt and review outcome. The raw provider response is separate from normalized observations and business results. There is no direct vision-to-disposition or vision-to-condition-grade path.

The public integration entry is `service.inspect_capture(row, source, store, images, provider=None)`. It validates the row against the Store's trusted tenant context and preserves the capture before processing. `images` is a tuple of `vision.ImageInput` values bound to the capture's organization/client, unit_id and record_id through `ObservationScope.from_capture(capture)`. Callers supply image_id, evidence_id, capture photo reference, image role and source kind. IDs are not generated from model assertions. Each reference must already belong to that capture. Returned-product and returned-packaging image roles are supported; the validated relationship is `capture_photo_ref`.

`VisionProvider.observe(VisionRequest)` receives one batch containing image descriptors, any validated image bytes and expected component names. It does not receive CSV identity/disposition/condition history. It must return a ProviderResponse containing raw JSON plus actual provider metadata where available. No real adapter is configured or implemented. A future real adapter must enforce its own network timeout, translate its response into the internal observation JSON contract, keep image contents as data rather than instructions, and provide real metadata or null. No API credentials are required or used in this implementation.

`FixtureProvider(response_text)` replays **explicitly supplied synthetic test JSON**, with provider name `fixture-json` and mode `fixture`. It performs no inference, cannot claim model/request/token/latency metadata, and only accepts metadata inputs labelled `kind="fixture"`. Such evidence is `fixture_only`, never a claim that genuine images were inspected. Test assertions and fixture IDs in `tests/test_vision.py` are not product evidence or model outputs. No fake image files were created.

For genuine inputs, callers must supply actual bytes (`kind="genuine"`); this layer does not fetch arbitrary paths/URLs. Missing bytes, non-images and corrupt/unreadable images stop the batch before a provider call. A genuine PNG/JPEG decoder is optional:

```powershell
# Optional, only when genuine image-byte validation is needed:
python -m pip install --target ./runtime/image-deps -r requirements-images.txt
$env:PYTHONPATH = (Join-Path (Get-Location) 'agent') + [IO.Path]::PathSeparator + (Join-Path (Get-Location) 'runtime/image-deps')
```

The loader uses [Pillow image verification and loading](https://pillow.readthedocs.io/en/stable/reference/Image.html), with limits of 20 images, 10 MB per image, 20 million pixels per image and single-frame PNG/JPEG only. These are implementation limits, not challenge requirements. Decoded content receives its actual SHA-256; unavailable/fixture content does not receive a fabricated digest. With Pillow absent, potentially supported bytes return `image_decoder_unavailable`. No genuine product image or successful real-provider call was tested in this phase. Image byte content remains transient; durable image storage and authenticated upload resolution are still extension points.

### Internal normalized observations

The internal provider JSON requires `scope`, `identity`, `components`, `condition` and `limitations`. The scope uses the existing tenant/unit/record identities, not another identity system. See dataclasses and validation in observations.py for exact field names. Unknown fields, duplicate JSON keys, nonfinite JSON values, wrong types, missing fields, unsupported values and unresolved evidence IDs are rejected. Raw text is bounded to 1,000,000 characters, text fields to 8,192 characters and lists to 200 items. No official wire schema is asserted.

- Identity: brand, model, SKU, ASIN, model number, product name, markings, packaging identifiers, physical characteristics and provider-supplied OCR text. States distinguish observed, not_observed, not_visible, unknown and conflicting; values are never filled from catalogue/history.
- Components: component name, present/absent/unknown/conflicting assertion, visibility, optional reliable visible quantity, citations and limitations. Unknown, occluded or partial evidence cannot support a reliable exact count. An absence assertion requires visible coverage, quantity zero, `full_expected_area_visible`, citations and a coverage explanation. This records the provider's assertion and rationale; it does not independently prove physical absence or produce a business missing-parts verdict.
- Condition: visible scratches/scuffs/cracks/dents/deformation/stains/tears/wear/discoloration/broken parts/packaging damage/signs of use/surface condition, with observation state, provider description, evidence and limitations. No condition-grade enumeration or damage-to-grade mapping is introduced. A negative finding describes the inspected visible scope, not an unseen whole product.
- Evidence: substantive assertions require references to supplied usable evidence IDs. Unknown observations may have no citation but must state a limitation. Bounding boxes, coordinates and regions are not supported or generated. Every descriptor retains image identity, role and capture relationship.
- Uncertainty: global and per-observation limitations retain blur, glare, occlusion, poor lighting, insufficient angle and similar descriptions as supplied. Multiple observations are retained in order. Explicit conflicts and contradictory identity/component/condition assertions are flagged rather than resolved by choosing an image.

The deterministic rule boundary reparses normalized observations, so constructing a dataclass manually does not bypass structural/evidence validation. Current rules retain the observation batch for traceability but still return UNCERTAIN and pending_review because authoritative reference/policy dependencies remain unresolved. Fixture runs retain a `fixture_observations_only` blocker. There is no model confidence or invented telemetry.

### Failures, attempts and isolation

Unconfigured provider, provider unavailability, timeout, exception, empty/invalid response and missing/unreadable images produce explicit unavailable runs and review results. Invalid JSON/schema/evidence is reported as `invalid_response`; foreign organization/client/unit/record responses become `response_scope_mismatch`. Rejected raw text is discarded rather than stored under a potentially wrong owner. Valid raw text and normalized observations are retained separately. Failed runs contain no observations and never imply mismatch, missing parts or damage. Invalid input scopes are rejected before any provider call and no foreign inputs are persisted.

Audit fixes reject invalid Unicode scalars in raw response text, decoded observation text and textual provider metadata without replacement or normalization. Oversized latency integers that overflow finite-number validation are rejected as ValidationError. Both audited cases follow the existing `invalid_response` unavailable/review path and persist a failure attempt without invalid observations or replacement telemetry.

`Store.vision_attempts(record_id)` returns attempts only inside its bound organization/client scope. Each saved run is revalidated against its capture, raw response and deterministic assessment. The additive `vision_attempts` table works with existing Phase 1 databases without replacing captures or prior assessments. A local database-generated attempt_id identifies an attempt; it is not a provider request ID or a replacement for record_id/unit_id. Explicit repeat inspection calls append attempts, including failures; they are not silently cached or auto-retried. The original `ingest()` retains Phase 1 idempotency.

The library boundary still trusts the authenticated-context supplier and image registration caller; authentication and image ownership resolution must be provided by a future application. Parser validation establishes structure and declared provenance, not the truth of model assertions. Test success is not visual accuracy. Complete review/override UI, real vision calls, official wire export, business policy, deployment and genuine visual benchmarking remain unimplemented.

## Phase 3 backend evidence and review workflow

`ReviewWorkflow(store)` adds `review_items` and `review_events` tables on the existing tenant-bound SQLite connection. Phase 1/2 code and behavior are unchanged. Routing is an explicit library call after ingestion/inspection; the CSV CLI does not automatically populate this queue. No additional dependency is needed.

The API accepts persisted source identifiers, not caller-supplied evidence, assessments or observation payloads:

- `route(record_id, unit_id, attempt_id=None)` returns a review ID. Omit attempt_id to select the original capture assessment; supply the actual saved vision attempt ID to select that attempt. Retrying the same source returns the same case without resetting its state. Distinct vision attempts get distinct cases.
- `get(review_id, record_id, unit_id)` assembles the scoped capture, original photo references, descriptor availability, raw response, normalized observations, automated assessment (including rule version), routing reasons, human decisions and effective results. It joins existing evidence instead of copying raw/normalized evidence into review tables. Invalid provider responses remain unavailable as in Phase 2.
- `queue(status=None)` lists only cases in the Store's trusted organization/client scope, optionally filtered by internal review status. `history(review_id, record_id, unit_id)` returns ordered events after the same scoped parent check.
- `transition(..., reviewer, command_id, expected_revision, status, reason, decisions=())` appends an event. The reviewer must be a trusted `ReviewerContext(store.context, actual_operator_identity)`. The API validates its identity and tenant association; it does not authenticate the person. Actual timestamps are generated locally in UTC.

Example integration after an actual existing `inspect_capture` call (the variables below must come from that caller; they are not generated evidence or client IDs):

```python
from returns_manager.review import ReviewerContext
from returns_manager.review_storage import ReviewWorkflow

workflow = ReviewWorkflow(store)
review_id = workflow.route(record_id, unit_id, attempt_id=attempt_id)
item = workflow.get(review_id, record_id, unit_id)
event = workflow.transition(
    review_id, record_id, unit_id,
    reviewer=ReviewerContext(store.context, authenticated_operator_id),
    command_id=review_action_id, expected_revision=item["revision"],
    status="in_review", reason=operator_reason,
)
```

Uncertainty is a deterministic list of internal `{code, dimension}` objects. It distinguishes missing/not-supplied evidence, unreadable images, unavailable decoding/providers, provider timeout/failure/invalid response, fixture-only evidence, ambiguous identity/components, identity/component/condition conflicts, insufficient coverage/condition evidence, missing client context, unverified references, unresolved condition/disposition policy and insufficient evidence for decisions. Provider limitations and conflicting assertions remain in the unchanged observation batch. Unknown/occluded does not become absent. Empty image lists and interrupted assessments remain reviewable; a case routed before assessment completion retains that original unavailable assessment context even if ingestion later resumes. A subsequent vision attempt can create a new case.

Internal workflow transitions are `pending_review -> in_review`, `in_review -> in_review | pending_review | reviewed`, and `reviewed -> in_review` (reopen). `reviewed` means the human finished that review pass; it does **not** mean an official final disposition or policy approval. `business_status` remains `pending_review` and unresolved decisions remain explicit. These are internal application states, not claimed official external contract values.

During active review, pass a tuple of `HumanDecision(dimension, verdict, evidence_refs)` values to record independent identity/completeness decisions. Verdicts use PASS/FAIL/UNCERTAIN; decisive human assertions require existing usable evidence IDs from that case. Missing, unavailable and foreign references are rejected. Fixture citations remain explicitly `fixture_only` and support test workflow only, not genuine product conclusions. The override endpoint cannot add images, OCR, coordinates, model metadata, observations or confidence. Free-text reasons are attributed human statements, never parsed into visual evidence.

Human decisions overlay the reviewer-facing effective results with `source="human"` and an event revision. They never replace automated observations or results. Each event retains previous/new review state, actor identity, UTC timestamp, reason and override information/citations. Revisions and per-case command IDs prevent stale updates and duplicate retry events; reusing a command with changed content raises ConflictError. Case creation and its initial event, and each subsequent event, are transactional. There is no public history edit/delete API and no cryptographic immutability claim.

Condition-grade and disposition overrides are deliberately rejected until authoritative policies and their validation contract are available. The workflow cannot turn a human review into guessed restock/refurbish/liquidate/dispose logic. Original uncertainty reasons remain preserved after human decisions. Review identity is supplied by trusted local configuration or a future authentication layer; choosing an ID is not proof of authority. SQLite owner access remains outside application isolation. The queue currently reads full cases without pagination, and each worker must use its own Store connection. No HTTP endpoints, UI, genuine provider integration, image serving, evaluation or deployment were added.

## Engineering test result

Phase 4 final suite: **163 passed, 263 subtests passed in 10.42s; 0 failures, 0 errors, 0 warnings** on Python 3.13.4/pytest 9.1.1. The previous 143 tests are unchanged; 20 new tests cover the harness. These timings are test-runner durations, not provider telemetry.

Phase 2 final runs on 2026-09-26: **92 tests passed, 0 failures, 0 errors** per run (35 unchanged foundation tests plus 57 observation-layer tests). Executed `python -B -m unittest discover -s tests -q` on Python 3.13.4 without Pillow, and the same suite with the bundled Python/Pillow 12.3.0 runtime to exercise the actual corrupt-image decoder path. The standard verbose command above runs the same suite. These are engineering tests, not a 50-unit visual evaluation or an accuracy/latency/cost measurement.

After the two audit fixes: **96 tests passed, 0 failures, 0 errors**, using the same complete suite on Python 3.13.4. All 92 existing tests remain; four new regression tests cover invalid Unicode persistence/review handling, invalid Unicode metadata, unchanged valid-Unicode round trips and oversized-latency failure persistence.

Phase 3 final verification on 2026-09-26: `python -B -m unittest discover -s tests -q` -> **Ran 132 tests in 1.862s; OK. Passed 132, failed 0, errors 0.** All 96 existing tests are unchanged; 36 new synthetic engineering tests cover evidence lineage, explicit uncertainty, routing, transitions, history, overrides, policy boundaries, rejected forged inputs, bidirectional tenant isolation, unit/record isolation, retries, stale updates, rollback and persistence across connections/restarts. This duration is the test runner's duration, not inference latency or an evaluation measurement.

After the two Phase 3 audit fixes, review record/unit lookups use the same identifier validation as ingestion, preserving accepted long identifiers exactly without imposing the observation-text limit. One shared Unicode-scalar validator rejects invalid capture values, tenant/source lineage and observation/provider text without replacement or normalization. Invalid capture input raises ValidationError before persistence; valid Unicode is preserved. The observation-text limit remains 8,192 characters and is not an official identifier-length rule.

Added `tests/test_input_boundaries.py` with 11 focused regressions. Targeted pytest: **11 passed, 56 subtests passed in 1.48s**. Complete `python -m pytest submissions/karthikk-2003/tests/ -v` from repository root: **143 passed, 251 subtests passed in 4.20s; 0 failures, 0 errors, 0 warnings**. Bytecode/cache writes were disabled. All previous 132 tests remain unchanged and pass; these are engineering results only.

## Phase 4 evaluation foundation

Discovery rechecked the actual repository: 24 synthetic units (11 alpha, 13 bravo), 72 placeholder image references with zero resolving files, 24 historical identity=yes annotations, 24 blank condition grades and unverified parts expectations on every row. Five rows list one missing component. The data guide expressly prohibits using these annotations as ground truth. There is no separate 50-unit set, independent labels, complete applicable condition policy or condition-to-disposition mapping.

The harness executes one missing-evidence contract case per sample row plus ten labelled safety/fault probes for each of the two existing organizations. Each case uses a fresh in-memory Store; original source records/images are not edited. It preserves identifiers, source hashes/rows, evidence references, observed results and uncertainty/review reasons. The isolation probe verifies the same populated SQLite image through the other existing tenant's scoped Store. Expected outputs are engineering contract assertions from repository/internal rules, never guessed product labels. No human decisions or visual observations are fabricated.

The executed report contains **54 cases: 44 engineering PASS, 0 FAIL, 10 visual-scenario BLOCKED**. **34 cases have an actual UNCERTAIN/REVIEW state**, which overlaps PASS/FAIL and is not a fourth additive status. The 24 unchanged sample cases all retain UNCERTAIN identity/completeness/condition and pending_review disposition. All ten requested visual scenarios remain blocked; the detailed contract records the exact available annotation candidates and missing prerequisites for each. This is not 54 unseen units or completed visual scenario coverage.

Supported metrics are inventory/availability counts, observed per-layer verdict counts, engineering failure counts and deterministic review-reason distributions. Identity/component/physical-observation/condition/disposition accuracy and review precision/recall are BLOCKED with null values. Automated review routing is not independent human labelling. Real latency/cost and human agreement remain unmeasured. Repeated execution produced identical report bytes and preserved the source CSV hash.

Run from repository root (PowerShell):

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_ADDOPTS = '-p no:cacheprovider'
python -m pytest submissions/karthikk-2003/tests/ -v
$env:PYTHONPATH = Join-Path (Get-Location) 'submissions/karthikk-2003/agent'
python -B -m returns_manager.evaluation --output submissions/karthikk-2003/evaluation/results.json
```

See [evaluation/README.md](evaluation/README.md) for the internal report contract, exact probe definitions, exit codes, scenario blockers and required genuine benchmark collection. Exit 0 means no engineering failures, even while visual scenarios remain blocked.

## Expected layout from the template

The template lists README.md, 01-customer-letter.md, 02-prfaq.md, 03-one-pager.md, CLAUDE.md, build-brief.md, build-log.md, eval-report.md, contract/ and agent/. This README, planning documents and the Phase 1 package/tests exist. Other entries are deferred, not completed requirements. Current Round 2 instructions require the official evidence contract and explicitly reject a separately negotiated cross-pod contract.

## Status of template faces

- Face 1, customer letter/PRFAQ/one-pager: not created.
- Face 2, CLAUDE.md: not created.
- Face 3, headless agent on fixtures: Phase 1 foundation, Phase 2 fixture observation pipeline and Phase 3 backend review workflow; no real model inference or decisive grading.
- Face 4, evaluation report: Phase 4 engineering report executed; all ten genuine visual scenarios blocked. Separate unseen-unit benchmarking remains outstanding.
- Face 5, evidence record page: concept only.
- Face 6, cross-pod contract: template conflict; use official organiser contract for Round 2.

## Kill condition

Not yet established through customer validation. Proposed engineering stop gate: do not issue a definitive grade or disposition while its required evidence or governing policy is unavailable; preserve the case for review.

## Final submission work still outstanding

Full working inspection implementation, ARCHITECTURE.md, actual evaluation results, real demo video, deployment where applicable and required LinkedIn/submission links. Do not treat the fixture observation layer as a completed submission. Assumptions, limitations and questions are recorded in the build brief. All future writes remain within this participant directory unless the user changes the scope.
