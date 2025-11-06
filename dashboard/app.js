// dashboard/app.js

// 공통 베이스: 옵션 A → /api
const API_BASE = '/api';

// 인증 키를 쓰는 경우(옵션): 여기에 세팅하거나, 요청마다 헤더 추가 로직 넣기
const ADMIN_KEY = null; // 예: 'YOUR_ADMIN_KEY' 또는 null

async function fetchJSON(path) {
  const headers = { 'Accept': 'application/json' };
  if (ADMIN_KEY) headers['X-Admin-Key'] = ADMIN_KEY;
  const r = await fetch(`${API_BASE}${path}`, { headers });
  if (!r.ok) throw new Error(`HTTP ${r.status} for ${path}`);
  return r.json();
}

// DOM 헬퍼
const $ = (sel) => document.querySelector(sel);

// 차트 인스턴스 보관
let chartHourly, chartBlocked, chartRatio, chartIpBand;

function ensureChart(ctx, type, data, options) {
  if (!ctx) return null;
  return new Chart(ctx, { type, data, options });
}

function upsertChart(chartRef, ctxSel, type, data, options) {
  if (chartRef && chartRef.destroy) chartRef.destroy();
  const ctx = $(ctxSel);
  return ensureChart(ctx, type, data, options);
}

function renderSummaryCards(summary) {
  $('#kpiTotal').textContent   = summary.total_sensitive ?? 0;

  // 총 차단건수 = type_blocked 총합 (간단 정의)
  const blocked = Object.values(summary.type_blocked || {}).reduce((a,b)=>a+b,0);
  $('#kpiBlocked').textContent = blocked;
  $('#lastRefreshed').textContent = new Date().toLocaleString();
}

function renderCharts(summary) {
  // 1) 시간대별 시도
  chartHourly = upsertChart(
    chartHourly,
    '#chartHourly',
    'bar',
    {
      labels: Array.from({length:24}, (_,i)=>`${i}시`),
      datasets: [{ label:'시도 수', data: summary.hourly_attempts || [] }]
    },
    { responsive:true, maintainAspectRatio:false }
  );

  // 2) 유형별 차단 횟수
  const tb = summary.type_blocked || {};
  const tbKeys = Object.keys(tb);
  const tbVals = tbKeys.map(k=>tb[k]);
  chartBlocked = upsertChart(
    chartBlocked,
    '#chartBlocked',
    'bar',
    {
      labels: tbKeys,
      datasets: [{ label:'차단 횟수', data: tbVals }]
    },
    { responsive:true, maintainAspectRatio:false }
  );

  // 3) 유형 비율(라벨 카운트)
  const tr = summary.type_ratio || {};
  const trKeys = Object.keys(tr);
  const trVals = trKeys.map(k=>tr[k]);
  chartRatio = upsertChart(
    chartRatio,
    '#chartRatio',
    'doughnut',
    { labels: trKeys, datasets: [{ data: trVals }] },
    { responsive:true, maintainAspectRatio:false }
  );

  // 4) IP 대역별 차단
  const ib = summary.ip_band_blocked || {};
  const ibKeys = Object.keys(ib);
  const ibVals = ibKeys.map(k=>ib[k]);
  chartIpBand = upsertChart(
    chartIpBand,
    '#chartIpBand',
    'bar',
    {
      labels: ibKeys,
      datasets: [{ label:'/16 대역별 차단', data: ibVals }]
    },
    { responsive:true, maintainAspectRatio:false }
  );
}

function renderRecentLogs(summary) {
  const tb = $('#logs tbody');
  tb.innerHTML = '';
  const rows = summary.recent_logs || [];
  for (const r of rows) {
    const tr = document.createElement('tr');
    const ents = (r.entities || []).map(e=>e.label).join(', ');
    tr.innerHTML = `
      <td>${r.time || '-'}</td>
      <td>${r.host || '-'}</td>
      <td>${r.hostname || '-'}</td>
      <td>${r.public_ip || '-'}</td>
      <td>${r.action || '-'}</td>
      <td>${r.has_sensitive ? 'Y' : 'N'}</td>
      <td>${r.file_blocked ? 'Y' : 'N'}</td>
      <td>${ents || '-'}</td>
      <td title="${r.prompt || ''}">${r.prompt || ''}</td>
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

// 초기 로드 + 주기 갱신
(async () => {
  try {
    await refreshAll();
    setInterval(refreshAll, 10_000);
  } catch (e) {
    console.error('Dashboard init failed:', e);
  }
})();
