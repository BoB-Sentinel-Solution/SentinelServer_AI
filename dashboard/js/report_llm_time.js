// dashboard/js/report_llm_time.js

let timeUsageChart = null;

document.addEventListener("DOMContentLoaded", () => {
  const updatedAtEl = document.getElementById("top-updated-at");
  const btnRefresh = document.getElementById("btn-refresh");
  const btnLogout = document.getElementById("btn-logout");
  const riskLevelEl = document.getElementById("time-risk-level");

  function pad(n) {
    return n.toString().padStart(2, "0");
  }

  // 상단 UPDATED 시계
  function updateClock() {
    const now = new Date();
    if (updatedAtEl) {
      updatedAtEl.textContent =
        `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(
          now.getSeconds()
        )} KST`;
    }
  }
  setInterval(updateClock, 1000);
  updateClock();

  // 로그아웃 버튼
  if (btnLogout) {
    btnLogout.addEventListener("click", () => {
      if (window.SentinelApi && window.SentinelApi.setAdminKey) {
        window.SentinelApi.setAdminKey("");
      }
      window.location.href = "./index.html";
    });
  }

  // 데이터 로드 + 차트 렌더링
  async function fetchSummaryAndRender() {
    if (!window.SentinelApi || !window.SentinelApi.get) {
      console.error("SentinelApi.get 가 정의되어 있지 않습니다.");
      return;
    }

    // 관리자 키 없으면 로그인 페이지로
    if (window.SentinelApi.getAdminKey && !window.SentinelApi.getAdminKey()) {
      window.location.href = "./index.html";
      return;
    }

    try {
      // LLM interface만 집계
      const summary = await window.SentinelApi.get("/summary?interface=LLM");
      renderTimeUsageChart(summary);
      renderRiskLevel(summary, riskLevelEl);
    } catch (err) {
      console.error(err);
      alert("리포트 데이터를 불러오는 중 오류가 발생했습니다.");
    }
  }

  if (btnRefresh) {
    btnRefresh.addEventListener("click", () => {
      fetchSummaryAndRender();
    });
  }

  fetchSummaryAndRender();
});

/* -----------------------
   차트 렌더링
   ----------------------- */

// ALLOWED 라벨들을 대분류 그룹으로 묶기
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
  "인증 정보": [
    "EMAIL",
    "PHONE",
    "JWT",
    "API_KEY",
    "GITHUB_PAT",
    "PRIVATE_KEY",
    "CARD_CVV",
  ],
  "금융 정보": [
    "CARD_NUMBER",
    "CARD_EXPIRY",
    "BANK_ACCOUNT",
    "PAYMENT_PIN",
    "MOBILE_PAYMENT_PIN",
  ],
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

// 개별 라벨이 어떤 그룹인지 찾기
function findGroupName(label) {
  for (const [group, labels] of Object.entries(LABEL_GROUPS)) {
    if (labels.includes(label)) return group;
  }
  return null;
}

function renderTimeUsageChart(summary) {
  const ctx = document.getElementById("chart-time-usage");
  if (!ctx) return;

  const hourlyAttempts = summary.hourly_attempts || [];
  const hourlyType = summary.hourly_type || {};

  const labels = Array.from({ length: 24 }, (_, i) => `${i}시`);

  // 그룹별 [24시간] 배열 초기화
  const groupSeries = {};
  GROUP_ORDER.forEach((g) => {
    groupSeries[g] = Array(24).fill(0);
  });

  // hourly_type: { "0": {NAME:1,...}, "1": {...}, ... }
  for (let h = 0; h < 24; h++) {
    const bucket = hourlyType[String(h)] || {};
    for (const [label, count] of Object.entries(bucket)) {
      const group = findGroupName(label);
      if (!group) continue;
      groupSeries[group][h] += count || 0;
    }
  }

  // 스택 막대 데이터셋 생성
  const datasets = [];
  GROUP_ORDER.forEach((groupName) => {
    datasets.push({
      type: "bar",
      label: groupName,
      data: groupSeries[groupName],
      stack: "stack1",
    });
  });

  // 선 그래프: 전체 사용량 (hourlyAttempts)
  const usageData = labels.map((_, i) => hourlyAttempts[i] || 0);
  datasets.push({
    type: "line",
    label: "전체 사용량",
    data: usageData,
    yAxisID: "y2",
    tension: 0.3,
    borderWidth: 2,
    pointRadius: 2,
  });

  if (timeUsageChart) timeUsageChart.destroy();

  timeUsageChart = new Chart(ctx, {
    data: {
      labels,
      datasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          stacked: true,
          ticks: {
            maxRotation: 0,
            autoSkip: true,
            maxTicksLimit: 12,
          },
        },
        y: {
          stacked: true,
          beginAtZero: true,
          ticks: { precision: 0 },
          title: { display: true, text: "탐지 건수" },
        },
        y2: {
          beginAtZero: true,
          position: "right",
          grid: { drawOnChartArea: false },
          ticks: { precision: 0 },
          title: { display: true, text: "전체 사용량" },
        },
      },
      plugins: {
        tooltip: {
          mode: "index",
          intersect: false,
        },
        legend: {
          position: "bottom",
          labels: {
            boxWidth: 10,
          },
        },
      },
    },
  });
}

/* -----------------------
   위험 지수 표시
   ----------------------- */

function renderRiskLevel(summary, el) {
  if (!el) return;

  const total = summary.total_sensitive || 0;
  const today = summary.today_sensitive || 0;

  let level = "없음";
  if (total > 0) {
    const ratio = today / total;
    if (today >= 10 || ratio > 0.4) level = "높음";
    else if (today >= 3 || ratio > 0.15) level = "보통";
    else if (today > 0) level = "낮음";
  }

  el.textContent = level;
}
