// js/reason.js

// ===== 라벨 그룹 정의 (유형별 차트 계산용) =====
const LABEL_GROUPS = {
  "기본 신원 정보": ["NAME", "RESIDENT_ID", "FOREIGNER_ID", "ADDRESS", "POSTAL_CODE"],
  "공적 식별 번호": [
    "PERSONAL_CUSTOMS_ID",
    "DRIVER_LICENSE",
    "PASSPORT",
    "HEALTH_INSURANCE_ID",
    "BUSINESS_ID",
    "MILITARY_ID",
  ],
  "인증 정보": ["EMAIL", "PHONE", "JWT", "API_KEY", "GITHUB_PAT", "PRIVATE_KEY", "CARD_CVV"],
  "금융 정보": ["CARD_NUMBER", "CARD_EXPIRY", "BANK_ACCOUNT", "PAYMENT_PIN", "MOBILE_PAYMENT_PIN"],
  "가상화폐 정보": ["MNEMONIC", "CRYPTO_PRIVATE_KEY", "HD_WALLET", "PAYMENT_URI_QR"],
  "네트워크 정보": ["IPV4", "IPV6", "MAC_ADDRESS", "IMEI"],
};

const GROUP_ORDER = [
  "기본 신원 정보",
  "공적 식별 번호",
  "인증 정보",
  "금융 정보",
  "가상화폐 정보",
  "네트워크 정보",
];

// ===== 프롬프트 위험 콤보 매핑 (캐러셀 설명용) =====
const COMBO_RULES = [
  // 1. 신원 정보 유출
  {
    category: "신원 정보 유출",
    labels: ["NAME", "PHONE", "ADDRESS"],
    title: "신원 정보 유출 가능성",
    desc: "개인을 특정하고 직접 연락 및 방문하여 피싱 가능",
  },
  {
    category: "신원 정보 유출",
    labels: ["NAME", "EMAIL", "ADDRESS", "POSTAL_CODE"],
    title: "신원 정보 유출 가능성",
    desc: "온라인·오프라인 모두에서 특정인을 정밀하게 타겟팅 가능",
  },
  // 2. 신원 도용 · 본인인증 우회 계열
  {
    category: "신원 도용 · 본인인증 우회",
    labels: ["PASSPORT", "NAME", "ADDRESS"],
    title: "신원 도용 · 본인인증 우회 위험",
    desc: "여권 정보와 거주지가 결합되어 해외 출입·신분 사칭에 악용 가능",
  },
  {
    category: "신원 도용 · 본인인증 우회",
    labels: ["DRIVER_LICENSE", "NAME", "PHONE"],
    title: "신원 도용 · 본인인증 우회 위험",
    desc: "실명·연락처·공적 신분증 번호가 묶여 각종 본인인증 우회에 사용될 수 있음",
  },
  {
    category: "신원 도용 · 본인인증 우회",
    labels: ["BUSINESS_ID", "NAME", "PHONE"],
    title: "사업자 신원 도용 위험",
    desc: "특정 사업자를 정확히 식별해 피싱·사기성 비즈니스 메일 타겟팅에 악용 가능",
  },
  {
    category: "신원 도용 · 본인인증 우회",
    labels: ["RESIDENT_ID", "NAME", "PHONE"],
    title: "신원 도용 · 본인인증 우회 위험",
    desc: "실명 확인 체계와 직접적인 연관성이 있어 사칭·본인인증 우회·금융사기 등 다수의 고위험 공격이 가능",
  },
  // 3. 금융 · 결제 탈취 계열
  {
    category: "금융 · 결제 탈취",
    labels: ["CARD_NUMBER", "CARD_EXPIRY", "CARD_CVV"],
    title: "금융 · 결제 탈취 위험",
    desc: "온라인 결제에 필요한 모든 요소가 조합되어 카드 실물 없이 결제가 바로 가능",
  },
  {
    category: "금융 · 결제 탈취",
    labels: ["CARD_NUMBER", "CARD_CVV", "PAYMENT_PIN"],
    title: "금융 · 결제 탈취 위험",
    desc: "카드 정보와 인증 수단이 동시에 노출되어 고액 결제·인출에 직접 사용 가능",
  },
  {
    category: "금융 · 결제 탈취",
    labels: ["MNEMONIC", "PAYMENT_URI_QR"],
    title: "가상자산 탈취 위험",
    desc: "지갑 복구용 시드와 송금 대상 정보가 동시에 노출되어 가상자산 전체 탈취 가능",
  },
  {
    category: "금융 · 결제 탈취",
    labels: ["CRYPTO_PRIVATE_KEY", "PAYMENT_URI_QR"],
    title: "가상자산 탈취 위험",
    desc: "특정 지갑 주소와 대응하는 프라이빗키가 함께 노출되어 잔액을 즉시 이체할 수 있음",
  },
  {
    category: "금융 · 결제 탈취",
    labels: ["HD_WALLET", "MNEMONIC"],
    title: "가상자산 탈취 위험",
    desc: "다수 지갑을 생성하는 상위 키와 시드가 동시에 유출되어 서브 주소를 장악 가능",
  },
  // 4. 위치·접근 위협 계열
  {
    category: "위치·접근 위협",
    labels: ["NAME", "ADDRESS", "POSTAL_CODE"],
    title: "위치·접근 위협",
    desc: "특정 개인의 실제 거주 위치를 매우 정밀하게 식별 가능",
  },
  {
    category: "위치·접근 위협",
    labels: ["PHONE", "ADDRESS", "POSTAL_CODE"],
    title: "위치·접근 위협",
    desc: "이름이 없어도 실제 거주지 기반 스토킹·피싱·방문 위협이 가능",
  },
  // 5. 복합 정보 결합 위협 (5개 이상)
  {
    category: "복합 정보 결합 위협",
    labels: [], // 5개 이상인 경우 별도 처리
    title: "복합 정보 결합 위협",
    desc: "중요정보 5개 이상이 동시에 조합되어 다각도로 악용될 수 있는 고위험 프롬프트",
  },
];

// ===== 전역 상태 =====
let reasonTop5Chart = null;
let reasonTypeChart = null;
let selectedPc = null; // { pc_name, host, public_ip, private_ip }

let carouselItems = []; // 위험 콤보가 탐지된 프롬프트 목록
let carouselIndex = 0;

let isAnalyzing = false;

// ===== 초기화 =====
document.addEventListener("DOMContentLoaded", () => {
  initTopBarClock();
  hookRefreshButton();
  hookAnalyzeButton();
  hookCarouselButtons();
  loadReasonTop5();
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

function hookCarouselButtons() {
  const prev = document.getElementById("reason-carousel-prev");
  const next = document.getElementById("reason-carousel-next");

  if (prev) {
    prev.addEventListener("click", () => {
      if (carouselItems.length === 0) return;
      if (carouselIndex > 0) {
        carouselIndex--;
        renderCarousel();
      }
    });
  }

  if (next) {
    next.addEventListener("click", () => {
      if (carouselItems.length === 0) return;
      if (carouselIndex < carouselItems.length - 1) {
        carouselIndex++;
        renderCarousel();
      }
    });
  }
}

// ===================== TOP5 섹션 =====================

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

// ===================== 분석 API 호출 =====================

/** 선택된 PC에 대해 분석 API 호출 */
async function analyzeSelectedPc() {
  if (!selectedPc || !selectedPc.pc_name) {
    alert("먼저 탐지 건수 TOP 5에서 PC를 선택해주세요.");
    return;
  }

  // 이미 분석 중이면 추가 호출 막기
  if (isAnalyzing) return;
  isAnalyzing = true;

  const btn = document.getElementById("btn-reason-analyze");
  const statusEl = document.getElementById("reason-status");

  // 버튼 잠그고 텍스트/로딩 상태 표시
  if (btn) {
    btn.disabled = true;
    btn.classList.add("is-loading");

    if (!btn.dataset.originalText) {
      btn.dataset.originalText = btn.textContent || "분석하기";
    }
    btn.textContent = "분석 중…";
  }

  if (statusEl) {
    statusEl.textContent = "분석 중입니다. 잠시만 기다려 주세요…";
  }

  try {
    const summary = await SentinelApi.fetchReasonSummary({
      pc_name: selectedPc.pc_name,
      host: selectedPc.host,
      // interface: "LLM"  // 필요하면 추가
    });

    renderReasonSummary(summary);
  } catch (err) {
    console.error("reason summary error:", err);
    alert("Reason 분석 데이터를 불러오는 중 오류가 발생했습니다.");
  } finally {
    // 상태 복원
    isAnalyzing = false;

    if (btn) {
      btn.disabled = false;
      btn.classList.remove("is-loading");
      btn.textContent = btn.dataset.originalText || "분석하기";
    }

    if (statusEl) {
      statusEl.textContent = "";
    }
  }
}

// ===================== 분석 결과 렌더링 =====================

function renderReasonSummary(summary) {
  if (!summary) return;

  const sect = document.getElementById("reason-analysis-section");
  if (sect) {
    sect.style.display = "flex";
  }

  // ---- 1) 종합 분석 결과 스트립 ----
  setText("reason-summary-overall", summary.overall_result || "-");
  setText("reason-summary-investigate", summary.investigate_users ?? 0);
  setText("reason-summary-educate", summary.educate_users ?? 0);

  const rate =
    typeof summary.intent_rate === "number"
      ? `${summary.intent_rate.toFixed(1)}%`
      : summary.intent_rate || "0%";
  setText("reason-summary-intent-rate", rate);

  // ---- 2) Intent 집계 카드 ----
  const intents = summary.intent_counts || {};
  setText("reason-intent-intentional", intents.intentional || 0);
  setText("reason-intent-negligent", intents.negligent || 0);
  setText("reason-intent-unknown", intents.unknown || 0);

  // ---- 3) 하단 로그 + 유형별 통계 계산 ----
  const rows = Array.isArray(summary.logs) ? summary.logs : [];

  renderReasonLogsTable(rows);
  renderTypeChartFromLogs(rows);
  renderLabelDetails(rows);

  // ---- 4) 프롬프트 카드 및 캐러셀 ----
  const cards = Array.isArray(summary.cards) ? summary.cards : [];
  renderPromptCards(cards);
  buildCarouselItems(cards);
  renderCarousel();
}

// ----- 로그 테이블 -----
function renderReasonLogsTable(rows) {
  const tbody = document.getElementById("reason-log-tbody");
  if (!tbody) return;

  tbody.innerHTML = "";
  if (!rows.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 9;
    td.textContent = "선택된 PC에서 분석 가능한 중요정보 탐지 로그가 없습니다.";
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

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

// ----- 프롬프트 카드 -----
function renderPromptCards(cards) {
  const wrap = document.getElementById("reason-prompt-cards");
  if (!wrap) return;

  wrap.innerHTML = "";
  if (!cards.length) {
    const p = document.createElement("p");
    p.className = "small-note";
    p.textContent = "선택된 PC에서 분석 가능한 중요정보 탐지 로그가 없습니다.";
    wrap.appendChild(p);
    return;
  }

  cards.forEach((c) => {
    wrap.appendChild(buildPromptCard(c));
  });
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

// ===================== 유형별 통계 & 라벨 상세 =====================

function renderTypeChartFromLogs(rows) {
  const canvas = document.getElementById("chart-reason-type");
  if (!canvas) return;

  const stats = buildTypeStatsFromLogs(rows);

  if (reasonTypeChart) {
    reasonTypeChart.destroy();
    reasonTypeChart = null;
  }

  const labels = stats.labels;
  const normal = stats.normal;
  const negligent = stats.negligent;
  const intentional = stats.intentional;

  if (!labels.length) {
    // 데이터 없으면 그냥 비워둠
    return;
  }

  const ctx = canvas.getContext("2d");
  reasonTypeChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "정상",
          data: normal,
          stack: "reason-type",
        },
        {
          label: "부주의",
          data: negligent,
          stack: "reason-type",
        },
        {
          label: "고의적",
          data: intentional,
          stack: "reason-type",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          stacked: true,
        },
        y: {
          stacked: true,
          beginAtZero: true,
        },
      },
      plugins: {
        legend: {
          position: "right",
        },
      },
    },
  });
}

function buildTypeStatsFromLogs(rows) {
  const groupIndex = {};
  GROUP_ORDER.forEach((g, idx) => {
    groupIndex[g] = idx;
  });

  const normal = new Array(GROUP_ORDER.length).fill(0);
  const negligent = new Array(GROUP_ORDER.length).fill(0);
  const intentional = new Array(GROUP_ORDER.length).fill(0);

  rows.forEach((r) => {
    const ents = Array.isArray(r.entities) ? r.entities : [];
    if (!ents.length) return;

    const reasonType = r.reason_type;
    let bucket = normal;
    if (reasonType === "negligent") bucket = negligent;
    else if (reasonType === "intentional") bucket = intentional;

    ents.forEach((e) => {
      const label = (e.label || e.LABEL || "").toUpperCase();
      if (!label) return;

      const groupName = findGroupForLabel(label);
      if (!groupName) return;
      const idx = groupIndex[groupName];
      if (idx == null) return;

      bucket[idx] += 1;
    });
  });

  return {
    labels: GROUP_ORDER,
    normal,
    negligent,
    intentional,
  };
}

function findGroupForLabel(label) {
  for (const [g, labels] of Object.entries(LABEL_GROUPS)) {
    if (labels.includes(label)) return g;
  }
  return null;
}

function renderLabelDetails(rows) {
  const highEl = document.getElementById("reason-label-highrisk");
  const negEl = document.getElementById("reason-label-negligent");

  if (!highEl || !negEl) return;

  const highText = buildLabelSummaryText(rows, "intentional");
  const negText = buildLabelSummaryText(rows, "negligent");

  highEl.textContent = highText || "데이터가 아직 없습니다.";
  negEl.textContent = negText || "데이터가 아직 없습니다.";
}

function buildLabelSummaryText(rows, reasonType) {
  const counter = {};

  rows.forEach((r) => {
    if (r.reason_type !== reasonType) return;
    const ents = Array.isArray(r.entities) ? r.entities : [];
    ents.forEach((e) => {
      const lab = (e.label || e.LABEL || "").toUpperCase();
      if (!lab) return;
      counter[lab] = (counter[lab] || 0) + 1;
    });
  });

  const entries = Object.entries(counter);
  if (!entries.length) return "";

  entries.sort((a, b) => b[1] - a[1]); // count desc
  const top = entries.slice(0, 6);
  return top.map(([lab, cnt]) => `${lab} ${cnt}건`).join(", ");
}

// ===================== 캐러셀 (프롬프트 위험 분석 결과) =====================

function buildCarouselItems(cards) {
  // 사전에 정의된 라벨 조합이 탐지된 프롬프트만 추림
  const filtered = [];

  (cards || []).forEach((c) => {
    const labels = Array.isArray(c.combo_labels)
      ? c.combo_labels.map((x) => String(x).toUpperCase())
      : [];
    const uniqLabels = Array.from(new Set(labels));

    const match = findComboRule(uniqLabels);
    if (!match) return;

    filtered.push({
      time: c.time,
      prompt: c.prompt,
      labels: uniqLabels,
      comboRule: match,
    });
  });

  // 복합 정보 결합 위협 (중요 정보 5개 이상) 처리 – 라벨 수로 판단
  (cards || []).forEach((c) => {
    if (Array.isArray(c.combo_labels) && c.combo_labels.length >= 5) {
      const labels = Array.from(
        new Set(c.combo_labels.map((x) => String(x).toUpperCase()))
      );
      filtered.push({
        time: c.time,
        prompt: c.prompt,
        labels,
        comboRule: COMBO_RULES.find(
          (r) => r.category === "복합 정보 결합 위협"
        ),
      });
    }
  });

  carouselItems = filtered;
  carouselIndex = 0;
}

function findComboRule(labels) {
  if (!labels || !labels.length) return null;
  const labelSet = new Set(labels);

  return (
    COMBO_RULES.find((rule) => {
      if (!rule.labels || !rule.labels.length) return false;
      if (rule.labels.length !== labelSet.size) return false;
      return rule.labels.every((lab) => labelSet.has(lab));
    }) || null
  );
}

function renderCarousel() {
  const timeEl = document.getElementById("reason-carousel-time");
  const promptEl = document.getElementById("reason-carousel-prompt");
  const titleEl = document.getElementById("reason-carousel-title");
  const comboEl = document.getElementById("reason-carousel-combo");
  const descEl = document.getElementById("reason-carousel-desc");
  const dotsWrap = document.getElementById("reason-carousel-dots");
  const prev = document.getElementById("reason-carousel-prev");
  const next = document.getElementById("reason-carousel-next");

  if (
    !timeEl ||
    !promptEl ||
    !titleEl ||
    !comboEl ||
    !descEl ||
    !dotsWrap
  )
    return;

  dotsWrap.innerHTML = "";

  if (!carouselItems.length) {
    // 기본 문구
    timeEl.textContent = "-";
    promptEl.textContent = "분석 대상 프롬프트가 없습니다.";
    titleEl.textContent = "-";
    comboEl.textContent = "-";
    descEl.textContent =
      "사전에 정의된 엔티티 조합이 탐지되면 이 영역에 프롬프트 기반 위험 분석 결과가 표시됩니다.";

    if (prev) prev.classList.add("disabled");
    if (next) next.classList.add("disabled");
    return;
  }

  if (carouselIndex < 0) carouselIndex = 0;
  if (carouselIndex >= carouselItems.length) {
    carouselIndex = carouselItems.length - 1;
  }

  const item = carouselItems[carouselIndex];
  const rule = item.comboRule;

  timeEl.textContent = formatTime(item.time);
  promptEl.textContent = item.prompt || "";

  titleEl.textContent = rule?.title || rule?.category || "위험 프롬프트";
  if (item.labels && item.labels.length) {
    comboEl.textContent = item.labels.join(", ");
  } else if (rule && rule.labels && rule.labels.length) {
    comboEl.textContent = rule.labels.join(", ");
  } else {
    comboEl.textContent = "-";
  }

  descEl.textContent =
    rule?.desc ||
    "사전에 정의된 라벨 조합에 해당하는 프롬프트로, 추가 점검이 필요합니다.";

  // 점(dot) 렌더링
  carouselItems.forEach((_, idx) => {
    const dot = document.createElement("div");
    dot.className = "carousel-dot" + (idx === carouselIndex ? " active" : "");
    dotsWrap.appendChild(dot);
  });

  // 화살표 활성/비활성
  if (prev) {
    if (carouselIndex === 0) prev.classList.add("disabled");
    else prev.classList.remove("disabled");
  }
  if (next) {
    if (carouselIndex === carouselItems.length - 1)
      next.classList.add("disabled");
    else next.classList.remove("disabled");
  }
}

// ===================== 유틸 =====================

function setText(id, val) {
  const el = document.getElementById(id);
  if (el != null) el.textContent = val;
}

function formatTime(iso) {
  if (!iso) return "";
  try {
    return iso.replace("T", " ").slice(0, 19);
  } catch {
    return iso;
  }
}
