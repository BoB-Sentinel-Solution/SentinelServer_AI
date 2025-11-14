// MCP - INFORMATION BASED 리포트 페이지 스크립트

(function () {
  const { fetchSummary } = window.SentinelAPI || {};

  const LABEL_KR_MAP = {
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
    MNEMONIC: "지갑 니모닉",
    CRYPTO_PRIVATE_KEY: "암호화폐 개인키",
    HD_WALLET: "HD 월렛키",
    IPV4: "IPv4",
    IPV6: "IPv6",
    MAC_ADDRESS: "MAC 주소",
    IMEI: "IMEI",
    OTHER: "기타",
  };

  let chartTypeTotal;
  let chartByHost;
  let chartUsageTrend;

  function formatUpdatedAt() {
    const el = document.getElementById("top-updated-at");
    if (!el) return;
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, "0");
    const mm = String(now.getMinutes()).padStart(2, "0");
    const ss = String(now.getSeconds()).padStart(2, "0");
    el.textContent = `${hh}:${mm}:${ss} KST`;
  }

  function buildLabelAndCounts(typeRatio) {
    const labels = [];
    const counts = [];
    Object.entries(typeRatio || {}).forEach(([label, count]) => {
      const kr = LABEL_KR_MAP[label] || label;
      labels.push(kr);
      counts.push(count);
    });
    return { labels, counts };
  }

  function buildHostSensitiveCounts(recentLogs) {
    const map = new Map();
    (recentLogs || []).forEach((log) => {
      if (!log.has_sensitive) return;
      const host = log.host || "기타";
      map.set(host, (map.get(host) || 0) + 1);
    });

    const labels = Array.from(map.keys());
    const counts = labels.map((h) => map.get(h));
    return { labels, counts };
  }

  function buildUsageHourly(hourlyAttempts) {
    const labels = [];
    const counts = [];
    (hourlyAttempts || []).forEach((cnt, hour) => {
      labels.push(`${hour}시`);
      counts.push(cnt);
    });
    return { labels, counts };
  }

  function renderTypeTotalChart(data) {
    const ctx = document
      .getElementById("chart-mcp-info-type-total")
      .getContext("2d");

    const { labels, counts } = buildLabelAndCounts(data.type_ratio);

    if (chartTypeTotal) {
      chartTypeTotal.data.labels = labels;
      chartTypeTotal.data.datasets[0].data = counts;
      chartTypeTotal.update();
      return;
    }

    chartTypeTotal = new Chart(ctx, {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            label: "탐지 건수",
            data: counts,
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
            ticks: {
              precision: 0,
            },
          },
        },
      },
    });
  }

  function renderByHostChart(data) {
    const ctx = document
      .getElementById("chart-mcp-info-by-host")
      .getContext("2d");

    const { labels, counts } = buildHostSensitiveCounts(data.recent_logs);

    if (chartByHost) {
      chartByHost.data.labels = labels;
      chartByHost.data.datasets[0].data = counts;
      chartByHost.update();
      return;
    }

    chartByHost = new Chart(ctx, {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            label: "중요정보 탐지 건수",
            data: counts,
            borderWidth: 1,
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
      },
    });
  }

  function renderUsageTrendChart(data) {
    const ctx = document
      .getElementById("chart-mcp-usage-trend")
      .getContext("2d");

    const { labels, counts } = buildUsageHourly(data.hourly_attempts);

    if (chartUsageTrend) {
      chartUsageTrend.data.labels = labels;
      chartUsageTrend.data.datasets[0].data = counts;
      chartUsageTrend.update();
      return;
    }

    chartUsageTrend = new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "호출 시도 횟수",
            data: counts,
            tension: 0.3,
            borderWidth: 2,
            pointRadius: 2,
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
      },
    });
  }

  async function loadData(range) {
    if (!fetchSummary) {
      console.error("SentinelAPI.fetchSummary 가 정의되지 않았습니다.");
      return;
    }

    // range 값은 향후 백엔드 확장용. 현재는 사용하지 않고 interface 만 필터.
    const data = await fetchSummary({ interface: "MCP" });

    renderTypeTotalChart(data);
    renderByHostChart(data);
    renderUsageTrendChart(data);
    formatUpdatedAt();
  }

  function initRangeButtons() {
    const buttons = document.querySelectorAll(".range-btn");
    buttons.forEach((btn) => {
      btn.addEventListener("click", () => {
        buttons.forEach((b) => b.classList.remove("range-btn--active"));
        btn.classList.add("range-btn--active");
        const range = btn.getAttribute("data-range");
        loadData(range);
      });
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    initRangeButtons();
    loadData("recent");

    const refreshBtn = document.getElementById("btn-refresh");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", () => loadData("recent"));
    }
  });
})();
