// js/network.js

let chartPublicBands = null;

document.addEventListener("DOMContentLoaded", () => {
  initTopBarClock();
  hookRefreshButton();
  loadNetworkSummary();
});

/** 상단 UPDATED 시계 */
function initTopBarClock() {
  const el = document.getElementById("top-updated-at");
  if (!el) return;

  function tick() {
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, "0");
    const mm = String(now.getMinutes()).padStart(2, "0");
    const ss = String(now.getSeconds()).padStart(2, "0");
    el.textContent = `${hh}:${mm}:${ss} KST`;
  }

  tick();
  setInterval(tick, 1000);
}

/** Refresh 버튼 */
function hookRefreshButton() {
  const btn = document.getElementById("btn-refresh");
  if (!btn) return;
  btn.addEventListener("click", () => {
    loadNetworkSummary();
  });
}

/** 공통: 안전한 텍스트 셀 추가 */
function appendCell(tr, text) {
  const td = document.createElement("td");
  td.textContent = text == null || text === "" ? "-" : String(text);
  tr.appendChild(td);
  return td;
}

/** /api/network/summary 호출 */
async function loadNetworkSummary() {
  try {
    const data = await SentinelApi.get("/network/summary");

    renderPublicBandSummary(data);
    renderTopPrivateBands(data.top_private_bands || []);
    renderSuspiciousPcList(data.suspicious_pcs || []);
    renderSuspiciousLogs(data.suspicious_logs || []);
  } catch (err) {
    console.error(err);
    alert("네트워크 리포트 데이터를 불러오는 중 오류가 발생했습니다.");
  }
}

/** PUBLIC 대역 개수 + 파이차트 */
function renderPublicBandSummary(data) {
  const totalEl = document.getElementById("public-band-count");
  if (totalEl) {
    totalEl.textContent =
      data.public_band_count != null ? String(data.public_band_count) : "0";
  }

  const canvas = document.getElementById("chart-public-bands");
  const emptyMsg = document.getElementById("public-bands-empty");
  if (!canvas || !window.Chart) return;

  const usage = data.public_band_usage || {};
  const bands = Object.keys(usage);

  if (chartPublicBands) {
    chartPublicBands.destroy();
    chartPublicBands = null;
  }

  if (!bands.length) {
    canvas.style.display = "none";
    if (emptyMsg) emptyMsg.style.display = "block";
    return;
  } else {
    canvas.style.display = "block";
    if (emptyMsg) emptyMsg.style.display = "none";
  }

  const counts = bands.map((b) => usage[b] || 0);

  chartPublicBands = new Chart(canvas.getContext("2d"), {
    type: "pie",
    data: {
      labels: bands,
      datasets: [
        {
          data: counts,
        },
      ],
    },
    options: {
      plugins: {
        legend: {
          position: "bottom",
        },
      },
    },
  });
}

/** 대역폭 별 연결 사설망 (상위 3개 카드) */
function renderTopPrivateBands(items) {
  const wrap = document.getElementById("top-private-bands");
  if (!wrap) return;

  wrap.innerHTML = "";

  if (!items.length) {
    const p = document.createElement("p");
    p.className = "empty-hint";
    p.textContent = "공인 IP 대역 사용 기록이 없습니다.";
    wrap.appendChild(p);
    return;
  }

  items.forEach((item) => {
    const card = document.createElement("div");
    card.className = "band-card";

    const header = document.createElement("div");
    header.className = "band-card-header";
    header.textContent = item.public_band || "UNKNOWN";

    const body = document.createElement("div");
    body.className = "band-card-body";

    const privBands =
      Array.isArray(item.private_bands) && item.private_bands.length
        ? item.private_bands.join(", ")
        : "-";

    body.innerHTML = `
      <div class="band-card-line">
        <span class="label">연결 사설망 대역:</span>
        <span class="value">${privBands}</span>
      </div>
      <div class="band-card-line">
        <span class="label">연결 에이전트 PC 수:</span>
        <span class="value">${item.pc_count ?? 0}대</span>
      </div>
      <div class="band-card-line">
        <span class="label">총 로그 수:</span>
        <span class="value">${item.total_logs ?? 0}건</span>
      </div>
      <div class="band-card-line">
        <span class="label">중요정보 탐지 로그:</span>
        <span class="value">${item.sensitive_count ?? 0}건</span>
      </div>
    `;

    card.appendChild(header);
    card.appendChild(body);
    wrap.appendChild(card);
  });
}

/** 외부 IP 사용 의심 PC 정보 (카드 안 bullet list) */
function renderSuspiciousPcList(items) {
  const ul = document.getElementById("suspicious-pc-list");
  if (!ul) return;

  ul.innerHTML = "";

  if (!items.length) {
    const li = document.createElement("li");
    li.textContent = "현재 외부 IP 사용 의심 PC는 없습니다.";
    ul.appendChild(li);
    return;
  }

  items.forEach((pc) => {
    const li = document.createElement("li");
    const reasonLabel =
      pc.reason === "direct_exposure" ? "직접 노출" : "신규 출구";
    li.textContent = `${pc.public_ip} / ${pc.private_ip} / ${pc.pc_name} (${reasonLabel})`;
    ul.appendChild(li);
  });
}

/** 외부 IP 사용 의심 PC 로그 테이블 */
function renderSuspiciousLogs(rows) {
  const tbody = document.getElementById("network-table-body");
  if (!tbody) return;

  tbody.innerHTML = "";

  if (!rows.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 11;
    td.textContent = "외부 IP 사용 의심 PC 로그가 없습니다.";
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  rows.forEach((r) => {
    const tr = document.createElement("tr");

    appendCell(tr, r.prompt);
    appendCell(tr, r.time);
    appendCell(tr, r.host);
    appendCell(tr, r.pc_name);
    appendCell(tr, r.public_ip);
    appendCell(tr, r.private_ip);
    appendCell(tr, r.interface);
    appendCell(tr, r.action);

    // Sensitivity: has_sensitive → Y/N
    appendCell(tr, r.has_sensitive ? "Y" : "N");
    // Block files: file_blocked → Y/N
    appendCell(tr, r.file_blocked ? "Y" : "N");

    // Entity: 첫 번째 라벨만 간단 표시
    let entityLabel = "-";
    if (Array.isArray(r.entities) && r.entities.length) {
      const e0 = r.entities[0];
      entityLabel = e0.label || e0.type || "-";
    }
    appendCell(tr, entityLabel);

    tbody.appendChild(tr);
  });
}
