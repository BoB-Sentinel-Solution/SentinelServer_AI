// dashboard/js/report.js

// 전역 Chart 인스턴스 보관 (리프레시 시 destroy 용)
let chartInfoRatio = null;
let chartInfoStats = null;
let chartInfoTypes = null;
let chartInfoTrendWeek = null;
let chartInfoTrendCompare = null;

document.addEventListener("DOMContentLoaded", () => {
  const updatedAtEl = document.getElementById("top-updated-at");
  const btnRefresh = document.getElementById("btn-refresh");
  const btnLogout = document.getElementById("btn-logout");
  const predictionScoreEl = document.getElementById("prediction-score");

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

  // 요약 데이터 가져오기
  async function fetchSummaryAndRender() {
    if (!window.SentinelApi || !window.SentinelApi.get) {
      console.error("SentinelApi.get 가 정의되어 있지 않습니다.");
      return;
    }

    // 관리자 키 체크 (없으면 로그인 페이지로 이동)
    if (window.SentinelApi.getAdminKey && !window.SentinelApi.getAdminKey()) {
      window.location.href = "./index.html";
      return;
    }

    try {
      const summary = await window.SentinelApi.get("/summary?interface=LLM");

      renderInfoRatio(summary);
      renderInfoStats(summary);
      renderInfoTypes(summary);
      renderInfoTrend(summary);
      renderInfoTrendCompare(summary);
      renderPrediction(summary, predictionScoreEl);
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

  // 초기 로딩
  fetchSummaryAndRender();
});

/* =========================
   차트 렌더링 함수들
   ========================= */

// 1) 오늘 시간대별 중요정보 탐지 (라인 차트)
function renderInfoRatio(summary) {
  const ctx = document.getElementById("chart-info-ratio");
  if (!ctx) return;

  const todayHourly = summary.today_hourly || [];
  const labels = Array.from({ length: 24 }, (_, i) => `${i}시`);
  const data = labels.map((_, i) => todayHourly[i] || 0);

  if (chartInfoRatio) chartInfoRatio.destroy();

  chartInfoRatio = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "시간대별 탐지 건수",
          data,
          fill: false,
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
          ticks: { precision: 0 },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => `탐지 ${ctx.parsed.y}건`,
          },
        },
      },
    },
  });
}

// 2) 중요정보 탐지 통계 (라벨별 Bar 차트)
function renderInfoStats(summary) {
  const ctx = document.getElementById("chart-info-stats");
  if (!ctx) return;

  const typeRatio = summary.type_ratio || {};
  const labels = Object.keys(typeRatio);
  const data = labels.map((k) => typeRatio[k] || 0);

  if (chartInfoStats) chartInfoStats.destroy();

  chartInfoStats = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "탐지 횟수",
          data,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          ticks: { autoSkip: false, maxRotation: 60, minRotation: 30 },
        },
        y: {
          beginAtZero: true,
          ticks: { precision: 0 },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => `${ctx.parsed.y}건`,
          },
        },
      },
    },
  });
}

// 3) 중요정보 탐지 유형 분류 (도넛)
function renderInfoTypes(summary) {
  const ctx = document.getElementById("chart-info-types");
  if (!ctx) return;

  const typeRatio = summary.type_ratio || {};
  let entries = Object.entries(typeRatio);

  // 상위 6개만 표시, 나머지는 "OTHER" 로 묶기
  entries.sort((a, b) => b[1] - a[1]);
  const top = entries.slice(0, 6);
  const rest = entries.slice(6);
  const restSum = rest.reduce((acc, [, v]) => acc + v, 0);
  let labels = top.map(([k]) => k);
  let data = top.map(([, v]) => v);
  if (restSum > 0) {
    labels.push("OTHER");
    data.push(restSum);
  }

  if (chartInfoTypes) chartInfoTypes.destroy();

  chartInfoTypes = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels,
      datasets: [
        {
          data,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: "right",
          labels: {
            boxWidth: 12,
          },
        },
      },
    },
  });
}

// 4) 시간대별 중요정보 탐지 추이 (전체 기간 기준)
function renderInfoTrend(summary) {
  const ctx = document.getElementById("chart-info-trend-week");
  if (!ctx) return;

  const hourlyAttempts = summary.hourly_attempts || [];
  const labels = Array.from({ length: 24 }, (_, i) => `${i}시`);
  const data = labels.map((_, i) => hourlyAttempts[i] || 0);

  if (chartInfoTrendWeek) chartInfoTrendWeek.destroy();

  chartInfoTrendWeek = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "전체 요청 수",
          data,
          fill: false,
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
          ticks: { precision: 0 },
        },
      },
      plugins: {
        legend: { display: false },
      },
    },
  });
}

// 5) 시간대별 탐지 비교 (오늘 탐지 vs 전체 요청)
function renderInfoTrendCompare(summary) {
  const ctx = document.getElementById("chart-info-trend-compare");
  if (!ctx) return;

  const hourlyAttempts = summary.hourly_attempts || [];
  const todayHourly = summary.today_hourly || [];
  const labels = Array.from({ length: 24 }, (_, i) => `${i}시`);

  const todayData = labels.map((_, i) => todayHourly[i] || 0);
  const otherData = labels.map(
    (_, i) => Math.max(0, (hourlyAttempts[i] || 0) - (todayHourly[i] || 0))
  );

  if (chartInfoTrendCompare) chartInfoTrendCompare.destroy();

  chartInfoTrendCompare = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "오늘 탐지",
          data: todayData,
          stack: "stack1",
        },
        {
          label: "기타 요청",
          data: otherData,
          stack: "stack1",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          stacked: true,
          ticks: { autoSkip: true, maxTicksLimit: 12 },
        },
        y: {
          stacked: true,
          beginAtZero: true,
          ticks: { precision: 0 },
        },
      },
      plugins: {
        tooltip: {
          callbacks: {
            label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y}건`,
          },
        },
      },
    },
  });
}

// 6) Prediction 점수 계산 (간단한 휴리스틱)
function renderPrediction(summary, scoreEl) {
  if (!scoreEl) return;

  const total = summary.total_sensitive || 0;
  const today = summary.today_sensitive || 0;

  let score = 0;
  if (total === 0) {
    score = 0;
  } else {
    // 오늘 비중을 기반으로 간단한 위험 점수 계산
    const ratio = today / total;        // 0 ~ 1
    score = Math.round(Math.min(100, ratio * 120 + today * 2));
  }

  scoreEl.textContent = String(score);
}
