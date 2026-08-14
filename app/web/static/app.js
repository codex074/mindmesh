// MindMesh dashboard (small, dependency-free JS; chart is inline SVG).

const $ = (id) => document.getElementById(id);
let currentSnapshot = null;

$('search-btn').addEventListener('click', loadMarket);
$('symbol').addEventListener('keydown', (e) => { if (e.key === 'Enter') loadMarket(); });
$('csv-btn').addEventListener('click', downloadCsv);
$('ai-btn').addEventListener('click', () => $('ai-modal').classList.remove('hidden'));
$('ai-cancel').addEventListener('click', () => $('ai-modal').classList.add('hidden'));
$('ai-form').addEventListener('submit', startAnalysis);

$('ai-provider').addEventListener('change', updateBaseUrlVisibility);
updateBaseUrlVisibility();

function updateBaseUrlVisibility() {
  const provider = $('ai-provider').value;
  const needsBase = provider === 'openai_compatible';
  $('base-url-field').classList.toggle('hidden', !needsBase);
}

async function loadMarket() {
  const symbol = $('symbol').value.trim().toUpperCase();
  const period = $('period').value;
  if (!symbol) return;
  showError('');
  $('summary').innerHTML = '<p class="empty">Loading…</p>';
  $('csv-btn').disabled = true;

  try {
    const resp = await fetch(`/api/market/${encodeURIComponent(symbol)}?period=${period}`);
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      showError(err.detail || `HTTP ${resp.status}`);
      $('summary').innerHTML = '<p class="empty">No data.</p>';
      return;
    }
    currentSnapshot = await resp.json();
    renderSnapshot(currentSnapshot);
    $('csv-btn').disabled = false;
  } catch (e) {
    showError('Network error');
    $('summary').innerHTML = '<p class="empty">No data.</p>';
  }
}

function renderSnapshot(s) {
  const pct = s.percent_change;
  const pctClass = pct == null ? '' : (pct >= 0 ? 'up' : 'down');
  const cards = [
    ['Latest', fmtPrice(s.latest_price), pctClass],
    ['Change', `${fmtChange(s.absolute_change)} (${fmtPct(pct)})`, pctClass],
    ['High', fmtPrice(s.high), ''],
    ['Low', fmtPrice(s.low), ''],
    ['Volume', fmtVolume(s.volume), ''],
    ['Open', fmtPrice(s.open), ''],
  ];
  $('summary').innerHTML = cards.map(([label, value, cls]) =>
    `<div class="card"><div class="label">${label}</div><div class="value ${cls}">${value}</div></div>`
  ).join('');
  $('chart').innerHTML = renderChart(s.series);
  $('table-panel').innerHTML = renderTable(s.series);
}

function renderChart(series) {
  if (!series || series.length < 2) return '<p class="empty">Insufficient data.</p>';
  const W = 1000, H = 320, PAD = 8;
  const closes = series.map(p => p.close);
  const min = Math.min(...closes), max = Math.max(...closes);
  const range = max - min || 1;
  const n = closes.length;
  const x = (i) => PAD + (i / (n - 1)) * (W - 2 * PAD);
  const y = (v) => H - PAD - ((v - min) / range) * (H - 2 * PAD);
  const line = closes.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const area = `${line} L${x(n - 1).toFixed(1)},${(H - PAD)} L${x(0).toFixed(1)},${(H - PAD)} Z`;
  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Price chart">
    <path d="${area}" fill="rgba(76,154,255,0.12)"/>
    <path d="${line}" fill="none" stroke="#4c9aff" stroke-width="2"/>
  </svg>`;
}

function renderTable(series) {
  if (!series || !series.length) return '<p class="empty">No rows.</p>';
  const rows = [...series].slice(-30).reverse().map(p =>
    `<tr><td>${p.timestamp}</td><td>${fmtPrice(p.open)}</td><td>${fmtPrice(p.high)}</td><td>${fmtPrice(p.low)}</td><td>${fmtPrice(p.close)}</td><td>${fmtVolume(p.volume)}</td></tr>`
  ).join('');
  return `<table>
    <thead><tr><th>Date</th><th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Volume</th></tr></thead>
    <tbody>${rows}</tbody></table>`;
}

async function startAnalysis(e) {
  e.preventDefault();
  if (!currentSnapshot) return;
  const provider = $('ai-provider').value;
  const payload = {
    symbol: currentSnapshot.symbol,
    period: $('period').value,
    analysis_type: 'trend',
    analysis_mode: $('ai-mode').value,
    output_language: 'English',
    user_question: $('ai-question').value || null,
    ai: {
      provider,
      model: $('ai-model').value,
      api_key: $('ai-key').value || null,
      base_url: provider === 'openai_compatible' ? ($('ai-base-url').value || null) : null,
    },
  };

  const out = $('ai-output');
  out.classList.remove('hidden');
  out.textContent = '';
  $('ai-status').textContent = 'Starting…';

  try {
    const resp = await fetch('/api/analysis', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) {
      $('ai-status').textContent = `HTTP ${resp.status}`;
      return;
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split('\n\n');
      buffer = parts.pop();
      for (const part of parts) {
        if (!part.startsWith('data: ')) continue;
        const evt = JSON.parse(part.slice(6));
        handleEvent(evt, out);
      }
    }
  } catch (err) {
    $('ai-status').textContent = 'Stream error';
  }
}

function handleEvent(evt, out) {
  if (evt.type === 'token') {
    out.textContent += evt.message;
  } else if (evt.type === 'status') {
    $('ai-status').textContent = evt.message;
  } else if (evt.type === 'error') {
    $('ai-status').textContent = `Error: ${evt.message}`;
  }
}

function downloadCsv() {
  if (!currentSnapshot) return;
  const head = 'date,open,high,low,close,volume';
  const rows = currentSnapshot.series.map(p =>
    `${p.timestamp},${p.open},${p.high},${p.low},${p.close},${p.volume}`
  );
  const csv = [head, ...rows].join('\n');
  const blob = new Blob([csv], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${currentSnapshot.symbol}_${$('period').value}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

function showError(msg) { $('error').textContent = msg; $('error').classList.toggle('hidden', !msg); }
function fmtPrice(v) { return v == null ? '—' : Number(v).toFixed(2); }
function fmtChange(v) { return v == null ? '—' : (v >= 0 ? '+' : '') + Number(v).toFixed(2); }
function fmtPct(v) { return v == null ? '—' : (v >= 0 ? '+' : '') + Number(v).toFixed(2) + '%'; }
function fmtVolume(v) { return v == null ? '—' : Number(v).toLocaleString(); }