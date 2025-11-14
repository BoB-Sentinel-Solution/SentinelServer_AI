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

/** /api/summary?interface=LLM 호출해서 FILE BASED 통계 로딩 */
async function loadFileBasedReport() {
  try {
    const data = await fetchSummary({ interface: "LLM" });
    renderFileDonut(data);
    renderFileStack(data);
    renderFileTable(data);
  } catch (err) {
    console.error("파일 기반 리포트 로딩 실패:", err);
  }
}

/** 도넛: 파일 확장자별 탐지 건수 (file_detect_by_ext) */
function renderFileDonut(data) {
  const canvas = document.getElementById("chart-file-ext-donut");
  const emptyMsg = document.getElementById("file-donut-empty");
  if (!canvas) return;

  const stat = (data && data.file_detect_by_ext) || {};
  const exts = Object.keys(stat).sort();
  const values = exts.map((ext) => stat[ext] || 0);

  if (fileExtDonutChart) {
    fileExtDonutChart.destroy();
    fileExtDonutChart = null;
  }

  if (!exts.length) {
    canvas.style.display = "none";
    if (emptyMsg) emptyMsg.style.display = "block";
    return;
  }

  canvas.style.display = "block";
  if (emptyMsg) emptyMsg.style.display = "none";

  const ctx = canvas.getContext("2d");
  fileExtDonutChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: exts.map((e) => e.toUpperCase()),
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
              return `${label}: ${value}건`;
            },
          },
        },
      },
      cutout: "55%",
    },
  });
}

/** 가로 스택바: 확장자 × 라벨 (file_label_by_ext) */
function renderFileStack(data) {
  const canvas = document.getElementById("chart-file-ext-labels");
  const emptyMsg = document.getElementById("file-stack-empty");
  if (!canvas) return;

  const stat = (data && data.file_label_by_ext) || {};
  const exts = Object.keys(stat).sort();

  // 전체 라벨 목록 수집
  const labelSet = new Set();
  exts.forEach((ext) => {
    const byLabel = stat[ext] || {};
    Object.keys(byLabel).forEach((lbl) => labelSet.add(lbl));
  });
  const labels = Array.from(labelSet).sort();

  if (fileExtStackChart) {
    fileExtStackChart.destroy();
    fileExtStackChart = null;
  }

  if (!exts.length || !labels.length) {
    canvas.style.display = "none";
    if (emptyMsg) emptyMsg.style.display = "block";
    return;
  }

  canvas.style.display = "block";
  if (emptyMsg) emptyMsg.style.display = "none";

  const datasets = labels.map((lbl) => {
    return {
      label: lbl,
      data: exts.map((ext) => {
        const byLabel = stat[ext] || {};
        return byLabel[lbl] || 0;
      }),
      stack: "file-labels",
    };
  });

  const ctx = canvas.getContext("2d");
  fileExtStackChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: exts.map((e) => e.toUpperCase()),
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

/** 테이블: recent_file_logs */
function renderFileTable(data) {
  const tbody = document.getElementById("file-log-tbody");
  const emptyMsg = document.getElementById("file-table-empty");
  if (!tbody) return;

  tbody.innerHTML = "";

  const logs = (data && data.recent_file_logs) || [];

  if (!logs.length) {
    if (emptyMsg) emptyMsg.style.display = "block";
    return;
  }
  if (emptyMsg) emptyMsg.style.display = "none";

  logs.forEach((row) => {
    const tr = document.createElement("tr");

    const time = formatTime(row.time);
    const host = row.host || "";
    const pcName = row.hostname || "";
    const pubIp = row.public_ip || "";
    const privIp = row.private_ip || "";
    const action = row.action || "";
    const sensitive = row.has_sensitive ? "Y" : "N";
    const fileBlocked = row.file_blocked || row.blocked ? "Y" : "N";

    tr.appendChild(td(time));
    tr.appendChild(td(host));
    tr.appendChild(td(pcName));
    tr.appendChild(td(pubIp));
    tr.appendChild(td(privIp));
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
