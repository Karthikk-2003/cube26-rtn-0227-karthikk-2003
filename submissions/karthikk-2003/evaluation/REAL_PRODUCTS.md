# Local real-product collection and review demo

This workflow audits the read-only collection and prepares its populated records for the existing inspection workstation. It is an **offline evidence/review demo**, not a successful AI inspection or independent-human benchmark.

## Verified collection

The repository-local source is `CUBE 2026 — RTN PRODUCT COLLECTION-20260930T161737Z-1-001/`, containing the inner collection directory. No corresponding ZIP was found at repository root. Source folders, photographs and DOCX files are unchanged.

- 50 numbered product folders, with supplied RTN/UNIT/ORD collection identifiers.
- Only Products 01–06 have populated product names and photographs; Products 07–50 remain incomplete/template records and are skipped by preparation.
- 30 readable JPEG files, 18 unique SHA-256 hashes, 12 duplicate copies. No extension/content mismatches or corrupt images were found.
- 102 readable DOCX files. Product 48 has two semantically identical product-detail documents; neither is silently preferred if their metadata diverges in a future collection.
- Product 05 lacks an image filed under Identification. Product 06 lacks one filed under Front, but has an uncategorized photograph. No visual category was invented from its pixels. Condition folders may legitimately be empty.
- All 132 original file hashes were checked unchanged after implementation and preparation.

The filled names are supplier statements: samsung laptop, Oneplus Pad, Zebronics Jukebar, GOVO Gosurround, boAt PartyPal 60 and boAt Airdopes Alpha. Exact model/variant text is retained as supplied, without claiming independent verification. Literal `UNKNOWN`, `Unknown`, `unknown` and blank values remain in the metadata snapshot. Where the existing capture contract requires nonempty SKU/ASIN, a blank is projected to the explicit `UNKNOWN` sentinel; the original blank stays visible in source metadata.

The DOCX forms explicitly describe order IDs as **synthetic collection labels**, not verified customer orders. Supplier component lists remain unverified; lists under “Example” are explicitly ambiguous template content. “Actually providing” lists are blank in these six records. Missing/condition statements are stored as supplier statements only, never as independent labels or model observations. Unanswered option lists are not interpreted as selected answers. Personal Name/Relationship sections are excluded from derived snapshots; original file hashes still provide provenance.

## Exact PowerShell workflow

From `submissions/karthikk-2003/`:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'agent'
$env:PYTHONDONTWRITEBYTECODE = '1'
$source = Join-Path (Resolve-Path '../..').Path 'CUBE 2026 — RTN PRODUCT COLLECTION-20260930T161737Z-1-001'
if (-not (Test-Path -LiteralPath $source -PathType Container)) { throw 'Collection directory not found' }

# Audit all products, documents and images without altering source files.
python -B -m returns_manager.collection --source $source

# Prepare populated products in a separate local database. No network or model calls.
python -B -m returns_manager.collection_pipeline --source $source --organization org_demo_alpha --operator karthikk-2003 --database runtime/real-products.sqlite3

# Launch the existing workstation, restricted to loopback.
python -B -m returns_manager.ui --organization org_demo_alpha --reviewer karthikk-2003 --provider disabled --database runtime/real-products.sqlite3 --collection-source $source --port 8765
```

Open `http://127.0.0.1:8765/` manually. The queue contains six cases. Select a case to inspect genuine images, supplier context, source hashes, separate automated results, uncertainty and audit history. AI is disabled and the demo-inspection button is disabled. Start/review a case only when you actually perform that action; record your own explanation. Human assertions are attributed review decisions, not automatically independent evaluation annotations. Final condition/disposition policy remains unresolved.

`org_demo_alpha` reuses the existing local demo tenant; it is **not** asserted to be the supplier's organization. The collection provides no client identifier, so client remains null. `karthikk-2003` is the configured ingestion operator/reviewer, not an invented independent annotator or photographer. The timestamp shown for collection cases is explicitly **ingestion time**, not an inferred camera capture time.

Repeated preparation retains the original source/capture timestamp, one observation attempt and one initial routing event per case. Existing reviewer actions are preserved. Changed metadata/images under the same identifiers cause a conflict; use a deliberately separate runtime database for a new collection version rather than overwriting prior evidence. Multiple preexisting attempts require explicit investigation; the importer never silently picks the latest.

## Implementation and evidence boundary

Set `$source` in the same PowerShell session used to launch the server. An unset variable previously became `--collection-source ""`, which resolved to the working directory and caused correctly rejected image requests despite valid stored evidence. The UI CLI now rejects empty/whitespace source arguments before startup. Use the outer extracted directory named above, matching the stored source identity; do not substitute its inner directory or the participant directory.

`collection.py` extracts only known DOCX labels/sections, records raw source hashes, MIME/content format, size, dimensions, readability, image categories and duplicate paths. It does not inspect photographs semantically or follow document instructions. `CollectionLineage` preserves the sanitized metadata snapshot and its digest; `parse_record` binds original record/unit/order/image references to that snapshot. Collection statements cannot be inserted into historical decision fields or promoted to a trusted parts reference.

`collection_pipeline.py` reuses existing `ingest`, image preparation, `inspect_capture`, deterministic `assess`, Store and ReviewWorkflow. Its explicitly named `offline-no-inference` provider makes no HTTP requests and returns unavailable through the existing mechanism. Genuine image descriptors and hashes are still validated and retained. No vision output, latency, model version, condition grade or missing-component result is invented. Six records are prepared; zero have validated AI observations; all six remain UNCERTAIN/pending_review. Forty-four unpopulated products are reported as skipped, not successfully inspected.

The optional workstation `--collection-source` allows only images listed in the selected scoped capture snapshot. The source path must resolve inside the configured repository-local collection, and both snapshot and stored evidence hashes must match the bytes. Requests use existing review/image IDs, never browser-supplied filesystem paths. Cross-tenant access, path traversal, changed images and unbound references fail closed. Images are served only through the existing loopback adapter, with its origin/host checks and security headers; no public URLs, uploads or photo copies are created.

Derived inventory/preparation reports live under `evaluation/real-products/` with content-addressed filenames. The SQLite file lives under ignored `runtime/`. Reports include original metadata/image hashes, bindings, actual provider status, schema/configuration and relevant code hashes. Supplier metadata is not authenticated catalogue evidence, and file hashes do not establish product truth.

## Independent human evaluation and provider limits

### Explicit one-image provider attempt (2026-10-01)

Provider selection on the workstation configures its demo mode; it does not infer over existing collection records or establish provider reachability. For a deliberate collection attempt, use the new command below from the participant directory, after the `$env:PYTHONPATH` and `$source` setup above:

```powershell
# Pick ONE provider deliberately; each execution appends a new attempt/review.
python -B -m returns_manager.collection_inspect --organization org_demo_alpha --provider ollama --record RTN-001 --image-index 0 --collection-source $source --database runtime/real-products.sqlite3
# Gemini alternative: requires the existing environment key and confirmed Free tier.
# Do not run this just to overcome overload; stop after a capacity failure.
python -B -m returns_manager.collection_inspect --organization org_demo_alpha --provider gemini --record RTN-001 --image-index 0 --collection-source $source --database runtime/real-products.sqlite3
```

The command selects one image from the stored, scoped metadata snapshot, verifies collection identity and image hash, decodes through the existing pipeline, validates any provider output, persists an attempt and routes its own review. It does not copy source files, change original reviews or pass supplier statements as verified references. Unselected images remain unavailable for that attempt, not missing components. `--provider disabled` makes no model call. Ollama uses its existing loopback-only transport; the collection Gemini command explicitly caps HTTP attempts at one. Neither path falls back. Re-running this command is a new authorized attempt, not an idempotent retry. Do not re-run the offline importer to overwrite or select among multiple attempts; use the existing reviews.

Existing configuration: `OLLAMA_BASE_URL=http://localhost:11434`, `OLLAMA_MODEL=qwen2.5vl:3b`, `OLLAMA_TIMEOUT_SECONDS=240`; `GEMINI_MODEL=gemini-3.8-flash`, `GEMINI_TIMEOUT_SECONDS=90`, `GEMINI_API_KEY` from the user's environment, and `GEMINI_FREE_TIER_CONFIRMED=1` only after confirmation. No key belongs in a file or command literal. Cold Ollama inference can exceed warm latency; increasing timeout does not prove readiness.

Launch the workstation with the earlier command and choose `--provider disabled`, `--provider ollama` or `--provider gemini`. No `--demo-image` is needed to view collection attempts. Collection inspection is explicit through the command above, not an automatic page-load action. The header distinguishes configured provider/model from reachability; each selected review shows its persisted attempt's provider/mode/status, validation/persistence state, and actual model/latency only when retained. Refresh and select the new review ID printed by the command. Human assertions and condition/disposition policies remain unchanged.

Controlled live results: one Ollama attempt failed with `provider_unavailable` in **2.2204s** (localhost discovery was also unreachable); one Gemini HTTP request returned **503 / gemini_overloaded** in **13.4464s**, with no retry. These are measured elapsed pipeline durations, not successful-inference latency. Attempts/reviews 7 and 8 were persisted in the ignored local database. Neither produced an accepted raw response or validated observation. The six original reviews remain; all 30 original images still serve with matching hashes, plus the one bound image on each new failed attempt. No further live request was made.

Offline regression: **364 passed, 2 skipped, 507 subtests in 9.97s; zero failures/errors**. Mocked validation/persistence proves engineering integration, not live model success. API/static checks passed; no new browser visual check was performed because localhost browser access remains blocked. All 132 source file hashes remain unchanged. Successful real-provider validation/persistence and independent evaluation remain outstanding.

No independent human annotations or annotator identities were supplied. Agreement, kappa and accuracy cannot legitimately be computed. The preparation report explicitly marks human evaluation BLOCKED with null metrics. No placeholder Annotator A/B records were created for real products.

The existing annotation schema/version and comparison policy remain unchanged. Its system reader now recognizes CollectionLineage and revalidates it using the same capture boundary. Once actual independent annotations and annotator IDs are supplied, construct the documented manifest using the preparation report's exact product/record/unit/attempt bindings and the source reference metadata. Follow [ANNOTATIONS.md](ANNOTATIONS.md). Human condition labels remain evaluation-only and never become disposition rules.

Gemini and Ollama were not called in this run. Earlier Gemini capacity failures and Ollama latency remain historical limitations, not freshly measured failures. This offline mode does not automatically retry or switch providers. Live inspection remains a separate authorized task; this workflow is usable without consuming quota.

## Verification and honest demo limit

Baseline: 339 passed, 2 skipped, 495 subtests. Added 19 focused collection tests, including synthetic test-only image/metadata fixtures, corruption, duplicate/missing files, identifier binding, strict supplier separation, repeated import, tenant isolation, source changes, image hashes, review history/stale revisions, evaluator compatibility and in-process UI image delivery. Existing tests were not removed or weakened.

Final full suite: **358 passed, 2 skipped, 501 subtests in 15.07s; zero failures/errors**. The two existing opt-in live-provider tests stayed skipped. JavaScript syntax and Git whitespace checks passed. The task-created verification server was stopped after checks; the owner's existing port-8000 server was not touched. Use the launch command above to start the final code on port 8765.

The actual six-product preparation command was run twice with identical report/attempt bindings. In-process WSGI verification against the real local database checked six queue/detail/history records and served all 30 images with matching SHA-256. All six had zero observations/raw responses and remained pending review. No human review event was fabricated on real records.

**Visual browser validation is not complete.** The browser tool declined access to the local workstation, reporting a permission denial. No alternate browser, CDP or browser-control workaround was attempted. The server launch and API/backend checks passed, but the owner must perform the final visual review manually.

The final hardening pass added explicitly authorized, root-anchored `.gitignore` rules for this exact collection directory and its matching `.zip` filename. The raw collection is now ignored and remains unstaged; no root ZIP is present. Participant source and derived reports remain visible to Git. Runtime databases and caches remain ignored. Review and selectively stage only intended source/docs/derived metadata when you later decide to commit. Never force-add the raw collection, a ZIP, runtime databases, `.env` files or private logs.

Final hardening verification repeated preparation with the identical content-addressed report and checked all 132 source hashes unchanged. Supported local HTTP checks served six details, six histories and all 30 hash-matched images; six stale-revision requests returned 409 without adding events. A separate bravo-scoped local adapter returned an empty queue and rejected all 18 alpha detail/history/image lookups. Host/origin violations, unsupported scope queries and missing records were rejected. Temporary verification servers were shut down. This is HTTP verification, not visual browser verification. The initial hardening suite passed 358 tests, with 2 live tests skipped and 501 subtests, in 16.55s; no failures/errors or live inference calls.
