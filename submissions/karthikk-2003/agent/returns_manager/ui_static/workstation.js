/* Internal UI projections only. All provider/source strings are rendered as text. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const state = {context: null, queue: [], queueReady: false, selected: null, detail: null, history: [], generation: 0, queueGeneration: 0, saving: false};
  const pending = new Map();
  const drafts = new Map();
  const el = (tag, text, cls) => { const n = document.createElement(tag); if (text !== undefined && text !== null) n.textContent = String(text); if (cls) n.className = cls; return n; };
  const pretty = value => String(value ?? 'Unavailable').replaceAll('_', ' ');
  const date = value => { const d = new Date(value); return Number.isNaN(d.getTime()) ? String(value ?? 'Unavailable') : d.toLocaleString(); };
  const button = (label, action, cls = 'quiet') => { const n = el('button', label, cls); n.type = 'button'; n.addEventListener('click', action); return n; };
  const badge = (label, cls = '') => el('span', label, 'badge ' + cls);
  const unavailable = text => el('p', text, 'unavailable');
  function notice(message, error = false) { $('notice').textContent = message; $('notice').className = 'notice' + (error ? ' error' : ''); }
  function errorBox(parent, message, retry) { parent.replaceChildren(el('p', message, 'error-box'), button('Retry', retry)); }
  async function api(path, body, timeoutMs = 12000) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const options = {signal: controller.signal, cache: 'no-store', credentials: 'same-origin'};
      if (body) Object.assign(options, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Returns-Request': '1'}, body: JSON.stringify(body)});
      let response;
      try { response = await fetch(path, options); }
      catch (err) { $('system-status').textContent = 'Connection unavailable'; throw err; }
      $('system-status').textContent = 'Connected · local adapter';
      let result;
      try { result = await response.json(); } catch { throw Object.assign(new Error('The server response could not be read.'), {status: response.status >= 400 ? response.status : 0}); }
      if (!response.ok) throw Object.assign(new Error(result.error?.message || 'Request failed.'), {status: response.status});
      return result;
    } finally { clearTimeout(timeout); }
  }
  function workflowLabel(item) { return item.reopened ? 'Reopened · in review' : pretty(item.status); }
  function renderQueue() {
    if (!state.queueReady) return;
    const filter = $('queue-filter').value;
    const rows = state.queue.filter(r => filter === 'all' || (filter === 'reopened' ? r.reopened : r.status === filter));
    $('queue-count').textContent = state.queue.length;
    $('queue-list').replaceChildren();
    $('queue-state').textContent = !state.queue.length ? 'No review cases in this scope.' : !rows.length ? 'No cases match this workflow filter.' : `${rows.length} cases shown`;
    for (const row of rows) {
      const b = button('', () => selectCase(row.review_id), 'queue-row');
      b.setAttribute('aria-current', String(row.review_id === state.selected));
      b.append(el('span', row.unit_id, 'row-title'), el('div', `${row.record_id} · Case ${row.review_id}`, 'row-sub'), badge(workflowLabel(row), row.status === 'reviewed' ? 'good' : 'warning'));
      const conflict = row.uncertainty.some(r => r.code.startsWith('conflicting_'));
      b.append(el('div', conflict ? 'Conflict · review required' : row.unresolved_decisions.length ? 'Uncertain · review required' : 'See review reasons', 'row-reason'));
      b.append(el('time', date(row.updated_at)));
      $('queue-list').append(b);
    }
  }
  async function loadQueue() {
    const token = ++state.queueGeneration;
    state.queueReady = false;
    $('queue-list').replaceChildren(); $('queue-state').textContent = 'Loading review queue…';
    try {
      const data = await api('/api/reviews');
      if (token !== state.queueGeneration) return;
      state.queue = data.reviews; state.queueReady = true; renderQueue();
      if (state.selected !== null && !state.queue.some(r => r.review_id === state.selected)) {
        ++state.generation; state.selected = null; state.detail = null; clearWorkspace('This review is no longer available in this scope.');
      }
    } catch (err) {
      if (token !== state.queueGeneration) return;
      $('queue-count').textContent = '—';
      errorBox($('queue-state'), 'Review queue unavailable. ' + err.message, loadQueue);
    }
  }
  function clearWorkspace(message) {
    $('workspace-content').hidden = true;
    $('workspace-state').hidden = false;
    $('workspace-state').replaceChildren(el('p', 'INSPECTION', 'eyebrow'), el('h2', message));
    $('open-review').disabled = true;
  }
  async function selectCase(id) {
    const token = ++state.generation;
    state.selected = id; state.detail = null; state.history = [];
    renderQueue(); clearWorkspace('Loading return…');
    try {
      const detail = await api(`/api/reviews/${id}`);
      if (token !== state.generation) return;
      state.detail = detail;
      $('workspace-state').hidden = true; $('workspace-content').hidden = false;
      renderDetail();
      await loadHistory(id, token);
    } catch (err) {
      if (token !== state.generation) return;
      clearWorkspace('Return unavailable');
      errorBox($('workspace-state'), 'Could not load this return. ' + err.message, () => selectCase(id));
    }
  }
  function datum(label, value) {
    const n = el('div', null, 'datum'); n.append(el('span', label, 'meta-label'), el('span', value ?? 'Unknown / unavailable', 'meta-value')); return n;
  }
  function citations(refs) {
    const box = el('div', null, 'citations');
    for (const ref of refs || []) box.append(button(ref, () => {
      const i = state.detail.evidence.findIndex(e => e.evidence_id === ref);
      const target = i < 0 ? $('evidence') : $('evidence-' + i);
      target.scrollIntoView({block: 'center'}); target.focus({preventScroll: true});
    }, 'citation'));
    return box;
  }
  function resultLines(dimension) {
    const d = state.detail, box = el('div', null, 'result-line');
    box.append(el('p', `Automated result: ${d.automated_assessment?.[dimension]?.verdict ?? 'Unavailable'}`));
    const automated = d.automated_assessment?.[dimension];
    if (automated) box.append(el('p', (automated.reasons || []).map(pretty).join(' · ')), citations(automated.evidence || []));
    const human = d.human_decisions[dimension];
    box.append(el('p', human ? `Human assertion: ${human.verdict} · ${human.reviewer_id} · revision ${human.revision}` : 'Human assertion: Not recorded'));
    if (human) box.append(el('p', human.reason), citations(human.evidence_refs));
    return box;
  }
  function renderDetail() {
    const d = state.detail, c = d.capture, batch = d.observations;
    const reference = d.automated_assessment?.decision_reference;
    $('return-title').textContent = c.unit.unit_id;
    $('return-meta').replaceChildren(...[
      ['Record', d.record_id], ['Organization', d.organization_id], ['Order', c.order.order_id],
      ['Capture timestamp', `${date(c.captured_at)} · ${c.captured_at}`], ['Capture operator', c.operator_id], ['Review case / revision', `${d.review_id} / ${d.revision}`]
    ].map(([k,v]) => datum(k,v)));
    const row = state.queueReady ? state.queue.find(r => r.review_id === d.review_id && r.revision === d.revision) : null;
    $('return-status').replaceChildren(badge('Workflow: ' + workflowLabel({...d, reopened: row?.reopened || false}), 'warning'), el('strong', 'Business disposition: ' + pretty(d.business_status)));
    const telemetry = d.raw_response;
    const providerLabel = batch?.provider_name === 'gemini' ? 'Gemini · LIVE' : batch?.provider_name === 'ollama' ? 'Ollama · LOCAL' : 'Fixture · TEST ONLY';
    $('provenance-banner').textContent = `${reference?.reference_status === 'synthetic_demo' ? 'DEMO / SYNTHETIC REFERENCE DATA. Not a verified real catalogue.' : reference ? 'Order/catalogue reference attested by ' + reference.verified_by + '; source snapshot retained.' : 'Reference context is synthetic and unverified.'} ${batch ? providerLabel : 'No validated visual observations.'} ${telemetry?.model_version || ''} ${telemetry?.latency_ms != null ? '· Measured latency: ' + (telemetry.latency_ms / 1000).toFixed(2) + 's' : ''}. Model observations are not verified facts or business decisions.`;
    const expected = el('div'), observed = el('div'), compare = el('div', null, 'comparison');
    expected.append(el('p', 'EXPECTED', 'column-label'), badge(reference?.reference_status === 'synthetic_demo' ? 'DEMO / SYNTHETIC REFERENCE DATA' : reference ? 'Attested order/catalogue context' : 'Synthetic reference context'), datum('SKU', c.order.ordered_sku), datum('ASIN', c.order.ordered_asin));
    observed.append(el('p', 'OBSERVED', 'column-label'));
    if (!batch?.identity.length) observed.append(unavailable('Not observed / unavailable'));
    for (const o of batch?.identity || []) {
      const n = el('div', null, 'observation');
      n.append(el('strong', `${pretty(o.field)} · ${pretty(o.state)}`), el('p', o.values.length ? o.values.join(' / ') : 'No observed value'), el('p', o.limitations.join(' · '), 'caption'), citations(o.evidence_refs)); observed.append(n);
    }
    compare.append(expected, observed); $('identity-body').replaceChildren(compare, resultLines('identity'));
    const cb = $('condition-body'); cb.replaceChildren();
    if (!batch?.condition.length) cb.append(unavailable('Physical observations unavailable'));
    for (const o of batch?.condition || []) {
      const n = el('div', null, 'observation'); n.append(el('strong', `${pretty(o.feature)} · ${pretty(o.state)}`), el('p', o.description || 'No description supplied'), el('p', o.limitations.join(' · '), 'caption'), citations(o.evidence_refs)); cb.append(n);
    }
    cb.append(datum('Condition grade', d.automated_assessment?.condition?.grade ?? 'Not assigned'), el('p', 'Insufficient evidence or unresolved policy.', 'caption'), resultLines('condition'));
    if (d.automated_assessment?.condition?.policy_source) cb.append(
      datum('Condition definition source', d.automated_assessment.condition.policy_source),
      el('p', 'Amazon condition guidance requires category-specific and nonvisual checks. Photographs alone do not establish a final grade. No grade-to-disposition mapping has been supplied.', 'caption'));
    const comp = $('completeness-body'); comp.replaceChildren(el('p', 'UNKNOWN ≠ MISSING · NOT VISIBLE ≠ MISSING', 'caption'));
    const table = el('table'), head = el('thead'), hr = el('tr');
    for (const title of ['Expected component', 'Expected qty', 'Observed qty', 'Presence / visibility', 'Evidence']) hr.append(el('th', title));
    head.append(hr); table.append(head); const tbody = el('tbody');
    const components = reference?.components || c.reference.components;
    const names = [...new Set([...components.map(x => x.name), ...(batch?.components || []).map(x => x.component)])];
    for (const name of names) {
      const expectedPart = components.find(x => x.name === name);
      const observations = (batch?.components || []).filter(x => x.component === name);
      for (const o of observations.length ? observations : [null]) {
        const tr = el('tr');
        tr.append(el('td', name + (expectedPart ? '' : ' (not in reference)')), el('td', expectedPart?.quantity ?? 'Unknown'), el('td', o?.quantity_reliable ? o.quantity : 'Unknown'));
        const cell = el('td'); cell.append(el('strong', o ? pretty(o.presence) : 'Unknown'), el('p', o ? 'Visibility: ' + pretty(o.visibility) : 'Not observed / unavailable'));
        if (o?.absence_basis) cell.append(el('p', 'Absence basis: ' + o.absence_basis));
        if (o?.limitations.length) cell.append(el('p', o.limitations.join(' · '), 'caption'));
        const evidence = el('td'); evidence.append(o ? citations(o.evidence_refs) : el('span', 'Unavailable'));
        tr.append(cell, evidence); tbody.append(tr);
      }
    }
    table.append(tbody); const wrap = el('div', null, 'table-wrap'); wrap.append(table);
    comp.append(names.length ? wrap : unavailable('Expected components unavailable'), resultLines('completeness'));
    const completeness = d.automated_assessment?.completeness;
    if (completeness) comp.append(datum('Confirmed missing components', completeness.missing_components.join(', ') || 'None established'),
      datum('Unresolved components', completeness.unknown_components.join(', ') || 'None listed'));
    renderEvidence(); renderUncertainty();
    $('open-review').disabled = !state.context || !d.allowed_transitions.length;
  }
  function renderEvidence() {
    const d = state.detail, body = $('evidence-body'), grid = el('div', null, 'evidence-grid');
    body.replaceChildren(el('p', 'Only configured demo images with matching persisted hashes can be displayed. Demo images are not benchmark data.', 'caption'));
    d.evidence.forEach((e,i) => {
      const card = el('article', null, 'evidence-card'); card.id = 'evidence-' + i; card.tabIndex = -1;
      const empty = el('div', null, 'image-unavailable'); empty.append(el('strong', 'IMAGE UNAVAILABLE'), el('span', e.availability === 'fixture_only' ? 'Fixture metadata only' : e.availability === 'available' ? 'Bytes not served by this UI' : 'No inspectable image supplied'));
      if (e.availability === 'available' && e.kind === 'genuine') {
        const image = el('img'); image.alt = 'Configured demo evidence ' + e.evidence_id;
        image.src = `/api/reviews/${d.review_id}/images/${i}`; image.className = 'demo-evidence-image';
        image.addEventListener('error', () => image.replaceWith(unavailable('Image unavailable or no longer matches its recorded hash.')));
        empty.replaceChildren(image);
      }
      card.append(empty, datum('Evidence ID', e.evidence_id || 'Not assigned'), datum('Reference', e.reference), datum('Availability', e.availability), datum('Type / designation', [e.image_role, e.kind].filter(Boolean).join(' / ') || 'Capture reference · synthetic placeholder'), datum('Source / reason', e.reason || e.source_relationship), datum('SHA-256', e.sha256 || 'Not available'));
      const related = [];
      for (const key of ['identity','components','condition']) for (const o of d.observations?.[key] || []) if (o.evidence_refs.includes(e.evidence_id)) related.push(`${key}: ${o.field || o.component || o.feature}`);
      card.append(datum('Observation citations', related.join('; ') || 'None')); grid.append(card);
    });
    body.append(d.evidence.length ? grid : unavailable('No evidence references supplied.'));
    const source = d.capture.source;
    body.append(datum('Source lineage', `${source.source_name} · row ${source.row_number} · ${source.kind}`), datum('Source SHA-256', source.source_sha256), datum('Observation source', d.source_key));
    const raw = el('details'); raw.append(el('summary', 'Raw provider response'), el('pre', d.raw_response ? JSON.stringify(d.raw_response, null, 2) : 'No accepted raw provider response available.'));
    body.append(raw);
    const reference = d.automated_assessment?.decision_reference;
    if (reference) {
      const sourceDetail = el('details'); sourceDetail.append(el('summary', reference.reference_status === 'synthetic_demo' ? 'DEMO / SYNTHETIC reference snapshot and image hash' : 'Order/catalogue attestation and source snapshot'),
        el('pre', JSON.stringify(reference, null, 2)));
      body.append(datum('Decision rule version', d.automated_assessment.rule_version), sourceDetail);
    }
  }
  function renderUncertainty() {
    const d = state.detail, box = $('uncertainty-body'), reasons = el('ul', null, 'reason-list');
    for (const r of d.uncertainty) reasons.append(el('li', `${r.dimension}: ${r.code}`));
    const conflicts = d.observations?.conflicts || [];
    const grid = el('div', null, 'review-grid');
    for (const [title, value] of [
      ['What is known', d.automated_assessment?.decision_reference?.reference_status === 'synthetic_demo' ? 'Synthetic demo expectations only; real product identity and accessories are unverified.' : d.automated_assessment?.decision_reference ? 'Order/catalogue attestation and exact source snapshot are preserved. Attestation is not independent proof of truth.' : 'Order and source context are preserved. Reference context remains unverified.'],
      ['What is unknown', d.unresolved_decisions.join(', ') || 'See recorded review reasons.'],
      ['What is conflicting', conflicts.length ? conflicts.join(' · ') : 'No validated conflicts recorded. This does not establish agreement.']
    ]) { const n = el('div'); n.append(el('h3', title), el('p', value)); grid.append(n); }
    box.replaceChildren(badge('REVIEW REQUIRED', 'warning'), reasons, grid, el('h3', 'What the reviewer can do'), el('p', 'Inspect available context, record a reason and use the permitted workflow or identity/completeness assertions. No condition or disposition override is available.'));
    if (d.observations?.limitations.length) box.append(datum('Observation limitations', d.observations.limitations.join(' · ')));
    if (d.processing_error_at_routing) box.append(datum('Processing error at routing', d.processing_error_at_routing));
  }
  async function loadHistory(id = state.selected, token = state.generation) {
    if (!id) return;
    $('history-body').replaceChildren(el('p', 'Loading audit history…', 'loading'));
    try {
      const data = await api(`/api/reviews/${id}/history`);
      if (token !== state.generation || id !== state.selected) return;
      state.history = data.events; $('history-body').replaceChildren();
      if (!data.events.length) $('history-body').append(unavailable('No history available.'));
      for (const event of data.events) {
        const n = el('details', null, 'history-event');
        const summary = el('summary'); summary.append(el('span', `Revision ${event.revision} · ${event.actor_kind}: ${event.actor_id}`), el('span', date(event.timestamp), 'caption'));
        n.append(summary, el('p', event.reason), datum('Workflow change', `${event.previous_state?.status || 'No prior state'} → ${event.new_state.status}`));
        if (event.overrides.length) n.append(el('pre', JSON.stringify(event.overrides, null, 2)));
        const full = el('details'); full.append(el('summary', 'Full event data'), el('pre', JSON.stringify(event, null, 2))); n.append(full); $('history-body').append(n);
      }
    } catch (err) { if (token === state.generation) errorBox($('history-body'), 'Audit history unavailable. ' + err.message, () => loadHistory()); }
  }
  function actionLabel(target) {
    if (target === 'in_review') return state.detail.status === 'reviewed' ? 'Reopen review' : state.detail.status === 'in_review' ? 'Save review' : 'Start review';
    return target === 'reviewed' ? 'Mark reviewed' : 'Return to pending review';
  }
  function configureForm(reason = '') {
    const d = state.detail;
    $('target-status').replaceChildren(...d.allowed_transitions.map(s => { const o = el('option', actionLabel(s)); o.value = s; return o; }));
    $('review-context').textContent = `${d.record_id} / ${d.unit_id} · Reviewer: ${state.context.reviewer_id} · Expected revision: ${d.revision}`;
    $('review-reason').value = reason;
    $('identity-decision').value = ''; $('completeness-decision').value = '';
    $('citation-list').replaceChildren();
    for (const e of d.evidence.filter(e => ['available','fixture_only'].includes(e.availability) && e.evidence_id)) {
      const label = el('label'), input = el('input'); input.type = 'checkbox'; input.value = e.evidence_id;
      label.append(input, document.createTextNode(` ${e.evidence_id} · ${e.availability} · ${e.reference}`)); $('citation-list').append(label);
    }
    $('review-fields').disabled = false; updateDecisionControls();
  }
  function updateDecisionControls() {
    const permitted = state.detail.status === 'in_review' && ['in_review','reviewed'].includes($('target-status').value);
    const hasEvidence = $('citation-list').children.length > 0;
    for (const dimension of ['identity','completeness']) {
      const select = $(dimension + '-decision'); select.disabled = !permitted;
      if (!permitted) select.value = '';
      for (const option of select.options) if (['PASS','FAIL'].includes(option.value)) option.disabled = !hasEvidence;
    }
    $('citation-options').hidden = !permitted || !hasEvidence;
    $('assertion-guidance').textContent = !permitted ? 'Start an active review before recording human assertions.' : hasEvidence ? 'Decisive assertions require selected citations. Fixture evidence remains fixture-only.' : 'No usable evidence citations. Only UNCERTAIN assertions are available.';
  }
  function openReview() {
    if (!state.detail || !state.context) return;
    const saved = pending.get(state.selected);
    configureForm(saved?.reason ?? drafts.get(state.selected) ?? '');
    $('review-feedback').textContent = '';
    if (saved) {
      const option = el('option', 'Retry previous action: ' + pretty(saved.status)); option.value = saved.status; $('target-status').replaceChildren(option);
      $('review-context').textContent += ` · Retrying original revision ${saved.expected_revision}`;
      for (const d of saved.decisions || []) $(d.dimension + '-decision').value = d.verdict;
      $('review-fields').disabled = true;
      $('review-feedback').textContent = 'Previous outcome is unconfirmed. Retry sends the exact original command, not a new action.';
    }
    $('save-review').textContent = saved ? 'Retry same action' : 'Save review action';
    $('review-dialog').showModal(); $('review-reason').focus();
  }
  async function submitReview(event) {
    event.preventDefault();
    if (state.saving || !state.detail) return;
    const id = state.selected;
    let command = pending.get(id);
    if (!command) {
      if (!$('review-reason').value.trim()) { $('review-feedback').textContent = 'A reason is required.'; $('review-reason').focus(); return; }
      const refs = [...$('citation-list').querySelectorAll('input:checked')].map(n => n.value);
      const decisions = ['identity','completeness'].filter(d => !$(d + '-decision').disabled && $(d + '-decision').value).map(d => ({dimension:d, verdict:$(d+'-decision').value, evidence_refs:refs}));
      if (decisions.some(d => d.verdict !== 'UNCERTAIN' && !d.evidence_refs.length)) { $('review-feedback').textContent = 'Select existing evidence citations for PASS or FAIL.'; return; }
      command = {status:$('target-status').value, reason:$('review-reason').value, expected_revision:state.detail.revision, command_id:crypto.randomUUID(), decisions};
      pending.set(id, command);
    }
    state.saving = true; $('save-review').disabled = true; $('close-review').disabled = true; $('review-fields').disabled = true;
    $('review-feedback').textContent = 'Saving review action…';
    try {
      await api(`/api/reviews/${id}/transition`, command);
      pending.delete(id); drafts.delete(id); $('review-dialog').close();
      notice('Review action recorded. Original automated evidence is retained; business disposition remains pending review.');
      await loadQueue(); if (state.selected === id) await selectCase(id);
    } catch (err) {
      if (err.status === 409) {
        pending.delete(id); drafts.set(id, command.reason);
        await selectCase(id);
        if (state.detail) configureForm(command.reason);
        $('review-feedback').textContent = 'The record changed or the command conflicted. Current state was reloaded; your explanation is preserved. Review the action and submit again explicitly.';
        $('save-review').textContent = 'Save review action';
      } else if (err.status && err.status < 500) {
        pending.delete(id); $('review-fields').disabled = false; updateDecisionControls();
        $('review-feedback').textContent = err.message; $('save-review').textContent = 'Save review action';
      } else {
        $('review-feedback').textContent = 'Save outcome unconfirmed. ' + err.message + ' Retry the same action; do not create a new command. Keep this page open or check history before acting after a reload.';
        $('save-review').textContent = 'Retry same action';
      }
    } finally { state.saving = false; $('save-review').disabled = !state.detail; $('close-review').disabled = false; }
  }
  async function bootstrap() {
    try {
      const [context] = await Promise.all([api('/api/context'), api('/health')]);
      state.context = context;
      if (context.demo_case) notice('DEMO / SYNTHETIC REFERENCE DATA · ' + context.demo_case + ' · not customer data or benchmark ground truth.');
      $('organization').textContent = context.organization_id + (context.client_id === null ? ' · Client not supplied' : ' · ' + context.client_id);
      $('reviewer').textContent = 'Reviewer: ' + context.reviewer_id;
      $('ai-provider').textContent = 'AI provider: ' + (context.ai_provider === 'gemini' ? 'Gemini · LIVE' : context.ai_provider === 'ollama' ? 'Ollama · LOCAL' : context.ai_provider === 'fixture' ? 'Fixture · TEST ONLY' : 'disabled');
      $('run-demo').disabled = !context.demo_enabled;
      $('system-status').textContent = 'Connected · local adapter';
    } catch (err) { $('system-status').textContent = 'Connection unavailable'; notice('Could not establish trusted server context. Use Refresh to retry. ' + err.message, true); }
    await loadQueue();
  }
  $('queue-filter').addEventListener('change', renderQueue);
  let demoCommand = null;
  $('run-demo').addEventListener('click', async () => {
    if (!state.context?.demo_enabled) return;
    const control = $('run-demo'); control.disabled = true;
    demoCommand = demoCommand || crypto.randomUUID();
    $('demo-progress').textContent = state.context.ai_provider === 'gemini'
      ? 'Inspecting configured images. Temporary Gemini HTTP failures may retry twice at most; no provider fallback. Please wait…'
      : 'Inspecting configured images. No fallback or automatic retry. Please wait…';
    try {
      const result = await api('/api/demo/inspect', {command_id: demoCommand}, 650000);
      demoCommand = null;
      $('demo-progress').textContent = result.reused ? 'Existing attempt recovered.' : result.status === 'validated' ? 'Validated observations recorded; review required.' : `Inspection unavailable: ${result.diagnostic || result.error_code}. Review case recorded.`;
      await loadQueue(); await selectCase(result.review_id);
    } catch (err) {
      $('demo-progress').textContent = 'Outcome unconfirmed. Refresh the queue before retrying the same attempt. ' + err.message;
    } finally { control.disabled = false; }
  });
  $('refresh').addEventListener('click', async () => { if (!state.context) await bootstrap(); else { await loadQueue(); if (state.selected) await selectCase(state.selected); } });
  $('queue-list').addEventListener('keydown', event => {
    const rows = [...$('queue-list').querySelectorAll('button')], i = rows.indexOf(document.activeElement);
    let next = i; if(event.key === 'ArrowDown') next = Math.min(i+1, rows.length-1); else if(event.key === 'ArrowUp') next = Math.max(0,i-1); else if(event.key === 'Home') next=0; else if(event.key === 'End') next=rows.length-1; else return;
    event.preventDefault(); rows[next]?.focus();
  });
  $('reload-history').addEventListener('click', () => loadHistory());
  $('open-review').addEventListener('click', openReview);
  $('target-status').addEventListener('change', updateDecisionControls);
  $('review-form').addEventListener('submit', submitReview);
  $('close-review').addEventListener('click', () => { if (!state.saving) { drafts.set(state.selected, $('review-reason').value); $('review-dialog').close(); } });
  $('review-dialog').addEventListener('cancel', event => { if (state.saving) event.preventDefault(); else drafts.set(state.selected, $('review-reason').value); });
  bootstrap();
})();
