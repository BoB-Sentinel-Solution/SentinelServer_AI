// js/reason.js

let reasonTop5Chart = null;
let selectedPc = null; // { pc_name, host, public_ip, private_ip }

document.addEventListener("DOMContentLoaded", () => {
  initTopBarClock();
  hookRefreshButton();
  hookAnalyzeButton();
  loadReasonTop5();
});

/** 상단 UPDATED 시계 (다른 페이지와 동일 패턴) */
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

function hookRefreshButton() {
  const btn = document.getElementById("btn-refresh");
  if (!btn) return;
  btn.addEventListener("click", () => {
    loadReasonTop5();
    if (selectedPc) {
      analyzeSelectedPc(); // 선택 PC가 있을 때만 재분석
    }
  });
}

function hookAnalyzeButton() {
  const btn = document.getElementById("btn-reason-analyze");
  if (!btn) return;
  btn.addEventListener("click", () => {
    analyzeSelectedPc();
  });
}

/** Reason TOP5 로딩 */
async function loadReasonTop5() {
  try {
    const data = await SentinelApi.fetchReasonTop5();
    const items = Array.isArray(data?.items) ? data.items : [];
    renderReasonTop5(items);
  } catch (err) {
    console.error("reason top5 load error:", err);
    const tbody = document.getElementById("reason-top5-body");
    if (tbody) {
      tbody.innerHTML =
        '<tr><td colspan="5">Reason Top5 데이터를 불러오는 중 오류가 발생했습니다.</td></tr>';
    }
  }
}

function renderReasonTop5(items) {
  const tbody = document.getElementById("reason-top5-body");
  const canvas = document.getElementById("chart-reason-top5");
  if (!tbody || !canvas) return;

  // 테이블 렌더링
  tbody.innerHTML = "";
  if (!items.length) {
    tbody.innerHTML =
      '<tr><td colspan="5">중요정보가 탐지된 PC가 아직 없습니다.</td></tr>';
  } else {
    items.forEach((row, idx) => {
      const tr = document.createElement("tr");
      tr.dataset.idx = String(idx);

      tr.addEventListener("click", () => {
        setSelectedPc(row, tr);
      });

      appendCell(tr, row.pc_name || "");
      appendCell(tr, row.host || "");
      appendCell(tr, row.public_ip || "");
      appendCell(tr, row.private_ip || "");
      appendCell(tr, row.count != null ? row.count : "");

      tbody.appendChild(tr);
    });
  }

  // 차트 렌더링
  if (reasonTop5Chart) {
    reasonTop5Chart.destroy();
    reasonTop5Chart = null;
  }

  if (!items.length) return;

  const labels = items.map((r) => r.pc_name || "UNKNOWN");
  const values = items.map((r) => r.count || 0);

  const ctx = canvas.getContext("2d");
  reasonTop5Chart = new Chart(ctx, {
    type: "bar",
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
      scales: {
        x: {
          ticks: {
            font: { size: 11 },
          },
        },
        y: {
          beginAtZero: true,
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: function (ctx) {
              const val = ctx.parsed.y || 0;
              return `탐지 ${val}건`;
            },
          },
        },
      },
    },
  });
}

function appendCell(tr, text) {
  const td = document.createElement("td");
  td.textContent = text == null ? "" : String(text);
  tr.appendChild(td);
  return td;
}

function setSelectedPc(row, trElement) {
  selectedPc = {
    pc_name: row.pc_name,
    host: row.host,
    public_ip: row.public_ip,
    private_ip: row.private_ip,
  };

  // 테이블 하이라이트
  const tbody = trElement.parentElement;
  if (tbody) {
    Array.from(tbody.children).forEach((tr) => {
      tr.classList.remove("top5-row--selected");
    });
    trElement.classList.add("top5-row--selected");
  }

  const label = document.getElementById("reason-selected-pc");
  if (label) {
    label.textContent = `${row.pc_name || "-"} / ${row.host || ""}`;
  }
}

/** 선택된 PC에 대해 분석 API 호출 */
async function analyzeSelectedPc() {
  if (!selectedPc || !selectedPc.pc_name) {
    alert("먼저 탐지 건수 TOP 5에서 PC를 선택해줘.");
    return;
  }

  try {
    const summary = await SentinelApi.fetchReasonSummary({
      pc_name: selectedPc.pc_name,
      host: selectedPc.host,
      // interface: "llm"  // 필요하면 추가
    });

    renderReasonSummary(summary);
  } catch (err) {
    console.error("reason summary error:", err);
    alert("Reason 분석 데이터를 불러오는 중 오류가 발생했어.");
  }
}

/** 분석 결과 렌더링 */
function renderReasonSummary(summary) {
  if (!summary) return;

  const sect = document.getElementById("reason-analysis-section");
  if (sect) {
    sect.style.display = "flex";
  }

  const intents = summary.intent_counts || {};
  setText("reason-intent-intentional", intents.intentional || 0);
  setText("reason-intent-negligent", intents.negligent || 0);
  setText("reason-intent-unknown", intents.unknown || 0);

  // 프롬프트 카드들
  const cardsWrap = document.getElementById("reason-prompt-cards");
  if (cardsWrap) {
    cardsWrap.innerHTML = "";
    const cards = Array.isArray(summary.cards) ? summary.cards : [];
    if (!cards.length) {
      const p = document.createElement("p");
      p.className = "small-note";
      p.textContent = "선택된 PC에서 분석 가능한 중요정보 탐지 로그가 없습니다.";
      cardsWrap.appendChild(p);
    } else {
      cards.forEach((c) => {
        cardsWrap.appendChild(buildPromptCard(c));
      });
    }
  }

  // 하단 테이블
  const tbody = document.getElementById("reason-log-tbody");
  if (tbody) {
    tbody.innerHTML = "";
    const rows = Array.isArray(summary.logs) ? summary.logs : [];
    if (!rows.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 9;
      td.textContent =
        "선택된 PC에서 분석 가능한 중요정보 탐지 로그가 없습니다.";
      tr.appendChild(td);
      tbody.appendChild(tr);
    } else {
      rows.forEach((r) => {
        const tr = document.createElement("tr");
        appendCell(tr, formatTime(r.time));
        appendCell(tr, r.host || "");
        appendCell(tr, r.pc_name || "");
        appendCell(tr, r.public_ip || "");
        appendCell(tr, r.private_ip || "");
        appendCell(tr, r.action || "");
        appendCell(tr, r.risk_category || "");
        appendCell(
          tr,
          r.reason_type === "intentional"
            ? "고의 의심"
            : r.reason_type === "negligent"
            ? "부주의"
            : "-"
        );
        appendCell(tr, r.reason || "");
        tbody.appendChild(tr);
      });
    }
  }
}

function buildPromptCard(c) {
  const div = document.createElement("div");
  div.className = "prompt-card";

  const meta = document.createElement("div");
  meta.className = "prompt-meta";
  meta.textContent = `${formatTime(c.time)} · ${c.host || ""} · ${
    c.pc_name || ""
  }`;
  div.appendChild(meta);

  const promptBox = document.createElement("div");
  promptBox.className = "prompt-text";
  promptBox.textContent = c.prompt || "";
  div.appendChild(promptBox);

  const riskTitle = document.createElement("div");
  riskTitle.className = "prompt-risk-title";
  riskTitle.textContent = `[${c.risk_category || "위험"}] ${
    c.risk_pattern || ""
  }`;
  div.appendChild(riskTitle);

  const riskDesc = document.createElement("div");
  riskDesc.className = "prompt-risk-desc";
  riskDesc.textContent = c.risk_description || "";
  div.appendChild(riskDesc);

  const reasonDiv = document.createElement("div");
  reasonDiv.className = "prompt-reason";
  const intentLabel =
    c.intent_type === "intentional"
      ? "고의적 유출 의심"
      : c.intent_type === "negligent"
      ? "사용자 부주의"
      : "판별 불가";
  reasonDiv.textContent = `AI 판단: ${intentLabel} · ${c.reason || ""}`;
  div.appendChild(reasonDiv);

  return div;
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function formatTime(iso) {
  if (!iso) return "";
  try {
    return iso.replace("T", " ").slice(0, 19);
  } catch {
    return iso;
  }
}
