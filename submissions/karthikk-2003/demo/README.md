# Headphones case — DEMO / SYNTHETIC REFERENCE DATA

This package defines one synthetic order/catalogue case. It is not official CUBE data, customer data, benchmark ground truth or an externally verified catalogue. "Verified" here means the authorized local image decodes, matches the recorded SHA-256, and is bound consistently to the explicit synthetic reference. It does not establish real product identity.

The only image used is `runtime/demo-images/headphones_smoke.png.png`. Its SHA-256 is `18b05ac0c02bcc12171f311d1f0eb48fb985b232f939893f290817d56581404d`. It is not copied, modified, uploaded or committed by this work. The existing optional Pillow dependency is needed for the case's local image preflight, including fixture mode.

## Visual inspection versus expectations

Assistant inspection found black over-ear headphones, padded earcups, a curved headband, colored trim, small controls/openings and a stylized emblem. No exact brand/model/SKU/ASIN is established. Functionality, authenticity, wireless capability, usage history and a condition grade cannot be established. No separate accessories are visible; this does not prove absence. These inspection notes are contextual prose in the package, never replayed as provider output.

The synthetic product is explicitly defined to expect one headphones unit, carrying case, USB cable and manual. The accessories are inspired by the CUBE problem-statement example, but are OUR synthetic expectations. Neither that example nor the image establishes this pictured product's actual bill of materials. Synthetic SKU, ASIN placeholder and order values are labelled accordingly. Existing `org_demo_alpha` is used with null client context; no client identifier is invented.

## Run offline from the participant directory

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'agent'
python -B -m returns_manager.ui --organization org_demo_alpha --reviewer karthikk-2003 --provider fixture --demo-case headphones --demo-image runtime/demo-images/headphones_smoke.png.png --database runtime/headphones-fixture.sqlite3 --port 8000
```

Stop any existing UI process occupying port 8000 first. Click **Inspect configured demo images** once. This creates a scoped review case, not a live model request. The workstation explicitly labels the case DEMO / SYNTHETIC REFERENCE DATA and shows the four expected components, source snapshot, actual package verifier/time and reference digest. The verifier records local package preparation, not an external catalogue attestation.

FixtureProvider is the existing class (not a separate FixtureVisionProvider implementation). It returns labelled empty synthetic observations with explicit limitations; it does not inspect pixels or fabricate OCR. Its image descriptor remains fixture_only with no invented image hash or model metadata. The actual photo hash is retained separately inside the reference source snapshot. A real-mode dry preparation test proves that the same photo bytes pass the existing image boundary and yield that actual hash without calling any provider.

Expected fixture results: identity UNCERTAIN, completeness UNCERTAIN, all four components unresolved, no confirmed missing components, condition UNCERTAIN with null grade, disposition pending_review. Raw fixture response, rule version, source snapshot and scoped assessment persist through review/history. Completing human review does not invent or release a final business disposition.

## Existing integration

`--demo-case headphones` selects this fixed project-local file; the browser cannot supply arbitrary reference paths, case names or tenant context. `prepare_demo` binds the explicit order/parts definition; `demo_reference` builds the existing DecisionReference. Source text is preserved and hashed by that contract, with reference_status=synthetic_demo. The existing service, deterministic checks, SQLite JSON payloads, review history and UI projection are reused. No parallel reference store or SQL migration exists.

Synthetic references cannot yield decisive automated identity/completeness even if a future model echoes a synthetic identifier. Old attested references retain their existing behavior. Missing/changed/unreadable images and foreign tenant/client contexts reject preparation before provider invocation.

## Later real-model verification

No Gemini/Ollama call was made for this package. When a real test is explicitly authorized, the same command can select `--provider gemini` and a separate database such as `runtime/headphones-gemini.sqlite3`, using the already documented Free-tier environment configuration. Do not run it now merely to verify setup. Existing Gemini retry bounds still apply; no automatic provider fallback is added.

This case is ready to exercise real image transmission, structured observations, lineage, persistence and review later. It cannot prove real catalogue identity or completeness, assign a condition grade or select a final disposition. Those require actual reference/policy evidence. The synthetic marker must not be removed to manufacture a successful demo.

## Tests

Run `python -B -m pytest tests/test_headphones_demo.py tests/test_policy.py tests/test_demo.py -q` with both live-test flags disabled and pytest cache disabled as described in the main README. Local-photo tests skip explicitly when this ignored image or Pillow is unavailable; no substitute photo or fabricated image is generated. The full suite retains the existing regression tests.
