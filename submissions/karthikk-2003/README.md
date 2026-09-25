# karthikk-2003 - Returns Manager

Participant: Karthik Karunakaran (@Karthikk-2003, supplied handoff).

Status: Phase 1 headless foundation implemented. It validates and preserves synthetic CSV captures, isolates persisted records by tenant, and produces conservative review results. No vision inference, UI, authoritative grading/disposition policy, official wire-contract implementation or deployment exists.

This index is adapted from [submissions/_TEMPLATE/README.md](../_TEMPLATE/README.md), which requests a participant README. Current [RULES](../../RULES.md) and [GitHub guide](../../GITHUB-GUIDE.md) instead describe an own-fork workflow without requiring participant folders or organiser PRs. This directory follows the user's requested boundary and is compatible with the retained guard's path rule; it does not imply a PR is required.

## Current documentation

- [Build brief](build-brief.md): source-backed repository findings, proposed architecture, data/evidence contract, evaluation methodology, roadmap and open questions.
- [Build log](build-log.md): audit, implementation history and actual engineering test results.

## Implemented structure

- `agent/returns_manager/domain.py`: immutable internal tenant, unit, order, reference, capture, observation placeholder and separate result types.
- `agent/returns_manager/validation.py`: strict synthetic CSV adapter, source digest/row lineage and input/reference checks.
- `agent/returns_manager/rules.py`: pure missing-evidence rule scaffolding; no model calls or business-policy mappings.
- `agent/returns_manager/storage.py`: tenant-bound SQLite capture/result persistence and scoped record/unit/evidence-reference lookups.
- `agent/returns_manager/service.py`: persist capture before assessment, preserve failures, resume unfinished ingestion and reject conflicting duplicates.
- `agent/returns_manager/__main__.py` and `__init__.py`: local CLI and package entry.
- `tests/test_foundation.py`: explicitly synthetic engineering tests; no image generation or model output fixtures.
- `.gitignore`: excludes local runtime databases and temporary test directories within this directory.

## Setup, run and test

Requires Python 3.10+ with standard-library SQLite; tested here with Python 3.13.4. No pip dependencies, API keys or network access are needed. Run the following PowerShell commands from this participant directory:

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

Every photo reference remains **unavailable**. Input paths and URLs are never opened, fetched or served, even if a file happens to exist. There is no observation beyond an unavailable placeholder. Identity, completeness and condition are separate UNCERTAIN results with null confidence, no supporting image evidence, no assigned grade and no fabricated missing-component claims. Disposition is `pending_review`, with explicit blockers. Future decisive checks require a new implementation phase and validated evidence/policies.

SQLite lookups require a Store bound to an explicit trusted TenantContext and include organization and client scope in every query. Missing client_id remains JSON null and is an exact scope, not a wildcard or generated identifier. `--client` is only for a real trusted client context if one becomes available; the supplied data has none. No client IDs are invented in the implementation or tests. Actual client-level authorization remains unverified until real context is supplied.

This local CLI trusts the operator's organization argument; it is **not an authentication service**. Database file access is not protected against its local owner. A future server must derive tenant context from authentication rather than user-submitted fields and protect storage at the host level. Phase 1 prevents accidental cross-tenant application lookups and never serves image bytes.

Repeated ingestion of identical scoped record ID and full lineage returns the stored result without another assessment. Changed data or source lineage under the same scoped record ID raises ConflictError and does not overwrite prior input. Distinct organizations may use identical record/unit IDs safely. A processing exception preserves the committed capture, pending state and exception type (not sensitive exception text); an exact retry can resume when no assessment exists. Existing assessments cannot be silently replaced. Review overrides/version history are not implemented yet.

The JSON output is labelled `internal_only_not_official_wire_contract`; it is not a Recovery Manager interoperability claim. Exact official schema, condition rules and disposition policy remain unresolved. See the build brief for details.

## Engineering test result

Final run on 2026-09-26: **35 tests passed, 0 failures, 0 errors**, using `python -B -m unittest discover -s tests -v`. Includes all 24 units/both organisations through persistence, lineage, malformed input, absent images/client context, disposition validation, bidirectional isolation, guessed evidence references, idempotency/conflicts, injected failure/retry and CLI behavior. These are foundation tests, not a 50-unit visual evaluation or an accuracy/latency/cost measurement.

## Expected layout from the template

The template lists README.md, 01-customer-letter.md, 02-prfaq.md, 03-one-pager.md, CLAUDE.md, build-brief.md, build-log.md, eval-report.md, contract/ and agent/. This README, planning documents and the Phase 1 package/tests exist. Other entries are deferred, not completed requirements. Current Round 2 instructions require the official evidence contract and explicitly reject a separately negotiated cross-pod contract.

## Status of template faces

- Face 1, customer letter/PRFAQ/one-pager: not created.
- Face 2, CLAUDE.md: not created.
- Face 3, headless agent on fixtures: Phase 1 ingestion/persistence/review scaffolding only; no vision or decisive grading.
- Face 4, evaluation report: not run; methodology planned in the brief.
- Face 5, evidence record page: concept only.
- Face 6, cross-pod contract: template conflict; use official organiser contract for Round 2.

## Kill condition

Not yet established through customer validation. Proposed engineering stop gate: do not issue a definitive grade or disposition while its required evidence or governing policy is unavailable; preserve the case for review.

## Final submission work still outstanding

Full working inspection implementation, ARCHITECTURE.md, actual evaluation results, real demo video, deployment where applicable and required LinkedIn/submission links. Do not treat Phase 1 as a completed submission. Assumptions, limitations and questions are recorded in the build brief. All future writes remain within this participant directory unless the user changes the scope.
