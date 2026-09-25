# Returns Manager build log

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
