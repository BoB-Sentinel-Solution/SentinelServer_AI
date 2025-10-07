// dashboard/app.js  (XSS 완화 + API Key 옵션 + 캐시 방지)

async function fetchSummary() {
  const headers = { 'Cache-Control': 'no-store' };

  // 대시보드 API 키를 사용하는 경우에만 헤더 추가
  //   - 서버의 config.py(.env)에서 DASHBOARD_API_KEY가 설정되어 있다면,
  //     아래 상수에 동일 값을 넣거나, Nginx Basic Auth 등 다른 보호 수단을 권장.
  const ADMIN_KEY = null; // 예: 'p4eHk9...'; 공개 노출 위험 있으니 필요 시 프록시 인증 사용 권장
  if (ADMIN_KEY) headers['X-Admin-Key'] = ADMIN_KEY;

  const res = await fetch('/dashboard/api/summary', { headers });
  if (!res.ok) throw new Error('failed to load summary');
  return await res.json();
}

function toLabelsValues(obj) {
  obj = obj || {};
  const labels = Object.keys(obj);
  const values = labels.map(k => obj[k]);
  return { labels, values };
}

let ratioChart, hourlyChart, blockedChart, ipBandChart;

function renderCharts(data) {
  // 총 건수 - 안전하게 텍스트만 삽입
  const totalEl = document.getElementById('total');
  totalEl.textContent = data.total_sensitive ?? 0;

  // 유형 비율
  const ratio = toLabelsValues(data.type_ratio);
  if (ratioChart) ratioChart.destroy();
  ratioChart = new Chart(document.getElementById('chartRatio'), {
    type: 'doughnut',
    data: { labels: ratio.labels, datasets: [{ data: ratio.values }] },
    options: { plugins: { legend: { position: 'right', labels: { color: '#eef1f6' } } } }
  });

  // 시간대별 입력 시도 (0~23)
  const hours = Array.from({ length: 24 }, (_, i) => i);
  if (hourlyChart) hourlyChart.destroy();
  hourlyChart = new Chart(document.getElementById('chartHourly'), {
    type: 'line',
    data: {
      labels: hours,
      datasets: [{ label: '시도 건수', data: data.hourly_attempts || [], tension: .2 }]
    },
    options: {
      scales: {
        x: { ticks: { color: '#cfe0ff' } },
        y: { ticks: { color: '#cfe0ff' } }
      },
      plugins: { legend: { labels: { color: '#eef1f6' } } }
    }
  });

  // 유형별 차단
  const blocked = toLabelsValues(data.type_blocked);
  if (blockedChart) blockedChart.destroy();
  blockedChart = new Chart(document.getElementById('chartBlocked'), {
    type: 'bar',
    data: { labels: blocked.labels, datasets: [{ label: '차단', data: blocked.values }] },
    options: {
      scales: {
        x: { ticks: { color: '#cfe0ff' } },
        y: { ticks: { color: '#cfe0ff' } }
      },
      plugins: { legend: { labels: { color: '#eef1f6' } } }
    }
  });

  // IP 대역 차단
  const ipb = toLabelsValues(data.ip_band_blocked);
  if (ipBandChart) ipBandChart.destroy();
  ipBandChart = new Chart(document.getElementById('chartIpBand'), {
    type: 'bar',
    data: { labels: ipb.labels, datasets: [{ label: '차단', data: ipb.values }] },
    options: {
      scales: {
        x: { ticks: { color: '#cfe0ff' } },
        y: { ticks: { color: '#cfe0ff' } }
      },
      plugins: { legend: { labels: { color: '#eef1f6' } } }
    }
  });
}

// ✅ XSS 차단: innerHTML 사용 금지. 셀은 createElement + textContent로만 생성.
function td(text) {
  const c = document.createElement('td');
  c.textContent = text ?? '';
  return c;
}

function renderLogs(data) {
  const tbody = document.querySelector('#logs tbody');
  // 기존 노드 제거(스크롤/메모리 누수 방지)
  tbody.textContent = '';

  (data.recent_logs || []).forEach(row => {
    const tr = document.createElement('tr');
    const ents = (row.entities || []).map(e => e.label).join(', ');

    tr.appendChild(td(row.time || ''));
    tr.appendChild(td(row.host || ''));
    tr.appendChild(td(row.hostname || ''));
    tr.appendChild(td(row.public_ip || ''));
    tr.appendChild(td(row.action || ''));
    tr.appendChild(td(row.has_sensitive ? 'Y' : 'N'));
    tr.appendChild(td(row.file_blocked ? 'Y' : 'N'));
    tr.appendChild(td(ents));
    tr.appendChild(td(row.prompt || ''));

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
setInterval(refresh, 10000); // 10초마다 갱신
