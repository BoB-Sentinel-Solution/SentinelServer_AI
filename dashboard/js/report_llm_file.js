// js/report_llm_file.js

let fileExtDonutChart = null;
let fileExtStackChart = null;

document.addEventListener("DOMContentLoaded", () => {
  initTopBarClock();
  hookRefreshButton();
  loadFileBasedReport();
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
    loadFileBasedReport();
  });
}

/**
 * 파일 기반 리포트 로딩
 * /api/report/llm/file-summary 호출
 */
async function loadFileBasedReport() {
  try {
    // api.js에 정의된 fetchLlmFileSummary() 사용
    const summary = await fetchLlmFileSummary();
    console.log("[report_llm_file] summary:", summary);

    renderFileDonut(summary?.donut);
    renderFileStack(summary?.stacked);
    renderFileTable(summary?.recent);
  } catch (err) {
    console.error("파일 기반 리포트 로딩 실패:", err);
    const errBox = document.getElementById("file-error-box");
    if (errBox) {
      errBox.textContent = "파일 리포트 데이터를 불러오는 중 오류가 발생했습니다.";
      errBox.style.display = "block";
    }
  }
}

/** 도넛: 파일 확장자별 탐지 건수 */
function renderFileDonut(donut) {
  const canvas = document.getElementById("chart-file-ext-donut");
  const emptyMsg = document.getElementById("file-donut-empty");
  if (!canvas) return;

  // 이전 차트 제거
  if (fileExtDonutChart) {
    fileExtDonutChart.destroy();
    fileExtDonutChart = null;
  }

  const labels = (donut?.labels || []).map((x) => String(x).toUpperCase());
  const values = donut?.data || [];

  if (!labels.length || !values.length) {
    canvas.style.display = "none";
    if (emptyMsg) emptyMsg.style.display = "block";
    return;
  }

  canvas.style.display = "block";
  if (emptyMsg) emptyMsg.style.display = "none";

  const total = values.reduce((a, b) => a + b, 0) || 1;

  const ctx = canvas.getContext("2d");
  fileExtDonutChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels,
      datasets: [
        {
          label: "탐지 건수",
          data: values,
          borderWidth: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: "right",
        },
        tooltip: {
          callbacks: {
            label: function (ctx) {
              const label = ctx.label || "";
              const value = ctx.parsed || 0;
              const pct = ((value / total) * 100).toFixed(1);
              return `${label}: ${value}건 (${pct}%)`;
            },
          },
        },
      },
      cutout: "55%",
    },
  });
}

/** 가로 스택바: 확장자 × 라벨 */
function renderFileStack(stacked) {
  const canvas = document.getElementById("chart-file-ext-labels");
  const emptyMsg = document.getElementById("file-stack-empty");
  if (!canvas) return;

  // 이전 차트 제거
  if (fileExtStackChart) {
    fileExtStackChart.destroy();
    fileExtStackChart = null;
  }

  const formats = stacked?.formats || [];
  const entityLabels = stacked?.labels || [];
  const matrix = stacked?.matrix || [];

  if (!formats.length || !entityLabels.length || !matrix.length) {
    canvas.style.display = "none";
    if (emptyMsg) emptyMsg.style.display = "block";
    return;
  }

  canvas.style.display = "block";
  if (emptyMsg) emptyMsg.style.display = "none";

  // datasets: 각 엔티티 라벨별로 한 줄
  const datasets = entityLabels.map((lab, labIdx) => {
    return {
      label: lab,
      data: formats.map((_, fmtIdx) => matrix[fmtIdx]?.[labIdx] || 0),
      stack: "file-labels",
    };
  });

  const ctx = canvas.getContext("2d");
  fileExtStackChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: formats.map((f) => String(f).toUpperCase()),
      datasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: "y", // 가로 막대
      scales: {
        x: {
          stacked: true,
          title: {
            display: true,
            text: "탐지 건수",
          },
        },
        y: {
          stacked: true,
        },
      },
      plugins: {
        legend: {
          position: "bottom",
        },
        tooltip: {
          callbacks: {
            label: function (ctx) {
              const lbl = ctx.dataset.label || "";
              const val = ctx.parsed.x || 0;
              return `${lbl}: ${val}건`;
            },
          },
        },
      },
    },
  });
}

/** 테이블: 최근 파일 첨부 로그 */
function renderFileTable(recent) {
  const tbody = document.getElementById("file-log-tbody");
  const emptyMsg = document.getElementById("file-table-empty");
  if (!tbody) return;

  tbody.innerHTML = "";

  const rows = Array.isArray(recent) ? recent : [];

  if (!rows.length) {
    if (emptyMsg) emptyMsg.style.display = "block";
    return;
  }
  if (emptyMsg) emptyMsg.style.display = "none";

  rows.forEach((row) => {
    const tr = document.createElement("tr");

    const time = formatTime(row.time || row.created_at);
    const host = row.host || "";
    const pcName = row.pc_name || row.hostname || "";
    const pubIp = row.public_ip || "";
    const privIp = row.private_ip || "";
    const fileExt = (row.file_ext || "").toUpperCase();
    const action = row.action || "";
    const sensitive = row.has_sensitive ? "Y" : "N";
    const fileBlocked = row.file_blocked ? "Y" : "N";

    tr.appendChild(td(time));
    tr.appendChild(td(host));
    tr.appendChild(td(pcName));
    tr.appendChild(td(pubIp));
    tr.appendChild(td(privIp));
    tr.appendChild(td(fileExt, "center"));
    tr.appendChild(td(action));
    tr.appendChild(td(sensitive, "center"));
    tr.appendChild(td(fileBlocked, "center"));

    // Download 컬럼 (추후 구현용 더미 버튼)
    const tdDownload = document.createElement("td");
    tdDownload.className = "text-center";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn btn-icon btn-ghost";
    btn.title = "파일 다운로드 기능은 추후 제공 예정입니다.";
    btn.textContent = "⬇";
    btn.disabled = true;
    tdDownload.appendChild(btn);
    tr.appendChild(tdDownload);

    tbody.appendChild(tr);
  });
}

function td(text, align) {
  const el = document.createElement("td");
  el.textContent = text == null ? "" : String(text);
  if (align === "center") el.style.textAlign = "center";
  return el;
}

function formatTime(iso) {
  if (!iso) return "";
  try {
    // "2025-11-14T09:30:12.345678" -> "2025-11-14 09:30:12"
    return iso.replace("T", " ").slice(0, 19);
  } catch {
    return iso;
  }
}
