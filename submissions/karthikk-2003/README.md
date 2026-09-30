# karthikk-2003 - Returns Manager

Participant: Karthik Karunakaran (@Karthikk-2003, supplied handoff).

Status: Phases 1-5, optional Ollama and Gemini observation providers, and an explicit image-to-review demo workflow are implemented. Offline tests cover the integrations. Live Gemini attempts on 2026-09-30 did not produce accepted observations: the diagnostic request returned HTTP 503 (model overload). Live AI presentation readiness is not established. Visual benchmarking, authoritative grading/disposition policies, the official wire contract and public deployment remain outstanding.

## One synthetic headphones reference case (2026-09-30)

The [headphones package and launch instructions](demo/README.md) bind the existing authorized local image to an explicitly **DEMO / SYNTHETIC REFERENCE DATA** order and parts list. Use the existing fixture UI command with `--demo-case headphones` and `--database runtime/headphones-fixture.sqlite3`. The image remains local and unchanged. The package hash verifies its bytes, not real product identity.

The existing DecisionReference now records `reference_status`: `operator_attested` by default for the prior library path, or `synthetic_demo` for this package. Synthetic references cannot produce decisive automated identity/completeness results even with a real provider. The fixture result has no invented observations, missing accessories, model telemetry or condition grade; disposition remains pending_review. Package verification identity/time, source snapshot/hash and review history use the existing storage contract. This is ready for a later authorized image-to-observation Gemini test, not a benchmark or verified real catalogue case.

Verification: **286 passed, 2 skipped, 427 subtests; 0 failures/errors**. Nine new local-photo tests use FixtureProvider and offline preparation; no Gemini/Ollama requests. These nine tests explicitly skip when the ignored authorized image or Pillow is absent. Full setup and expected results are in the package README.

## Source-backed policy extension (2026-09-30)

[Architecture and policy resolution](ARCHITECTURE.md) records the official challenge/handbook requirements, repository clarification, Verity context and narrowly researched Amazon guidance. The optional trusted `DecisionReference` now enables exact identity matching and evidence-backed completeness checks through the existing `assess` / `inspect_capture` pipeline. It is scoped to organization/client/record/unit/order and preserves the verifier, source snapshot and calculated digest. Existing synthetic CSV/default demo inputs are never automatically promoted into trusted references.

With genuine validated observations and a verified reference, identity/completeness can return PASS or FAIL with citations. Full-coverage absence can identify one or multiple missing parts; unknown/occluded evidence and partial counts remain uncertain. Fixture output cannot release these checks. The UI exposes the reference snapshot, rule version, per-check reasons/citations, missing components and unresolved components. Reference ingestion is a trusted library argument, not a new browser form; see the architecture document for its exact signature and prerequisites.

The Amazon condition source is identified, but applicable category/marketplace definitions and required nonvisual checks are not established for the supplied demo. Condition remains UNCERTAIN with grade null and physical-observation citations. No complete authoritative customer disposition rules were supplied; restock/refurbish/liquidate/dispose are allowed vocabulary, not an invented decision table. pending_review remains the automated outcome. A missing cable in the challenge example does not establish a universal refurbish rule.

Verification: **277 passed, 2 skipped, 427 subtests; 0 failures/errors/warnings**. Added 27 offline policy tests; no live API requests.

All older phase sections below describe their original scope; this extension supersedes statements that identity/completeness are universally scaffolding. No provider, UI transport or evaluation architecture was replaced. No real visual benchmark or live inference is claimed for this extension.

## Gemini demo workflow (2026-09-30)

The existing flow remains: prepared genuine image bytes -> explicitly selected VisionProvider -> raw response -> existing observation validation -> deterministic assessment -> persisted review/history. Gemini is a proposed primary live-demo provider; Ollama remains local/offline and FixtureProvider remains deterministic/test-only. No automatic provider fallback, model downloads, billing changes or business decisions were added. Gemini retries only explicit HTTP 429/500/502/503/504 responses, at most twice (three HTTP attempts per inspection); other failures are not automatically retried.

`gemini-3.8-flash` is the default configured candidate. Official [model documentation](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash) lists image input and structured output; [pricing](https://ai.google.dev/gemini-api/docs/pricing) lists standard Free-tier input/output. Authenticated model discovery listed it. The user's AI Studio screenshot showed the matching project on Free tier with Set up billing. Model discovery alone does not verify billing. Numeric quotas are project-specific; inspect [active rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) in AI Studio. Free-tier content may be used to improve Google's products: use non-sensitive demo photos only.

No new dependencies were added. The existing optional Pillow decoder in `requirements-images.txt` is needed for genuine JPEG/PNG inputs. REST uses the documented [generateContent endpoint](https://ai.google.dev/api/generate-content), the `x-goog-api-key` header and JSON-schema output. Images are inline base64; no file-upload service, tools, search or grounding is used. The application validator retains all length, scope, evidence, uncertainty and observation-only checks. Latency is measured client-side around the provider transport, including any retry delays; returned model/version, response ID and total token usage are retained only when supplied. Rejected raw responses are discarded by the existing safety contract.

From this participant directory, in PowerShell:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'agent'
$env:GEMINI_API_KEY = [Environment]::GetEnvironmentVariable('GEMINI_API_KEY', 'User')
$env:GEMINI_MODEL = 'gemini-3.8-flash'
$env:GEMINI_TIMEOUT_SECONDS = '90'
# Set only after confirming this key's project is Free tier, without billing.
$env:GEMINI_FREE_TIER_CONFIRMED = '1'
python -B -m returns_manager.ui --organization org_demo_alpha --reviewer karthikk-2003 --provider gemini --demo-image runtime/demo-images/headphones_smoke.png.png --database runtime/gemini-demo.sqlite3 --port 8000
```

The actual supplied filename has two `.png` suffixes. Open `http://127.0.0.1:8000/`. Inspect existing cases without invoking AI. The explicit **Inspect configured demo images** button sends one application request, persists its accepted observations or unavailable state, and opens the review case. Gemini transport may make up to three bounded HTTP attempts for transient failures; the browser never automatically repeats the inspection. Never click repeatedly to overcome quota/overload. A completed command can be retried with the same command ID without another inference; an interrupted persisted capture requires investigation rather than an automatic retry. The local server is single-process/synchronous and may be busy during inference. This is not production authentication or a background job service.

Only one to four launch-configured participant-local JPEG/PNG files can be used; browsers cannot choose arbitrary disk paths, providers or tenants. Display routes resolve scoped review evidence and verify the persisted SHA-256 against allowlisted bytes. Changed/unavailable images are not displayed. The demo records use new `DEMO-` record/unit IDs and explicitly synthetic unknown order/SKU/ASIN context, with the configured organization/reviewer and no invented client. Photos are genuine but are not benchmark data. The UI shows separate AI observations, model/latency when available, deterministic uncertainty, unassigned condition grade, pending-review disposition and attributed human history.

To switch, restart with `--provider ollama` or `--provider fixture`; use a separate demo database if desired. Ollama retains its existing `OLLAMA_*` configuration and may cold-start slowly. Fixture mode returns labelled empty synthetic observations with limitations, never visual claims. Default `--provider disabled` performs no inference. Gemini models currently permitted by the adapter are the documented Free-tier candidates `gemini-3.8-flash`, `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-3.5-flash`; configuration is explicit and availability is not guaranteed. `GEMINI_FREE_TIER_CONFIRMED` is a local operator confirmation, not an API billing attestation or protection against later account changes.

Offline verification (no live API calls):

```powershell
$env:PYTEST_ADDOPTS = '-p no:cacheprovider'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:GEMINI_LIVE_TEST = '0'
$env:OLLAMA_LIVE_TEST = '0'
python -B -m pytest tests/ -v
```

Optional one-inspection structural smoke (up to three HTTP attempts), after checking Free tier/quota and only when a live call is explicitly authorized. Further live Gemini requests are currently paused by the user:

```powershell
$env:GEMINI_LIVE_TEST = '1'
$env:GEMINI_LIVE_IMAGE = Join-Path (Get-Location) 'runtime/demo-images/headphones_smoke.png.png'
python -B -m pytest tests/test_gemini_live.py -v -s
Remove-Item Env:GEMINI_LIVE_TEST
```

The opt-in test skips without a key, image setting or Free-tier confirmation. A provider failure with those prerequisites present fails visibly; it does not become a fake pass. Do not run it merely to replay the existing demo. On 2026-09-30 three live image requests were attempted: two with 3.8 Flash (second for bounded error diagnosis, HTTP 503 high demand) and one explicit alternate 3.7 Flash attempt (generic HTTP failure). None yielded validated observations; no successful-inference latency, accuracy or 50-unit evaluation is claimed. The ignored demo database preserves the three unavailable review cases. Numeric active quota information was unavailable through model metadata; no quota-exhaustion probes were performed.

This index is adapted from [submissions/_TEMPLATE/README.md](../_TEMPLATE/README.md), which requests a participant README. Current [RULES](../../RULES.md) and [GitHub guide](../../GITHUB-GUIDE.md) instead describe an own-fork workflow without requiring participant folders or organiser PRs. This directory follows the user's requested boundary and is compatible with the retained guard's path rule; it does not imply a PR is required.

## Offline/local readiness check (2026-09-30)

Current regression result: **250 passed, 2 skipped, 427 subtests passed; 0 failures/errors**. Both live-provider tests were disabled. Nine new regressions exercise bounded retries, elapsed-budget exhaustion, explicit provider switching, 503 review routing without fallback or duplicate inference, complete fixture review/history, mocked Ollama persistence/latency, and unchanged application array limits. No Gemini API requests were made during this offline/local continuation.

Gemini retry delays use exponential jitter (0.5–1 seconds, then 1–2 seconds), with at most two retries. Numeric `Retry-After` values up to 30 seconds are respected; longer, invalid or unsupported values stop retries. Remaining timeout budget is checked before each attempt and sleep. The socket timeout bounds blocking operations, not a hard total deadline against a trickling response. Exhaustion produces `provider_unavailable` with sanitized `gemini_overloaded` or `gemini_rate_limited` diagnostics; no accepted observations, latency, grade or business disposition is fabricated. Authentication errors, ambiguous network failures and timeouts are not retried. There is no provider fallback.

Fixture inspection through review/history is verified with offline application tests. Start it from this participant directory:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'agent'
python -B -m returns_manager.ui --organization org_demo_alpha --reviewer karthikk-2003 --provider fixture --demo-image runtime/demo-images/headphones_smoke.png.png --database runtime/fixture-demo.sqlite3 --port 8000
```

Click **Inspect configured demo images** to create a labelled fixture review case. Fixture mode intentionally produces no visual findings, real-image evidence or inference latency. It demonstrates the workflow, not AI quality. Review can be completed with an attributed UNCERTAIN assertion; business status remains pending review.

Use the same workflow with local Ollama by stopping this UI server and starting:

```powershell
python -B -m returns_manager.ui --organization org_demo_alpha --reviewer karthikk-2003 --provider ollama --demo-image runtime/demo-images/headphones_smoke.png.png --database runtime/ollama-demo.sqlite3 --port 8000
```

Ollama selection, request/validation/persistence, image serving and returned latency are covered with explicitly mocked tests. Actual local inference is **not ready on the tested machine**: the service returned HTTP 500 reporting 6.9 GiB required versus 5.0 GiB available. A separate in-memory diagnostic using request `num_batch=64` reached the 240-second timeout with no accepted observations; this experimental setting was not adopted. No Ollama service lifecycle or OS memory settings were changed. The unavailable attempt remains reviewable in `runtime/ollama-demo.sqlite3`. Free sufficient local memory before another deliberate local test; success is not guaranteed by a higher timeout.

Source and API checks confirm configured provider/mode, accepted latency when present, unavailable evidence and pending-review rendering. Browser visual verification was blocked by browser permission policy; no fresh visual pass is claimed. A successful Gemini request is still needed to establish actual Gemini schema compatibility, accepted grounded observations and successful-inference latency. Official visual accuracy and the 50-unit evaluation remain separate uncompleted work.

## Current documentation

- [Architecture and policy](ARCHITECTURE.md): current flow, reference integration, source findings and unresolved policy.
- [Build brief](build-brief.md): source-backed repository findings, proposed architecture, data/evidence contract, evaluation methodology, roadmap and open questions.
- [Build log](build-log.md): audit, implementation history and actual engineering test results.
- [Evaluation contract/discovery](evaluation/README.md) and [executed JSON report](evaluation/results.json): reproducible engineering checks and explicitly blocked visual scenarios.

## Implemented structure

- `agent/returns_manager/domain.py`: immutable internal tenant, unit, order, reference, capture, observation placeholder and separate result types.
- `agent/returns_manager/validation.py`: strict synthetic CSV adapter, source digest/row lineage and input/reference checks.
- `agent/returns_manager/rules.py`: pure scoped identity/completeness checks with optional attested references; conservative missing-evidence behavior and no guessed disposition mappings.
- `agent/returns_manager/storage.py`: tenant-bound SQLite capture/result persistence and scoped record/unit/evidence-reference lookups.
- `agent/returns_manager/service.py`: persist capture before assessment, preserve failures, resume unfinished ingestion and reject conflicting duplicates.
- `agent/returns_manager/__main__.py` and `__init__.py`: local CLI and package entry.
- `tests/test_foundation.py`: explicitly synthetic engineering tests; no image generation or model output fixtures.
- `agent/returns_manager/observations.py`: observation dataclasses, strict raw JSON parser, evidence/scope validation and conflict detection.
- `agent/returns_manager/vision.py`: image-input boundary, provider protocol, fixture replay provider and failure-safe observation pipeline.
- `agent/returns_manager/ollama.py`: opt-in loopback HTTP observation provider using the existing internal contract.
- `tests/test_ollama.py` and `test_ollama_live.py`: isolated mocked integration tests and an explicitly opt-in live smoke test.
- `tests/test_vision.py`: synthetic observation/metadata fixtures, provider failures, isolation and integration tests.
- `agent/returns_manager/review.py`: internal human decision contracts and pure deterministic uncertainty routing.
- `agent/returns_manager/review_storage.py`: scoped evidence view, retry-safe review cases and append-only review events over an existing Store.
- `tests/test_review.py`: synthetic review, lineage, isolation, override and persistence tests.
- `agent/returns_manager/evaluation.py` and `evaluation_data.py`: isolated engineering cases, repository-data inventory, blocked scenarios and structured results.
- `tests/test_evaluation.py`: evaluation harness regression tests; no visual golden labels.
- `agent/returns_manager/ui.py`: standard-library, loopback-only WSGI adapter over existing scoped review APIs.
- `agent/returns_manager/ui_static/index.html`: semantic inspection workstation and native review dialog.
- `agent/returns_manager/ui_static/workstation.css`: desktop layout, responsive stacking and keyboard focus styles.
- `agent/returns_manager/ui_static/workstation.js`: vanilla JavaScript queue, inspection/evidence/history views and Fetch-based review actions.
- `tests/test_ui.py`: HTTP boundary, review/isolation regressions and real loopback endpoint smoke checks.
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

`VisionProvider.observe(VisionRequest)` receives one batch containing image descriptors, any validated image bytes and expected component names. It does not receive CSV identity/disposition/condition history. It must return a ProviderResponse containing raw JSON plus actual provider metadata where available. Phase 6 adds an explicitly selected Ollama adapter; no real provider is enabled by default. Adapters must enforce their network timeout, keep image contents as data rather than instructions, and provide real metadata or null. No API credentials are required or used in this implementation.

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

The library boundary still trusts the authenticated-context supplier and image registration caller; authentication and image ownership resolution must be provided by a future application. Parser validation establishes structure and declared provenance, not the truth of model assertions. Test success is not visual accuracy. Official wire export, business policy, deployment and genuine visual benchmarking remain unimplemented. Phase 5B exposes the supported human review actions in the local browser; Phase 6 enables optional library-level Ollama calls.

## Phase 6 optional local Ollama observations

`OllamaVisionProvider` implements the existing `VisionProvider` protocol. It uses the already-running local Ollama HTTP service; it never starts/stops Ollama, pulls models, calls a paid service, or needs an API key. The supplied setup is Ollama with locally installed `qwen2.5vl:3b`. The operator reported approximately 168 seconds cold and 12 seconds warm inference; these are supplied setup observations, not measurements or performance claims from this integration.

From this participant directory, configure the calling Python process:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'agent'
$env:OLLAMA_BASE_URL = 'http://localhost:11434'
$env:OLLAMA_MODEL = 'qwen2.5vl:3b'
$env:OLLAMA_TIMEOUT_SECONDS = '240'
```

These values are also the defaults. `OllamaConfig.from_env()` reads them when constructing a provider. Timeout must be finite and positive, with an implementation ceiling of 86,400 seconds. It is the HTTP socket-operation timeout, not a total wall-clock deadline. Allow for the reported cold start. Invalid configuration is rejected before a request. Explicit `OllamaConfig(...)` is also supported. Only loopback HTTP bases without credentials, paths or queries are accepted. `localhost` connects directly to 127.0.0.1; environment proxies and redirects are disabled. Known `:cloud`/`-cloud` model suffixes are rejected. Select a locally installed model and keep the daemon itself locally configured; the adapter cannot attest to daemon internals.

The adapter uses [Ollama chat](https://docs.ollama.com/api/chat), [structured output](https://docs.ollama.com/capabilities/structured-outputs) and [base64 image inputs](https://docs.ollama.com/capabilities/vision): one non-streaming `/api/chat` request, a JSON schema in `format`, temperature 0, a 1024-token generation cap, and explicit image/evidence mapping in attachment order. The schema is not duplicated in the user prompt. Generation omits large `maxLength`/`maxItems` grammar repetitions; application limits of 8192 characters and 200 array entries remain enforced. Output stopped by the token cap is rejected, never repaired or accepted partially. Unverified expected parts are labelled as context, not observations. The prompt prohibits grades/dispositions, guessed OCR/identifiers, fabricated evidence and treating occlusion as absence. Schema constraints do not prove a model's visual assertions true.

The existing image boundary decodes genuine JPEG/PNG bytes before any provider request. Use the already documented optional Pillow installation for genuine image validation. No new dependency was added. Missing/corrupt images or missing decoder keep their existing unavailable states. Fixture metadata cannot be sent to this real provider.

Enable it through the existing library call, using a real capture-bound `row`, `source`, scoped `store`, and explicitly supplied `ImageInput` tuple `images`:

```python
from returns_manager.ollama import OllamaVisionProvider
from returns_manager.service import inspect_capture
from returns_manager.review_storage import ReviewWorkflow

# images must already contain genuine bytes and existing capture references,
# scoped image/evidence IDs, and ObservationScope.from_capture(capture).
attempt_id = inspect_capture(row, source, store, images, provider=OllamaVisionProvider())
review_id = ReviewWorkflow(store).route(row['record_id'], row['unit_id'], attempt_id=attempt_id)
```

This is an integration snippet, not a seed command: supply actual registered image inputs. Do not bind an unrelated photo to a sample return. The CSV CLI and browser do not upload images or invoke inference, and setting environment variables alone does not enable a provider there. Image ownership/registration remains the trusted caller's responsibility. The scoped review can display an accepted attempt through the existing UI; image bytes are still not served.

Raw `message.content` is returned unchanged and validated by the existing `observe()`/`parse_response()` pipeline before domain observations, deterministic rules or persistence. No code-fence stripping, JSON repair, partial acceptance or fallback observations occur. Unknown fields, policy fields, forged citations and foreign scope fail existing validation. Conflicts remain separate. Without an attested DecisionReference, identity/completeness remain UNCERTAIN. With one, the scoped deterministic checks may resolve those dimensions from sufficient genuine observations. Condition grade remains null and disposition pending_review under current policy/evidence gaps.

Accepted model text and existing image descriptors/hashes/source lineage are persisted. The full Ollama HTTP envelope is not stored by the current contract. Returned model name is recorded in `model_version` as a tag, not an immutable model digest. Actual `total_duration` is converted from nanoseconds to milliseconds; token usage is the sum of actual prompt/output counts only when both are present. Missing metadata stays null; no request ID, confidence or replacement telemetry is invented. Malformed/overflowing metadata is rejected. These values describe daemon-reported generation, not end-to-end application latency.

Connection/HTTP errors route to provider_unavailable; socket timeouts to provider_timeout; malformed/incomplete envelopes and other provider exceptions to provider_failure. Invalid observation JSON/schema routes to invalid_response, and foreign scope to response_scope_mismatch. All use the existing unavailable/review mechanism. As before, rejected raw content is discarded, not persisted under a potentially wrong owner. There are no automatic retries, streaming fallback or additional review/business states.

### Offline and optional live tests

Standard tests are offline, independent of Ollama. The new successful-path tests mock the transport and decoder with explicitly labelled TEST bytes; they do not create fake image files or claim model output. Missing/corrupt-image checks exercise the actual image boundary. `FixtureProvider` continues to work unchanged.

```powershell
# From repository root; no live Ollama required:
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_ADDOPTS = '-p no:cacheprovider'
python -m pytest submissions/karthikk-2003/tests/test_ollama.py -v
python -m pytest submissions/karthikk-2003/tests/ -v
```

Optional live smoke requires deliberate opt-in, an already-running local daemon/model, the existing image decoder and an operator-selected genuine image. From repository root:

```powershell
$env:OLLAMA_LIVE_TEST = '1'
$env:OLLAMA_LIVE_IMAGE = Read-Host 'Absolute path to your genuine JPEG or PNG'
python -B -m pytest -p no:cacheprovider submissions/karthikk-2003/tests/test_ollama_live.py -v
Remove-Item Env:OLLAMA_LIVE_TEST
Remove-Item Env:OLLAMA_LIVE_IMAGE
```

The live smoke uses an explicit TEST context in the existing alpha organization, no invented client, and persists nothing. It skips when not opted in, image/decoder unavailable, or the provider is unavailable/times out. A structurally invalid model response fails the opted-in test. Even a pass proves only transport/schema integration, not correct visual findings or benchmark accuracy. It does not complete any portion of the 50-unit visual evaluation.

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

## Phase 5 local browser workstation and boundary

No new runtime dependency is required. From this participant directory, supply your actual local reviewer identity explicitly:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'agent'
$reviewerId = Read-Host 'Your actual reviewer identifier'
python -B -m returns_manager.ui --organization org_demo_alpha --reviewer $reviewerId --port 8000
```

Open `http://127.0.0.1:8000/`. The exact numeric host is required; `localhost` is not an accepted Host alias. The server always binds to 127.0.0.1, defaults to participant-local `runtime/returns.sqlite3`, and accepts `--database` only for a `.sqlite3` path within the participant directory. `--client` is optional and must identify actual trusted client context; omission remains the exact null scope. Missing/invalid reviewer configuration fails startup. Sample `op_*` values are dummy capture operators, not authenticated reviewer identities.

This is trusted local configuration, **not production authentication**. Organization and reviewer identity are configured on the server, never taken from browser fields or identity headers. Python's reference WSGI server is for the local demo, not public hosting. Do not expose it with a public tunnel or reverse proxy and claim authentication.

Startup initializes SQLite schemas but does not seed captures, call a provider, route reviews or append events. A new database returns an empty queue. Existing ingestion alone does not create review cases. A trusted local caller can explicitly call `ingest(row, source, store)` and then `ReviewWorkflow(store).route(record_id, unit_id)` for its selected organization, as described in the Phase 3 library example. There is deliberately no import/upload/routing browser endpoint in Phase 5A. Tests seed only their own temporary databases; the server never imports test modules or the mixed-tenant evaluation report.

Internal routes (not the official Buildathon schema):

- `GET /health`: `{"status":"ok"}`; confirms the adapter is responding, not model/database readiness.
- `GET /api/context`: read-only configured organization, optional client, reviewer, local-demo environment and internal-contract notice. Browser identity overrides are rejected.
- `GET /api/reviews`: `reviews` containing minimal identifiers, exact scope, source key, status/business status, revision, timestamps, uncertainty and unresolved decisions. Optional `?status=pending_review`, `in_review` or `reviewed` uses the existing workflow filter.
- `GET /api/reviews/{review_id}`: review metadata, capture order/reference/provenance, evidence descriptors, normalized observations, accepted raw response if available, separate automated/human/effective results and allowed transitions. Historical CSV labels are not projected as current findings. Null grade/confidence and unknown/occluded component states are preserved.
- `GET /api/reviews/{review_id}/history`: existing events, with `(review_id, revision)` as event identity. Actors, reasons, timestamps, prior/new state and overrides are retained. Append-only through the workflow API does not mean cryptographically immutable.
- `POST /api/reviews/{review_id}/transition`: existing transactional workflow transition; response contains the actual appended or replayed `event` and `review_id`. Reload detail after success to obtain current state. No vision run or original assessment is modified.

Case IDs are numeric review IDs. The adapter resolves their record/unit association via the tenant-scoped public queue, then calls the scoped get/history/transition API. There is no adapter SQL. This O(n) resolution is intended for the small local dataset. Multiple observation attempts can have separate review cases for one return. Each request opens/closes its own Store; browser GETs never route cases or create events.

Transition JSON requires exactly `status`, `reason`, `expected_revision` and `command_id`, plus optional `decisions`. Each decision has exactly `dimension`, `verdict`, `evidence_refs`; existing domain rules allow only identity/completeness PASS/FAIL/UNCERTAIN and require usable citations for decisive assertions. Condition/disposition overrides remain rejected. The server does not invent IDs, grades, missing components or evidence. Fixture citations retain `fixture_only` provenance. A reviewed workflow still has `pending_review` business status.

For same-origin browser mutations, send `Content-Type: application/json` and `X-Returns-Request: 1`; the browser supplies its `Origin`. An example body for an existing revision-1 case is:

```json
{"status":"in_review","reason":"Starting review of unavailable evidence","expected_revision":1,"command_id":"<unique-command-id-for-this-action>"}
```

Generate a command ID once for each intentional action and reuse the exact body/ID when retrying an uncertain network result. Do not automatically retry a stale revision with a new revision number. Existing revision and command-conflict safeguards return 409.

Boundary protections: exact configured Host, loopback peer, same-origin checks, rejection of cross-site/same-site Fetch Metadata, required Origin plus custom header for POST, JSON-only mutations, maximum 65,536 body bytes, strict field allowlists, duplicate-key/invalid-Unicode rejection and no CORS allowance. These stop cross-origin browser actions but are not authorization against other local processes/users. Responses use no-store, nosniff, same-origin resource policy, frame denial and restrictive CSP. The workstation renders untrusted strings with textContent/createTextNode, including raw provider JSON; it never inserts them as HTML. CSP permits only same-origin scripts, styles and Fetch connections, with no inline scripts, remote assets or frames.

Only `/`, `/assets/workstation.css` and `/assets/workstation.js` serve fixed allowlisted assets. Request paths are never joined to filesystem paths. No image bytes, CSV, database, source modules, directory listing or evaluation/results.json are served. Evidence references are literal provenance strings, never fetchable image URLs supplied by this adapter.

All errors use `{"error":{"code":"...","message":"..."}}`: 400 malformed/unsupported fields or query, 403 local/origin boundary rejection, 404 unavailable scoped resource, 405 unsupported method, 409 review conflict, 413 excessive body, 415 unsupported media type, 422 existing domain validation failure, 500 unexpected internal error. Errors do not echo exception text, SQL, stack traces or server paths. A 500/network failure after an attempted write should be reconciled by retrying the same command or reading history, not assuming success or failure.

### Workstation and sample demonstration

The single-page workstation uses plain HTML/CSS/JavaScript and Fetch, without npm or a build step. It contains a filtered review queue, return metadata, expected/observed identity, component comparison, physical observations, evidence lineage, uncertainty reasons, supported human decisions and expandable audit history. Loading a new case clears the previous case's panels. Errors offer safe retries; empty queues say "No review cases in this scope."

The Reopened filter uses an adapter-derived flag from actual scoped history: the case is in_review and its latest status-changing event came from reviewed. This is not a new workflow status or business decision. Saving within that reopened state preserves the flag. Identity/completeness human assertions remain separate from original automated results. Unknown/not-visible components never become missing merely because an observation is absent.

For an explicit sample demonstration, run this once from the participant directory before starting the server above. This imports only the unchanged alpha sample rows and routes their existing missing-evidence assessments. It does not invoke vision, create photographs or seed human review decisions. Repeating it preserves existing cases/history.

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'agent'
@'
from pathlib import Path
from returns_manager.domain import TenantContext
from returns_manager.storage import Store
from returns_manager.service import ingest
from returns_manager.validation import read_csv
from returns_manager.review_storage import ReviewWorkflow

Path("runtime").mkdir(exist_ok=True)
context = TenantContext("org_demo_alpha")
with Store(Path("runtime/returns.sqlite3"), context) as store:
    workflow = ReviewWorkflow(store)
    for row, source in read_csv(Path("../../data/returns_sample.csv")):
        if row["org_id"] == context.organization_id:
            ingest(row, source, store)
            workflow.route(row["record_id"], row["unit_id"])
'@ | python -B -
```

Demo flow: select a return; inspect expected identity, unknown components and unavailable physical observations; follow evidence references and source lineage; read the explicit review reasons; open Review actions; start review with a legitimate explanation; record only supported assertions; inspect the updated revision and audit history. A reviewed case still shows business disposition pending review. Every reference is visibly synthetic/unverified; unavailable image bytes are represented by text placeholders, not photographs. Actual provider JSON, if stored, appears as escaped text. Conflicting observations are retained independently.

Every mutation requires a reason, uses the server-configured reviewer and submits the current revision plus a once-generated command ID. Available transitions come from the backend. Decisive identity/completeness assertions require existing usable citations; no condition/disposition overrides exist. Duplicate clicks are disabled during saving. A stale revision reloads current detail/history, retains the explanation and requires deliberate reselection before resubmission. A timeout/network/5xx outcome locks the pending body and offers Retry same action with its original command ID. Pending bodies/drafts are kept in page memory only: keep the page open while reconciling an uncertain save; after a reload, check history before starting a new action.

Semantic controls, labelled inputs, a native modal dialog, visible keyboard focus, a skip link and live status/error announcements support keyboard use. The sidebar/panels stack on narrow screens and wide tables scroll within their container. This is not a formal accessibility certification. The local server has no production authentication, image-serving/upload facility, automatic inference route or finalized grading/disposition policy.

## Engineering test result

Phase 6 baseline: **197 passed, 355 subtests passed in 9.48s**. Targeted Ollama tests: **19 passed, 1 skipped, 53 subtests passed in 0.32s**. Complete suite: **216 passed, 1 skipped, 408 subtests passed in 6.85s; 0 failures, 0 errors, 0 warnings**. The skipped test is the deliberately opt-in live smoke. All previous 197 tests are unchanged and passing. No live inference or genuine visual evaluation was executed for this phase.

Phase 5B final: **197 passed, 355 subtests passed in 8.57s; 0 failures, 0 errors, 0 warnings**. Baseline was 192 passed / 348 subtests in 8.96s. All 192 prior tests remain; five adapter regressions cover trusted context, static/CSP boundaries, reopened history derivation, scope isolation and read-only GET behavior. Actual browser smoke covered selection, unavailable evidence, required reasons, successful review/history refresh, stale-revision draft preservation and retry after a deliberate server interruption. Desktop 1440px and narrow 390px checks showed no horizontal page overflow. These are engineering checks, not real visual inference or benchmark results.

Phase 5A: **192 passed, 348 subtests passed in 10.40s; 0 failures, 0 errors, 0 warnings**. All previous 163 tests remain unchanged; 29 adapter tests were added. The suite includes real ephemeral loopback HTTP checks for the shell, health, scoped queue/detail/history and review transition; all returned 200 for valid requests. No external provider or production identity was used.

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
- Face 5, evidence record page: Phase 5B local workstation with lineage, unavailable evidence, observations and review history; genuine image display is unavailable.
- Face 6, cross-pod contract: template conflict; use official organiser contract for Round 2.

## Kill condition

Not yet established through customer validation. Proposed engineering stop gate: do not issue a definitive grade or disposition while its required evidence or governing policy is unavailable; preserve the case for review.

## Final submission work still outstanding

Full working inspection implementation, ARCHITECTURE.md, actual evaluation results, real demo video, deployment where applicable and required LinkedIn/submission links. Do not treat the fixture observation layer as a completed submission. Assumptions, limitations and questions are recorded in the build brief. All future writes remain within this participant directory unless the user changes the scope.
