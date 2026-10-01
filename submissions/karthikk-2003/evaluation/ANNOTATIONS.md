# Offline independent annotation evaluation — Phase 7

**NO REAL EVALUATION DATA LOADED.** This platform accepts future **Independent Human Evaluation Annotations**, not official CUBE ground truth. The checked-in `annotation-fixtures/synthetic.json` is a SYNTHETIC TEST FIXTURE. It does not represent PRODUCT 01–50. No photos, Drive data, Gemini or Ollama calls are needed or made by the evaluator.

The existing `returns_manager.evaluation` remains the synthetic engineering/blocked-scenario harness. The new `returns_manager.annotation_evaluation` package evaluates independent annotations against existing automated assessments. Neither module creates application policy. The headphones demo and production decision rules are unchanged.

## Contract

Run `python -B -m returns_manager.annotation_evaluation schema` to print the complete machine-readable JSON Schema. Runtime validation also enforces scope, uniqueness and UTC timestamps. This is an internal evaluation contract, not the official CUBE wire schema. Standard library only; no JSON Schema runtime dependency.

Canonical JSON contains:

- `schema_version`: exactly `independent-annotations-1`.
- `evaluation_set_id`, `dataset_version`: supplied nonempty identifiers, up to 256 characters.
- `kind`: `independent_human_annotations` for actual supplied independent annotations, or `synthetic_test_fixture` for fictional tests. No official-ground-truth designation is supported.
- `tenant`: explicit `organization_id` and nullable `client_id`. Use actual authorized context; never invent a client. Use separate datasets for separate tenants.
- `annotators`: exactly two distinct, supplied annotator IDs. Each case can have zero, one or both annotations. Missing annotations stay missing; they are not turned into `not_sure`.
- `cases`: zero to 1,000 uniquely identified products. A 50-case dataset is supported, not required for development.

Each case has `product_id`, `reference`, nullable `binding`, `annotations` and `provenance`:

- `reference`: required `title`, `model`, `sku`, `asin`, `expected_components` and `images`; optional nullable `brand` and `variant`. Preserve literal `UNKNOWN` when model/SKU/ASIN is unknown. Components contain `name` and positive integer or null `quantity`. Empty lists are allowed but reported as reference limitations, not proof of completeness.
- Images contain `reference` and nullable lowercase 64-character `sha256`. They are **metadata only**. No image paths are opened. A supplied hash must match the selected stored image descriptor; missing hashes remain a limitation. No file hashes are invented.
- `binding`: null when no existing system output is associated, otherwise exact `record_id`, `unit_id` and nullable positive `attempt_id`. A null attempt selects the original Phase 1 assessment. An integer selects precisely that vision attempt. There is no implicit latest-attempt choice. Duplicate bindings across products are rejected.
- `provenance`: `source_name` and optional nullable `notes` identify the supplied reference. This declaration does not authenticate a catalogue or turn it into a trusted DecisionReference.
- Each annotation: matching `product_id`, one declared `annotator_id`, `identity_label`, `completeness_label`, `condition_label`, `schema_version`; optional nullable `notes` and `captured_at`. A supplied timestamp must be ISO-8601 UTC. Unknown times stay null.

Identity/completeness labels are exactly `yes`, `no`, `not_sure`. Condition labels are exactly `like_new`, `very_good`, `good`, `acceptable`, `not_sure`. These are **evaluation labels only**, never an application condition scale or disposition mapping. Space-separated/capitalized aliases are rejected rather than normalized.

Text is bounded at 8,192 characters, with invalid Unicode scalars/control characters and edge whitespace rejected. Empty optional text and null are legitimate. Components/images/annotations have bounded lengths; duplicates and unexpected keys are rejected. JSON duplicate keys, nonfinite numbers and malformed structures are rejected. Sources are bounded to 8 MiB. Validation is fail-fast with structured record index, product ID where safe, field, code and message; nothing is imported partially.

## PowerShell workflow

Run from `submissions/karthikk-2003/`:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'agent'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:GEMINI_LIVE_TEST = '0'
$env:OLLAMA_LIVE_TEST = '0'

# Inspect the exact contract and rehearse without real data or any network call.
python -B -m returns_manager.annotation_evaluation schema
python -B -m returns_manager.annotation_evaluation validate evaluation/annotation-fixtures/synthetic.json
python -B -m returns_manager.annotation_evaluation synthetic
```

`synthetic` creates an isolated temporary SQLite database, calls the existing capture/service/FixtureProvider pipeline, validates and imports the fixture, evaluates twice and checks equivalent reports. It removes its temporary database. It persists an immutable import plus JSON/Markdown reports under `evaluation/offline/`. It never opens a production database or invokes a real provider. The four fixture cases cover a validated-but-uncertain attempt, malformed-provider unavailability, a baseline assessment and missing binding/annotations. Unit tests separately exercise decisive comparisons, conflicting labels, compatible synthetic condition comparisons and incompatible condition taxonomies.

After the owner supplies real annotation/reference files **inside this participant directory**, use their actual paths in place of the examples below:

```powershell
python -B -m returns_manager.annotation_evaluation validate evaluation/incoming/annotations.json
$import = python -B -m returns_manager.annotation_evaluation import evaluation/incoming/annotations.json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Annotation import rejected' }

# Supply the existing DB containing the exact authorized record/unit/attempt bindings.
python -B -m returns_manager.annotation_evaluation evaluate $import.imported --database runtime/inspections.sqlite3
```

The incoming file and example inspections database are **not provided or created by these instructions**. Without `--database`, evaluation works but reports every system output unavailable. A missing database is rejected and never created. SQL access uses `mode=ro`, `query_only`, a read snapshot and organization/client/record/unit/attempt predicates. This is a trusted local tool, not user authentication or a database access-control service.

### CSV convenience import

Create a canonical JSON reference manifest with the same case identities, tenant, intended annotators, reference metadata and bindings, but empty `annotations` arrays. Supply a CSV with **exactly** these columns (any column order is accepted):

```csv
product_id,annotator_id,identity_label,completeness_label,condition_label,notes,captured_at,schema_version
```

One row is one independent annotation. Two annotators produce two rows for a product. Empty optional notes/timestamp cells mean null; labels and identifiers are never trimmed/coerced. Header-only CSV means no annotations; a completely empty file is invalid. Missing products, repeated annotator/product pairs, duplicate columns and malformed row counts/quoting are rejected. Annotated manifests are rejected rather than silently merged.

```powershell
python -B -m returns_manager.annotation_evaluation validate evaluation/incoming/labels.csv --manifest evaluation/incoming/references.json
$import = python -B -m returns_manager.annotation_evaluation import evaluation/incoming/labels.csv --manifest evaluation/incoming/references.json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Annotation import rejected' }
python -B -m returns_manager.annotation_evaluation evaluate $import.imported --database runtime/inspections.sqlite3
```

## Comparison and metrics

The adapter revalidates stored capture lineage, observation raw-response consistency, scope and reference snapshots, then recomputes the existing deterministic rules offline and requires equality with the stored automated assessment. It does not promote evaluation references into business references or use human review overrides as automated predictions. The capture/assessment/run hashes, source keys, provider mode and actual available metadata are retained; raw model text is not copied into reports.

Actual `Verdict.PASS` maps to `yes`, `FAIL` to `no`, and `UNCERTAIN` to an uncertain system dimension. Current condition is grade-null/UNCERTAIN and remains so. There is no authorized condition-taxonomy adapter beyond the current unresolved state; the generic comparator can compare explicitly compatible labels in synthetic tests. It refuses incompatible labels. No disposition is evaluated or generated.

Each annotator is compared independently; no consensus is selected. Results are `MATCH`, `MISMATCH`, `HUMAN_UNCERTAIN`, `SYSTEM_UNCERTAIN`, `BOTH_UNCERTAIN`, `SYSTEM_UNAVAILABLE` or `NOT_COMPARABLE`. Unavailability takes precedence as the comparison category, while separate human-uncertainty counts retain uncertain annotations even when the provider was unavailable. Source dimensional values and reasons remain in each comparison.

Agreement uses **matches / (matches + mismatches)**. All abstentions, incompatible results and unavailable outputs are excluded from that denominator. Counts describe annotation-dimension pairs (up to two per product), not independent products; do not call this overall accuracy. Availability and system uncertainty use case denominators; human uncertainty uses annotation counts. Provider availability excludes baseline assessments/unbound cases where no provider attempt is known. Every rate includes numerator and denominator; zero eligible denominators produce JSON null / Markdown N/A.

Human pair states are agreement, disagreement, both uncertain, one uncertain and incomplete. Raw pair agreement includes equal `not_sure` answers and is labelled accordingly. Decisive pair agreement and unweighted Cohen's kappa exclude any pair with `not_sure`. Kappa requires at least two decisive pairs and nondegenerate expected agreement; otherwise its value is null with a reason. Both independent labels and their identities are preserved, even in disagreement.

## Reproducibility, safety and limitations

Original JSON/CSV files remain unchanged. All inputs must resolve under the participant directory. Output names are generated SHA-256 values beneath fixed `evaluation/offline/imports` and `evaluation/offline/reports` directories. There are no arbitrary output-path options or overwrite operations. The import envelope retains normalized cases and original source byte hashes; an identical re-import returns the same artifact. CSV and manifest hashes are retained separately. Reordering semantic data normalizes case/annotator order, while different source bytes still have distinct provenance.

Reports contain set/version, evaluator/code hashes, annotation completeness, dimension counts/rates, human pair states/kappa, system/provider availability, uncertainty, disagreement/unavailable cases, reference limitations and source provenance. JSON holds full detail; Markdown summarizes it. Reports are deterministic for identical source/import, selected database snapshot, evaluator code and timestamp. The default timestamp is actual current UTC. Use `--timestamp` with a recorded prior UTC timestamp to reproduce a run exactly; that field is report provenance, never inference latency. Changing code hashes, database contents or timestamps intentionally changes report identity.

Hashes prove content identity, not truth. Independent human labels are not official ground truth. Existing capture storage still originates from the synthetic CSV-shaped adapter; reports expose that limitation rather than presenting it as an authenticated real-product input contract. Future real images/verified order context and properly bound persisted outputs remain necessary. Fixture observations are explicitly labelled; no benchmark result, 50-unit visual evaluation, image accuracy or real model success is claimed. Source annotations never modify policy, records, reference snapshots, review history or UI.

## Tests

```powershell
$env:PYTEST_ADDOPTS = '-p no:cacheprovider'
python -B -m pytest tests/test_annotation_evaluation.py -q
python -B -m pytest tests/ -q
```

Tests use participant-local temporary files and explicitly synthetic annotations. They cover strict input boundaries, UNKNOWN preservation, CSV/JSON/idempotency, every comparison category, meaningful/zero denominators, paired-label/kappa edge cases, fifty-case shape, read-only scoped retrieval, corrupted outputs, hashes, CLI, disabled network and repeat-run equality. Existing headphones/demo/provider/rule tests remain unchanged.
