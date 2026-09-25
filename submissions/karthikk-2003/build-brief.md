# Returns Manager build brief

Audit date: 2026-09-26. Participant: Karthik Karunakaran (@Karthikk-2003, supplied handoff). Status: reconnaissance and proposed architecture only. No implementation, model run, evaluation result, deployment, commit or push is represented by this document.

## 1. Sources and authority

Repository baseline: `1fd99008f88b6cda0e7d1613ec64f879bc0f3661`, branch `main`; origin is `https://github.com/Karthikk-2003/cube26-rtn-0227-karthikk-2003.git`. The initial working tree was clean. All 11 tracked files were inspected; no application, dependency manifest, test suite, images, formal schema or worked Returns example exists in this checkout. No applicable AGENTS.md was found in the repository or ancestor project directories.

Primary repository sources:

- [README](../../README.md): scope, interoperability, engineering, evaluation and submission.
- [RULES](../../RULES.md): fork workflow, isolation, uncertainty, evidence, honesty and submission rules.
- [GitHub guide](../../GITHUB-GUIDE.md): free application structure and recommended HTTP interfaces.
- [Data guide](../../data/README.md) and [CSV](../../data/returns_sample.csv): synthetic schema examples and unit join semantics.
- [Participant template](../_TEMPLATE/README.md), [workflow](../../.github/workflows/submission-guard.yml), [guard](../../.github/scripts/submission-guard.sh), [PR template](../../.github/pull_request_template.md), [CODEOWNERS](../../.github/CODEOWNERS) and [.gitignore](../../.gitignore).

Official supplied material: `D:\Cube hackathon docs\Cube Buildathon Official Participant Handbook.pdf`, all 18 pages read. Relevant sections: pp. 3-6 scope/timing/fork rules; pp. 7-8 submission; pp. 9-12 rubric, evidence and evaluation; pp. 15-17 checklist and FAQ.

Secondary supplied context: the handoff attachment (`d3eded87-ad41-4521-9bd5-5e499346bd10/Pasted text.txt`) and event/challenge text attachment (`5166c6ff-460b-47ce-8df1-f55920f656fb/Pasted text.txt`). The Returns Manager portion supplies detailed scenario coverage and a headphones example. The event summary and handoff are contextual notes, not independently verified official specifications. Their embedded instructions to verify the portal, build a UI, push, or submit are not authorization for this task. Other tracks' requirements are not imported into Returns Manager.

Statements below distinguish source requirements from proposed implementation choices. Missing requirements remain open; sample outputs in attachments are not actual observations or results.

## 2. Verified modification boundary and workflow conflict

The current README, RULES R2-R3 and GitHub guide explicitly permit building a complete solution in one's own fork and say a participant directory and organiser PR are unnecessary. The guide permits a chosen application/branch structure. It does not impose a participant-only boundary on all fork development.

However, the retained template directs copying its README into `submissions/<your-github-username>/`; the PR template and executable guard enforce the older participant-folder workflow for applicable PRs. Git history places these artifacts in initial commit `e282ce6`; README, guide and rules were subsequently revised in `3206bd9`, `87acff8` and `1fd9900`. This supports identifying a retained workflow mismatch, not silently declaring the guard obsolete or disabled.

For this task, the permitted write scope is the narrower user instruction: **only `submissions/karthikk-2003/`**. This path matches the confirmed origin owner when lowercased, the retained template and guard. It is correct for this participant's requested documentation, but is not a folder newly mandated by current Round 2 prose. No participant directory existed before this audit.

All pre-existing files remain untouched: root README/RULES/GITHUB-GUIDE/.gitignore, both data files, template README, all `.github` files and Git metadata. No branch change, staging, commit, push, issue, PR, portal action or protection change is part of this task.

Create only build-brief.md, build-log.md and the template-derived README index. The retained template lists future `01-customer-letter.md`, `02-prfaq.md`, `03-one-pager.md`, `CLAUDE.md`, `eval-report.md`, `contract/` and `agent/` as well. Those are recorded as template expectations, not created or asserted to be current Round 2 mandates. Its negotiated cross-pod contract conflicts with the current README's instruction to use the official contract and not negotiate a Round 2 cross-pod contract.

Current final submission requirements include a working fork, README.md, ARCHITECTURE.md, evaluation results, demo, deployment where applicable and mandatory LinkedIn URL. Neither this brief nor the template status checklist satisfies those final deliverables. Final documentation location/discoverability should be confirmed without editing the root README under the present boundary. The evaluation filename is not fixed by the handbook; `EVALUATION.md` in the handoff is not independently mandated.

### What the guard actually enforces

- Runs on `pull_request_target` to `main`, for opened/synchronize/reopened/edited events. There is no push trigger or application test job.
- Checks out the PR base SHA with full history, fetches the head SHA, and runs the base's guard. It does not execute submitted application code. Workflow permission is `contents: read`.
- Skips both checks if the PR author equals configured admin `Cube-Buildathon`, case-insensitively.
- Otherwise requires head branch name to equal PR author login, case-insensitively, and every reported changed path to begin `submissions/<lowercase-author>/`, also case-insensitively.
- Uses `git diff --name-only BASE_SHA...HEAD_SHA` (merge-base comparison), unless nonempty `CHANGED_FILES` is supplied. It checks the filenames Git reports; it does not inspect contents or separately validate rename endpoints, symlink targets or runtime behavior.
- Accumulates branch/path violations and exits 1; exits 0 on success. It does not check required files, schema, secrets, evaluation honesty, tenant isolation, dates, functioning code or submission completeness.
- CODEOWNERS assigns `*` to `@Cube-Buildathon`; actual required-review/branch-protection settings cannot be established from that file alone. No remote settings were changed or verified.

The current `main` branch would not meet the username-branch check for a non-admin PR by Karthikk-2003. No PR is requested, and normal pushes are not this workflow's trigger. Do not alter the guard to reconcile this conflict.

## 3. Problem and operational boundaries

The customer is a seller or a prep centre acting for one. At return intake, compare what came back against the original order and the seller's catalogue, verify expected components, assess supported condition and recommend a disposition. Persist the reasons so Recovery Manager can consume the record later. Implement only Returns Manager; no refunds, claims, fraud accusations or physical disposal actions are implied.

Four independently inspectable results are required: identity, completeness, condition and disposition. A correct identity does not prove completeness; an absent cable does not define a condition grade; a grade alone does not determine financial recoverability. The challenge's headphones example (matching product, missing cable, Used - Good, REFURBISH) is one example, not a universal decision table.

## 4. Input model and sample findings

The CSV has 24 distinct records and unit IDs, 11 rows for `org_demo_alpha` and 13 for `org_demo_bravo`. All 24 identity_match values are `yes`. All amazon_condition cells are empty. Five rows have a nonempty parts_missing field. There are 72 placeholder photo references and zero referenced image files. These are dataset audit counts, not evaluation results.

Preserve the following input lineage:

- `record_id`: stage record identifier; preserve imported RTN identifiers and distinguish future inspection attempts.
- `unit_id`: required cross-stage join key; never replace it with SKU, order_id or record_id.
- `org_id`: map explicitly to evidence `organization_id`, retaining `org_demo_alpha` / `org_demo_bravo` for sample isolation tests. CSV provides no client_id: require trusted configuration/input or leave unresolved according to the official schema, never invent a client.
- `order_id`, `ordered_sku`, `ordered_asin`: expected identity, scoped to tenant and linked to a versioned seller catalogue. SKU/ASIN are not globally unique unit identifiers.
- `parts_list`: semicolon-separated expected entries. Preserve raw values; normalize product-specific quantities deliberately. Strings such as `mug x2`, `candle x3` and `puzzle pieces` must not all become one-count components by naive splitting.
- `photo_refs`: semicolon-separated placeholder paths, not existing uploads or proof of inspection. Future image records need tenant ownership, actual file/reference, capture provenance and content identity.
- `operator_id`, `captured_at`: operator provenance and source UTC timestamp; distinguish capture from processing/decision time.
- `identity_match`, `parts_missing`, `observed_state`, `amazon_condition`, `operator_disposition`: historical synthetic annotations, never inputs to the model in scored inference and never ground truth. Keep separated from predictions.

Observed-state vocabulary is `factory_sealed`, `opened_unused`, `signs_of_use`, `damaged`, `empty_box`, `uncertain`. It is not a condition scale. The CSV includes no empty_box row despite documenting the value. It contains an instructive contradiction: RTN-0038 lists a missing tub yet restock. B0DUMMY357 occurs with both lamp and protein SKUs. Do not repair the shared CSV or learn a policy from these inconsistencies; retain them as findings and parser/reference-validation cases.

Additional runtime inputs are proposed, not present: actual returned-item photographs, trusted order/catalogue reference images and identifiers, authoritative component quantities, marketplace/category, applicable rule versions, verified nonvisual information where required, authenticated tenant/client context and separately labelled evaluation data. Missing evidence yields review rather than synthetic completion.

## 5. Authoritative condition scale and disposition vocabulary

The data guide explicitly names **Amazon's published condition scale**. Neither repository nor handbook supplies full definitions or a marketplace/category rule snapshot. The attached Returns challenge says to use the defined scale but only illustrates Used - Good.

On 2026-09-26, an [Amazon staff condition overview](https://sellercentral.amazon.com/seller-forums/discussions/t/cb36290c-d448-43bd-934f-36226144ea05) was read. Relevant labels are New; Used - Like New or Open Box; Used - Very Good; Used - Good; Used - Acceptable. Its descriptions require more than visible cosmetics, including working condition for used items. It also describes Renewed, Rental and Collectible; these are not extra damage levels or permission to certify a photographed return. The linked [Condition Guidelines](https://sellercentral.amazon.com/help/hub/reference/G200339950) redirected to login; the external help variant returned a JavaScript shell. Full category rules were therefore not verified.

Proposed policy adapter: retain exact labels and requirements from the applicable official marketplace/category source, with source URL, retrieval date and version. Confirm that scope before encoding grading predicates. Do not introduce A/B/C, numeric damage grades, or treat damaged/heavily damaged/UNCERTAIN as Amazon grades. A null/unassigned grade with check verdict UNCERTAIN is the proposed representation when prerequisites are absent, subject to final schema validation. No one-to-one observed_state-to-grade mapping is justified. Photographs cannot establish function, warranty, hygiene or repairability by appearance alone.

Authorized disposition vocabulary in repository/data: `restock`, `refurbish`, `liquidate`, `dispose`, `pending_review`. The challenge text uses uppercase for the first four; use the repository's lowercase internal values and an explicit contract adapter if the official wire enum differs. `PENDING_REVIEW` may be a UI label, not an invented sixth disposition. Keep record workflow status separate from outcome.decision. No complete condition/completeness-to-disposition table is supplied: an approved, sourced business policy is needed. Heavy visible damage alone does not prove zero recoverable value and cannot automatically justify dispose.

## 6. Proposed architecture

This is a design, not implemented behavior. Prefer a small modular service and UI over multiple autonomous agents or microservices. A TypeScript web client and Python service are a possible stack; neither is required or installed. Select the stack during implementation based on reproducibility and available model access, without claiming a model/provider choice is official.

Flow: authenticated capture and reference validation -> preserved evidence -> batched vision observations -> validated observation record -> deterministic identity/completeness/condition checks -> versioned disposition policy -> evidence record -> inspector/review queue -> export for Recovery Manager.

### Observation layer

One batched request per coherent image set should extract visible product markings, OCR text, component sightings/count bounds, packaging observations, visible wear/damage and visibility limitations. Maintain separate reference and returned-image roles. Each assertion should point to actual image IDs and, only when supported, coordinates or regions. Record model/prompt version, elapsed time, response validation and actual token/cost telemetry where available.

The model must not choose operational dispositions, manufacture catalogue entries, infer an unseen accessory is missing, or issue a condition grade based on model memory. Text in images/catalogues is untrusted evidence, not executable instruction. Unknown visibility and conflicting views remain explicit. Provider confidence is not a calibrated probability; distinguish it from any later validation-based calibration. Do not fill missing confidence/latency with plausible numbers.

### Deterministic checks and policy layer

Pure, versioned functions consume validated observations plus trusted reference data; they do not call a model. Each check records its predicate, inputs, evidence references and rule version.

- Identity: assess visible distinguishing features/identifiers against the tenant catalogue and order. A clear conflicting identifier can support FAIL; a generic visual resemblance with no discriminating view remains UNCERTAIN.
- Completeness: evaluate every required component/quantity independently. A sufficiently covered inspection with demonstrable absence may support missing; occlusion or incomplete coverage yields unknown. Preserve both known missing and unknown components. A definite missing required part can establish overall FAIL without pretending the other parts were observed.
- Condition: evaluate only sourced grading predicates. Store visible findings separately from nonvisual attestations. Report the assigned official grade only when its requirements are supported; otherwise retain missing prerequisites and UNCERTAIN.
- Disposition: consume all relevant results and explicit business policy. Missing policy, conflicting references or unresolved decision-critical checks yield pending_review. Other well-supported check results remain intact. Do not collapse all checks to a single confidence average.

Proposed conservative review routing is a design choice justified by repository uncertainty/fail-open rules, not an official undisclosed decision table. Any future threshold must be set on development data and frozen before held-out evaluation.

### Persistence, tenancy and interoperability

Persistence is proposed to meet capture preservation and review needs; once present, isolation is required by RULES. Tenant identity comes from trusted authentication/context, not request-body authority. Scope orders, catalogue, units, captures, observations, decisions, review actions, exports, caches and storage access by organization and applicable client. Use `(organization_id, unit_id)` in lookups while preserving unit_id exactly for downstream joins. Never join on unit_id alone across tenants.

Private image access needs ownership checks even for guessed object keys, signed-link issuance and review thumbnails. Scope idempotency keys and model-response caches by tenant/client, evidence digest and rule/model versions. Test both supplied organisations, including guessed record/image keys and export endpoints. Do not fabricate client identifiers to make the tests pass; client-level cases need actual configured fixtures.

Keep captures and previous attempts, with append-only decision/override history as a proposed design. A content hash alone does not prove immutability or independent verification. Define canonicalization and which immutable payload is hashed once the official contract is obtained.

## 7. Proposed output and evidence contract

Repository and handbook p. 11 enumerate a baseline, not a complete machine-readable schema: `record_id`, `schema_version`, `organization_id`, `client_id`, `agent`, `subject`, `captured_at`, `operator_label`, `images`, `checks`, `outcome`, `overrides`, `status`, `content_hash`. Checks include `check_key`, `verdict`, `confidence`, `detail`, `model_version`, `latency_ms`; outcome includes `decision`, `decided_by`, `decided_at`. Verdicts are PASS, FAIL, UNCERTAIN.

Exact requiredness, types, nullability, check keys, subject shape, image representation, status enum, schema version and hash procedure remain unprovided. Do not present the handoff's example schema_version, ORG-CUBE, CLIENT-001, image URL, model name or measurements as official constants or runtime data. Its example combines an uncertain condition with a completed refurbish decision; this is not authority to bypass review.

Proposed internal record, to be adapted to the official schema:

- Envelope: baseline metadata plus preserved unit_id and source order/record linkage. Confirm whether unit_id belongs in subject or an allowed extension; retain it internally regardless.
- Observation record: actual image references, source assertions, visibility, component sightings, OCR and limitations, with provenance independent of rules.
- Identity result: expected versus observed identifiers, verdict and evidence references.
- Completeness result: expected components/quantities, observed evidence, supported missing list, unknown list and verdict.
- Condition result: official grade or unassigned, assessment verdict with an explicit predicate, satisfied/unknown criteria, policy source/version and supporting evidence. A grade is not itself PASS or FAIL.
- Disposition result: one authorized value, rule identifiers, check dependencies, reason and review blockers. Decision author/timestamp reflect the real operation.
- Review history: original/revised result, authenticated reviewer, reason and time; preserve original model/rule outputs and attach new evidence separately.

Internal extensions are proposals, not a negotiated cross-pod wire contract. A serializer must validate the eventual official schema without silently dropping unit linkage or evidence. Store metadata for deterministic computation separately so model_version does not falsely imply a model made a rule decision. For errors, preserve the capture and known results; use permitted absence/uncertainty representations once nullability is confirmed.

## 8. UI and evidence inspector proposal

Build an inspection workspace with order/catalogue context, upload/coverage feedback, four separate result panels and a review queue. Show actual processing/failure states, not simulated success. The inspector should let the user select a check, view its source image(s), compare expected/observed/missing/unknown components, inspect rule source/version and see the exact rationale. Show highlights only when grounded coordinates exist; otherwise provide an honest image-level citation. Include rule dependencies for disposition and a visible override history with required reasons.

Recommended HTTP endpoints in the guide are POST /agent and GET /health, not mandated framework choices. Other upload/review/export interfaces are implementation proposals. Keep provider credentials and rule execution on the server. Do not claim authentication, persistence, tests or a working UI exist yet.

## 9. UNCERTAIN, errors and edge cases

UNCERTAIN describes evidential insufficiency; pending_review describes the operational routing. Preserve partial results and request the specific missing view/reference/test rather than repeatedly calling a model hoping for a confident answer.

Plan coverage for absent/corrupt/unsupported images; inaccessible placeholder paths; blur/glare/occlusion; conflicting photos; empty boxes; duplicates; multi-unit images; similar variants; missing or contradictory order/catalogue data; unknown quantities; required parts not visible in a sealed box; identical parts; superficial versus functional damage; prohibited category assumptions; malformed model output; timeout/rate limit/dependency failure; retry duplication; and cross-tenant lookups.

For accepted captures, retain input before inference, preserve attempt/error details, retry transient failures within a documented bound and route unresolved attempts to review. Validation errors should identify repairable fields without assigning invented IDs. Unauthorized requests are rejected without disclosing another tenant's data: fail-open capture preservation does not mean fail-open authorization. Conflicting or duplicate submissions require idempotent handling and separate versions when evidence changes. Recovery exports must not present review-pending cases as settled decisions.

## 10. Evaluation harness and 50-unit methodology

No evaluation dataset or measured agent result exists yet. The sample CSV is for schema/UI engineering, explicitly not training or ground truth. The data guide specifies 50 unseen units labelled independently by two humans; README/RULES/handbook reinforce this approach with 'where applicable' language. Plan at least 50 genuinely distinct held-out physical units for this visual track, separate from development fixtures.

Proposed coverage budget: five distinct units assigned to each of ten primary scenarios, for 50 total. These are collection targets, not observed counts or benchmark weights:

1. Correct returned product: matching identifiers and adequate component coverage.
2. Wrong returned product: documented discrepancy, including legible conflicting labels.
3. Missing accessory: one independently verified absent required item.
4. Multiple missing accessories: several verified absent components.
5. New-looking return: distinguish visual appearance from evidence needed for an official New grade.
6. Lightly used return: variable minor wear; grade only under confirmed criteria.
7. Damaged return: visible damage with independent functional information where needed.
8. Heavily damaged return: severe visible damage without assuming economic worthlessness.
9. Visually similar products: variants requiring discriminating identifiers/views.
10. Ambiguous/low-visibility evidence: blur, glare, occlusion or unavailable relevant views; uncertainty may be the correct label.

Primary scenario assignments avoid counting a unit twice; secondary tags can overlap. Balance identities/components/grades and relevant product categories across these groups, acknowledging that five per group gives limited precision. Include lighting, angles, backgrounds and capture devices as secondary variation. Extra functional/security/failure-injection tests do not inflate the 50-unit vision denominator.

Two humans independently label each frozen unit before inference using the same documented reference information and authoritative rules. Record labels per layer and per component, uncertainty reason and evidence visibility. Where physical truth is available, retain it separately from what the supplied photos can justify; do not punish correct abstention on invisible facts. Compute agreement before adjudication; record disagreements and independent reasons, then adjudicate transparently. If ground truth remains unresolved, report it explicitly rather than forcing consensus.

Split by physical unit before prompt/rule tuning; near-duplicate views of the same unit stay in one partition. Freeze unit/image hashes, label versions, policy versions, prompt/model configuration and scoring code before the held-out run. Do not put labels, synthetic operator decisions or scenario names revealing the answer into inference requests. A rerun after tuning is a new evaluation version and no longer an untouched holdout.

Proposed harness stages: validate manifests and tenant ownership -> load only permitted inputs -> run observation/check pipeline -> validate schema and evidence references -> retain actual raw/normalized outputs and timing -> compare to adjudicated labels -> report every unit, including failures. Dry-run wiring may use explicitly marked synthetic test inputs, never presented as model predictions or scored visual evidence.

Planned metrics and denominators:

- Identity/completeness: define positive as a supported PASS (correct identity/complete unit). FP is predicted PASS on human FAIL; FN is predicted FAIL on human PASS. Report TP/TN/FP/FN counts, FPR = FP/(FP+TN), FNR = FN/(FN+TP) on determinate human and agent cases, plus those denominator counts. Abstentions stay outside binary denominators and are reported separately, preventing high abstention from masquerading as accuracy.
- Show the complete PASS/FAIL/UNCERTAIN confusion counts and abstentions among human-determinate cases. Report decisive coverage, accuracy among decided cases, and correct decisive predictions divided by all human-determinate cases. Report unsupported definitive decisions on human-UNCERTAIN cases.
- Components: per-component missing detection and per-unit completeness, with defined count matching and explicit unknown components.
- Condition: confusion matrix and exact agreement for confirmed official grades; separate unknown/unassignable cases. Do not encode an invented severity scale to compute distance metrics.
- Disposition: five-value confusion matrix including pending_review, policy-expected agreement and inappropriate definitive recommendations. Do not treat high restock rate as success.
- Human agreement: raw per-layer agreement and Cohen's kappa where meaningful; report label distributions and undefined cases. Adjudicated labels must not replace original labels for agreement calculations.
- Uncertainty/review rate: per-check UNCERTAIN count over all attempted units; pending_review count over all attempted units; break down missing evidence, policy gaps and dependency failures.
- Latency/cost: actual end-to-end and provider durations, sample counts, median/p95, retries and failures; actual usage with pricing basis when available. Report unavailable telemetry as unavailable, not zero. Distinguish cached from fresh inference.

Each evaluation row should contain tenant-scoped unit_id, evidence references, two independent labels, adjudication, actual agent results, versions, agreement, uncertainty, failure notes and telemetry. Report all cases and uncertainty intervals where practical. No numerical accuracy, kappa, latency or cost targets are fabricated here.

## 11. Phased roadmap and acceptance gates

Phase 0 (this task): complete repository audit, boundary verification, conflict register and planning documents. No implementation.

Phase 1 (recommended next, requires a new implementation request): establish a minimal headless contract/capture foundation inside the participant directory. Obtain the official schema and applicable condition/disposition policy; define validated inputs and four independent result types; preserve tenant/unit context; support unavailable-evidence -> UNCERTAIN/pending_review; build parser, reference validation and pure-rule test scaffolding using explicitly labelled fixtures. If storing data, implement and test isolation before features. Create an evaluation manifest/label protocol separate from the sample CSV. Do not add speculative grade mappings while policy is unresolved.

Phase 1 acceptance: sample parsing preserves all 24 unit IDs and both existing org IDs, placeholder photos remain unavailable, missing client context is not fabricated, forbidden disposition values are rejected, captured input survives controlled dependency failure, and persistent record/image access cannot cross tenant boundaries. These are planned checks, not completed tests. Resolve wire-schema unknowns before claiming interoperability.

Phase 2: actual photo collection and catalogue references, batched vision adapter, grounded observations, sourced deterministic checks and disposition policy, with small development fixtures and honest telemetry.

Phase 3: UI inspection workspace, evidence inspector, review/override workflow and end-to-end error handling. Prove the workflow before visual polish.

Phase 4: freeze and run the 50-unit evaluation, report labels/metrics/failure modes; improve using development cases only or collect a new holdout after tuning.

Phase 5: reproducible setup, final architecture/evaluation docs, real demo and deployment if applicable, required public post and final submission checks. None of these external actions is authorized by the current planning request.

## 12. Risks and human confirmations

Evaluation risks: no supplied images, all-positive sample identities, blank grades, invented catalogue identifiers, unknown functional evidence, label disagreement, small strata, model confidence miscalibration, leakage through annotations/duplicate units, and policy ambiguity. Arrange genuine evidence and two labelers early; do not compensate with manufactured screenshots or outputs.

Submission/compliance risks: stale PR/template instructions, root README discoverability under the user boundary, exact official schema absent, no automatic correctness/secrets/deadline checks in the guard, and no resubmission. Repository/handbook dates state build opens 25 September 2026 at 09:00 IST, submissions open 27 September and close 1 October at 18:00 IST. Handbook p. 6 says organisers may communicate a distinct operational build cutoff. These are source-recorded dates, not a live portal verification. LinkedIn tags and official communicated hashtags are required; the template is not supplied. No mandatory 2-3 minute demo duration is established by the handbook's 'concise' wording.

Confirm before the dependent phase:

1. Organiser's exact versioned evidence schema, status/nullability/enums, unit_id placement and content_hash rules.
2. Applicable Amazon marketplace/category and accessible current condition definitions, plus accepted sources of nonvisual functional evidence.
3. Business disposition policy and who can approve it; condition definitions alone do not prescribe restock/refurbish/liquidate/dispose.
4. Real client_id/authentication context if client scoping is required; never substitute handoff example identifiers.
5. Availability of catalogue/order references, real image fixtures and two independent human labelers for 50 held-out units.
6. Organiser clarification on retained template/PR workflow and final nested-document discoverability, exact operational cutoff if different, and live portal fork verification. The origin confirms a configured fork URL, not registration/verification status.

These questions do not prevent the requested documentation. They constrain later implementation and claims. No external messages, issue creation or portal changes were performed.
