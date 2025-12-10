// dashboard/js/report_llm_service.js

let svcTotalUsageChart = null;
let svcSensitiveByHostChart = null;
let svcHourlyUsageChart = null;

document.addEventListener("DOMContentLoaded", () => {
  const updatedAtEl = document.getElementById("top-updated-at");
  const btnRefresh = document.getElementById("btn-refresh");
  const btnLogout = document.getElementById("btn-logout");
  const riskLevelEl = document.getElementById("service-risk-level");

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
      renderServiceTotalUsage(summary);
      renderServiceSensitiveByHost(summary);
      renderServiceHourlyUsage(summary);
      renderServiceRiskLevel(summary, riskLevelEl);
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
   차트 1: 전체 서비스 사용량 비율
   (서비스/Host 별 호출 비중 도넛 차트)
   ----------------------- */

function renderServiceTotalUsage(summary) {
  const canvas = document.getElementById("chart-service-total-usage");
  if (!canvas) return;

  // TODO: 백엔드에서 service_usage_by_host 를 제공하면 그 값을 사용.
  // 아직 없다면, 임시로 service_sensitive_by_host 를 사용해 비율만 표현.
  const usageByHost =
    summary.service_usage_by_host || summary.service_sensitive_by_host || {};

  const entries = Object.entries(usageByHost);
  if (entries.length === 0) {
    if (svcTotalUsageChart) {
      svcTotalUsageChart.destroy();
      svcTotalUsageChart = null;
    }
    return;
  }

  // 호출 수 기준 내림차순 정렬
  entries.sort((a, b) => (b[1] || 0) - (a[1] || 0));

  const labels = entries.map(([host]) => host || "unknown");
  const data = entries.map(([, count]) => count || 0);

  if (svcTotalUsageChart) svcTotalUsageChart.destroy();

  const ctx = canvas.getContext("2d");
  svcTotalUsageChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels,
      datasets: [
        {
          label: "호출 비율",
          data,
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

/* -----------------------
   차트 2: 서비스 별 중요 정보 탐지
   (호스트별 바 차트)
   ----------------------- */

function renderServiceSensitiveByHost(summary) {
  const ctx = document.getElementById("chart-service-sensitive-by-host");
  if (!ctx) return;

  const byHost = summary.service_sensitive_by_host || {};
  const entries = Object.entries(byHost);

  // 탐지 건수 순으로 정렬해서 상위 8개 정도만 보여주기
  entries.sort((a, b) => b[1] - a[1]);
  const top = entries.slice(0, 8);

  const labels = top.map(([host]) => host || "unknown");
  const data = top.map(([, count]) => count || 0);

  if (svcSensitiveByHostChart) svcSensitiveByHostChart.destroy();

  svcSensitiveByHostChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "중요 정보 탐지 건수",
          data,
        },
      ],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          beginAtZero: true,
          ticks: { precision: 0 },
        },
      },
      plugins: {
        legend: {
          display: false,
        },
        tooltip: {
          callbacks: {
            label: (ctx) => ` ${ctx.parsed.x} 건`,
          },
        },
      },
    },
  });
}

/* -----------------------
   차트 3: 시간대 별 서비스 사용량 추이
   (hourly_attempts 라인 + 오늘 탐지 건수 today_hourly 라인)
   ----------------------- */

function renderServiceHourlyUsage(summary) {
  const ctx = document.getElementById("chart-service-hourly-usage");
  if (!ctx) return;

  const hourlyAttempts = summary.hourly_attempts || [];
  const todayHourly = summary.today_hourly || [];

  const labels = Array.from({ length: 24 }, (_, i) => `${i}시`);

  const usageData = labels.map((_, idx) => hourlyAttempts[idx] || 0);
  const sensitiveData = labels.map((_, idx) => todayHourly[idx] || 0);

  if (svcHourlyUsageChart) svcHourlyUsageChart.destroy();

  svcHourlyUsageChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "전체 호출 수",
          data: usageData,
          tension: 0.3,
          borderWidth: 2,
          pointRadius: 2,
          yAxisID: "y1",
        },
        {
          label: "오늘 민감정보 탐지",
          data: sensitiveData,
          tension: 0.3,
          borderWidth: 2,
          pointRadius: 2,
          borderDash: [4, 2],
          yAxisID: "y2",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y1: {
          position: "left",
          beginAtZero: true,
          ticks: { precision: 0 },
          title: { display: true, text: "전체 호출 수" },
        },
        y2: {
          position: "right",
          beginAtZero: true,
          ticks: { precision: 0 },
          grid: { drawOnChartArea: false },
          title: { display: true, text: "오늘 탐지 건수" },
        },
      },
      plugins: {
        legend: {
          position: "bottom",
        },
      },
    },
  });
}

/* -----------------------
   위험 지수 표시 + 서비스별 위험 TOP3 패널
   ----------------------- */

function renderServiceRiskLevel(summary, el) {
  if (!el) return;

  const total = summary.total_sensitive || 0;
  const today = summary.today_sensitive || 0;

  let level = "";
  // if (total > 0) {
  //   const ratio = today / total;
  //   if (today >= 10 || ratio > 0.4) level = "강함";
  //   else if (today >= 3 || ratio > 0.15) level = "보통";
  //   else if (today > 0) level = "낮음";
  // }
  el.textContent = level;

  // ----- 우측 "서비스별 위험 TOP 3" 리스트 업데이트 -----
  const listEl = document.getElementById("service-risk-top-list");
  if (!listEl) return;

  const byHost = summary.service_sensitive_by_host || {};
  const entries = Object.entries(byHost);

  listEl.innerHTML = "";

  if (!entries.length) {
    const li = document.createElement("li");
    const spanLabel = document.createElement("span");
    spanLabel.className = "service-risk-label";
    spanLabel.textContent = "데이터 없음";
    const spanMeta = document.createElement("span");
    spanMeta.className = "service-risk-meta";
    spanMeta.textContent = "-";
    li.appendChild(spanLabel);
    li.appendChild(spanMeta);
    listEl.appendChild(li);
    return;
  }

  // 현재는 "탐지 건수" 기준 TOP3 (추후 호출 수 대비 비율로 확장 가능)
  entries.sort((a, b) => (b[1] || 0) - (a[1] || 0));
  const top3 = entries.slice(0, 3);

  top3.forEach(([host, count]) => {
    const li = document.createElement("li");

    const spanLabel = document.createElement("span");
    spanLabel.className = "service-risk-label";
    spanLabel.textContent = host || "unknown";

    const spanMeta = document.createElement("span");
    spanMeta.className = "service-risk-meta";
    spanMeta.textContent = `${count || 0}건 탐지`;

    li.appendChild(spanLabel);
    li.appendChild(spanMeta);
    listEl.appendChild(li);
  });
}
