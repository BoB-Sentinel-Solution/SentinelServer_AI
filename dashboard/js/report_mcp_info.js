// js/report_mcp_info.js

let chartServiceRank = null;
let chartUsageRatio = null;
let chartUsageTrend = null;
// let chartIntExt = null;        // ✅ (제거된 카드) 내부/외부 MCP 차트
// let chartServiceUsage = null;  // ✅ (제거된 카드) MCP 서버별 사용량 차트

// ★ 추가: 라벨 → 한글 매핑 (다른 파일과 동일하게)
const MCP_LABEL_KR_MAP = {
  NAME: "이름",
  PHONE: "전화번호",
  EMAIL: "이메일",
  ADDRESS: "주소",
  POSTAL_CODE: "우편번호",
  PERSONAL_CUSTOMS_ID: "개인통관고유부호",
  RESIDENT_ID: "주민등록번호",
  PASSPORT: "여권번호",
  DRIVER_LICENSE: "운전면허번호",
  FOREIGNER_ID: "외국인등록번호",
  HEALTH_INSURANCE_ID: "건보/보험번호",
  BUSINESS_ID: "사업자등록번호",
  JWT: "JWT 토큰",
  API_KEY: "API 키",
  GITHUB_PAT: "GitHub PAT",
  PRIVATE_KEY: "개인키",
  CARD_NUMBER: "카드번호",
  CARD_EXPIRY: "카드유효기간",
  CARD_CVV: "CVV",
  BANK_ACCOUNT: "계좌번호",
  PAYMENT_PIN: "결제 PIN",
  MOBILE_PAYMENT_PIN: "모바일 결제 PIN",
  PAYMENT_URI_QR: "결제 URI/QR",
  MNEMONIC: "지갑 복구키",
  CRYPTO_PRIVATE_KEY: "암호화폐 개인키",
  HD_WALLET: "HD 월렛키",
  IPV4: "IPv4",
  IPV6: "IPv6",
  MAC_ADDRESS: "MAC 주소",
  IMEI: "IMEI",
  OTHER: "기타",
};

document.addEventListener("DOMContentLoaded", () => {
  initTopBarClock();
  hookRefreshButton();
  loadMcpOverview();
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
    loadMcpOverview();
  });
}

/** MCP OVERALL 데이터 로딩 */
async function loadMcpOverview() {
  try {
    // 1) MCP 전용 요약
    // 2) LLM 전용 요약 (LLM vs MCP 비율용)
    // 3) 최근 로그 (MCP 필터용)
    const [summaryMcp, summaryLlm, logsResp] = await Promise.all([
      fetchSummary({ interface: "MCP" }),
      fetchSummary({ interface: "LLM" }),
      fetchLogs({ page: 1, page_size: 200 }),
    ]);

    const allLogs = (logsResp && logsResp.items) || [];
    const mcpLogs = allLogs.filter((row) => {
      const iface = (row.interface || "").toLowerCase();
      return iface === "mcp";
    });

    const serviceCounts = buildServiceCounts(mcpLogs);

    renderMcpServiceRank(serviceCounts);
    renderUsageRatio(summaryLlm, summaryMcp);
    renderUsageTrend(summaryMcp);

    // ✅ 제거된 카드라서 렌더 호출 제거
    // renderInternalExternal(mcpLogs);
    // renderServiceUsage(serviceCounts);

    // ★ 추가: Prediction 텍스트 갱신
    updatePredictionFromSummary(summaryMcp);
  } catch (err) {
    console.error("MCP overall report load failed:", err);
  }
}

/** host / hostname 기준 서비스별 카운트 */
function buildServiceCounts(logs) {
  const counts = {};
  logs.forEach((r) => {
    const raw = r.host || r.hostname || "UNKNOWN";
    const name = raw && raw.trim() ? raw.trim() : "UNKNOWN";
    counts[name] = (counts[name] || 0) + 1;
  });
  return counts;
}

/** MCP 서비스별 사용 순위 (도넛) */
function renderMcpServiceRank(serviceCounts) {
  const canvas = document.getElementById("chart-mcp-service-rank");
  const emptyMsg = document.getElementById("mcp-service-empty");
  if (!canvas) return;

  const labels = Object.keys(serviceCounts).sort((a, b) => {
    return serviceCounts[b] - serviceCounts[a];
  });
  const values = labels.map((k) => serviceCounts[k]);

  if (chartServiceRank) {
    chartServiceRank.destroy();
    chartServiceRank = null;
  }

  if (!labels.length) {
    canvas.style.display = "none";
    if (emptyMsg) emptyMsg.style.display = "block";
    return;
  }

  canvas.style.display = "block";
  if (emptyMsg) emptyMsg.style.display = "none";

  const ctx = canvas.getContext("2d");
  chartServiceRank = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels,
      datasets: [
        {
          label: "호출 건수",
          data: values,
          borderWidth: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "55%",
      plugins: {
        legend: {
          position: "right",
        },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const label = ctx.label || "";
              const val = ctx.parsed || 0;
              return `${label}: ${val}회`;
            },
          },
        },
      },
    },
  });
}

/** MCP 사용량 비율 (LLM vs MCP) */
function renderUsageRatio(summaryLlm, summaryMcp) {
  const canvas = document.getElementById("chart-mcp-usage-ratio");
  if (!canvas) return;

  const llmTotal = sumArray((summaryLlm && summaryLlm.hourly_attempts) || []);
  const mcpTotal = sumArray((summaryMcp && summaryMcp.hourly_attempts) || []);

  if (chartUsageRatio) {
    chartUsageRatio.destroy();
    chartUsageRatio = null;
  }

  const ctx = canvas.getContext("2d");
  chartUsageRatio = new Chart(ctx, {
    type: "bar",
    data: {
      labels: ["LLM", "MCP"],
      datasets: [
        {
          label: "호출 건수",
          data: [llmTotal, mcpTotal],
          borderWidth: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          beginAtZero: true,
          title: {
            display: true,
            text: "호출 건수",
          },
        },
      },
      plugins: {
        legend: {
          display: false,
        },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const v = ctx.parsed.y || 0;
              return `${v}회`;
            },
          },
        },
      },
    },
  });
}

/** MCP 사용량 추이 (시간대별) */
function renderUsageTrend(summaryMcp) {
  const canvas = document.getElementById("chart-mcp-usage-trend");
  if (!canvas) return;

  const hourly = (summaryMcp && summaryMcp.hourly_attempts) || [];
  const labels = Array.from({ length: 24 }, (_, i) => `${i}시`);

  if (chartUsageTrend) {
    chartUsageTrend.destroy();
    chartUsageTrend = null;
  }

  const ctx = canvas.getContext("2d");
  chartUsageTrend = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "MCP 호출 건수",
          data: hourly,
          tension: 0.3,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          beginAtZero: true,
        },
      },
      plugins: {
        legend: {
          display: false,
        },
      },
    },
  });
}

/** 외부 MCP / 내부 MCP 비중 (public_ip 기준, RFC1918 = 내부) */
function renderInternalExternal(mcpLogs) {
  const canvas = document.getElementById("chart-mcp-int-ext");
  const emptyMsg = document.getElementById("mcp-int-ext-empty");
  if (!canvas) return;

  let internal = 0;
  let external = 0;

  mcpLogs.forEach((r) => {
    const ip = r.public_ip || "";
    if (!ip) return;
    if (isPrivateIp(ip)) internal += 1;
    else external += 1;
  });

  // if (chartIntExt) {
  //   chartIntExt.destroy();
  //   chartIntExt = null;
  // }

  if (internal === 0 && external === 0) {
    canvas.style.display = "none";
    if (emptyMsg) emptyMsg.style.display = "block";
    return;
  }

  canvas.style.display = "block";
  if (emptyMsg) emptyMsg.style.display = "none";

  const ctx = canvas.getContext("2d");
  // chartIntExt = new Chart(ctx, {
  new Chart(ctx, {
    type: "bar",
    data: {
      labels: ["외부 MCP", "내부 MCP"],
      datasets: [
        {
          label: "호출 건수",
          data: [external, internal],
          borderWidth: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          beginAtZero: true,
          title: {
            display: true,
            text: "호출 건수",
          },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => `${ctx.parsed.y || 0}회`,
          },
        },
      },
    },
  });
}

/** MCP 서버별 사용량 (bar) */
function renderServiceUsage(serviceCounts) {
  const canvas = document.getElementById("chart-mcp-service-usage");
  if (!canvas) return;

  const labels = Object.keys(serviceCounts).sort((a, b) => {
    return serviceCounts[b] - serviceCounts[a];
  });
  const values = labels.map((k) => serviceCounts[k]);

  // if (chartServiceUsage) {
  //   chartServiceUsage.destroy();
  //   chartServiceUsage = null;
  // }

  const ctx = canvas.getContext("2d");
  // chartServiceUsage = new Chart(ctx, {
  new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "호출 건수",
          data: values,
          borderWidth: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          beginAtZero: true,
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => `${ctx.parsed.y || 0}회`,
          },
        },
      },
    },
  });
}

/** ★ 추가: summaryMcp.type_ratio 기반으로 Prediction 텍스트 갱신 */
function updatePredictionFromSummary(summaryMcp) {
  const span = document.getElementById("mcp-pred-main-labels");
  if (!span) return;

  const typeRatio = (summaryMcp && summaryMcp.type_ratio) || {};
  const entries = Object.entries(typeRatio).filter(
    ([, count]) => (Number(count) || 0) > 0
  );

  if (!entries.length) {
    span.textContent = "중요정보";
    return;
  }

  let maxCount = 0;
  entries.forEach(([, cnt]) => {
    const n = Number(cnt) || 0;
    if (n > maxCount) maxCount = n;
  });

  const topLabels = entries
    .filter(([, cnt]) => Number(cnt) === maxCount)
    .map(([label]) => MCP_LABEL_KR_MAP[label] || label);

  span.textContent = topLabels.join(", ");
}

/** 유틸: 배열 합 */
function sumArray(arr) {
  return arr.reduce((acc, v) => acc + (Number(v) || 0), 0);
}

/** 유틸: 사설 IP 여부 */
function isPrivateIp(ip) {
  // 아주 간단한 RFC1918 체크
  const m = ip.split(".");
  if (m.length !== 4) return false;
  const a = Number(m[0]);
  const b = Number(m[1]);

  if (a === 10) return true;
  if (a === 172 && b >= 16 && b <= 31) return true;
  if (a === 192 && b === 168) return true;
  return false;
}
