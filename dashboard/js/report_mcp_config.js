// js/report_mcp_config.js

let chartTypeDist = null;

document.addEventListener("DOMContentLoaded", () => {
  initTopBarClock();
  hookRefreshButton();
  loadMcpConfigSummary();
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
    loadMcpConfigSummary();
  });
}

/** 공통: 안전한 셀 추가 */
function appendCell(tr, text) {
  const td = document.createElement("td");
  td.textContent = text == null || text === "" ? "-" : String(text);
  tr.appendChild(td);
  return td;
}

/** MCP CONFIG 요약 로딩 */
async function loadMcpConfigSummary() {
  try {
    const summary = await SentinelApi.get("/mcp/config_summary");

    if (!summary) return;

    renderActiveCount(summary);
    renderTimeline(summary.timeline || []);
    renderTypeDistribution(summary.type_distribution || {});
    renderPrediction(summary.prediction || {});

  } catch (err) {
    console.error(err);
    alert("MCP CONFIG 데이터를 불러오는 중 오류가 발생했습니다.");
  }
}

/** 활성 MCP 개수 / 순위 */
function renderActiveCount(summary) {
  const totalEl = document.getElementById("mcp-active-total");
  if (totalEl) {
    totalEl.textContent =
      summary.active_total != null ? String(summary.active_total) : "0";
  }

  const listEl = document.getElementById("mcp-active-rank-list");
  if (!listEl) return;

  listEl.innerHTML = "";

  const rank = Array.isArray(summary.active_rank)
    ? summary.active_rank
    : [];

  if (!rank.length) {
    const li = document.createElement("li");
    li.textContent = "활성화된 MCP 설정이 없습니다.";
    listEl.appendChild(li);
    return;
  }

  rank.slice(0, 5).forEach((item, idx) => {
    const li = document.createElement("li");

    const idxSpan = document.createElement("span");
    idxSpan.textContent = `${idx + 1}.`;

    const nameSpan = document.createElement("span");
    nameSpan.className = "mcp-rank-name";
    nameSpan.textContent = item.mcp_name || "UNKNOWN";

    const countSpan = document.createElement("span");
    countSpan.className = "mcp-rank-count";
    countSpan.textContent = String(item.count || 0);

    li.appendChild(idxSpan);
    li.appendChild(nameSpan);
    li.appendChild(countSpan);

    listEl.appendChild(li);
  });
}

/** 타임라인 렌더링 */
function renderTimeline(timeline) {
  const tbody = document.getElementById("mcp-timeline-body");
  if (!tbody) return;

  tbody.innerHTML = "";

  if (!timeline.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 7;
    td.textContent = "최근 MCP 설정 변경 이력이 없습니다.";
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  timeline.forEach((row) => {
    const tr = document.createElement("tr");
    appendCell(tr, row.time);
    appendCell(tr, row.event);
    appendCell(tr, row.pc_name);
    appendCell(tr, row.private_ip);
    appendCell(tr, row.host);
    appendCell(tr, row.mcp);
    appendCell(tr, row.type);
    tbody.appendChild(tr);
  });
}

/** 타입 분포 (Local / Remote / 기타) 파이 차트 */
function renderTypeDistribution(dist) {
  const canvas = document.getElementById("chart-mcp-type-distribution");
  const emptyMsg = document.getElementById("mcp-type-empty");
  if (!canvas || !window.Chart) return;

  const local = dist.local || 0;
  const remote = dist.external || 0;
  const other = dist.other || 0;
  const total = local + remote + other;

  if (chartTypeDist) {
    chartTypeDist.destroy();
    chartTypeDist = null;
  }

  if (!total) {
    canvas.style.display = "none";
    if (emptyMsg) emptyMsg.style.display = "block";
    return;
  } else {
    canvas.style.display = "block";
    if (emptyMsg) emptyMsg.style.display = "none";
  }

  chartTypeDist = new Chart(canvas.getContext("2d"), {
    type: "pie",
    data: {
      labels: ["Local", "Remote", "기타"],
      datasets: [
        {
          data: [local, remote, other],
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

/** Prediction 카드 내용 업데이트 */
function renderPrediction(pred) {
  const statusEl = document.getElementById("mcp-pred-status");
  const titleEl = document.getElementById("mcp-pred-title");
  const bodyEl = document.getElementById("mcp-pred-body");

  const hasSuspicious = !!pred.has_suspicious;

  if (statusEl) {
    statusEl.textContent = hasSuspicious ? "주의 필요" : "정상";
  }
  if (titleEl) {
    titleEl.textContent =
      pred.headline ||
      (hasSuspicious
        ? "MCP 설정에서 잠재적인 위험이 감지되었습니다."
        : "현재 MCP 설정에서 특이사항은 없습니다.");
  }
  if (bodyEl) {
    bodyEl.textContent =
      pred.detail ||
      (hasSuspicious
        ? "일부 MCP 서버의 URL 또는 설정 값이 정규표현식 기반 검사에서 위험 징후로 분류되었습니다."
        : "정규표현식 기준으로는 https URL에 직접 IP가 사용된 사례 등이 확인되지 않았습니다.");
  }
}
