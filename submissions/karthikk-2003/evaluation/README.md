# Phase 4 evaluation contract and discovery

This is an internal, deterministic engineering evaluation of the repository's available synthetic sample. It is **not** the official evidence wire schema, a visual benchmark, or the required separate 50-unit evaluation. Scenario names follow the Phase 4 request and the planning brief. No product photographs, labels, condition definitions, business policy or model output are generated here.

## Discovery and authority

Inspected at checkpoint `fd88e20`: root README/RULES/GitHub guide, data guide/CSV, participant brief/log/README, all current domain/validation/rules/service/storage/vision/observation/review modules and existing test fixtures. The tracked repository has no separate evaluation dataset, image assets, catalogue reference images, formal official wire schema, or complete applicable condition/disposition policy. The build brief records partial external condition information but explicitly leaves full marketplace/category rules and business policy unresolved. This phase does not infer those missing definitions.

The data guide explicitly says the CSV is dummy data and must not be treated as ground truth. The harness uses its annotations for inventory and candidate descriptions only. It never compares predictions against historical identity, condition, parts-missing or disposition annotations as accuracy labels.

The checked-in sample contains:

- 24 rows, distinct record IDs and distinct unit IDs; 11 alpha and 13 bravo rows.
- Every unit has three placeholder image references: 72 distinct references. None resolves to a file under either repository-relative or data-directory-relative interpretation.
- All 24 identity annotations are `yes`; zero `no`/`uncertain` annotations. These cannot establish correct-product accuracy or wrong-product coverage.
- All 24 condition grades are blank. No authoritative condition labels exist.
- All rows list synthetic expected parts. Five rows list exactly one missing part: UNIT-0021 (puzzle pieces), UNIT-0038 (tub), UNIT-0050 (poster), UNIT-0092 (dropper), UNIT-0097 (scoop). These are unverified expectations/annotations, not observations.
- Historical states: 3 factory_sealed, 10 opened_unused, 4 signs_of_use, 6 damaged, 1 uncertain. No supplied severity definition establishes lightly/heavily damaged grades.
- Historical dispositions: 10 restock, 5 refurbish, 5 liquidate, 3 dispose, 1 pending_review. None is authoritative ground truth. UNIT-0038 combines a missing-tub annotation with restock; B0DUMMY357 is used for different SKUs. Neither fact licenses a business-policy inference.
- No client IDs, independently paired human labels or genuine returned/reference image set.

The machine-readable inventory lists every organization/unit/record, annotation and reference, with the exact relative paths checked. Presence checks do not open image bytes or fetch URLs; external/traversal paths are rejected, unreadable metadata is explicit, and a found file is only `present_unverified`. File existence is not proof of a valid, owned image or sufficient visual coverage.

## Layers and expected behavior

1. **Input/data quality:** run each unchanged CSV row through the existing input pipeline. Controlled negative probes derive copies of representative rows; original CSV bytes are never edited. Missing required order ID, invalid Unicode operator, duplicated photo reference and unsupported historical disposition must be rejected without persisted partial records.
2. **Observation quality:** without images or a real provider, actual visual correctness is BLOCKED. Missing evidence and deliberately invalid non-image bytes must not become findings; malformed fixture JSON and an injected timeout must yield unavailable observations and review. Existing Phase 2 tests exercise synthetic identity/component/condition ambiguity and conflicts; those tests are engineering validation, not visual scenario coverage. This harness does not relabel them as a benchmark.
3. **Decision/routing quality:** separate identity/completeness/condition results must remain UNCERTAIN with null confidence/grade, no manufactured missing components, and pending review. Preserve input/reference/source lineage and policy/context reasons. Repeated ingestion/routing must remain idempotent, and repeated pure rule calls must agree.
4. **Isolation/failure safety:** each case has a fresh in-memory SQLite Store. For each existing organization, the isolation probe clones its populated SQLite image into another in-memory Store bound to the other existing organization. It checks record/unit/evidence/attempt/queue/history reads, review routing, review-update and capture-write rejection, plus wrong record/unit lookups. This is application-scope testing, not authentication testing. A SQLite trigger deliberately rejects review-event insertion; the case must roll back without losing its capture, then succeed on retry without duplicate history. No persistent runtime database is modified.

There are ten named control kinds per organization, plus one unchanged-input contract case per CSV row. Probe kind, original source lineage and code hashes identify the reproducible mutation/fault. Fixture descriptors refer to existing sample placeholder references, are marked TEST/fixture_only, and supply no visual findings. Invalid bytes are explicitly non-image failure input, not a fabricated photograph. Human overrides are not executed by the evaluator; automated routing is not a human label or adjudication.

## Result contract

`internal-evaluation-1` is a local report version. Each case contains case/category/scenario, organization_id/unit_id/record_id, source filename/hash/row, expectation basis, expected/actual assertions, evidence references, uncertainty, status and failure explanation. Review projections retain actual automated assessments and unavailable provider output. Volatile review timestamps are omitted only from this projection so repeated reports are identical; application history keeps its actual timestamps. No times, confidence, cost or model metadata are invented.

- **PASS:** explicit engineering assertions matched actual execution. It does not mean the returned item passed identity/completeness/condition checks.
- **FAIL:** assertion mismatch or unexpected case exception. Other cases continue. Malformed datasets/invalid output paths cause a structured CLI failure.
- **BLOCKED:** a visual scenario lacks evidence/authoritative labels. Its expected and actual visual result remain null; no inference runs.
- **UNCERTAIN/REVIEW:** the observed application state, counted separately. It can coexist with a case PASS and is not added to PASS + FAIL + BLOCKED.

Each mismatch identifies check, expected value, actual value and whether the value was missing. Unexpected exceptions record their class, not possibly sensitive raw text. The CLI exits 0 when engineering cases have no failures (even if visual scenarios are blocked), 1 for engineering case failures, and 2 for dataset/output validation errors. An exit code of 0 is never visual readiness.

## Ten scenarios

Every listed scenario is **BLOCKED** for genuine scenario evaluation and final business-decision evaluation. None has genuine visual evidence plus authoritative expected labels. The following are candidate pointers only, not verified scenario instances:

- Correct returned product: all 24 `identity_match=yes` annotations; no distinguishing returned/catalogue images.
- Wrong returned product: no `identity_match=no` rows or wrong-product image set.
- Missing accessory: the five single-missing-part rows above; the absent entries are not all necessarily accessories and no photos prove absence.
- Multiple missing components: no multi-entry missing-parts annotations or corresponding imagery.
- New-looking item: 13 factory_sealed/opened_unused annotations; appearance and functional condition are unverified.
- Lightly used item: four signs_of_use annotations; the degree of use is not defined or observable.
- Damaged item: six damaged annotations without photographs or authoritative condition labels.
- Heavily damaged item: no severity-specific labels or images. Do not promote generic damaged rows into this category.
- Ambiguous condition: UNIT-0092 has uncertain history, but no corresponding image to judge ambiguity.
- Visually similar products: no paired comparison images/labels; catalogue identifier collisions do not establish visual similarity.

To unblock these, collect genuine returned-item and seller-reference images with ownership/lineage, verified expected parts/quantities, and independently assigned labels (including uncertainty) from two humans across at least 50 unseen units where required. Record adjudication separately. Condition/disposition decisions additionally need applicable authoritative definitions and approved business mappings; provide real client/auth context and the official interoperability schema when available. Do not duplicate these 24 known synthetic units to claim 50 unseen units.

## Metrics and reproducibility

Supported: dataset completeness and annotation distributions; file-reference availability counts; engineering PASS/FAIL counts by named probe; unchanged-input uncertainty/review counts with explicit denominators; review-reason distribution. Accuracy, component detection accuracy, physical-observation accuracy, condition-grade accuracy, disposition accuracy and review precision/recall are BLOCKED with null values because authoritative labels/evidence are absent. No aggregate benchmark score or arbitrary scoring threshold exists. Real model latency/cost and human agreement are unmeasured.

From repository root in PowerShell:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_ADDOPTS = '-p no:cacheprovider'
python -m pytest submissions/karthikk-2003/tests/ -v
$env:PYTHONPATH = Join-Path (Get-Location) 'submissions/karthikk-2003/agent'
python -B -m returns_manager.evaluation --output submissions/karthikk-2003/evaluation/results.json
```

Omit `--output` for full JSON on stdout. The default CSV is the repository sample; `--csv` accepts another repository-local CSV using the same explicitly synthetic adapter, without asserting that its annotations are authoritative. No write is allowed to the input path or outside the participant evaluation directory. Reports include source/code hashes and a source-unchanged check. Re-running against identical code, input and filesystem availability produces the same report bytes; harness regression tests verify this. JSON output is generated by actual execution, never hand-authored results.
