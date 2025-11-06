const API_BASE = '/api/summary';

async function fetchJSON(url){
  const r = await fetch(url, { headers: { 'Accept':'application/json' }});
  if(!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

function toLabelsValues(obj) {
  const labels = Object.keys(obj || {});
  const values = labels.map(k => obj[k]);
  return { labels, values };
}

let ratioChart, hourlyChart, blockedChart, ipBandChart;

// 공통 차트 옵션: 부모 크기 맞춤 + 다크 테마
function baseOptions() {
  return {
    responsive: true,
    maintainAspectRatio: false,          // 부모 .chart 높이에 맞춤
    plugins: { legend: { labels: { color: '#cfe0ff' } } },
    scales: {
      x: { ticks: { color: '#cfe0ff' }, grid: { color: 'rgba(255,255,255,0.06)' } },
      y: { beginAtZero: true, ticks: { color: '#cfe0ff' }, grid: { color: 'rgba(255,255,255,0.06)' } }
    },
    elements: { line: { tension: .3 } }
  };
}

function makeResizeAware(chart, el) {
  // 컨테이너 크기 변화 감지 시 차트 리사이즈
  const ro = new ResizeObserver(() => chart.resize());
  ro.observe(el);
  return ro;
}

let observers = [];

function renderCharts(data) {
  // KPI
  const totalSensitive = data.total_sensitive ?? 0;
  const totalBlocked = Object.values(data.type_blocked || {}).reduce((a, b) => a + b, 0);
  document.getElementById('kpiTotal').textContent = totalSensitive;
  document.getElementById('kpiBlocked').textContent = totalBlocked;
  document.getElementById('lastRefreshed').textContent = new Date().toLocaleString();

  // 기존 옵저버 해제
  observers.forEach(o => o.disconnect?.());
  observers = [];

  // 시간대별
  const hours = Array.from({length:24}, (_,i)=>i);
  if (hourlyChart) hourlyChart.destroy();
  const hourlyEl = document.getElementById('chartHourly').parentElement;
  hourlyChart = new Chart(document.getElementById('chartHourly'), {
    type: 'line',
    data: {
      labels: hours,
      datasets: [{
        label: '시도 건수',
        data: data.hourly_attempts || [],
        borderColor: '#3b82f6',
        backgroundColor: 'rgba(59,130,246,.25)',
        pointRadius: 2
      }]
    },
    options: baseOptions()
  });
  observers.push(makeResizeAware(hourlyChart, hourlyEl));

  // 유형별 차단
  const blocked = toLabelsValues(data.type_blocked || {});
  if (blockedChart) blockedChart.destroy();
  const blockedEl = document.getElementById('chartBlocked').parentElement;
  blockedChart = new Chart(document.getElementById('chartBlocked'), {
    type: 'bar',
    data: {
      labels: blocked.labels,
      datasets: [{ label:'차단', data: blocked.values, backgroundColor: '#ef4444' }]
    },
    options: baseOptions()
  });
  observers.push(makeResizeAware(blockedChart, blockedEl));

  // 유형 비율
  const ratio = toLabelsValues(data.type_ratio || {});
  if (ratioChart) ratioChart.destroy();
  const ratioEl = document.getElementById('chartRatio').parentElement;
  ratioChart = new Chart(document.getElementById('chartRatio'), {
    type: 'doughnut',
    data: {
      labels: ratio.labels,
      datasets: [{
        data: ratio.values,
        backgroundColor: ['#3b82f6','#22c55e','#eab308','#ef4444','#8b5cf6','#14b8a6']
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position:'right', labels:{ color:'#cfe0ff' } } }
    }
  });
  observers.push(makeResizeAware(ratioChart, ratioEl));

  // IP 대역 차단
  const ipb = toLabelsValues(data.ip_band_blocked || {});
  if (ipBandChart) ipBandChart.destroy();
  const ipEl = document.getElementById('chartIpBand').parentElement;
  ipBandChart = new Chart(document.getElementById('chartIpBand'), {
    type: 'bar',
    data: { labels: ipb.labels, datasets: [{ label:'차단', data: ipb.values, backgroundColor: '#22c55e' }] },
    options: baseOptions()
  });
  observers.push(makeResizeAware(ipBandChart, ipEl));
}

function renderLogs(data) {
  const tbody = document.querySelector('#logs tbody');
  tbody.innerHTML = '';
  (data.recent_logs || []).forEach(row => {
    const ents = (row.entities || []).map(e => e.label).join(', ');
    const tr = document.createElement('tr');
    const cols = [
      row.time || '', row.host || '', row.hostname || '', row.public_ip || '',
      row.action || '', (row.has_sensitive ? 'Y' : 'N'), (row.file_blocked ? 'Y' : 'N'),
      ents || '', row.prompt || ''
    ];
    cols.forEach((c, idx) => {
      const td = document.createElement('td');
      if (idx === 4) { // 액션
        const span = document.createElement('span');
        span.className = 'badge';
        span.textContent = c;
        td.appendChild(span);
      } else {
        td.textContent = c;
      }
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}

async function refresh() {
  try {
    const data = await fetchSummary();
    renderCharts(data);
    renderLogs(data);
  } catch (e) {
    console.error(e);
  }
}

refresh();
setInterval(refresh, 10000);
