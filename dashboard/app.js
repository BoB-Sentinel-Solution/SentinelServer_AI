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

// DOM 헬퍼
const $ = (sel) => document.querySelector(sel);

// 차트 인스턴스
let chartHourly, chartDetected, chartRatio, chartIpBand;

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
  for (let i = 0; i < Math.min(24, arr.length); i++) {
    out[i] = Math.max(0, Number(arr[i]) || 0);
  }
  return out;
}

function renderSummaryCards(summary) {
  const total = Number(summary?.total_sensitive ?? 0);
  $('#kpiTotal').textContent = Number.isFinite(total) ? total : 0;

  // KPI: 총 차단건수(기존 정의 유지)
  const tb = summary?.type_blocked || {};
  const blocked = Object.values(tb).reduce((a, b) => a + (Number(b) || 0), 0);
  $('#kpiBlocked').textContent = blocked;

  $('#lastRefreshed').textContent = new Date().toLocaleString();
}

function renderCharts(summary) {
  // 1) 시간대별 시도 — 꺾은선
  const hourly = normalizeHourly(summary?.hourly_attempts);
  const hourLabels = Array.from({ length: 24 }, (_, i) => `${i}시`);
  chartHourly = upsertChart(
    chartHourly,
    '#chartHourly',
    'line',
    {
      labels: hourLabels,
      datasets: [{
        label: '입력 시도 수',
        data: hourly,
        borderWidth: 3,
        tension: 0.35,
        pointRadius: 0
      }]
    },
    {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { color: '#9ca3af' } },
        y: { beginAtZero: true, ticks: { stepSize: 1, color: '#9ca3af' } }
      }
    }
  );

  // 2) 중요정보 유형별 "탐지" — 막대
  //    서버가 type_detected 제공 시 우선 사용, 없으면 type_blocked로 폴백
  const td = summary?.type_detected ?? summary?.type_blocked ?? {};
  const tdKeys = Object.keys(td);
  const tdVals = tdKeys.map(k => Number(td[k]) || 0);

  chartDetected = upsertChart(
    chartDetected,
    '#chartDetected',
    'bar',
    {
      labels: tdKeys,
      datasets: [{ label: '탐지 횟수', data: tdVals, borderWidth: 1 }]
    },
    {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true } }
    }
  );

  // 3) 유형 비율 — 도넛
  const tr = summary?.type_ratio || {};
  const trKeys = Object.keys(tr);
  const trVals = trKeys.map(k => Number(tr[k]) || 0);
  chartRatio = upsertChart(
    chartRatio,
    '#chartRatio',
    'doughnut',
    { labels: trKeys, datasets: [{ data: trVals }] },
    { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } } }
  );

  // 4) IP 대역별 "탐지" — 막대
  //    서버가 ip_band_detected 제공 시 우선 사용, 없으면 ip_band_blocked로 폴백
  const ib = summary?.ip_band_detected ?? summary?.ip_band_blocked ?? {};
  const ibKeys = Object.keys(ib);
  const ibVals = ibKeys.map(k => Number(ib[k]) || 0);

  chartIpBand = upsertChart(
    chartIpBand,
    '#chartIpBand',
    'bar',
    {
      labels: ibKeys,
      datasets: [{ label: '대역별 탐지 건수', data: ibVals }]
    },
    {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true } }
    }
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

    const promptText = (r.prompt || '').toString().replaceAll('"', '&quot;');

    tr.innerHTML = `
      <td>${r.time || '-'}</td>
      <td>${r.host || '-'}</td>
      <td>${r.hostname || '-'}</td>
      <td>${r.public_ip || '-'}</td>
      <td>${r.action || '-'}</td>
      <td>${r.has_sensitive ? 'Y' : 'N'}</td>
      <td>${r.file_blocked ? 'Y' : 'N'}</td>
      <td>${ents || '-'}</td>
      <td title="${promptText}">${r.prompt || ''}</td>
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

// 초기 로드 + 10초 주기 새로고침
(async () => {
  try {
    await refreshAll();
    setInterval(refreshAll, 10_000);
  } catch (e) {
    console.error('Dashboard init failed:', e);
  }
})();
