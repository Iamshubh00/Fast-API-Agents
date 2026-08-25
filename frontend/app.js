const state = { alerts: [], selectedId: null, filter: 'all' };
const $ = (selector) => document.querySelector(selector);

function showToast(message, isError = false) {
  const toast = $('#toast');
  toast.textContent = message;
  toast.className = `toast visible ${isError ? 'error' : ''}`;
  window.setTimeout(() => toast.classList.remove('visible'), 3500);
}

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || body.error?.message || `Request failed (${response.status})`);
  return body;
}

function severityClass(severity) { return ['critical', 'high'].includes(String(severity).toLowerCase()) ? 'high' : String(severity).toLowerCase(); }
function formatDate(value) { return value ? new Date(value).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : 'Just now'; }
function label(value) { return String(value || '').replaceAll('_', ' '); }

async function loadAlerts() {
  try {
    state.alerts = await api('/agents/alerts');
    renderStats(); renderAlerts();
    if (state.selectedId && state.alerts.some((alert) => alert.id === state.selectedId)) await selectAlert(state.selectedId, false);
  } catch (error) { showToast(error.message, true); $('#alert-list').innerHTML = `<div class="empty-state error-state">Could not load alerts.<br><small>${error.message}</small></div>`; }
}

function renderStats() {
  const open = state.alerts.filter((alert) => !['closed', 'response_approved', 'response_denied'].includes(alert.status)).length;
  $('#open-count').textContent = open;
  $('#approval-count').textContent = state.alerts.filter((alert) => alert.status === 'awaiting_approval').length;
  $('#closed-count').textContent = state.alerts.filter((alert) => ['closed', 'response_approved', 'response_denied'].includes(alert.status)).length;
}

function renderAlerts() {
  const filtered = state.alerts.filter((alert) => state.filter === 'all' || (state.filter === 'high' ? ['high', 'critical'].includes(alert.severity_raw) : alert.status === state.filter));
  $('#alert-count').textContent = `${filtered.length} alert${filtered.length === 1 ? '' : 's'}`;
  $('#alert-list').innerHTML = filtered.length ? filtered.map((alert) => `<button class="alert-row ${alert.id === state.selectedId ? 'selected' : ''}" data-id="${alert.id}"><span class="severity-dot ${severityClass(alert.severity_raw)}"></span><span class="alert-main"><strong>${escapeHtml(alert.raw_event?.event || 'Unspecified security event')}</strong><small>${escapeHtml(alert.source)} / ${escapeHtml(alert.raw_event?.host_id || 'No host')} &middot; ${formatDate(alert.created_at)}</small></span><span class="row-status status-${alert.status}">${label(alert.status)}</span><span class="row-arrow">&#8250;</span></button>`).join('') : '<div class="empty-state">No alerts match this view.</div>';
  document.querySelectorAll('.alert-row').forEach((row) => row.addEventListener('click', () => selectAlert(Number(row.dataset.id))));
}

function escapeHtml(value) { return String(value).replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[char]); }

async function selectAlert(id, notify = true) {
  state.selectedId = id; renderAlerts();
  const panel = $('#detail-panel'); panel.innerHTML = '<div class="empty-state">Loading trace...</div>';
  try { const trace = await api(`/agents/alerts/${id}/trace`); renderDetail(trace); if (notify) panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
  catch (error) { panel.innerHTML = `<div class="empty-state error-state">${escapeHtml(error.message)}</div>`; }
}

function renderDetail(trace) {
  const alert = state.alerts.find((item) => item.id === state.selectedId) || { id: trace.alert.id, status: trace.alert.status, raw_event: trace.alert.raw_event, source: 'unknown', severity_raw: 'unknown' };
  const response = trace.agent_runs.find((run) => run.agent === 'response');
  const action = response?.output?.recommended_action;
  const canApprove = alert.status === 'awaiting_approval' && action;
  $('#detail-panel').innerHTML = `<div class="detail-header"><div><span class="section-kicker">ALERT #${alert.id}</span><h2>${escapeHtml(alert.raw_event?.event || 'Security event')}</h2></div><button class="close-detail" id="close-detail">&times;</button></div><div class="detail-meta"><span class="severity-badge ${severityClass(alert.severity_raw)}">${escapeHtml(alert.severity_raw)} severity</span><span class="row-status status-${alert.status}">${label(alert.status)}</span><span>${escapeHtml(alert.source)} &middot; ${formatDate(alert.created_at)}</span></div><div class="event-fields">${Object.entries(alert.raw_event || {}).filter(([key]) => key !== 'event').map(([key, value]) => `<div><span>${escapeHtml(key.replaceAll('_', ' '))}</span><strong>${escapeHtml(value ?? 'n/a')}</strong></div>`).join('')}</div>${canApprove ? `<div class="approval-box"><div><span class="section-kicker">RESPONSE RECOMMENDATION</span><strong>${escapeHtml(action)}</strong><p>${escapeHtml(response.output.rationale || 'The response agent recommends human review.')}</p></div><div class="approval-actions"><button class="danger-button" id="approve-btn">Approve action</button><button class="quiet-button" id="deny-btn">Deny</button></div></div>` : ''}<div class="trace-heading"><span class="section-kicker">AGENT TRACE</span><span>${trace.agent_runs.length} recorded runs</span></div><div class="trace-list">${trace.agent_runs.length ? trace.agent_runs.map((run) => `<details class="trace-item"><summary><span class="trace-index">${run.agent.slice(0, 1).toUpperCase()}</span><strong>${escapeHtml(run.agent)} agent</strong><span>${run.latency_ms} ms</span><span class="row-arrow">&#8250;</span></summary><pre>${escapeHtml(JSON.stringify(run.output, null, 2))}</pre></details>`).join('') : '<div class="empty-state">No agent runs yet. Run the pipeline to see its trace.</div>'}</div><div class="detail-footer"><button class="run-button" id="run-btn" ${['awaiting_approval', 'closed', 'response_approved', 'response_denied'].includes(alert.status) ? 'disabled' : ''}>Run agent pipeline <span>&#8594;</span></button></div>`;
  $('#close-detail').addEventListener('click', () => { state.selectedId = null; $('#detail-panel').innerHTML = '<div class="empty-detail"><div class="empty-glyph">+</div><h2>Select an alert</h2><p>Choose an alert from the queue to inspect its event and agent trace.</p></div>'; renderAlerts(); });
  $('#run-btn')?.addEventListener('click', runPipeline);
  $('#approve-btn')?.addEventListener('click', () => decideResponse(true));
  $('#deny-btn')?.addEventListener('click', () => decideResponse(false));
}

async function runPipeline() { const button = $('#run-btn'); button.disabled = true; button.textContent = 'Running pipeline...'; try { await api(`/agents/alerts/${state.selectedId}/run`, { method: 'POST' }); showToast('Pipeline completed and trace recorded.'); await loadAlerts(); await selectAlert(state.selectedId, false); } catch (error) { showToast(error.message, true); button.disabled = false; button.innerHTML = 'Run agent pipeline <span>&#8594;</span>'; } }
async function decideResponse(approved) { const justification = window.prompt(approved ? 'Justification for approving this action:' : 'Reason for denying this action:'); if (!justification?.trim()) return; try { await api(`/agents/alerts/${state.selectedId}/approve-response`, { method: 'POST', body: JSON.stringify({ approved, justification }) }); showToast(approved ? 'Response approved.' : 'Response denied.'); await loadAlerts(); await selectAlert(state.selectedId, false); } catch (error) { showToast(error.message, true); } }

function showView(view) { document.querySelectorAll('.view').forEach((item) => item.classList.toggle('hidden', item.id !== `${view}-view`)); document.querySelectorAll('.nav-item').forEach((item) => item.classList.toggle('active', item.dataset.view === view)); }
$('#alert-form').addEventListener('submit', async (event) => { event.preventDefault(); const data = new FormData(event.target); const eventData = { event: data.get('event'), ...(data.get('host_id') && { host_id: data.get('host_id') }), ...(data.get('src_ip') && { src_ip: data.get('src_ip') }), ...(data.get('user') && { user: data.get('user') }), timestamp: new Date().toISOString() }; try { const created = await api('/agents/alerts', { method: 'POST', body: JSON.stringify({ source: data.get('source'), severity_raw: data.get('severity_raw'), raw_event: eventData }) }); showToast(`Alert #${created.alert_id} created.`); event.target.reset(); showView('overview'); await loadAlerts(); await selectAlert(created.alert_id); } catch (error) { showToast(error.message, true); } });
document.querySelectorAll('.nav-item').forEach((button) => button.addEventListener('click', () => showView(button.dataset.view)));
$('#new-alert-btn').addEventListener('click', () => showView('ingest')); $('#refresh-btn').addEventListener('click', loadAlerts);
document.querySelectorAll('.filter').forEach((button) => button.addEventListener('click', () => { state.filter = button.dataset.filter; document.querySelectorAll('.filter').forEach((item) => item.classList.toggle('active', item === button)); renderAlerts(); }));
$('#current-date').textContent = new Date().toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' });
loadAlerts();
