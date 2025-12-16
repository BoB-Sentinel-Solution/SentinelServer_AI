// dashboard/js/dashboard.js
document.addEventListener("DOMContentLoaded", () => {
  const updatedAtEl = document.getElementById("top-updated-at");
  const btnRefresh = document.getElementById("btn-refresh");
  const btnLogout = document.getElementById("btn-logout");

  const kpiTotalSensitive = document.getElementById("kpi-total-sensitive");
  const kpiTotalBlocked = document.getElementById("kpi-total-blocked");
  const todayDetected = document.getElementById("today-detected");
  const todayBlocked = document.getElementById("today-blocked");
  const todayDateEl = document.getElementById("today-date");
  const todayTimeEl = document.getElementById("today-time");
  const logTableBody = document.getElementById("log-table-body");

  // 차트 인스턴스
  let chartRecentAttempts;
  let chartIpBand;
  let chartTypeRatio;
  let chartTodayHourly;
  let chartTodayType;
  let chartHourlyType;

  function formatTimeKST(date) {
    const pad = (n) => n.toString().padStart(2, "0");
    return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(
      date.getSeconds()
    )} KST`;
  }

  function setNowForHeader() {
    const now = new Date();
    if (updatedAtEl) updatedAtEl.textContent = formatTimeKST(now);

    if (todayDateEl) {
      todayDateEl.textContent = `${String(now.getMonth() + 1).padStart(
        2,
        "0"
      )}/${String(now.getDate()).padStart(2, "0")}`;
    }
    if (todayTimeEl) {
      todayTimeEl.textContent = `${String(now.getHours()).padStart(
        2,
        "0"
      )}:${String(now.getMinutes()).padStart(2, "0")}:${String(
        now.getSeconds()
      ).padStart(2, "0")}`;
    }
  }

  async function loadSummary() {
    // ★ 백엔드 라우트: /api/summary
    const summary = await window.SentinelApi.get("/summary");

    // 1) KPI
    if (kpiTotalSensitive) {
      kpiTotalSensitive.textContent =
        summary.total_sensitive != null ? summary.total_sensitive : "-";
    }
    if (kpiTotalBlocked) {
      if (summary.total_blocked != null) {
        kpiTotalBlocked.textContent = summary.total_blocked;
      } else if (summary.type_blocked) {
        const totalBlocked = Object.values(summary.type_blocked).reduce(
          (acc, v) => acc + v,
          0
        );
        kpiTotalBlocked.textContent = totalBlocked;
      } else {
        kpiTotalBlocked.textContent = "-";
      }
    }

    // 오늘 탐지/차단 (없으면 전체와 동일하게 표현)
    if (todayDetected) {
      todayDetected.textContent =
        summary.today_sensitive != null
          ? summary.today_sensitive
          : summary.total_sensitive ?? "-";
    }
    if (todayBlocked) {
      todayBlocked.textContent =
        summary.today_blocked != null
          ? summary.today_blocked
          : kpiTotalBlocked.textContent;
    }

    // 2) 최근 개인정보 시도 (시간대 그래프)
    const ctxRecent = document
      .getElementById("chart-recent-attempts")
      ?.getContext("2d");
    if (ctxRecent) {
      const hourly = summary.hourly_attempts || [];

      // hourly는 [24] 숫자 배열이므로, 인덱스를 시간으로 사용
      const labels = Array.from({ length: 24 }, (_, i) => `${i}:00`);
      const data = labels.map((_, i) => hourly[i] || 0);

      if (chartRecentAttempts) chartRecentAttempts.destroy();
      chartRecentAttempts = new Chart(ctxRecent, {
        type: "line",
        data: {
          labels,
          datasets: [
            {
              label: "시도 횟수",
              data,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            y: { beginAtZero: true },
          },
        },
      });
    }

    // ✅ 3) 전체 중요정보 유형 TOP 5 (수평 bar)  ※ 기존 IP대역 차트 자리 그대로 사용
    const ctxIp = document.getElementById("chart-ip-band")?.getContext("2d");
    if (ctxIp) {
      const typeRatio = summary.type_ratio || {};

      // {LABEL: count} → [[label, count], ...] 정렬 후 TOP 5
      const top5 = Object.entries(typeRatio)
        .filter(([, v]) => typeof v === "number")
        .sort((a, b) => b[1] - a[1])
        .slice(0, 5);

      const labels = top5.map(([k]) => k);
      const data = top5.map(([, v]) => v);

      if (chartIpBand) chartIpBand.destroy();
      chartIpBand = new Chart(ctxIp, {
        type: "bar",
        data: {
          labels,
          datasets: [{ label: "탐지 건수", data }],
        },
        options: {
          indexAxis: "y",
          responsive: true,
          maintainAspectRatio: false,
          scales: { x: { beginAtZero: true } },
        },
      });
    }

    // 4) 전체 유형 비율 (도넛)
    const ctxTypeRatio = document
      .getElementById("chart-type-ratio")
      ?.getContext("2d");
    if (ctxTypeRatio) {
      const typeRatio = summary.type_ratio || {};
      const labels = Object.keys(typeRatio);
      const data = Object.values(typeRatio);

      if (chartTypeRatio) chartTypeRatio.destroy();
      chartTypeRatio = new Chart(ctxTypeRatio, {
        type: "doughnut",
        data: {
          labels,
          datasets: [{ data }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
        },
      });
    }

    // 5) 금일 시간대별 탐지 (line)
    const ctxTodayHourly = document
      .getElementById("chart-today-hourly")
      ?.getContext("2d");
    if (ctxTodayHourly) {
      // today_hourly가 있으면 그걸, 없으면 전체 hourly_attempts 사용
      const todayHourlyRaw =
        summary.today_hourly || summary.hourly_attempts || [];

      const labels = Array.from({ length: 24 }, (_, i) => `${i}:00`);
      const data = labels.map((_, i) => todayHourlyRaw[i] || 0);

      if (chartTodayHourly) chartTodayHourly.destroy();
      chartTodayHourly = new Chart(ctxTodayHourly, {
        type: "line",
        data: {
          labels,
          datasets: [{ label: "탐지 건수", data }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: { y: { beginAtZero: true } },
        },
      });
    }

    // 6) 금일 유형 비율 (pie)
    const ctxTodayType = document
      .getElementById("chart-today-type")
      ?.getContext("2d");
    if (ctxTodayType) {
      const todayTypeRatio =
        summary.today_type_ratio || summary.type_ratio || {};
      const labels = Object.keys(todayTypeRatio);
      const data = Object.values(todayTypeRatio);

      if (chartTodayType) chartTodayType.destroy();
      chartTodayType = new Chart(ctxTodayType, {
        type: "pie",
        data: {
          labels,
          datasets: [{ data }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
        },
      });
    }

    // 7) 시간대별 유형 (stacked bar) — summary.hourly_type 이 있을 때만
    const ctxHourlyType = document
      .getElementById("chart-hourly-type")
      ?.getContext("2d");
    if (ctxHourlyType && summary.hourly_type) {
      const hours = Object.keys(summary.hourly_type); // "0","1",...
      const typeNames = new Set();
      hours.forEach((h) => {
        Object.keys(summary.hourly_type[h]).forEach((t) => typeNames.add(t));
      });

      const labels = hours.map((h) => `${h}:00`);
      const datasets = Array.from(typeNames).map((type) => ({
        label: type,
        data: hours.map((h) => summary.hourly_type[h][type] || 0),
        stack: "stack1",
      }));

      if (chartHourlyType) chartHourlyType.destroy();
      chartHourlyType = new Chart(ctxHourlyType, {
        type: "bar",
        data: { labels, datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            x: { stacked: true },
            y: { stacked: true, beginAtZero: true },
          },
        },
      });
    }

    // 8) 로그 테이블 (Top 10)  ✅ 컬럼: 시간 / 서비스명 / PC이름 / Public IP / Internal IP / 처리결과 / 탐지정보내역
    if (logTableBody) {
      logTableBody.innerHTML = "";
      const logs = summary.recent_logs || [];
      logs.slice(0, 10).forEach((log) => {
        const tr = document.createElement("tr");

        const time = log.created_at || log.time || "";
        const host = log.host || "-";
        const pcName = log.hostname || log.pc_name || "-";
        const publicIp = log.public_ip || "-";
        const internalIp = log.internal_ip || "-";

        // 처리 결과: allow → 접속 허용 (그 외엔 기존 action 표시)
        let result = "-";
        if (log.allow === true || log.allow === false) {
          result = log.allow ? "접속 허용" : "차단";
        } else if (log.action) {
          result = log.action;
        }

        const labels =
          (log.entities || [])
            .map((e) => e.label || e.type)
            .filter(Boolean)
            .join(", ") || "-";

        tr.innerHTML = `
          <td>${time}</td>
          <td>${host}</td>
          <td>${pcName}</td>
          <td>${publicIp}</td>
          <td>${internalIp}</td>
          <td>${result}</td>
          <td>${labels}</td>
        `;
        logTableBody.appendChild(tr);
      });
    }

    setNowForHeader();
  }

  async function init() {
    // 관리자 키 없으면 로그인 페이지로
    if (!window.SentinelApi.getAdminKey()) {
      window.location.href = "./index.html";
      return;
    }

    await loadSummary();

    if (btnRefresh) {
      btnRefresh.addEventListener("click", () => {
        loadSummary().catch((err) => {
          console.error(err);
          alert("데이터를 새로고침하는 중 오류가 발생했습니다.");
        });
      });
    }

    if (btnLogout) {
      btnLogout.addEventListener("click", () => {
        window.SentinelApi.setAdminKey("");
        window.location.href = "./index.html";
      });
    }

    // 상단 시간 표시 주기적 업데이트
    setInterval(setNowForHeader, 1000);
  }

  init().catch((err) => {
    console.error(err);
    alert("대시보드를 초기화하는 중 오류가 발생했습니다.");
  });
});
