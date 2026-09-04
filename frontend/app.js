/**
 * LEDGER/CTRL — App Console JS
 * Complete logic for Pipeline, Import, Evaluation, Exceptions, and Audit tabs.
 */
'use strict';

const $ = id => document.getElementById(id);
const inr = n => '\u20b9' + new Intl.NumberFormat('en-IN', {maximumFractionDigits: 0}).format(n);
const pct = (x, digits=1) => (x != null && !isNaN(x)) ? (x * 100).toFixed(digits) + '%' : 'N/A';
const esc = s => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function jfetch(url, opts) {
  const r = await fetch(url, { headers: {'Content-Type': 'application/json'}, ...opts });
  if (!r.ok) { const t = await r.text(); throw new Error(`HTTP ${r.status}: ${t}`); }
  return r.json();
}

const S = {
  currentBatch: null,
  allRecords:   [],
  exceptions:   [],
  metrics:      null,
  uploadSession: null,
  selectedFiles: { settlements: null, bank: null, invoices: null },
};

function switchTab(tab) {
  document.querySelectorAll('.tab-btn').forEach(b => {
    b.classList.toggle('active', b.id === 'tab-' + tab);
    b.setAttribute('aria-selected', b.id === 'tab-' + tab);
  });
  document.querySelectorAll('.tab-panel').forEach(p => {
    p.classList.toggle('active', p.id === 'panel-' + tab);
  });
  location.hash = tab;
  if (tab === 'evaluation' && S.currentBatch) renderEvaluation();
  if (tab === 'exceptions' && S.currentBatch) renderExceptions();
}
window.switchTab = switchTab;

function applyHash() {
  const h = location.hash.replace('#', '');
  if (['pipeline','evaluation','exceptions','audit'].includes(h)) switchTab(h);
}
window.addEventListener('hashchange', applyHash);
document.addEventListener('DOMContentLoaded', () => { applyHash(); loadLatestBatch(); });

function setLoading(on) {
  $('main-spinner').classList.toggle('active', on);
  $('btn-run').disabled = on;
}

const STAGES = ['generate','normalize','match','policy','audit','eval','done'];
function resetStages() {
  $('stages-wrap').style.display = 'block';
  STAGES.forEach(s => { const el = $('stage-' + s); if (el) el.className = 'stage-chip'; });
}
function setStage(name, done=false) {
  STAGES.forEach(s => {
    const el = $('stage-' + s);
    if (!el) return;
    if (s === name && !done) { el.className = 'stage-chip active'; }
    else if (STAGES.indexOf(s) < STAGES.indexOf(name)) { el.className = 'stage-chip done'; }
    else { el.className = 'stage-chip'; }
  });
  if (done) { const el = $('stage-' + name); if (el) el.className = 'stage-chip done'; }
}

async function runFull() {
  setLoading(true);
  resetStages();
  hideSummary();
  setStage('generate');
  try {
    const n    = parseInt(($('n') || {}).value) || 200;
    const seed = parseInt(($('seed') || {}).value) || null;
    const split = ($('split') || {}).value || 'holdout';
    const useLLM = ($('use-llm') || {}).value === 'true';

    const gen = await jfetch('/api/batches/generate', {
      method: 'POST',
      body: JSON.stringify({ n, seed: seed || undefined, split }),
    });
    S.currentBatch = {
      id:    gen.batch_id,
      n:     gen.n_settlements,
      seed:  gen.seed,
      split: gen.split,
    };
    if ($('seed')) $('seed').value = gen.seed;
    setStage('generate', true);
    setStage('normalize');
    await sleep(120);

    setStage('normalize', true);
    setStage('match');
    await jfetch(`/api/batches/${gen.batch_id}/reconcile`, {
      method: 'POST',
      body: JSON.stringify({ use_llm: useLLM }),
    });
    setStage('match', true); setStage('policy'); await sleep(80);
    setStage('policy', true); setStage('audit'); await sleep(80);
    setStage('audit', true); setStage('eval');

    const detail = await jfetch('/api/batches/' + gen.batch_id);
    S.metrics = detail.metrics || {};
    if (detail.run_id && S.metrics) S.metrics.run_id = detail.run_id;
    setStage('eval', true); setStage('done');

    const [matches, exc] = await Promise.all([
      jfetch('/api/batches/' + gen.batch_id + '/matches').catch(() => []),
      jfetch('/api/batches/' + gen.batch_id + '/exceptions?min_amount=0').catch(() => []),
    ]);
    S.allRecords = matches || [];
    S.exceptions = exc || [];

    renderSummary(detail);
    renderTable(S.allRecords);
    renderTwinBanner(detail.metrics);
    enableRunActions();

  } catch(e) {
    console.error(e);
    alert('Run failed: ' + e.message);
  } finally {
    setLoading(false);
  }
}
window.runFull = runFull;

async function rerunLast() {
  if (!S.currentBatch) return;
  setLoading(true);
  try {
    resetStages();
    setStage('match');
    const useLLM = ($('use-llm') || {}).value === 'true';
    await jfetch(`/api/batches/${S.currentBatch.id}/reconcile`, {
      method: 'POST',
      body: JSON.stringify({ use_llm: useLLM }),
    });
    setStage('match', true); setStage('policy'); await sleep(60);
    setStage('policy', true); setStage('audit'); await sleep(60);
    setStage('audit', true); setStage('done');
    const detail = await jfetch('/api/batches/' + S.currentBatch.id);
    S.metrics = detail.metrics || {};
    if (detail.run_id && S.metrics) S.metrics.run_id = detail.run_id;
    const [matches, exc] = await Promise.all([
      jfetch('/api/batches/' + S.currentBatch.id + '/matches').catch(() => []),
      jfetch('/api/batches/' + S.currentBatch.id + '/exceptions?min_amount=0').catch(() => []),
    ]);
    S.allRecords = matches || [];
    S.exceptions = exc || [];
    renderSummary(detail);
    renderTable(S.allRecords);
    renderTwinBanner(detail.metrics);
    enableRunActions();
  } catch(e) {
    alert('Rerun failed: ' + e.message);
  } finally {
    setLoading(false);
  }
}
window.rerunLast = rerunLast;

function hideSummary() { const el = $('summary-wrap'); if (el) el.style.display = 'none'; }

function enableRunActions() {
  ['btn-rerun', 'btn-ai-off', 'btn-replay'].forEach(id => {
    const el = $(id); if (el) el.disabled = false;
  });
}

function renderSummary(detail) {
  const m = detail.metrics || {};
  const total = m.records_processed || 0;
  const autoN  = m.auto_matched    || 0;
  const escN   = m.escalated       || 0;
  const unresN = m.unresolved      || 0;
  const setText = (id, v) => { const el = $(id); if (el) el.textContent = v; };

  setText('s-auto',  autoN);
  setText('s-esc',   escN);
  setText('s-unres', unresN);
  setText('s-rate',  total > 0 ? pct(autoN/total) : 'N/A');
  setText('m-prec',  pct(m.precision));
  setText('m-rec',   pct(m.recall));
  setText('m-fmr2',  pct(m.false_match_rate));

  // Canonical exception value from the eval run (integer paise), not a second sum.
  setText('s-esc-val', m.exception_value != null ? inr(m.exception_value) : inr((S.exceptions || []).reduce((sum, e) => sum + (e.amount || 0), 0)));

  const fmrEl = $('m-fmr2');
  if (fmrEl) fmrEl.style.color = m.false_match_rate === 0 ? 'var(--sage)' : m.false_match_rate > 0.05 ? 'var(--rust)' : 'var(--amber)';
  const drps = m.deterministic_rps;
  setText('m-drps', drps != null ? drps.toFixed(0) + '/s' : 'N/A');

  // Populate Executive Run Card
  const b = S.currentBatch || {};
  const runIdStr = detail.run_id || (m.lineage && m.lineage.run_id) || '—';
  const split = (b.split || 'holdout').toUpperCase();
  setText('run-card-title', `${split}  ${runIdStr}`);
    const baseN = ($('n') ? $('n').value : 200);
  setText('run-card-sub', `${baseN} base → ${total} observed records · ${autoN} auto-closed · ${escN + unresN} refused`);
  const lin = m.lineage || {};
  setText('run-card-meta', `Seed ${b.seed} · Split ${split} · Matcher ${lin.matcher_version || '—'} · Policy ${lin.policy_version || '—'} · ${drps != null ? drps.toFixed(0) : '--'} rec/s · AI explains, policy decides`);
  const splitPill = $('env-split-pill');
  if (splitPill) splitPill.textContent = split + ' EVAL';
  const runPill = $('env-run-pill');
  if (runPill) runPill.textContent = runIdStr;

  const sw = $('summary-wrap');
  if (sw) sw.style.display = 'block';
}

function renderTwinBanner(metrics) {
  if (!metrics) return;
  const pn = metrics.policy_note || {};
  const slipped = pn.auto_closed_ambiguous_twins || [];
  const twinN = (metrics.slices && metrics.slices.ambiguous_twin) ? metrics.slices.ambiguous_twin.n : 0;
  const banner = $('twin-banner');
  if (!banner) return;
  if (twinN === 0) { banner.className = 'banner'; return; }
  if (slipped.length === 0) {
    banner.className = 'banner banner-good visible';
    banner.innerHTML = '&#x2714; ' + twinN + ' ambiguous twin(s) — all refused auto-close by <code>never_auto_close_on_tie()</code>. Safety check working.';
  } else {
    banner.className = 'banner banner-bad visible';
    banner.innerHTML = '&#x26a0; ' + slipped.length + ' twin(s) incorrectly slipped to AUTO_CLOSE. Review tie-check thresholds.';
  }
}

function decBadge(dec) {
  if (!dec) return '<span class="badge badge-unresolved">—</span>';
  if (dec === 'auto_close')  return '<span class="badge badge-auto">AUTO_CLOSE</span>';
  if (dec === 'escalate')    return '<span class="badge badge-escalate">ESCALATE</span>';
  return '<span class="badge badge-unresolved">UNRESOLVED</span>';
}

function renderTable(records) {
  const q   = (($('search-q')   || {}).value || '').toLowerCase();
  const dec = (($('filter-dec') || {}).value || '');
  const filtered = records.filter(r => {
    const ev = r.evidence || {};
    const vendor = (ev.vendor_name_raw || r.settlement_id).toLowerCase();
    const matchQ = !q || r.settlement_id.toLowerCase().includes(q) || vendor.includes(q);
    const matchD = !dec || r.decision === dec;
    return matchQ && matchD;
  });

  const rc = $('row-count');
    const baseN = ($('n') ? $('n').value : 200);
  if (rc) rc.textContent = `${filtered.length} of ${records.length} observed records (${baseN} base)`;

  const tbody = $('records-tbody');
  if (!tbody) return;

  if (filtered.length === 0) {
    const msg = records.length === 0
      ? 'No data. Click <strong>GENERATE &amp; RECONCILE</strong> on the Pipeline tab.'
      : 'No records match the current filter.';
    tbody.innerHTML = `<tr><td colspan="6"><div class="empty-state"><div class="es-icon">&#x25cb;</div><p>${msg}</p></div></td></tr>`;
    return;
  }
  tbody.innerHTML = filtered.map(r => {
    const conf = r.confidence != null ? r.confidence.toFixed(3) : 'N/A';
    const reason = esc(r.reason_code || '--');
    const sid = esc(r.settlement_id);
    return `<tr onclick="openDrawerFromRow(${JSON.stringify(JSON.stringify(r))})">
      <td class="cell-dim">${sid}</td>
      <td class="cell-dim">${esc(r.invoice_id || '—')}</td>
      <td>${decBadge(r.decision)}</td>
      <td class="cell-dim" style="font-size:11px;color:var(--amber)">${reason}</td>
      <td class="cell-dim">${conf}</td>
      <td class="cell-dim" style="font-size:11px">${esc(r.match_type || '—')}</td>
    </tr>`;
  }).join('');
}
window.filterTable = () => renderTable(S.allRecords);

function openDrawerFromRow(rawJson) {
  openDrawer(typeof rawJson === 'string' ? JSON.parse(rawJson) : rawJson);
}
window.openDrawerFromRow = openDrawerFromRow;

function openDrawer(r) {
  const ev = r.evidence || {};
  $('drawer-title').textContent = r.settlement_id;
  const invCands = ev.invoice_top || [];
  const bankCands = ev.bank_top  || [];

  const sources = [
    { type: 'SETTLEMENT', id: r.settlement_id, fee: ev.fee, tax: ev.tax, currency: ev.currency, txn: ev.txn_type },
    { type: 'INVOICE',    id: r.invoice_id || '—' },
    { type: 'BANK',       id: r.bank_txn_id || '—' },
  ];
  const sourceHTML = sources.map(s => `
    <div class="source-card">
      <div class="sc-type">${s.type}</div>
      <div class="sc-kv"><span class="k">ID</span><span class="v">${esc(s.id || '—')}</span></div>
      ${s.currency ? `<div class="sc-kv"><span class="k">CCY</span><span class="v">${esc(s.currency)}</span></div>` : ''}
      ${s.txn ? `<div class="sc-kv"><span class="k">Type</span><span class="v">${esc(s.txn)}</span></div>` : ''}
      ${s.fee != null ? `<div class="sc-kv"><span class="k">Fee</span><span class="v">${inr(s.fee)}</span></div>` : ''}
      ${s.tax != null ? `<div class="sc-kv"><span class="k">Tax</span><span class="v">${inr(s.tax)}</span></div>` : ''}
    </div>`).join('');

  function renderCands(cands, label) {
    if (!cands || cands.length === 0) return `<p class="cell-dim" style="font-size:12px;font-family:var(--mono)">No ${label} candidates.</p>`;
    return cands.map((c, i) => {
      const sc = c.components || {};
      const bars = [
        ['Reference', sc.reference ?? sc.ref_sim],
        ['Amount',    sc.amount    ?? sc.amt_sim],
        ['Vendor',    sc.vendor    ?? sc.vnd_sim],
        ['Date',      sc.date      ?? sc.date_sim],
      ].filter(([,v]) => v != null);
      const barsHTML = bars.map(([lbl, val]) => {
        const v = Math.max(0, Math.min(1, val));
        return `<div class="sbar-row">
          <span class="sbar-label">${lbl}</span>
          <div class="sbar-track"><div class="sbar-fill" style="width:${(v*100).toFixed(0)}%"></div></div>
          <span class="sbar-num">${v.toFixed(3)}</span>
        </div>`;
      }).join('');
      const isTop = i === 0;
      const blockersHTML = c.blockers && c.blockers.length > 0
        ? `<div style="color:var(--rust);font-size:10px;font-family:var(--mono);margin-top:4px">${c.blockers.join(' · ')}</div>` : '';
      return `<div class="cand-block">
        <div class="cand-id">
          <span>${esc(c.record_id || 'Candidate '+(i+1))} ${isTop ? '<span style="color:var(--amber);font-size:10px">&#x25b2; TOP</span>' : ''}</span>
          <span class="cand-total">Score ${(c.score||0).toFixed(3)}</span>
        </div>
        ${barsHTML}${blockersHTML}
      </div>`;
    }).join('');
  }

  const proof = ev.proof || {};
  const checks = proof.policy_checks || {};
  const isTie = ev.tie_check === true || checks.tie_margin === false;
  const thr   = ev.auto_close_threshold || 0.90;
  const conf  = r.confidence || 0;
  const confOk = checks.score_threshold != null ? checks.score_threshold : conf >= thr;
  const hasInv = !!r.invoice_id;
  const hasBank = !!r.bank_txn_id;
  const isAutoClose = r.decision === 'auto_close';
  const runner = proof.runner_up;
  const margin = proof.invoice_margin;

  const gateRows = [
    { label: `Score ≥ ${thr}`,  pass: confOk,  val: conf.toFixed(3) },
    { label: `Tie margin > ${ev.tie_delta || 0.05}`, pass: !isTie, val: margin != null ? ('Δ ' + margin) : (isTie ? 'TIE' : 'clear') },
    { label: 'Invoice counterpart',               pass: hasInv,  val: hasInv  ? r.invoice_id  : 'missing' },
    { label: 'Bank counterpart',      pass: hasBank, val: hasBank ? r.bank_txn_id : 'missing' },
    { label: 'Currency aligned', pass: checks.currency !== false, val: checks.currency === false ? 'mismatch' : 'ok' },
    { label: 'Txn type aligned', pass: checks.txn_type !== false, val: checks.txn_type === false ? 'mismatch' : 'ok' },
  ];
  const gateHTML = gateRows.map(g => `
    <div class="gate-row ${g.pass ? 'gate-pass' : 'gate-fail'}">
      <span class="gi">${g.pass ? '&#x2714;' : '&#x2716;'}</span>
      <span>${esc(g.label)}</span>
      <span class="gate-val">${esc(g.val)}</span>
    </div>`).join('');

  let whyNotHTML = '';
  if (!isAutoClose) {
    const failures = gateRows.filter(g => !g.pass);
    if (failures.length > 0) {
      whyNotHTML = `<div class="drawer-section">
        <h4>WHY NOT AUTO-CLOSE?</h4>
        <div class="why-not-grid">${failures.map(f => `
          <div class="why-not-row">
            <span class="wi">&#x2716;</span>
            <div>
              <div class="wn-label">${esc(f.label)}</div>
              <div class="wn-val">${esc(f.val)}</div>
            </div>
          </div>`).join('')}
        </div>
        <div style="font-size:11px;color:var(--paper-faint);font-family:var(--mono);margin-top:8px">
          The deterministic policy gate refused auto-close. Human review required.
        </div>
      </div>`;
    }
  }

  const decClass = r.decision === 'auto_close' ? 'dec-auto' : r.decision === 'escalate' ? 'dec-escalate' : 'dec-unresolved';
  const decLabel = (r.decision || 'unknown').replace('_',' ').toUpperCase();

  const llm = r.llm_suggestion || {};
  const llmHTML = (llm.label && llm.label !== 'AI_UNAVAILABLE') ? `
    <div class="drawer-section">
      <h4>LLM Explanation <span style="color:var(--paper-faint);font-weight:400;font-size:11px">— explanation authority only</span></h4>
      <div class="llm-block">
        <div style="font-family:var(--mono); font-size:10px; font-weight:600; color:var(--amber); margin-bottom:8px; border-bottom:1px solid var(--rule); padding-bottom:6px;">
          AI CAN EXPLAIN &middot; AI CANNOT CHANGE THIS DECISION
        </div>
        <div class="llm-row"><span class="lk">Label</span><span>${esc(llm.label)}</span></div>
        <div class="llm-row"><span class="lk">Confidence</span><span>${esc(llm.confidence_band || '—')}</span></div>
        <div class="llm-row"><span class="lk">Reason</span><span>${esc(llm.reason_code || '—')}</span></div>
        ${(llm.evidence || []).map(e => `<div class="llm-row"><span class="lk">&#x2022;</span><span>${esc(e)}</span></div>`).join('')}
      </div>
    </div>` : '';

  const metaHTML = `<div class="drawer-section drawer-meta">
    <span>decision: <strong>${esc(r.decision)}</strong></span>
    <span>reason: <strong>${esc(r.reason_code)}</strong></span>
    <span>confidence: <strong>${conf.toFixed(4)}</strong></span>
    <span>match_type: <strong>${esc(r.match_type)}</strong></span>
  </div>`;

  const proofTitle = isAutoClose
    ? `<div style="padding:10px 14px; background:var(--sage-bg); border:1px solid var(--sage-brd); color:var(--sage); font-family:var(--mono); font-size:12px; font-weight:600; margin-bottom:16px;">PROOF OF CLOSURE &mdash; POLICY-AUTHORIZED AUTO_CLOSE</div>`
    : `<div style="padding:10px 14px; background:var(--amber-bg); border:1px solid var(--amber-brd); color:var(--amber); font-family:var(--mono); font-size:12px; font-weight:600; margin-bottom:16px;">PROOF OF REFUSAL &mdash; ${esc((r.reason_code || 'BLOCKED'))}</div>`;

  let comparisonCardHTML = '';
  if (!isAutoClose && invCands.length >= 2) {
    const c1 = invCands[0];
    const c2 = invCands[1];
    const delta = Math.abs((c1.score || 0) - (c2.score || 0)).toFixed(3);
    const deltaFailed = delta <= (ev.tie_delta || 0.05);
    comparisonCardHTML = `
      <div class="drawer-section" style="background:var(--slate-2); border:1px solid ${deltaFailed ? 'var(--amber-brd)' : 'var(--rule)'}; padding:14px; margin-bottom:16px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; border-bottom:1px solid var(--rule); padding-bottom:6px;">
          <h4 style="margin:0; font-family:var(--mono); font-size:11px; color:var(--amber);">DECISION PROOF: COMPETING CANDIDATE MARGIN</h4>
          <span style="font-family:var(--mono); font-size:10px; padding:2px 6px; background:${deltaFailed ? 'var(--amber-bg)' : 'var(--sage-bg)'}; color:${deltaFailed ? 'var(--amber)' : 'var(--sage)'}; border:1px solid ${deltaFailed ? 'var(--amber-brd)' : 'var(--sage-brd)'}; font-weight:600;">
            ${deltaFailed ? 'MARGIN FAILED (REFUSE)' : 'MARGIN CLEARED'}
          </span>
        </div>
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px; font-family:var(--mono); font-size:11px;">
          <div style="background:var(--slate); border:1px solid var(--rule); padding:8px 10px;">
            <div style="color:var(--paper-dim); font-size:10px;">CANDIDATE A (TOP)</div>
            <div style="color:var(--paper); font-weight:600; font-size:13px; margin:2px 0;">${esc(c1.record_id)}</div>
            <div style="color:var(--sage); font-weight:600;">Score: ${(c1.score || 0).toFixed(3)}</div>
          </div>
          <div style="background:var(--slate); border:1px solid var(--rule); padding:8px 10px;">
            <div style="color:var(--paper-dim); font-size:10px;">CANDIDATE B (RUNNER-UP)</div>
            <div style="color:var(--paper); font-weight:600; font-size:13px; margin:2px 0;">${esc(c2.record_id)}</div>
            <div style="color:var(--amber); font-weight:600;">Score: ${(c2.score || 0).toFixed(3)}</div>
          </div>
        </div>
        <div style="margin-top:10px; font-family:var(--mono); font-size:11px; display:flex; justify-content:space-between; align-items:center;">
          <span>Observed Score Delta: <strong style="color:${deltaFailed ? 'var(--rust)' : 'var(--sage)'};">Δ ${delta}</strong></span>
          <span style="color:var(--paper-dim); font-size:10px;">Required Policy Margin: &gt; ${ev.tie_delta || 0.05}</span>
        </div>
        <div style="margin-top:8px; font-family:var(--mono); font-size:10px; color:var(--paper-faint); border-top:1px dashed var(--rule); padding-top:6px;">
          never_auto_close_on_tie() triggered &middot; Greedy argmax would have closed &middot; Policy forces ESCALATE
        </div>
      </div>
    `;
  }
  const runnerHTML = runner && !comparisonCardHTML ? `<div class="drawer-section"><h4>Runner-up</h4><div style="font-family:var(--mono);font-size:12px;color:var(--paper-dim)">${esc(runner.record_id)} · score ${runner.score} · margin ${margin ?? '—'}</div></div>` : '';

  $('drawer-body').innerHTML = `
    ${proofTitle}
    ${comparisonCardHTML}
    <div class="drawer-section">
      <h4>Source Records</h4>
      <div class="source-grid">${sourceHTML}</div>
    </div>
    ${runnerHTML}
    <div class="drawer-section">
      <h4>Invoice Candidates</h4>
      ${renderCands(invCands, 'invoice')}
    </div>
    <div class="drawer-section">
      <h4>Bank Candidates</h4>
      ${renderCands(bankCands, 'bank')}
    </div>
    <div class="drawer-section">
      <h4>Policy Gate</h4>
      <div class="gate-list">${gateHTML}</div>
    </div>
    <div class="drawer-section">
      <h4>Final Decision</h4>
      <div class="dec-box ${decClass}">${decLabel}</div>
      <div style="display:flex; justify-content:space-between; margin-top:10px; font-family:var(--mono); font-size:10px; border:1px solid var(--rule); padding:8px 12px; background:var(--slate-2);">
        <div><span style="color:var(--paper-dim);">DECISION SOURCE:</span> <strong style="color:var(--sage);">DETERMINISTIC POLICY &#x2714;</strong></div>
        <div><span style="color:var(--paper-dim);">EXPLANATION SOURCE:</span> <strong style="color:var(--amber);">LLM (DECOUPLED)</strong></div>
      </div>
    </div>
    ${whyNotHTML}
    ${llmHTML}
    ${metaHTML}
  `;

  $('drawer').classList.add('open');
  $('drawer-overlay').classList.add('open');
  document.body.style.overflow = 'hidden';
}
window.openDrawer = openDrawer;

function closeDrawer() {
  $('drawer').classList.remove('open');
  $('drawer-overlay').classList.remove('open');
  document.body.style.overflow = '';
}
window.closeDrawer = closeDrawer;
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDrawer(); });

async function runAiOffCheck() {
  if (!S.currentBatch) return;
  try {
    const res = await jfetch(`/api/batches/${S.currentBatch.id}/ai-off-check`, { method: 'POST' });
    alert(res.pass
      ? `AI OFF check passed. n=${res.n}. Decisions identical; LLM cannot mutate them.`
      : `AI OFF check FAILED. identical=${res.decisions_identical} mutate=${!res.llm_cannot_mutate}`);
  } catch (e) { alert('AI OFF check failed: ' + e.message); }
}
window.runAiOffCheck = runAiOffCheck;

async function runReplay() {
  if (!S.currentBatch) return;
  try {
    const res = await jfetch(`/api/batches/${S.currentBatch.id}/replay`, { method: 'POST' });
    alert(res.pass
      ? `Replay matched stored decisions. run ${res.run_id} · n=${res.n}`
      : `Replay DIVERGED (${(res.diverged||[]).length} rows).`);
  } catch (e) { alert('Replay failed: ' + e.message); }
}
window.runReplay = runReplay;

// ── EVALUATION TAB LOGIC ─────────────────────────────────────────────────────
function renderEvaluation() {
  if (!S.metrics) {
    const tbody = $('slices-tbody');
    if (tbody) tbody.innerHTML = '<tr><td colspan="5"><div class="empty-state"><div class="es-icon">&#x25cb;</div><p>No evaluation run. Go to <strong>Pipeline</strong> tab and click GENERATE &amp; RECONCILE.</p></div></td></tr>';
    return;
  }
  const m = S.metrics;
  const n = m.records_processed || 0;
  const autoN = m.auto_matched || 0;
  const c = m.confusion || {};
  const correct = c.correct_auto_close ?? null;
  const wrong = c.wrong_auto_close ?? null;
  const trueMatchable = m.true_matchable ?? null;

  const setText = (id, v, color) => {
    const el = $(id); if (!el) return;
    el.textContent = v;
    if (color) el.style.color = color;
    el.classList.remove('loading');
  };
  setText('ev-prec', pct(m.precision));
  setText('ev-rec',  pct(m.recall));
  setText('ev-fmr',  pct(m.false_match_rate),
    m.false_match_rate === 0 ? 'var(--sage)' : m.false_match_rate > 0.05 ? 'var(--rust)' : 'var(--amber)');
  setText('ev-auto', n > 0 ? pct(autoN / n) : 'N/A');

  const setDef = (id, v) => { const el = $(id); if (el) el.textContent = v; };
  setDef('ev-prec-def', correct != null ? `${correct} / ${autoN} auto-closes correct` : `${autoN} auto-closes`);
  setDef('ev-rec-def', (correct != null && trueMatchable != null) ? `${correct} / ${trueMatchable} true matchable recovered` : 'recall vs hidden truth');
  setDef('ev-fmr-def', wrong != null ? `${wrong} / ${autoN} wrong auto-closes` : `FMR vs auto-closes`);
  setDef('ev-auto-def', `${autoN} / ${n} records auto-closed`);
  setText('ev-c-ok', correct != null ? correct : '—');
  setText('ev-c-wrong', wrong != null ? wrong : '—');
  setText('ev-c-miss', c.missed_true_matches != null ? c.missed_true_matches : '—');
  setText('ev-c-ref', c.correct_refusals != null ? c.correct_refusals : '—');

  const lin = m.lineage || {};
  const split = (lin.split || (S.currentBatch && S.currentBatch.split) || 'holdout').toUpperCase();
  const runId = m.run_id || lin.run_id || '—';
  const head = $('ev-run-title');
  if (head) head.textContent = `${split} EVALUATION · ${runId}`;
  const lineageEl = $('ev-run-lineage');
  if (lineageEl) {
    lineageEl.textContent = `Seed ${lin.seed ?? S.currentBatch?.seed} · ${split} · N=${n} · Matcher ${lin.matcher_version || '—'} · Policy ${lin.policy_version || '—'} · GT independent=${!!(m.ground_truth && m.ground_truth.independent)}`;
  }

  const meta = $('ev-meta');
  if (meta && S.currentBatch) {
      const baseN = ($('n') ? $('n').value : 200);
  meta.textContent = `${runId} · ${split} · SEED ${S.currentBatch.seed} · ${baseN} base → ${n} observed records · identical run to Pipeline`;
  }

  if ($('adv-bench-tbody') && $('adv-bench-tbody').textContent.includes('Click')) {
    runAdversarialLab();
  }
  if ($('seed-bench-tbody') && $('seed-bench-tbody').textContent.includes('Click')) {
    runSeedBenchmark();
  }

  const drps = m.deterministic_rps;
  const ev_rps = $('ev-rps');
  if (ev_rps) ev_rps.innerHTML = drps != null ? `<div class="summary-card" style="display:inline-block; padding:10px 16px;"><span style="color:var(--paper); font-weight:600; font-family:var(--mono);">${drps.toFixed(0)} rec/s</span> <span style="color:var(--paper-dim); font-size:11px; font-family:var(--mono);">deterministic throughput</span></div>` : '';

  const slices = m.slices || {};
  const tbody = $('slices-tbody');
  if (!tbody) return;
  const keys = Object.keys(slices);
  if (keys.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" style="padding:16px;color:var(--paper-faint);font-family:var(--mono);font-size:12px">No slice data.</td></tr>';
    return;
  }
  tbody.innerHTML = keys.map(k => {
    const s = slices[k];
    const n = s.n || 0;
    const autoN = s.auto_matched || s.auto_close || 0;
    const escN  = s.escalate || 0;
    const recall = n > 0 ? pct(autoN / n) : 'N/A';
    const barW = n > 0 ? Math.round(autoN/n*100) : 0;
    return `<tr>
      <td class="td-name">${esc(k.replace(/_/g,' '))}</td>
      <td>${n}</td>
      <td class="td-bar"><div class="td-bar-track"><div class="td-bar-fill" style="width:${barW}%"></div></div> <span>${autoN}</span></td>
      <td style="color:var(--amber)">${escN}</td>
      <td class="${barW > 80 ? 'td-good' : barW < 50 ? 'td-bad' : ''}">${recall}</td>
    </tr>`;
  }).join('');
}

async function runSeedBenchmark() {
  const tbody = $('seed-bench-tbody');
  if (tbody) tbody.innerHTML = '<tr><td colspan="7"><div class="empty-state"><p>Running 4-seed benchmark (seeds 42, 847, 1204, 3391)...</p></div></td></tr>';
  try {
    const res = await jfetch('/api/benchmark/seeds?seeds=42,847,1204,3391&n=200');
    tbody.innerHTML = res.map(r => {
      const isMean = r.seed === 'MEAN';
      const style = isMean ? 'font-weight:600; background:var(--slate-2);' : '';
      const autoN = r.auto_closed != null ? r.auto_closed : Math.round((r.auto_rate || 0) * (r.n || 0));
      return `<tr style="${style}">
        <td class="td-name">${r.seed}</td>
        <td>${r.n}</td>
        <td style="color:var(--sage); font-weight:600;">${autoN}</td>
        <td style="color:var(--sage)">${pct(r.precision)}</td>
        <td>${pct(r.recall)}</td>
        <td style="color:${r.fmr === 0 ? 'var(--sage)' : 'var(--rust)'}">${pct(r.fmr)}</td>
        <td>${pct(r.auto_rate)}</td>
        <td style="color:var(--paper-dim)">${r.rps ? r.rps.toFixed(0) + '/s' : '—'}</td>
      </tr>`;
    }).join('');
  } catch(e) {
    if (tbody) tbody.innerHTML = `<tr><td colspan="7"><div class="empty-state" style="color:var(--rust)"><p>Benchmark error: ${esc(e.message)}</p></div></td></tr>`;
  }
}
window.runSeedBenchmark = runSeedBenchmark;

async function runThroughputBenchmark() {
  const tbody = $('tp-bench-tbody');
  if (tbody) tbody.innerHTML = '<tr><td colspan="6"><div class="empty-state"><p>Measuring scaling throughput (sizes 100, 500, 1000, 2000)...</p></div></td></tr>';
  try {
    const res = await jfetch('/api/benchmark/throughput?sizes=100,500,1000,2000&seed=42');
    tbody.innerHTML = res.map(r => {
      const redPct = pct(r.blocking_reduction, 2);
      return `<tr>
        <td class="td-name">${r.n} records</td>
        <td>${r.elapsed_s}s</td>
        <td style="color:var(--sage); font-weight:600;">${r.rps.toFixed(0)} rec/s</td>
        <td>${r.total_candidates.toLocaleString()}</td>
        <td style="color:var(--paper-faint)">${r.naive_comparisons.toLocaleString()}</td>
        <td style="color:var(--amber); font-weight:600;">${redPct} fewer pairs</td>
      </tr>`;
    }).join('');
  } catch(e) {
    if (tbody) tbody.innerHTML = `<tr><td colspan="6"><div class="empty-state" style="color:var(--rust)"><p>Scaling benchmark error: ${esc(e.message)}</p></div></td></tr>`;
  }
}
window.runThroughputBenchmark = runThroughputBenchmark;

async function runAdversarialLab() {
  const tbody = $('adv-bench-tbody');
  if (tbody) tbody.innerHTML = '<tr><td colspan="5"><div class="empty-state"><p>Running constructed safety-lab fixtures...</p></div></td></tr>';
  try {
    const res = await jfetch('/api/safety-lab');
    const cases = res.cases || [];
    tbody.innerHTML = cases.map(t => `
    <tr>
      <td class="td-name">${esc(t.name)}</td>
      <td style="color:var(--paper-dim); font-size:11px;">${esc(t.condition || '')}</td>
      <td style="color:var(--amber); font-size:11px;">${esc(t.expected || '')}</td>
      <td style="font-size:11px;">${esc(t.actual || '')}</td>
      <td style="color:${t.pass ? 'var(--sage)' : 'var(--rust)'}; font-weight:600;">${t.pass ? '✓ PASSED' : '✕ FAIL'}</td>
    </tr>
  `).join('') + `<tr><td colspan="5" style="font-family:var(--mono);font-size:11px;color:var(--paper-dim);padding:10px 14px;">${res.passed}/${res.total} constructed cases passed. These are not holdout samples.</td></tr>`;
  } catch (e) {
    if (tbody) tbody.innerHTML = `<tr><td colspan="5"><div class="empty-state" style="color:var(--rust)"><p>${esc(e.message)}</p></div></td></tr>`;
  }
}
window.runAdversarialLab = runAdversarialLab;

// ── EXCEPTIONS TAB ───────────────────────────────────────────────────────────
function renderExceptions() {
  const q      = ($('exc-search')  || {}).value || '';
  const reason = ($('exc-reason')  || {}).value || '';
  const filtered = S.exceptions.filter(e => {
    const matchQ = !q || (e.settlement_id || '').toLowerCase().includes(q.toLowerCase()) || (e.vendor || '').toLowerCase().includes(q.toLowerCase());
    const matchR = !reason || (e.reason_code || '').toUpperCase() === reason;
    return matchQ && matchR;
  });
  const totalExcVal = filtered.reduce((sum, e) => sum + (e.amount || 0), 0);
  const sub = $('exc-subtitle');
  if (sub) sub.textContent = `${filtered.length} exceptions · ${inr(totalExcVal)} value requiring investigation · click any row for evidence`;

  // Compute SUM(amount) GROUP BY reason_code
  const byReason = {};
  S.exceptions.forEach(e => {
    const code = (e.reason_code || 'OTHER').toUpperCase();
    byReason[code] = (byReason[code] || 0) + (e.amount || 0);
  });
  const fromMetrics = (S.metrics && S.metrics.exception_value_by_reason) || {};
  const pickAmt = (keys) => keys.reduce((s, k) => s + (fromMetrics[k] || byReason[k] || 0), 0);
  const setVal = (id, val) => { const el = $(id); if (el) el.textContent = inr(val || 0); };
  setVal('exc-val-amb', pickAmt(['AMBIGUOUS_CANDIDATES', 'AMBIGUOUS']));
  setVal('exc-val-low', pickAmt(['LOW_CONFIDENCE']));
  setVal('exc-val-dup', pickAmt(['DUPLICATE_CANDIDATE', 'DUPLICATE']));
  setVal('exc-val-noc', pickAmt(['MISSING_COUNTERPART', 'NO_CANDIDATE']));

  const grid = $('exc-reason-group-grid');
  if (grid) grid.style.display = S.exceptions.length > 0 ? 'grid' : 'none';
  const tbody = $('exc-tbody');
  if (!tbody) return;
  if (S.exceptions.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6"><div class="empty-state"><div class="es-icon">&#x25cb;</div><p>No exceptions yet. Run a batch from the Pipeline tab first.</p></div></td></tr>';
    return;
  }
  if (filtered.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6"><div class="empty-state"><div class="es-icon">&#x2714;</div><p>No matches for current filter.</p></div></td></tr>';
    return;
  }
  tbody.innerHTML = filtered.map(e => {
    const conf = e.confidence != null ? e.confidence.toFixed(3) : 'N/A';
    const rec = {
      settlement_id: e.settlement_id,
      invoice_id: e.invoice_id,
      bank_txn_id: e.bank_txn_id,
      decision: e.decision,
      reason_code: e.reason_code,
      confidence: e.confidence,
      match_type: '—',
      evidence: e.evidence || {},
      llm_suggestion: e.llm_suggestion || null,
    };
    return `<tr onclick="openDrawer(${JSON.stringify(JSON.stringify(rec))})">
      <td class="cell-dim">${esc(e.settlement_id)}</td>
      <td>${e.amount != null ? inr(e.amount) : '—'}</td>
      <td class="cell-dim">${esc((e.vendor || '').substring(0,30))}</td>
      <td>${decBadge(e.decision)}</td>
      <td class="cell-dim" style="font-size:11px;color:var(--amber)">${esc(e.reason_code || '—')}</td>
      <td class="cell-dim">${conf}</td>
    </tr>`;
  }).join('');
}
window.filterExceptions = renderExceptions;

// ── AUDIT TAB ────────────────────────────────────────────────────────────────
async function searchAudit() {
  const sid = ($('audit-search-input') || {}).value.trim();
  if (!sid) return;
  const wrap = $('audit-events-wrap');
  if (!wrap) return;
  wrap.innerHTML = '<div class="empty-state"><p>Searching audit history...</p></div>';
  try {
    const events = await jfetch('/api/audit?settlement_id=' + encodeURIComponent(sid));
    if (!events || events.length === 0) {
      wrap.innerHTML = `<div class="empty-state"><div class="es-icon">&#x1f4cb;</div><p>No audit events found for: <code>${esc(sid)}</code><br>Try a settlement ID from the Pipeline tab.</p></div>`;
      return;
    }
    wrap.innerHTML = '<div class="audit-events">' + events.map((ev, i) => {
      const ts   = ev.timestamp ? new Date(ev.timestamp).toLocaleString('en-IN', {timeZone:'Asia/Kolkata'}) : '—';
      const dec  = decBadge(ev.decision || '');
      const conf = ev.evidence_snapshot && ev.evidence_snapshot.confidence != null ? ev.evidence_snapshot.confidence.toFixed(4) : '—';
      return `<div class="audit-event" id="ae-${i}">
        <div class="ae-header" onclick="toggleAuditEvent(${i})" style="display:flex; gap:12px; align-items:center; padding:12px; background:var(--slate); border:1px solid var(--rule); border-radius:var(--r); margin-bottom:8px; cursor:pointer;">
          <span style="font-family:var(--mono); font-size:11px; color:var(--paper-dim);">${esc(ts)}</span>
          <span style="font-family:var(--mono); font-size:12px; font-weight:600;">${esc(ev.settlement_id || sid)}</span>
          <span>${dec}</span>
          <span style="font-family:var(--mono); font-size:11px; color:var(--paper-dim);">conf ${conf}</span>
          <span style="font-family:var(--mono); font-size:10px; color:var(--paper-faint); margin-left:auto;">run ${esc((ev.run_id||'').substring(0,8))}</span>
        </div>
        <pre class="ae-body" style="background:var(--ink); border:1px solid var(--rule); padding:16px; font-family:var(--mono); font-size:11px; color:var(--paper-dim); overflow-x:auto; margin-bottom:16px;">${esc(JSON.stringify(ev, null, 2))}</pre>
      </div>`;
    }).join('') + '</div>';
  } catch(e) {
    wrap.innerHTML = `<div class="empty-state"><div class="es-icon">&#x26a0;</div><p>Error: ${esc(e.message)}</p></div>`;
  }
}
window.searchAudit = searchAudit;

function toggleAuditEvent(i) { const el = $('ae-'+i); if (el) el.classList.toggle('open'); }
window.toggleAuditEvent = toggleAuditEvent;

async function loadLatestBatch() {
  try {
    const batches = await jfetch('/api/batches');
    const reconciled = (batches || []).find(b => b.status === 'reconciled');

    if (!reconciled) {
      if ($('n')) $('n').value = 200;
      if ($('seed')) $('seed').value = 42;
      if ($('split')) $('split').value = 'holdout';
      await runFull();
      return;
    }

    S.currentBatch = { id: reconciled.id, n: reconciled.n, seed: reconciled.seed, split: reconciled.split };
    if ($('seed')) $('seed').value = reconciled.seed;
    if ($('split')) $('split').value = reconciled.split;

    const detail = await jfetch('/api/batches/' + reconciled.id);
    S.metrics = detail.metrics || {};
    if (detail.run_id && S.metrics) S.metrics.run_id = detail.run_id;

    const [matches, exc] = await Promise.all([
      jfetch('/api/batches/' + reconciled.id + '/matches').catch(() => []),
      jfetch('/api/batches/' + reconciled.id + '/exceptions?min_amount=0').catch(() => []),
    ]);
    S.allRecords = matches || [];
    S.exceptions = exc || [];

    renderSummary(detail);
    renderTable(S.allRecords);
    renderTwinBanner(detail.metrics);
    enableRunActions();

    STAGES.forEach(s => { const el = $('stage-' + s); if (el) el.className = 'stage-chip done'; });
    $('stages-wrap').style.display = 'flex';

  } catch(e) { console.log('Boot load:', e.message); }
}

document.addEventListener('DOMContentLoaded', () => {
  ['n','seed'].forEach(id => {
    const el = $(id);
    if (el) el.addEventListener('keydown', e => { if (e.key === 'Enter') runFull(); });
  });
  const ai = $('audit-search-input');
  if (ai) ai.addEventListener('keydown', e => { if (e.key === 'Enter') searchAudit(); });
});


// ── CSV Report Export ────────────────────────────────────────────────────────
function exportReportCSV() {
  if (!S.currentBatch) {
    alert('No reconciliation data available to export. Run a batch first.');
    return;
  }
  window.location.href = '/api/batches/' + encodeURIComponent(S.currentBatch.id) + '/export';
}
window.exportReportCSV = exportReportCSV;
