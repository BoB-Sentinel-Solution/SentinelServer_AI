// dashboard/app.js

const API_BASE = '/api';
const ADMIN_KEY = null; // 필요시 'X-Admin-Key' 전송

async function fetchJSON(path) {
  const headers = { 'Accept': 'application/json' };
  if (ADMIN_KEY) headers['X-Admin-Key'] = ADMIN_KEY;
  const r = await fetch(`${API_BASE}${path}`, { headers });
  if (!r.ok) throw new Error(`HTTP ${r.status} for ${path}`);
  return r.json();
}

const $ = (sel) => document.querySelector(sel);
let chartHourly, chartBlocked, chartRatio, chartIpBand;

function ensureChart(ctx, type, data, options) {
  if (!ctx) return null;
  return new Chart(ctx, { type, data, options });
}
function upsertChart(ref, ctxSel, type, data, options) {
  if (ref && ref.destroy) ref.destroy();
  const el = $(ctxSel);
  if (!el) return null;
  const ctx = el.getContext ? el.getContext('2d') : el;
  return ensureChart(ctx, type, data, options);
}

/* 0~23시 길이 보장 */
function normalizeHourly(arr) {
  const out = new Array(24).fill(0);
  if (!Array.isArray(arr)) return out;
  for (let i = 0; i < Math.min(24, arr.length); i++) out[i] = Math.max(0, Number(arr[i]) || 0);
  return out;
}

function renderSummaryCards(summary) {
  const total = Number(summary?.total_sensitive ?? 0);
  $('#kpiTotal').textContent = isFinite(total) ? total : 0;

  const tb = summary?.type_blocked || {};
  const blocked = Object.values(tb).reduce((a,b)=>a+(Number(b)||0),0);
  $('#kpiBlocked').textContent = blocked;

  $('#lastRefreshed').textContent = new Date().toLocaleString();
}

function renderCharts(summary) {
  // 1) 시간대별 시도 — 꺾은선
  const hourly = normalizeHourly(summary?.hourly_attempts);
  const hourLabels = Array.from({length:24}, (_,i)=>`${i}시`);
  chartHourly = upsertChart(
    chartHourly,
    '#chartHourly',
    'line',
    {
      labels: hourLabels,
      datasets: [{
        label: '시도 수',
        data: hourly,
        borderWidth: 3,
        tension: 0.35,
        pointRadius: 0
      }]
    },
    {
      responsive:true, maintainAspectRatio:false,
      interaction:{ mode:'index', intersect:false },
      plugins:{ legend:{ display:false } },
      scales:{
        x:{ grid:{ display:false }, ticks:{ color:'#9ca3af' } },
        y:{ beginAtZero:true, ticks:{ stepSize:1, color:'#9ca3af' } }
      }
    }
  );

  // 2) 유형별 차단 — 막대
  const tb = summary?.type_blocked || {};
  const tbKeys = Object.keys(tb);
  const tbVals = tbKeys.map(k=>Number(tb[k])||0);
  chartBlocked = upsertChart(
    chartBlocked,
    '#chartBlocked',
    'bar',
    { labels: tbKeys, datasets: [{ label:'차단 횟수', data: tbVals, borderWidth:1 }] },
    { responsive:true, maintainAspectRatio:false, plugins:{ legend:{ display:false } }, scales:{ y:{ beginAtZero:true } } }
  );

  // 3) 유형 비율 — 도넛
  const tr = summary?.type_ratio || {};
  const trKeys = Object.keys(tr);
  const trVals = trKeys.map(k=>Number(tr[k])||0);
  chartRatio = upsertChart(
    chartRatio,
    '#chartRatio',
    'doughnut',
    { labels: trKeys, datasets: [{ data: trVals }] },
    { responsive:true, maintainAspectRatio:false, plugins:{ legend:{ position:'bottom' } } }
  );

  // 4) IP 대역별 차단 — 막대
  const ib = summary?.ip_band_blocked || {};
  const ibKeys = Object.keys(ib);
  const ibVals = ibKeys.map(k=>Number(ib[k])||0);
  chartIpBand = upsertChart(
    chartIpBand,
    '#chartIpBand',
    'bar',
    { labels: ibKeys, datasets: [{ label:'/16 대역별 차단', data: ibVals }] },
    { responsive:true, maintainAspectRatio:false, plugins:{ legend:{ display:false } }, scales:{ y:{ beginAtZero:true } } }
  );
}

function renderRecentLogs(summary) {
  const tb = $('#logs tbody');
  if (!tb) return;
  tb.innerHTML = '';

  const rows = Array.isArray(summary?.recent_logs) ? summary.recent_logs : [];
  for (const r of rows) {
    const tr = document.createElement('tr');
    const ents = Array.isArray(r.entities)
      ? r.entities.map(e => e?.label ?? e?.type ?? '').filter(Boolean).join(', ')
      : (r.entities || '');
    tr.innerHTML = `
      <td>${r.time || '-'}</td>
      <td>${r.host || '-'}</td>
      <td>${r.hostname || '-'}</td>
      <td>${r.public_ip || '-'}</td>
      <td>${r.action || '-'}</td>
      <td>${r.has_sensitive ? 'Y' : 'N'}</td>
      <td>${r.file_blocked ? 'Y' : 'N'}</td>
      <td>${ents || '-'}</td>
      <td title="${(r.prompt || '').toString().replaceAll('"','&quot;')}">${r.prompt || ''}</td>
    `;
    tb.appendChild(tr);
  }
}

async function refreshAll() {
  const summary = await fetchJSON('/summary');
  renderSummaryCards(summary);
  renderCharts(summary);
  renderRecentLogs(summary);
}

// 부팅 + 10초 주기 새로고침
(async () => {
  try {
    await refreshAll();
    setInterval(refreshAll, 10_000);
  } catch (e) {
    console.error('Dashboard init failed:', e);
  }
})();