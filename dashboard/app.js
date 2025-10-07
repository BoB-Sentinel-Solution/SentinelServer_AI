async function fetchSummary() {
  const res = await fetch('/dashboard/api/summary');
  if (!res.ok) throw new Error('failed to load summary');
  return await res.json();
}

function toLabelsValues(obj) {
  const labels = Object.keys(obj);
  const values = labels.map(k => obj[k]);
  return { labels, values };
}

let ratioChart, hourlyChart, blockedChart, ipBandChart;

function renderCharts(data) {
  // 총 건수
  document.getElementById('total').textContent = data.total_sensitive ?? 0;

  // 유형 비율
  const ratio = toLabelsValues(data.type_ratio || {});
  if (ratioChart) ratioChart.destroy();
  ratioChart = new Chart(document.getElementById('chartRatio'), {
    type: 'doughnut',
    data: {
      labels: ratio.labels,
      datasets: [{ data: ratio.values }]
    },
    options: { plugins: { legend: { position: 'right', labels: { color: '#eef1f6' } } } }
  });

  // 시간대별 입력 시도 (0~23)
  const hours = Array.from({length:24}, (_,i)=>i);
  if (hourlyChart) hourlyChart.destroy();
  hourlyChart = new Chart(document.getElementById('chartHourly'), {
    type: 'line',
    data: {
      labels: hours,
      datasets: [{ label:'시도 건수', data: data.hourly_attempts || [], tension: .2 }]
    },
    options: {
      scales: {
        x: { ticks: { color:'#cfe0ff' } },
        y: { ticks: { color:'#cfe0ff' } }
      },
      plugins: { legend: { labels:{ color:'#eef1f6' } } }
    }
  });

  // 유형별 차단
  const blocked = toLabelsValues(data.type_blocked || {});
  if (blockedChart) blockedChart.destroy();
  blockedChart = new Chart(document.getElementById('chartBlocked'), {
    type: 'bar',
    data: { labels: blocked.labels, datasets: [{ label:'차단', data: blocked.values }] },
    options: {
      scales: {
        x: { ticks: { color:'#cfe0ff' } },
        y: { ticks: { color:'#cfe0ff' } }
      },
      plugins: { legend: { labels:{ color:'#eef1f6' } } }
    }
  });

  // IP 대역 차단
  const ipb = toLabelsValues(data.ip_band_blocked || {});
  if (ipBandChart) ipBandChart.destroy();
  ipBandChart = new Chart(document.getElementById('chartIpBand'), {
    type: 'bar',
    data: { labels: ipb.labels, datasets: [{ label:'차단', data: ipb.values }] },
    options: {
      scales: {
        x: { ticks: { color:'#cfe0ff' } },
        y: { ticks: { color:'#cfe0ff' } }
      },
      plugins: { legend: { labels:{ color:'#eef1f6' } } }
    }
  });
}

function renderLogs(data) {
  const tbody = document.querySelector('#logs tbody');
  tbody.innerHTML = '';
  (data.recent_logs || []).forEach(row => {
    const tr = document.createElement('tr');
    const ents = (row.entities || []).map(e => e.label).join(', ');
    tr.innerHTML = `
      <td class="muted">${row.time || ''}</td>
      <td>${row.host || ''}</td>
      <td>${row.hostname || ''}</td>
      <td>${row.public_ip || ''}</td>
      <td><span class="badge">${row.action || ''}</span></td>
      <td>${row.has_sensitive ? 'Y' : 'N'}</td>
      <td>${row.file_blocked ? 'Y' : 'N'}</td>
      <td>${ents}</td>
      <td class="muted">${row.prompt || ''}</td>
    `;
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
setInterval(refresh, 10000); // 10초마다 새로고침
