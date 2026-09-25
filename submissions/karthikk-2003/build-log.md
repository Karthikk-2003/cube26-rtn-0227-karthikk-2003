# Returns Manager build log

## 2026-09-26 - Fix the two Phase 2 P2 audit findings

Changed only observations.py, tests/test_vision.py, this log and the participant README. Strict UTF-8 scalar validation now rejects lone surrogates in raw responses, decoded observation text and textual metadata, without sanitizing values. Latency validation converts numeric-conversion OverflowError into ValidationError rather than letting it escape. Existing orchestration turns these rejected responses into explicit unavailable runs, persisted failure attempts and pending_review outcomes; it does not invent replacement observations or telemetry.

Added four focused tests: test_invalid_unicode_identity_persists_only_safe_failure (escaped/literal high and low surrogates); test_invalid_unicode_provider_metadata_is_rejected; test_valid_unicode_round_trips_without_sanitizing (literal/escaped valid Unicode); test_oversized_latency_persists_safe_unavailable_state. Existing tests were not weakened or removed.

Complete suite: `python -B -m unittest discover -s tests -q` on Python 3.13.4 -> **Ran 96 tests in 1.666s; OK. Passed 96, failed 0, errors 0.** This is the existing 92 tests plus four regressions; the duration is a test-runner duration, not provider latency.

No architecture redesign, Phase 3 work, dependency changes, cache changes, commit or push. All edits remain inside submissions/karthikk-2003/. The pre-existing Phase 2 changes remain uncommitted; existing real-provider/evidence/policy dependencies are unchanged.

## 2026-09-26 - Phase 2 vision observation layer

Started from `526ae19` (`feat: implement returns manager foundation`) with a clean working tree. Read the supplied Phase 2 request and existing brief/log/README/domain/rules/service/storage/validation/tests. The request's test path under `agent/returns_manager/tests/` does not exist; used the actual participant `tests/test_foundation.py`. Baseline command `python -B -m unittest discover -s tests -v`: **35 tests passed, 0 failures, 0 errors** before changes.

Implemented only the observation layer:

- New observations.py defines structured identity/component/condition findings, explicit uncertainty, image descriptors, raw provider envelope, strict parser/validator and conflict flags. It checks organization/client/unit/record association, provided evidence IDs, values/types, quantity visibility, coverage-based absence assertions and scoped negative findings. No condition scale or disposition policy was introduced.
- New vision.py defines the replaceable VisionProvider protocol, batched request, explicitly synthetic FixtureProvider, optional genuine PNG/JPEG byte validation and failure-safe orchestration. No real provider is configured or called. Fixture telemetry stays null. No generated photos, inferred OCR or fabricated coordinates were created.
- Small integration changes allow validated observations into the existing deterministic rules. Business results remain UNCERTAIN/pending_review with no grade. Original capture lineage and Phase 1 assessment behavior are retained.
- SQLite receives an additive vision_attempts table. Valid raw responses, normalized observations and assessments are stored separately per scoped capture. Invalid/foreign raw responses are not retained; errors remain explicit. Repeated explicit observation calls append attempts. Stored normalized results cannot bypass raw-response lineage through the Phase 1 assessment API.
- Added requirements-images.txt for optional Pillow 12.3.0 image validation and tests/test_vision.py containing clearly labelled synthetic JSON/metadata cases. Existing foundation tests and CSV were not edited. README documents the API, provider responsibilities, schema limits, failures, isolation, optional decoder and unimplemented dependencies.

Tests executed:

1. Baseline: 35/35 passed before modifications.
2. Initial full suite: 89/89 passed (35 Phase 1 + 54 Phase 2).
3. Boundary review added positive/negative identity conflict detection, explicit unconfigured-provider provenance and a guard requiring raw-response lineage for persisted vision assessments, with three additional tests.
4. Final system Python 3.13.4 run, no Pillow: `python -B -m unittest discover -s tests -q` -> **Ran 92 tests in 1.385s; OK. Passed 92, failed 0, errors 0.**
5. Final bundled Python run with Pillow 12.3.0: same unittest discovery command -> **Ran 92 tests in 1.517s; OK. Passed 92, failed 0, errors 0.** This also executes the corrupt/truncated image decoder path. No genuine product image or real multimodal inference was tested. Timings are test-runner durations, not provider latency or model performance.

Coverage includes valid/invalid/empty raw responses, duplicate JSON keys, provider failures/timeouts, unknown/ambiguous/conflicting identity, supplied OCR fields, component visibility/quantity/absence validation, multiple components/images/citations, scratches/damage/scoped negative findings, blur/glare/occlusion limitations, invalid evidence IDs, cross-organization/unit/record rejection, raw/normalized consistency, review routing, append-only attempts and Phase 1 database compatibility. No visual evaluation or model-accuracy measurement occurred.

Files created: agent/returns_manager/observations.py, agent/returns_manager/vision.py, requirements-images.txt, tests/test_vision.py. Files modified: agent/returns_manager/domain.py, rules.py, service.py, storage.py, participant README.md and build-log.md. Final git status and content checks confirmed four created/six modified files, all inside submissions/karthikk-2003/; all other tracked files match HEAD, the index is unchanged, git diff --check passes and the temporary test directory is empty.

Unresolved: real provider adapter/configuration and genuine returned-item/catalogue evidence; authenticated organization/client and image ownership resolution; authoritative condition/category definitions; disposition policy; official wire schema/hash procedure; durable image byte storage. Provider adapters must enforce transport timeouts. Parser/fixture tests validate engineering contracts, not the truth of visual observations. Optional image decoding is an input-integrity check, not vision inference.

Stopped after Phase 2. No UI, full review workflow, final business policy, evaluation, deployment, hosting, demo/submission work, commit or push.

## 2026-09-26 - Phase 1 headless foundation

Started from committed planning baseline `680f2be` with a clean working tree. Re-read the requested planning/repository/data/guard files. All implementation is inside `submissions/karthikk-2003/`; build-brief.md, root files, CSV and repository protection files were not modified.

Implemented a standard-library Python package with immutable internal domain types, strict synthetic CSV validation, exact source/raw-field lineage, unavailable observation/image placeholders, four separate deterministic result layers, tenant-bound SQLite persistence and a local CLI. Added the participant-local ignore file and synthetic engineering tests; updated this log and the participant README with actual setup/run/test instructions.

The adapter retains all 24 unit IDs, both supplied org IDs, record/order/product identifiers, operator/timestamp, image references and historical source values. Missing client context remains null. No client IDs, confidence, grades, observations, image evidence or policy mappings were invented. Missing evidence/reference/policy produces UNCERTAIN and pending_review. Historical annotations are lineage only. Explicit component quantities are parsed without guessing quantities for unqualified entries.

Persistence checks organization and client scope on writes and every public lookup, including evidence-reference access. Identical scoped input is idempotent; conflicting lineage cannot overwrite it. Captures commit before assessment; an injected processing timeout leaves a recoverable pending record and error type. Exact retries resume unfinished processing. CLI output is internal JSON, not the official wire contract. This is a trusted local operator tool, not a deployed authentication or image-serving service.

Files created: participant `.gitignore`; `agent/returns_manager/__init__.py`, `__main__.py`, `domain.py`, `validation.py`, `rules.py`, `storage.py`, `service.py`; `tests/test_foundation.py`. Files modified: participant README.md and build-log.md. Test fixtures are clearly labelled in the test module; no fake image files or evaluation artifacts were created.

Verification command (from the participant directory): `python -B -m unittest discover -s tests -v`, Python 3.13.4.

- Initial sandboxed execution: 33 setup errors because the shell sandbox denied temporary-directory creation; no test assertions ran.
- Execution with permission for participant-local test writes: initial 33 tests passed.
- Expanded suite: 35 tests, two Windows cleanup errors from unclosed direct SQLite connections in the tests. Fixed those test connections with contextlib.closing.
- Final complete run: **Ran 35 tests in 0.998s; OK. 35 passed, 0 failures, 0 errors.** The duration is unittest runner output, not agent inference latency.

Coverage includes all 24 records persisted and isolated in both directions; all 72 image references unavailable; preserved lineage; required identifiers and UTC timestamps; malformed CSV/components; missing references/client context; rejected dispositions; guessed record/unit/evidence and SQL-like lookups; same IDs in different tenants; idempotency/conflicts; immutable result checks; injected timeout/retry; selected-organization CLI import and rejection of database paths outside the participant directory.

Final boundary check: nine new files and two modified files, all within the participant directory. All other tracked files match HEAD (allowing checkout line-ending normalization), the index is unchanged and git diff --check found no whitespace errors. Removed the two temporary test directories left by the earlier cleanup errors; no test databases remain.

Unresolved for later phases: exact official wire schema and hash semantics; authoritative marketplace/category condition rules; approved disposition policy; actual authenticated client context; real image/catalogue evidence. No visual evaluation was run. The earlier 50-unit plan remains a methodology only. No Phase 2, UI, vision integration, deployment, commit, staging or push was performed. Stop at Phase 1.

## 2026-09-26 - Repository reconnaissance and architecture planning

Status: documentation only; application implementation has not started.

Audited all 11 tracked files at `1fd99008f88b6cda0e7d1613ec64f879bc0f3661`: root README, RULES, GITHUB-GUIDE, .gitignore, data guide and CSV, participant template, PR template, CODEOWNERS, workflow and guard. Read the supplied 18-page handbook and both pasted context attachments. Inspected local status, origin and relevant Git history. Initial working tree was clean; origin identifies Karthikk-2003's named fork. No source code, images, tests or machine-readable evidence schema exists in the starter checkout.

Verified boundary before writing: current repository prose permits work throughout one's own fork and explicitly does not require a participant folder/organiser PR. Retained template and PR guard still use participant folders. Under the user's stricter task scope, all writes are confined to `submissions/karthikk-2003/`, which matches the origin owner and the case-insensitive guard prefix. Every existing file and all protection mechanisms remain untouched.

Important findings:

- Guard checks PR author/branch equality and changed path prefix, case-insensitively, except configured organiser bypass. It runs on specified PR events targeting main, not pushes, and executes the base script. It is not a schema, application, secrets or deadline validator.
- Current main branch is not a username branch. No branch change or PR was requested or performed.
- CSV inspection found 24 distinct units, two existing organisations, 72 nonexistent image references, all identity labels yes and all condition grades blank. These are dataset audit facts, not agent evaluation results.
- Amazon's published scale is explicitly required. An Amazon staff overview was retrieved; full applicable marketplace/category definitions remain unresolved because the linked help page requires access. No alternative scale or sample-state grading map was invented.
- Dispositions supported by repository: restock, refurbish, liquidate, dispose, pending_review. UNCERTAIN is a first-class check result. Neither a complete disposition policy nor an exact wire schema is supplied.
- unit_id is the cross-stage join key. Persistent records and images require organisation/client isolation; CSV org IDs are retained and absent client IDs must not be invented.
- Two humans and 50 unseen units are planned for evaluation. Sample annotations and placeholder paths cannot substitute for evidence.

Created only [build brief](build-brief.md), this log and [participant README](README.md). README derives its index/layout/status purpose from the supplied template while recording conflicts with current Round 2 instructions. No additional template deliverables, application files, fake evidence or evaluation artifacts were created.

Architecture status: proposed separated capture, vision observations, deterministic checks/policy, official-contract adapter, tenant-scoped evidence storage and inspector/review UI. Four decision layers remain traceable. The brief includes a 50-unit collection/scoring method, error paths, roadmap and unresolved questions.

Next recommended phase: on a subsequent implementation request, begin a headless contract/capture foundation with tenant/unit preservation and missing-evidence review routing. Resolve official schema, category rules and disposition policy before final grading or interoperability claims. Collect genuine development/evaluation evidence and arrange independent labelers early.

Verification scope: documentation links/content and changed-file boundaries only. No application tests, model calls, measured evaluation, live portal verification, commit, staging, push, PR or deployment occurred.
