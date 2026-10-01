# Returns Manager — CUBE Buildathon

## 1. Project overview

Returns Manager turns returned-item captures into traceable observations, separate
deterministic assessments and human-review records. This is the CUBE Buildathon
Returns Manager track. The browser workstation exposes evidence and uncertainty;
it does not turn a model's description into an unsupported business decision.

## 2. Problem

Operators need to establish whether the returned product matches the order,
whether required components are present, its condition and what should happen
next. Photographs alone often cannot establish identity, functionality or value.
The system preserves those gaps rather than guessing.

## 3. Four decision layers

- **Identity:** exact supported identifiers against an attested reference, otherwise UNCERTAIN.
- **Completeness:** evidence-backed component checks only with the required verified context;
  not-visible never automatically means missing.
- **Condition:** physical observations are retained; business grade remains null while
  authoritative category rules and required nonvisual checks are unresolved.
- **Disposition:** pending_review until adequate evidence and governing policy exist.
  No guessed condition-to-disposition table is implemented.

## 4. Architecture

Capture/image preparation → explicit VisionProvider → raw provider response →
strict canonical observation validation → deterministic Python assessment →
tenant-scoped SQLite → review/history → workstation.

AI supplies observations, not grades or dispositions. Python rules assess validated
evidence against scoped references. Human assertions remain separately attributed;
review completion does not automatically release a business disposition.
Evidence IDs, record/unit scope, source lineage and SHA-256 are preserved.
Hashes establish byte integrity, not identity/authenticity.

See [ARCHITECTURE.md](ARCHITECTURE.md), [build-brief.md](build-brief.md) and
[build-log.md](build-log.md) for contracts, policy constraints and historical work.

## 5. Current verified status

Before deployment work: **377 passed, 2 skipped, 520 subtests; zero failures/errors**.
After deployment changes: **391 passed, 2 skipped, 542 subtests; zero failures/errors**.
The latest build-log entry records the verification scope.

One authorized real Groq request using qwen/qwen3.8-27b returned HTTP 200,
parsed successfully and passed the existing canonical validator. Attempt/review
12 was persisted through the normal pipeline. Measured provider time was 2.515s;
inspection pipeline time was 2.576s. Identity/completeness/condition remained
UNCERTAIN, grade null, disposition pending_review. Image SHA-256 was unchanged.
This single integration check is **not an accuracy or performance benchmark**.

The local collection has 50 folders, six populated products and 30 JPEG files.
Independent human annotations and official ground truth are unavailable.
No completed 50-unit visual evaluation, universal grading, successful Gemini/Ollama
application inference or public deployment is claimed.

## 6. Demo

The hosted demonstration is **SYNTHETIC / DEMONSTRATION DATA**: two reproducible
missing-evidence cases, no photographs, no AI inference, no real supplier records
and no browser mutations. Startup seeds it automatically. See
[demo/PUBLIC_DEMO.md](demo/PUBLIC_DEMO.md) and [DEPLOYMENT.md](DEPLOYMENT.md).

The optional [local headphones demonstration](demo/README.md) uses an ignored,
hash-bound authorized photo. It is not shipped in the public demo.
FixtureProvider is a deterministic synthetic replay provider, not image inference.
The public demo uses disabled inference; the local image demo can explicitly use
fixture mode.

## 7. Local setup

Clone your own fork, then enter the participant directory:

~~~sh
git clone <your-fork-url>
cd <repository-directory>/submissions/karthikk-2003
python -m pip install -r requirements-test.txt
~~~

Python 3.10+ is required; verification uses Python 3.13.4. Core local functionality
uses the standard library. Pillow is required for actual JPEG/PNG decoding.
The test manifest pins the versions used here; requirements-images.txt retains
the earlier optional decoder pin. No Linux runtime verification is claimed.

PowerShell:

~~~powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'agent'
python -B -m returns_manager.ui --organization org_demo_alpha --reviewer karthikk-2003 --port 8000
~~~

POSIX shell:

~~~sh
PYTHONPATH="$PWD/agent" python -B -m returns_manager.ui --organization org_demo_alpha --reviewer karthikk-2003 --port 8000
~~~

Use your actual reviewer identifier for local review work. Open the numeric loopback
host on port 8000. Local startup creates an empty database; it never imports the
collection or invokes AI automatically.

Offline tests from the participant directory:

~~~powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_ADDOPTS = '-p no:cacheprovider'
$env:GEMINI_LIVE_TEST = '0'
$env:OLLAMA_LIVE_TEST = '0'
python -B -m pytest tests -q
~~~

POSIX equivalent:

~~~sh
GEMINI_LIVE_TEST=0 OLLAMA_LIVE_TEST=0 PYTHONDONTWRITEBYTECODE=1 python -B -m pytest -p no:cacheprovider tests -q
~~~

Keep repository data/returns_sample.csv available for regression tests.
Some local-photo tests skip when the private image is absent. Counts on a fresh
clone can therefore differ. Live tests must remain explicitly disabled.

## 8. Environment variables

The application does not load .env files. [.env.example](.env.example) contains
placeholders only; configure real secrets privately.

- Hosted demo: DEPLOYMENT_MODE, DEMO_PUBLIC_ORIGIN, DEMO_ACCESS_TOKEN, PORT, PYTHONPATH.
- Optional Groq operation: GROQ_API_KEY.
- Optional Gemini: GEMINI_API_KEY, GEMINI_FREE_TIER_CONFIRMED;
  GEMINI_MODEL and GEMINI_TIMEOUT_SECONDS configure model/timeout.
- Optional local Ollama: OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT_SECONDS.
- Development: PYTHONDONTWRITEBYTECODE, PYTEST_ADDOPTS, GEMINI_LIVE_TEST,
  GEMINI_LIVE_IMAGE, OLLAMA_LIVE_TEST, OLLAMA_LIVE_IMAGE.

No AI credentials are required or read by the hosted demo.
Do not enable live tests or inference without authorization.

## 9. Groq

GroqVisionProvider uses model qwen/qwen3.8-27b, an environment-only key, one JPEG
data URI and JSON-object output. The existing validator remains authoritative.
The provider uses a normal application User-Agent, a bounded timeout, no automatic
retries and no fallback. Condition guidance explicitly requires descriptions for
observed/not_observed/conflicting findings and honest uncertainty for invisible
features. No adapter invents descriptions or changes model output.

On an already prepared **local** collection database, this command makes a new
external request and must only be run with explicit authorization:

~~~sh
python -B -m returns_manager.collection_inspect --organization org_demo_alpha --provider groq --record RTN-001 --image-index 0 --database runtime/real-products.sqlite3
~~~

It uses the configured default repository-local collection root; see
[evaluation/REAL_PRODUCTS.md](evaluation/REAL_PRODUCTS.md) for preparation and
alternate source configuration. Do not run it as a deployment health check.
The hosted demo exposes no Groq operation or key. One successful integration does
not establish visual accuracy or reliable acceptance on other photographs.

## 10. Evaluation

[Engineering evaluation](evaluation/README.md) and
[independent annotation evaluation](evaluation/ANNOTATIONS.md) are separate.
Synthetic fixtures demonstrate reproducibility, validation and isolation.
Historical CSV labels, supplier metadata and automated review routing are not
ground truth. Independent real annotations, adequate unseen evidence and applicable
policy are still required for genuine performance evaluation.

## 11. Security

Organization/client/record/unit scope is preserved. Images require approved paths,
capture membership and matching hashes. Unknown evidence stays unavailable.
Provider output is untrusted; canonical validation rejects unsupported fields,
business decisions, scope mismatches and invalid evidence. Rejected raw responses
are not retained as valid observations.

The public demo uses HTTPS-edge Basic access and read-only routes. Its fixed
synthetic tenant/reviewer/database cannot be selected remotely. The original
local server remains loopback-only and is not production authentication.
No raw collection, developer database or actual secret belongs in Git.
Ignore rules are defense in depth, not a substitute for reviewing staged files.

## 12. Deployment

Install requirements-deploy.txt. From the participant root, configure
PYTHONPATH to agent, DEPLOYMENT_MODE to demo, the exact HTTPS
DEMO_PUBLIC_ORIGIN and a privately generated DEMO_ACCESS_TOKEN; the host supplies PORT.

~~~sh
python -B -m returns_manager.deployment
~~~

See [DEPLOYMENT.md](DEPLOYMENT.md) for TLS/access prerequisites, initialization,
health, smoke checks and rollback. Waitress is a small WSGI dependency, not an AI
SDK. Its real installed launch must be verified in the hosting environment;
no hosting deployment or external network call occurred during implementation.

## 13. Limitations

- Shared demo access is not individual reviewer authentication.
- Hosted mode demonstrates read-only uncertainty/evidence workflow, not live inspection.
- Business condition grading and final disposition policy remain unresolved.
- Official interoperability schema is not claimed.
- Real independent annotation evaluation remains incomplete.
- Gemini/Ollama live application success is not established.
- Production multi-user operations, uploads and distributed storage are outside this scope.

## 14. Project structure

- agent/returns_manager/: domain, providers, validation, assessment, storage and UI.
- agent/returns_manager/deployment.py: restricted hosted entry point and synthetic seed.
- tests/: offline regression suite and opt-in live tests.
- demo/: synthetic reference documentation; no public raw photos.
- evaluation/: engineering reports and annotation-evaluation infrastructure.
- runtime/: ignored local databases/assets; never publish this directory.
- DEPLOYMENT.md: actual hosted-mode configuration and verification.
