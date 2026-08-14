// MindMesh dashboard — dependency-free interactions and inline SVG charting.

const $ = (id) => document.getElementById(id);
const periodLabels = {
  '1M': '1 month',
  '3M': '3 months',
  '6M': '6 months',
  '1Y': '1 year',
  '5Y': '5 years',
  MAX: 'maximum range',
};
const overviewMarkets = [
  { symbol: '^GSPC', name: 'S&P 500', short: 'SPX' },
  { symbol: '^IXIC', name: 'Nasdaq Composite', short: 'COMP' },
  { symbol: '^DJI', name: 'Dow Jones', short: 'DJI' },
  { symbol: '^RUT', name: 'Russell 2000', short: 'RUT' },
];

let currentSnapshot = null;
let lastFocusedElement = null;
let chatLastFocusedElement = null;
let chatAbortController = null;
let chatContextSymbol = null;
let chatMessages = [];

// This configuration must be initialised before updateProviderFields() runs.
// Keeping it near the top prevents a temporal-dead-zone failure that would
// stop the rest of the analysis UI from initialising.
const providerModels = {
  openai: ['gpt-4o', 'gpt-4o-mini', 'gpt-4.1', 'gpt-4.1-mini', 'o3-mini', 'o1-mini'],
  deepseek: ['deepseek-chat', 'deepseek-reasoner'],
  anthropic: [
    'claude-3-5-sonnet-latest',
    'claude-3-7-sonnet-latest',
    'claude-sonnet-4-20250514',
    'claude-haiku-4-20250514',
  ],
  gemini: ['gemini-1.5-pro', 'gemini-1.5-flash', 'gemini-2.0-flash', 'gemini-2.5-pro'],
};

$('market-search').addEventListener('submit', (event) => {
  event.preventDefault();
  loadMarket();
});
$('csv-btn').addEventListener('click', downloadCsv);
$('ai-btn').addEventListener('click', openAnalysis);
$('ai-promo-btn').addEventListener('click', openAnalysis);
$('ai-cancel').addEventListener('click', closeAnalysis);
$('ai-close').addEventListener('click', closeAnalysis);
$('ai-form').addEventListener('submit', startAnalysis);
$('ai-provider').addEventListener('change', updateProviderFields);
$('overview-refresh').addEventListener('click', loadMarketOverview);
$('chat-launcher').addEventListener('click', openChat);
$('nav-chat-btn').addEventListener('click', openChat);
$('chat-promo-btn').addEventListener('click', openChat);
$('chat-close').addEventListener('click', closeChat);
$('chat-new').addEventListener('click', startNewChat);
$('chat-provider').addEventListener('change', updateChatProviderFields);
$('chat-form').addEventListener('submit', sendChatMessage);
$('chat-stop').addEventListener('click', stopChatStream);

document.querySelector('[data-close-modal]').addEventListener('click', closeAnalysis);
document.querySelector('[data-close-chat]').addEventListener('click', closeChat);
document.querySelectorAll('[data-symbol]').forEach((button) => {
  button.addEventListener('click', () => {
    $('symbol').value = button.dataset.symbol;
    loadMarket();
  });
});
$('market-indices').addEventListener('click', (event) => {
  const card = event.target.closest('[data-overview-symbol]');
  if (!card) return;
  $('symbol').value = card.dataset.overviewSymbol;
  $('period').value = '1M';
  loadMarket();
  document.querySelector('#market-workspace').scrollIntoView({ behavior: 'smooth' });
});
$('chat-messages').addEventListener('click', (event) => {
  const suggestion = event.target.closest('[data-chat-prompt]');
  if (!suggestion) return;
  $('chat-input').value = suggestion.dataset.chatPrompt;
  sendChatMessage(new Event('submit'));
});
$('chat-input').addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    $('chat-form').requestSubmit();
  }
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    if (!$('ai-modal').classList.contains('hidden')) closeAnalysis();
    else if (!$('chat-shell').classList.contains('hidden')) closeChat();
  }
});

updateProviderFields();
updateChatProviderFields();
loadMarketOverview();

async function loadMarket() {
  const symbol = $('symbol').value.trim().toUpperCase();
  const period = $('period').value;
  if (!symbol) {
    $('symbol').focus();
    showError('Enter a ticker symbol to continue.');
    return;
  }

  $('symbol').value = symbol;
  showError('');
  setMarketBusy(true);
  renderLoadingState(symbol);

  try {
    const response = await fetch(`/api/market/${encodeURIComponent(symbol)}?period=${encodeURIComponent(period)}`);
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `Market data returned HTTP ${response.status}.`);
    }

    currentSnapshot = await response.json();
    renderSnapshot(currentSnapshot);
    setMarketActionsEnabled(true);
    loadTechnicalSignal(symbol);
  } catch (error) {
    currentSnapshot = null;
    setMarketActionsEnabled(false);
    renderEmptyState('No market data available.');
    showError(error instanceof Error ? error.message : 'Unable to load market data.');
  } finally {
    setMarketBusy(false);
  }
}

async function loadTechnicalSignal(symbol) {
  const card = $('tv-signal-card');
  card.classList.add('hidden');
  try {
    const response = await fetch(`/api/market/${encodeURIComponent(symbol)}/technical`);
    if (!response.ok) {
      // Unknown exchange/symbol under the default mapping: degrade
      // gracefully. The rest of the dashboard must keep working.
      return;
    }
    renderTechnicalSignal(await response.json());
  } catch (error) {
    // Network failure: same graceful degradation.
  }
}

function renderTechnicalSignal(tv) {
  const card = $('tv-signal-card');
  const ratingClass = {
    STRONG_BUY: 'is-buy', BUY: 'is-buy',
    STRONG_SELL: 'is-sell', SELL: 'is-sell',
    NEUTRAL: 'is-neutral', ERROR: 'is-neutral',
  }[tv.summary.recommendation] || 'is-neutral';
  card.innerHTML = `
    <div class="tv-signal-header">
      <span class="metric-label">TradingView technical signal</span>
      <span class="tv-signal-badge ${ratingClass}">${escapeHtml(tv.summary.recommendation.replace('_', ' '))}</span>
    </div>
    <div class="tv-signal-body">
      <span>Oscillators: ${escapeHtml(tv.oscillators.recommendation.replace('_', ' '))} (${tv.oscillators.buy} buy / ${tv.oscillators.sell} sell / ${tv.oscillators.neutral} neutral)</span>
      <span>Moving averages: ${escapeHtml(tv.moving_averages.recommendation.replace('_', ' '))} (${tv.moving_averages.buy} buy / ${tv.moving_averages.sell} sell / ${tv.moving_averages.neutral} neutral)</span>
      <span class="tv-signal-note">Rule-based technical consensus from TradingView — not MindMesh's own calculation, not financial advice.</span>
    </div>`;
  card.classList.remove('hidden');
}

async function loadMarketOverview() {
  const container = $('market-indices');
  $('market-overview').setAttribute('aria-busy', 'true');
  $('overview-refresh').disabled = true;
  $('overview-refresh').lastChild.textContent = ' Loading…';
  container.innerHTML = overviewMarkets.map(() =>
    '<div class="index-card index-card-loading" aria-hidden="true"></div>'
  ).join('');

  const results = await Promise.allSettled(overviewMarkets.map(async (market) => {
    const response = await fetch(`/api/market/${encodeURIComponent(market.symbol)}?period=1M`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return { market, snapshot: await response.json() };
  }));

  const successful = results
    .filter((result) => result.status === 'fulfilled')
    .map((result) => result.value);

  container.innerHTML = results.map((result, index) => {
    const market = overviewMarkets[index];
    if (result.status === 'rejected') {
      return `<div class="index-card index-card-unavailable">
        <div><span class="index-symbol">${escapeHtml(market.short)}</span><div class="index-name">${escapeHtml(market.name)}</div></div>
        <div><strong class="index-value">Unavailable</strong><span class="index-period">Try refreshing shortly</span></div>
      </div>`;
    }
    const snapshot = result.value.snapshot;
    const positive = Number(snapshot.percent_change) >= 0;
    return `<button class="index-card" type="button" data-overview-symbol="${escapeHtml(market.symbol)}" aria-label="Open ${escapeHtml(market.name)} details">
      <div class="index-card-top">
        <div><span class="index-symbol">${escapeHtml(market.short)}</span><div class="index-name">${escapeHtml(market.name)}</div></div>
        <span class="index-change${positive ? ' is-positive' : ''}">${escapeHtml(formatPercent(snapshot.percent_change))}</span>
      </div>
      <div class="index-card-bottom">
        <div><strong class="index-value">${escapeHtml(formatIndexValue(snapshot.latest_price))}</strong><span class="index-period">1 month · Open details</span></div>
      </div>
    </button>`;
  }).join('');

  if (successful.length) {
    const advancing = successful.filter(({ snapshot }) => Number(snapshot.percent_change) >= 0).length;
    const declining = successful.length - advancing;
    const direction = advancing > declining
      ? 'Broad benchmarks lean higher.'
      : advancing < declining
        ? 'Broad benchmarks lean lower.'
        : 'The major benchmarks are mixed.';
    $('market-pulse-copy').textContent = `${direction} ${advancing} advancing and ${declining} declining over the last month.`;
    $('overview-updated').textContent = `Updated ${new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit' }).format(new Date())}`;
  } else {
    $('market-pulse-copy').textContent = 'Market overview is temporarily unavailable. Your individual ticker search still works.';
    $('overview-updated').textContent = '';
  }

  $('market-overview').setAttribute('aria-busy', 'false');
  $('overview-refresh').disabled = false;
  $('overview-refresh').lastChild.textContent = ' Refresh';
}

function setMarketBusy(isBusy) {
  $('market-workspace').setAttribute('aria-busy', String(isBusy));
  $('search-btn').disabled = isBusy;
  $('search-btn').querySelector('.search-label').textContent = isBusy ? 'Loading…' : 'View market';
}

function setMarketActionsEnabled(isEnabled) {
  $('csv-btn').disabled = !isEnabled;
  $('ai-btn').disabled = !isEnabled;
  $('ai-promo-btn').disabled = !isEnabled;
  $('chat-launcher').disabled = !isEnabled;
  $('nav-chat-btn').disabled = !isEnabled;
  $('chat-promo-btn').disabled = !isEnabled;
}

function renderLoadingState(symbol) {
  $('summary-symbol').textContent = symbol;
  $('summary-meta').textContent = 'Fetching the latest available market data…';
  $('summary').innerHTML = Array.from({ length: 4 }, () =>
    '<div class="metric-card metric-card-placeholder" aria-hidden="true"></div>'
  ).join('');
}

function renderEmptyState(message) {
  $('summary').innerHTML = `
    <div class="metric-card metric-card-featured">
      <span class="metric-label">Nothing to show yet</span>
      <strong class="metric-placeholder">${escapeHtml(message)}</strong>
    </div>`;
  $('chart').innerHTML = `
    <div class="chart-empty">
      <svg viewBox="0 0 160 64" aria-hidden="true"><path d="M2 53c15-1 21-18 37-17 15 1 18 13 33 10 13-3 15-26 29-27 12-1 17 11 28 7 12-4 15-16 29-24"/></svg>
      <p>Your price chart will appear here.</p>
    </div>`;
  $('table-panel').innerHTML = '<div class="table-empty">Market history will appear after your search.</div>';
}

function renderSnapshot(snapshot) {
  const period = $('period').value;
  const direction = snapshot.percent_change == null ? '' : snapshot.percent_change >= 0 ? 'Gain' : 'Decline';
  const changeDetail = snapshot.percent_change == null
    ? 'Change unavailable'
    : `${direction} over the selected range`;
  const metrics = [
    ['Latest price', formatPrice(snapshot.latest_price, snapshot.currency), formatAsOf(snapshot.as_of), true],
    ['Period change', `${formatChange(snapshot.absolute_change, snapshot.currency)} · ${formatPercent(snapshot.percent_change)}`, changeDetail],
    ['Range high', formatPrice(snapshot.high, snapshot.currency), `Low ${formatPrice(snapshot.low, snapshot.currency)}`],
    ['Volume', formatVolume(snapshot.volume), `Open ${formatPrice(snapshot.open, snapshot.currency)}`],
  ];

  $('summary-symbol').textContent = snapshot.symbol;
  $('summary-meta').textContent = [
    periodLabels[period] || period,
    snapshot.currency,
    snapshot.provider,
  ].filter(Boolean).join(' · ');
  $('ai-symbol').textContent = snapshot.symbol;
  if (chatContextSymbol && chatContextSymbol !== snapshot.symbol) {
    startNewChat();
  }
  chatContextSymbol = snapshot.symbol;
  $('chat-context-symbol').textContent = snapshot.symbol;
  $('chat-context-period').textContent = periodLabels[period] || period;
  $('chart-range').textContent = `Closing price · ${periodLabels[period] || period}`;

  $('summary').innerHTML = metrics.map(([label, value, detail, featured]) => `
    <article class="metric-card${featured ? ' metric-card-featured' : ''}">
      <span class="metric-label">${escapeHtml(label)}</span>
      <div>
        <strong class="metric-value">${escapeHtml(value)}</strong>
        <div class="metric-detail">${escapeHtml(detail)}</div>
      </div>
    </article>`).join('');

  $('chart').innerHTML = renderChart(snapshot.series, snapshot.currency, snapshot.symbol);
  $('table-panel').innerHTML = renderTable(snapshot.series, snapshot.currency);
}

function renderChart(series, currency, symbol) {
  if (!series || series.length < 2) {
    return '<div class="chart-empty"><p>There is not enough data to draw this range.</p></div>';
  }

  const width = 1120;
  const height = 420;
  const pad = { top: 24, right: 20, bottom: 42, left: 84 };
  const closes = series.map((point) => Number(point.close));
  const rawMin = Math.min(...closes);
  const rawMax = Math.max(...closes);
  const buffer = (rawMax - rawMin || Math.max(Math.abs(rawMax) * 0.05, 1)) * 0.08;
  const min = rawMin - buffer;
  const max = rawMax + buffer;
  const range = max - min || 1;
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;
  const x = (index) => pad.left + (index / (closes.length - 1)) * plotWidth;
  const y = (value) => pad.top + (1 - (value - min) / range) * plotHeight;
  const line = closes.map((value, index) =>
    `${index ? 'L' : 'M'}${x(index).toFixed(1)},${y(value).toFixed(1)}`
  ).join(' ');
  const baseline = height - pad.bottom;
  const area = `${line} L${x(closes.length - 1).toFixed(1)},${baseline} L${x(0).toFixed(1)},${baseline} Z`;

  const gridCount = 4;
  const grid = Array.from({ length: gridCount + 1 }, (_, index) => {
    const value = max - (index / gridCount) * range;
    const yPos = pad.top + (index / gridCount) * plotHeight;
    return `<line class="chart-grid-line" x1="${pad.left}" y1="${yPos.toFixed(1)}" x2="${width - pad.right}" y2="${yPos.toFixed(1)}"/>
      <text class="chart-axis-label" x="${pad.left - 14}" y="${(yPos + 5).toFixed(1)}" text-anchor="end">${escapeHtml(formatAxisPrice(value, currency))}</text>`;
  }).join('');

  const xLabelIndexes = [...new Set([0, Math.floor((series.length - 1) / 2), series.length - 1])];
  const xLabels = xLabelIndexes.map((index) => {
    const anchor = index === 0 ? 'start' : index === series.length - 1 ? 'end' : 'middle';
    return `<text class="chart-axis-label" x="${x(index).toFixed(1)}" y="${height - 10}" text-anchor="${anchor}">${escapeHtml(formatDate(series[index].timestamp))}</text>`;
  }).join('');
  const lastIndex = closes.length - 1;
  const trendText = closes[lastIndex] >= closes[0] ? 'rising' : 'falling';

  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(`${symbol} closing price chart, ${trendText} from ${formatAxisPrice(closes[0], currency)} to ${formatAxisPrice(closes[lastIndex], currency)}`)}">
    ${grid}
    <path class="chart-area" d="${area}"/>
    <path class="chart-line" d="${line}"/>
    <circle class="chart-last-point" cx="${x(lastIndex).toFixed(1)}" cy="${y(closes[lastIndex]).toFixed(1)}" r="6"/>
    ${xLabels}
  </svg>`;
}

function renderTable(series, currency) {
  if (!series || !series.length) {
    return '<div class="table-empty">No historical rows are available.</div>';
  }

  const rows = [...series].slice(-30).reverse().map((point) => `
    <tr>
      <td>${escapeHtml(formatDate(point.timestamp, true))}</td>
      <td>${escapeHtml(formatPrice(point.open, currency))}</td>
      <td>${escapeHtml(formatPrice(point.high, currency))}</td>
      <td>${escapeHtml(formatPrice(point.low, currency))}</td>
      <td>${escapeHtml(formatPrice(point.close, currency))}</td>
      <td>${escapeHtml(formatVolume(point.volume))}</td>
    </tr>`).join('');

  return `<table>
    <thead><tr><th scope="col">Date</th><th scope="col">Open</th><th scope="col">High</th><th scope="col">Low</th><th scope="col">Close</th><th scope="col">Volume</th></tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

function openAnalysis() {
  if (!currentSnapshot) return;
  lastFocusedElement = document.activeElement;
  $('ai-symbol').textContent = currentSnapshot.symbol;
  $('ai-modal').classList.remove('hidden');
  document.body.classList.add('modal-open');
  $('ai-provider').focus();
}

function closeAnalysis() {
  $('ai-modal').classList.add('hidden');
  document.body.classList.remove('modal-open');
  if (lastFocusedElement instanceof HTMLElement) lastFocusedElement.focus();
}

function updateProviderFields() {
  const provider = $('ai-provider').value;
  const preset = providerModels[provider];
  const needsBaseUrl = provider === 'openai_compatible';

  $('base-url-field').classList.toggle('hidden', !needsBaseUrl);
  $('ai-base-url').disabled = !needsBaseUrl;

  const modelSelect = $('ai-model');
  const modelCustom = $('ai-model-custom');
  if (preset) {
    modelSelect.classList.remove('hidden');
    modelSelect.disabled = false;
    modelCustom.classList.add('hidden');
    modelCustom.disabled = true;
    modelSelect.innerHTML = preset.map((model, index) =>
      `<option value="${escapeHtml(model)}"${index === 0 ? ' selected' : ''}>${escapeHtml(model)}</option>`
    ).join('');
  } else {
    modelSelect.classList.add('hidden');
    modelSelect.disabled = true;
    modelCustom.classList.remove('hidden');
    modelCustom.disabled = false;
  }
}

function updateChatProviderFields() {
  const provider = $('chat-provider').value;
  const preset = providerModels[provider];
  const needsBaseUrl = provider === 'openai_compatible';
  const modelSelect = $('chat-model');
  const modelCustom = $('chat-model-custom');

  $('chat-provider-summary').textContent = $('chat-provider').selectedOptions[0].textContent;
  $('chat-base-url-field').classList.toggle('hidden', !needsBaseUrl);
  $('chat-base-url').disabled = !needsBaseUrl;

  if (preset) {
    const previousModel = modelSelect.value;
    modelSelect.innerHTML = preset.map((model) =>
      `<option value="${escapeHtml(model)}">${escapeHtml(model)}</option>`
    ).join('');
    modelSelect.classList.remove('hidden');
    modelSelect.disabled = false;
    modelCustom.classList.add('hidden');
    modelCustom.disabled = true;
    if (preset.includes(previousModel)) modelSelect.value = previousModel;
  } else {
    modelSelect.classList.add('hidden');
    modelSelect.disabled = true;
    modelCustom.classList.remove('hidden');
    modelCustom.disabled = false;
  }
}

function syncChatConnectionFromAnalysis() {
  if ($('chat-key').value || !$('ai-key').value) return;
  $('chat-provider').value = $('ai-provider').value;
  updateChatProviderFields();

  const analysisModel = $('ai-model').classList.contains('hidden')
    ? $('ai-model-custom').value
    : $('ai-model').value;
  if ($('chat-model').classList.contains('hidden')) $('chat-model-custom').value = analysisModel;
  else if ([...$('chat-model').options].some((option) => option.value === analysisModel)) $('chat-model').value = analysisModel;

  $('chat-base-url').value = $('ai-base-url').value;
  $('chat-key').value = $('ai-key').value;
}

function openChat() {
  if (!currentSnapshot) return;
  chatLastFocusedElement = document.activeElement;
  syncChatConnectionFromAnalysis();
  $('chat-context-symbol').textContent = currentSnapshot.symbol;
  $('chat-context-period').textContent = periodLabels[$('period').value] || $('period').value;
  $('chat-shell').classList.remove('hidden');
  document.body.classList.add('modal-open');
  $('chat-input').focus();
}

function closeChat() {
  $('chat-shell').classList.add('hidden');
  document.body.classList.remove('modal-open');
  if (chatLastFocusedElement instanceof HTMLElement) chatLastFocusedElement.focus();
}

function startNewChat() {
  if (chatAbortController) chatAbortController.abort();
  chatMessages = [];
  showChatError('');
  renderChatMessages();
  if (!$('chat-shell').classList.contains('hidden')) $('chat-input').focus();
}

function stopChatStream() {
  if (chatAbortController) chatAbortController.abort();
}

function renderChatMessages() {
  const container = $('chat-messages');
  if (!chatMessages.length) {
    container.innerHTML = `<div class="chat-welcome">
      <div class="chat-mark" aria-hidden="true">
        <svg viewBox="0 0 24 24"><path d="M4 6.5 9 3l5 3.5L19 3l1 17-6-3.5L9 20l-5-3.5V6.5Z"/><path d="m9 3 .1 17M14 6.5v10"/></svg>
      </div>
      <h3>What would you like to understand?</h3>
      <p>I’ll ground every answer in the latest snapshot for the selected symbol.</p>
      <div class="chat-suggestions">
        <button type="button" data-chat-prompt="What is driving the current trend?">What is driving the trend?</button>
        <button type="button" data-chat-prompt="What are the main downside risks in this data?">What are the downside risks?</button>
        <button type="button" data-chat-prompt="Explain the latest price action in plain language.">Explain the price action</button>
      </div>
    </div>`;
    return;
  }

  container.innerHTML = chatMessages.map((message) => `
    <article class="chat-message chat-message-${message.role}${message.streaming ? ' is-streaming' : ''}" data-message-id="${escapeHtml(message.id)}">
      <span class="chat-message-role">${message.role === 'user' ? 'You' : `MindMesh${message.status ? ` · ${escapeHtml(message.status)}` : ''}`}</span>
      <div class="chat-message-body">${escapeHtml(message.content || (message.streaming ? ' ' : 'No response.'))}</div>
    </article>`).join('');
  container.scrollTop = container.scrollHeight;
}

async function sendChatMessage(event) {
  event.preventDefault();
  if (chatAbortController || !currentSnapshot) return;

  const question = $('chat-input').value.trim();
  if (!question) return;

  const provider = $('chat-provider').value;
  const model = $('chat-model').classList.contains('hidden')
    ? $('chat-model-custom').value.trim()
    : $('chat-model').value.trim();
  const key = $('chat-key').value;
  const baseUrl = provider === 'openai_compatible' ? $('chat-base-url').value.trim() : null;
  if (!model || !key || (provider === 'openai_compatible' && !baseUrl)) {
    showChatError('Complete the AI connection settings before sending a message.');
    $('chat-settings').open = true;
    return;
  }

  showChatError('');
  const priorMessages = chatMessages.slice(-6);
  const assistantMessage = {
    id: createMessageId(),
    role: 'assistant',
    content: '',
    status: 'Starting…',
    streaming: true,
  };
  chatMessages.push({ id: createMessageId(), role: 'user', content: question });
  chatMessages.push(assistantMessage);
  $('chat-input').value = '';
  renderChatMessages();
  setChatBusy(true);

  const payload = {
    symbol: currentSnapshot.symbol,
    period: $('period').value,
    analysis_type: 'trend',
    analysis_mode: 'quick',
    output_language: 'English',
    user_question: buildChatQuestion(question, priorMessages),
    ai: { provider, model, api_key: key, base_url: baseUrl },
  };

  chatAbortController = new AbortController();
  try {
    await requestAnalysisStream(payload, (streamEvent) => {
      if (streamEvent.type === 'token') {
        assistantMessage.content += streamEvent.message || '';
        assistantMessage.status = '';
      } else if (streamEvent.type === 'section') {
        assistantMessage.content += `\n\n${streamEvent.message || ''}\n`;
      } else if (streamEvent.type === 'status') {
        assistantMessage.status = streamEvent.message || 'Working…';
      } else if (streamEvent.type === 'final') {
        assistantMessage.content += streamEvent.message || '';
        assistantMessage.status = 'Complete';
      } else if (streamEvent.type === 'error') {
        throw new Error(streamEvent.message || 'Chat request failed');
      }
      renderChatMessages();
    }, chatAbortController.signal);
    assistantMessage.status = 'Complete';
    if (!assistantMessage.content) assistantMessage.content = 'The model completed without returning text.';
  } catch (error) {
    if (error?.name === 'AbortError') {
      assistantMessage.status = 'Stopped';
      if (!assistantMessage.content) assistantMessage.content = 'Response stopped.';
    } else {
      assistantMessage.status = 'Error';
      if (!assistantMessage.content) assistantMessage.content = 'I couldn’t complete that response.';
      showChatError(error instanceof Error ? error.message : 'Unable to complete the chat request.');
    }
  } finally {
    assistantMessage.streaming = false;
    chatAbortController = null;
    setChatBusy(false);
    renderChatMessages();
  }
}

function buildChatQuestion(question, history) {
  const conversation = history.map((message) =>
    `${message.role === 'user' ? 'User' : 'Assistant'}: ${message.content}`
  ).join('\n');
  const historyBlock = conversation ? `Prior conversation:\n${conversation}\n\n` : '';
  return `You are continuing a concise market-data conversation about ${currentSnapshot.symbol}. Use the deterministic market facts provided below, answer the latest question directly, and clearly separate facts from interpretation. Do not give trade orders.\n\n${historyBlock}Latest user question: ${question}`;
}

function createMessageId() {
  return `message-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function setChatBusy(isBusy) {
  $('chat-send').disabled = isBusy;
  $('chat-stop').classList.toggle('hidden', !isBusy);
  $('chat-input').disabled = isBusy;
}

function showChatError(message) {
  $('chat-error').textContent = message;
  $('chat-error').classList.toggle('hidden', !message);
}

async function startAnalysis(event) {
  event.preventDefault();
  if (!currentSnapshot) return;

  const provider = $('ai-provider').value;
  const payload = {
    symbol: currentSnapshot.symbol,
    period: $('period').value,
    analysis_type: 'trend',
    analysis_mode: $('ai-mode').value,
    output_language: 'English',
    user_question: $('ai-question').value.trim() || null,
    ai: {
      provider,
      model: $('ai-model').classList.contains('hidden')
        ? $('ai-model-custom').value.trim()
        : $('ai-model').value.trim(),
      api_key: $('ai-key').value || null,
      base_url: provider === 'openai_compatible' ? ($('ai-base-url').value.trim() || null) : null,
    },
  };

  const output = $('ai-output');
  $('ai-result').classList.remove('hidden');
  output.textContent = '';
  setAnalysisBusy(true, 'Starting…');

  try {
    const { receivedFinal } = await requestAnalysisStream(
      payload,
      (streamEvent) => handleAnalysisEvent(streamEvent, output),
    );

    if (!$('ai-status').textContent.startsWith('Error')) {
      $('ai-status').textContent = receivedFinal || output.textContent ? 'Complete' : 'Finished';
    }
  } catch (error) {
    $('ai-status').textContent = `Error · ${error instanceof Error ? error.message : 'Unable to complete analysis'}`;
  } finally {
    setAnalysisBusy(false);
  }
}

async function requestAnalysisStream(payload, onEvent, signal) {
  const response = await fetch('/api/analysis', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Analysis returned HTTP ${response.status}.`);
  }
  if (!response.body) throw new Error('The analysis stream could not be opened.');

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let receivedFinal = false;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() || '';
    for (const part of parts) {
      if (!part.startsWith('data: ')) continue;
      try {
        const streamEvent = JSON.parse(part.slice(6));
        if (streamEvent.type === 'final') receivedFinal = true;
        onEvent(streamEvent);
      } catch (error) {
        if (error instanceof SyntaxError) continue;
        throw error;
      }
    }
  }
  return { receivedFinal };
}

function setAnalysisBusy(isBusy, statusText = '') {
  $('ai-start').disabled = isBusy;
  $('ai-start').textContent = isBusy ? 'Analysing…' : 'Start analysis';
  if (statusText) $('ai-status').textContent = statusText;
}

function handleAnalysisEvent(event, output) {
  if (event.type === 'token') {
    output.textContent += event.message || '';
  } else if (event.type === 'section') {
    const heading = event.message ? `\n\n${event.message}\n` : '\n\n';
    output.textContent += heading;
  } else if (event.type === 'final') {
    if (event.message) output.textContent += event.message;
    $('ai-status').textContent = 'Complete';
  } else if (event.type === 'status') {
    $('ai-status').textContent = event.message || 'Working…';
  } else if (event.type === 'error') {
    $('ai-status').textContent = `Error · ${event.message || 'Analysis failed'}`;
  }
}

function downloadCsv() {
  if (!currentSnapshot) return;
  const header = 'date,open,high,low,close,volume';
  const rows = currentSnapshot.series.map((point) =>
    [point.timestamp, point.open, point.high, point.low, point.close, point.volume].join(',')
  );
  const blob = new Blob([[header, ...rows].join('\n')], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `${currentSnapshot.symbol}_${$('period').value}.csv`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function showError(message) {
  $('error').textContent = message;
  $('error').classList.toggle('hidden', !message);
}

function formatPrice(value, currency) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  const numeric = Number(value);
  if (currency && /^[A-Z]{3}$/.test(currency)) {
    try {
      return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(numeric);
    } catch (_) {
      // Fall through for unsupported currency codes.
    }
  }
  return numeric.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatAxisPrice(value, currency) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  const numeric = Number(value);
  const amount = numeric >= 1000 ? numeric.toLocaleString('en-US', { maximumFractionDigits: 0 }) : numeric.toFixed(2);
  if (currency === 'USD') return `$${amount}`;
  return amount;
}

function formatIndexValue(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return Number(value).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatChange(value, currency) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  const numeric = Number(value);
  const formatted = formatPrice(Math.abs(numeric), currency);
  return `${numeric >= 0 ? '+' : '−'}${formatted}`;
}

function formatPercent(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  const numeric = Number(value);
  return `${numeric >= 0 ? '+' : '−'}${Math.abs(numeric).toFixed(2)}%`;
}

function formatVolume(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  const numeric = Number(value);
  return new Intl.NumberFormat('en-US', {
    notation: numeric >= 1000000 ? 'compact' : 'standard',
    maximumFractionDigits: 2,
  }).format(numeric);
}

function formatAsOf(value) {
  if (!value) return 'Latest available close';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return `As of ${value}`;
  return `As of ${new Intl.DateTimeFormat('en-US', { dateStyle: 'medium' }).format(parsed)}`;
}

function formatDate(value, long = false) {
  if (!value) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return new Intl.DateTimeFormat('en-US', long
    ? { year: 'numeric', month: 'short', day: 'numeric' }
    : { month: 'short', day: 'numeric', year: '2-digit' }
  ).format(parsed);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}
