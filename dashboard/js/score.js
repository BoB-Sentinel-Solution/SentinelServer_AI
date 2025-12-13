// dashboard/js/score.js

// ===== 전역 Chart 인스턴스 (리프레시 시 destroy 용) =====
let score7dRiskChart = null;
let score7dTrafficChart = null;

// LABEL → 한글 설명 매핑
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
  MILITARY_ID: "군번",

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
  MNEMONIC: "니모닉(지갑 복구키)",
  CRYPTO_PRIVATE_KEY: "암호화폐 개인키",
  HD_WALLET: "HD 월렛키",

  IPV4: "IPv4",
  IPV6: "IPv6",
  MAC_ADDRESS: "MAC 주소",
  IMEI: "IMEI",

  OTHER: "기타",
};

document.addEventListener("DOMContentLoaded", () => {
  const updatedAtEl = document.getElementById("top-updated-at");
  const btnRefresh = document.getElementById("btn-refresh");
  const btnLogout = document.getElementById("btn-logout");

  const apiModule = window.SentinelApi || window.SentinelAPI || {};
  const getAdminKey = apiModule.getAdminKey || window.getAdminKey || (() => "");
  const setAdminKey = apiModule.setAdminKey || window.setAdminKey || (() => {});
  const fetchLogs = apiModule.fetchLogs || window.fetchLogs || null;

  // --------------- 상단 UPDATED 시계 ---------------
  function pad(n) {
    return n.toString().padStart(2, "0");
  }

  function updateClock() {
    const now = new Date();
    if (updatedAtEl) {
      updatedAtEl.textContent = `${pad(now.getHours())}:${pad(
        now.getMinutes()
      )}:${pad(now.getSeconds())} KST`;
    }
  }
  updateClock();
  setInterval(updateClock, 1000);

  // --------------- 로그아웃 버튼 ---------------
  if (btnLogout) {
    btnLogout.addEventListener("click", () => {
      setAdminKey("");
      window.location.href = "./index.html";
    });
  }

  // --------------- 메인 로딩 함수 ---------------
  async function loadScoreDashboard() {
    // 관리자 키 없으면 로그인 페이지로 이동
    if (!getAdminKey()) {
      window.location.href = "./index.html";
      return;
    }

    if (typeof fetchLogs !== "function") {
      console.error("fetchLogs 가 정의되어 있지 않습니다.");
      return;
    }

    try {
      // 최근 로그 N개(예: 500개)만으로 7일 통계 근사
      const resp = await fetchLogs({ page: 1, page_size: 500 });
      const logs = Array.isArray(resp?.items) ? resp.items : [];

      // 일자별 통계/오늘 통계/Top 리스트/고위험 이벤트 추출
      const stats = buildDailyStats(logs);

      // 오늘 위험 지수 계산 및 UI 반영
      renderTodayRisk(stats);

      // 최근 7일 Risk Score & 사용량 차트
      render7dRiskChart(stats);
      render7dTrafficChart(stats);

      // 오늘 위험 기여 Top Host / Label
      renderTopHostsToday(stats);
      renderTopLabelsToday(stats);

      // 오늘 고위험 이벤트 타임라인
      renderHighRiskTimeline(stats);
    } catch (err) {
      console.error("score dashboard load error:", err);
      alert("오늘의 위험 지수 데이터를 불러오는 중 오류가 발생했습니다.");
    }
  }

  if (btnRefresh) {
    btnRefresh.addEventListener("click", () => {
      loadScoreDashboard();
    });
  }

  // 초기 로딩
  loadScoreDashboard();
});

// ======= 유틸 함수들 =======

// ISO 문자열 → 브라우저 로컬 기준 'YYYY-MM-DD'
function getLocalDateKey(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return null;
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

// 오늘 날짜 키 (브라우저 로컬 기준)
function getTodayKey() {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

// 고위험 여부 판별
function getHighRiskReason(log) {
  const action = (log.action || "").toLowerCase();
  const allow = log.allow;
  const fileBlocked = !!log.file_blocked;
  const entsRaw = Array.isArray(log.entities) ? log.entities : [];
  const labels = entsRaw
    .map((e) => (e.label || e.type || "").toUpperCase())
    .filter(Boolean);

  if (allow === false || action.startsWith("block")) {
    return "차단 정책이 적용된 요청";
  }
  if (fileBlocked) {
    return "파일 유사 차단 또는 파일 기반 차단 발생";
  }
  if (labels.length >= 3) {
    return "다수의 중요정보 LABEL이 동시에 탐지됨";
  }

  const highRiskLabels = new Set([
    "RESIDENT_ID",
    "CARD_NUMBER",
    "CRYPTO_PRIVATE_KEY",
    "MNEMONIC",
    "PAYMENT_PIN",
    "MOBILE_PAYMENT_PIN",
    "PASSPORT",
    "DRIVER_LICENSE",
    "HEALTH_INSURANCE_ID",
  ]);

  if (labels.some((lab) => highRiskLabels.has(lab))) {
    return "고위험 LABEL 포함 (주민번호, 카드번호, 지갑키 등)";
  }

  return null;
}

// 등급 정보
function getRiskLevelInfo(score) {
  let label = "정상";
  let desc = "평소 수준의 사용 패턴. 별도 조치 필요 없음.";
  let badgeClass = "score-level-badge--blue";

  if (score >= 85) {
    label = "위험";
    desc = "계정 잠금, 규칙 강화 등 강한 보안 조치 검토 필요.";
    badgeClass = "score-level-badge--red";
  } else if (score >= 70) {
    label = "경계";
    desc = "특정부서/계정 집중 점검 및 로그 상세 분석 필요.";
    badgeClass = "score-level-badge--orange";
  } else if (score >= 50) {
    label = "주의";
    desc = "중요정보 사용량 증가. 가이드/공지 재배포 고려.";
    badgeClass = "score-level-badge--yellow";
  } else if (score >= 30) {
    label = "관심";
    desc = "일시적인 증가. 특정 사용자/호스트 모니터링 권장.";
    badgeClass = "score-level-badge--green";
  }

  return { label, desc, badgeClass };
}

// Score₁, Score₂, 최종 Risk Score 계산
function computeScores(T_today, T_avg7d, T_total_today) {
  const denomAvg = Math.max(T_avg7d, 1);
  const R = T_today / denomAvg;
  let score1 = R * 25;
  if (score1 > 50) score1 = 50;

  const denomTotal = Math.max(T_total_today, 1);
  const r = T_today / denomTotal;
  let score2 = r * 100;
  if (score2 > 50) score2 = 50;

  const finalScore = Math.min(100, Math.round(score1 + score2));

  return {
    score1: Math.round(score1),
    score2: Math.round(score2),
    finalScore,
  };
}

// ======= 로그 → 일자별 통계 빌드 =======

function buildDailyStats(logs) {
  const dayStats = {};
  const todayKey = getTodayKey();
  const highRiskLogsToday = [];

  logs.forEach((log) => {
    const iso = log.time || log.created_at || log.timestamp;
    const dayKey = getLocalDateKey(iso);
    if (!dayKey) return;

    if (!dayStats[dayKey]) {
      dayStats[dayKey] = {
        total: 0,
        sensitive: 0,
        hosts: {}, // pairKey -> { host, pc, total, sensitive }
        labels: {}, // label -> count
      };
    }
    const stat = dayStats[dayKey];
    stat.total += 1;

    // ---- (수정) host/pc 분리 후 pairKey로 집계 ----
    const host = (log.host || "UNKNOWN").trim() || "UNKNOWN";
    const pc =
      (log.hostname || log.PCName || log.pc_name || "UNKNOWN").trim() ||
      "UNKNOWN";
    const pairKey = `${host}|||${pc}`;

    if (!stat.hosts[pairKey]) {
      stat.hosts[pairKey] = { host, pc, total: 0, sensitive: 0 };
    }
    stat.hosts[pairKey].total += 1;

    if (log.has_sensitive) {
      stat.sensitive += 1;
      stat.hosts[pairKey].sensitive += 1;

      const ents = Array.isArray(log.entities) ? log.entities : [];
      ents.forEach((e) => {
        const lab = (e.label || e.type || "OTHER").toUpperCase();
        stat.labels[lab] = (stat.labels[lab] || 0) + 1;
      });
    }

    // 오늘 고위험 이벤트 수집
    if (dayKey === todayKey) {
      const reason = getHighRiskReason(log);
      if (reason) {
        highRiskLogsToday.push({ log, reason });
      }
    }
  });

  // 최근 7일 키 정렬
  const allKeys = Object.keys(dayStats).sort(); // YYYY-MM-DD 기준 오름차순
  const last7Keys = allKeys.slice(-7);

  // 7일 평균 탐지 건수 계산
  let sumSensitive = 0;
  last7Keys.forEach((k) => {
    sumSensitive += dayStats[k].sensitive || 0;
  });
  const avg7dSensitive = last7Keys.length > 0 ? sumSensitive / last7Keys.length : 0;

  return {
    todayKey,
    dayStats,
    last7Keys,
    avg7dSensitive,
    highRiskLogsToday,
  };
}

// ======= 1. 오늘 위험 지수 렌더링 =======

function renderTodayRisk(stats) {
  const todayKey = stats.todayKey;
  const dayStats = stats.dayStats;
  const last7Keys = stats.last7Keys;
  const avg7dSensitive = stats.avg7dSensitive;

  const todayStat = dayStats[todayKey] || {
    total: 0,
    sensitive: 0,
    hosts: {},
    labels: {},
  };

  const T_today = todayStat.sensitive || 0;
  const T_total_today = todayStat.total || 0;
  const T_avg7d = avg7dSensitive;

  const { score1, score2, finalScore } = computeScores(T_today, T_avg7d, T_total_today);

  // DOM 엘리먼트
  const valueEl = document.getElementById("risk-score-value");
  const badgeEl = document.getElementById("risk-score-level-badge");
  const levelTextEl = document.getElementById("risk-score-level-text");
  const descEl = document.getElementById("risk-score-description");

  const todaySensitiveEl = document.getElementById("score-today-sensitive");
  const avg7dEl = document.getElementById("score-avg7d-sensitive");
  const todayTotalEl = document.getElementById("score-today-total");
  const todayRatioEl = document.getElementById("score-today-ratio");

  const part1El = document.getElementById("score-part1-value");
  const part2El = document.getElementById("score-part2-value");
  const finalEl = document.getElementById("score-final-value");

  if (valueEl) valueEl.textContent = String(finalScore);
  if (todaySensitiveEl) todaySensitiveEl.textContent = String(T_today);
  if (avg7dEl) avg7dEl.textContent = last7Keys.length > 0 ? avg7dSensitive.toFixed(1) : "-";
  if (todayTotalEl) todayTotalEl.textContent = String(T_total_today);

  if (todayRatioEl) {
    if (T_total_today > 0) {
      const ratioPct = ((T_today / T_total_today) * 100).toFixed(1);
      todayRatioEl.textContent = `${ratioPct}%`;
    } else {
      todayRatioEl.textContent = "-";
    }
  }

  if (part1El) part1El.textContent = String(score1);
  if (part2El) part2El.textContent = String(score2);
  if (finalEl) finalEl.textContent = String(finalScore);

  const { label, desc, badgeClass } = getRiskLevelInfo(finalScore);

  if (badgeEl) {
    // 기존 클래스 제거 후 새 등급 클래스 추가
    badgeEl.className = "score-level-badge " + badgeClass;
    badgeEl.textContent = label;
  }
  if (levelTextEl) {
    levelTextEl.textContent = `현재 등급: ${label}`;
  }
  if (descEl) {
    descEl.textContent = desc;
  }
}

// ======= 2. 최근 7일 Risk Score 추이 차트 =======

function render7dRiskChart(stats) {
  const canvas = document.getElementById("score-chart-7d-risk");
  if (!canvas) return;

  const { dayStats, last7Keys, avg7dSensitive } = stats;

  const labels = last7Keys.map((k) => {
    // 'MM/DD'로 간단히 표기
    const [, m, d] = k.split("-");
    return `${m}/${d}`;
  });

  const riskValues = last7Keys.map((k) => {
    const s = dayStats[k];
    const T_day = s ? s.sensitive || 0 : 0;
    const T_total_day = s ? s.total || 0 : 0;
    const { finalScore } = computeScores(T_day, avg7dSensitive, T_total_day);
    return finalScore;
  });

  if (score7dRiskChart) {
    score7dRiskChart.destroy();
    score7dRiskChart = null;
  }

  const ctx = canvas.getContext("2d");
  score7dRiskChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Risk Score",
          data: riskValues,
          tension: 0.3,
          borderWidth: 2,
          pointRadius: 3,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          beginAtZero: true,
          suggestedMax: 100,
          ticks: { stepSize: 20 },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => `Risk Score: ${ctx.parsed.y}`,
          },
        },
      },
    },
  });
}

// ======= 3. 최근 7일 탐지·사용량 추이 차트 =======

function render7dTrafficChart(stats) {
  const canvas = document.getElementById("score-chart-7d-traffic");
  if (!canvas) return;

  const { dayStats, last7Keys } = stats;

  const labels = last7Keys.map((k) => {
    const [, m, d] = k.split("-");
    return `${m}/${d}`;
  });

  const totalValues = last7Keys.map((k) => dayStats[k].total || 0);
  const sensitiveValues = last7Keys.map((k) => dayStats[k].sensitive || 0);

  if (score7dTrafficChart) {
    score7dTrafficChart.destroy();
    score7dTrafficChart = null;
  }

  const ctx = canvas.getContext("2d");
  score7dTrafficChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "전체 프롬프트 수",
          data: totalValues,
          tension: 0.3,
          borderWidth: 2,
          pointRadius: 2,
          yAxisID: "y1",
        },
        {
          label: "중요정보 탐지 건수",
          data: sensitiveValues,
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
          title: { display: true, text: "전체 프롬프트 수" },
        },
        y2: {
          position: "right",
          beginAtZero: true,
          ticks: { precision: 0 },
          grid: { drawOnChartArea: false },
          title: { display: true, text: "탐지 건수" },
        },
      },
      plugins: {
        legend: {
          position: "bottom",
        },
        tooltip: {
          callbacks: {
            label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y}건`,
          },
        },
      },
    },
  });
}

// ======= 4. 오늘 위험 기여 Top 서비스/PC =======

function renderTopHostsToday(stats) {
  const tbody = document.getElementById("score-top-hosts-body");
  if (!tbody) return;

  const todayStat = stats.dayStats[stats.todayKey];
  if (!todayStat || todayStat.total === 0) {
    tbody.innerHTML = '<tr><td colspan="5">오늘 기록된 로그가 없습니다.</td></tr>';
    return;
  }

  // ---- (수정) hosts가 pairKey -> {host, pc, total, sensitive} 형태 ----
  const rows = Object.values(todayStat.hosts).map((val) => {
    const total = val.total || 0;
    const sens = val.sensitive || 0;
    const ratio = total > 0 ? sens / total : 0;
    return { host: val.host, pc: val.pc, total, sens, ratio };
  });

  rows.sort((a, b) => {
    // 비율 우선, 동률이면 탐지 건수 많은 순
    if (b.ratio !== a.ratio) return b.ratio - a.ratio;
    return (b.sens || 0) - (a.sens || 0);
  });

  const top = rows.slice(0, 5);

  if (!top.length) {
    tbody.innerHTML = '<tr><td colspan="5">오늘 탐지된 로그가 없습니다.</td></tr>';
    return;
  }

  tbody.innerHTML = "";
  top.forEach((row, idx) => {
    const tr = document.createElement("tr");

    const pcName = row.pc === "UNKNOWN" ? "-" : row.pc;

    const ratioPct = row.total
      ? ((row.sens / row.total) * 100).toFixed(1) + "%"
      : "-";

    appendCell(tr, String(idx + 1));
    appendCell(tr, row.host);
    appendCell(tr, pcName);
    appendCell(tr, String(row.sens));
    appendCell(tr, ratioPct);

    tbody.appendChild(tr);
  });
}

// ======= 5. 오늘 많이 탐지된 LABEL =======

function renderTopLabelsToday(stats) {
  const tbody = document.getElementById("score-top-labels-body");
  if (!tbody) return;

  const todayStat = stats.dayStats[stats.todayKey];
  if (!todayStat || !todayStat.labels) {
    tbody.innerHTML = '<tr><td colspan="4">오늘 탐지된 중요정보 LABEL이 없습니다.</td></tr>';
    return;
  }

  const entries = Object.entries(todayStat.labels);
  if (!entries.length) {
    tbody.innerHTML = '<tr><td colspan="4">오늘 탐지된 중요정보 LABEL이 없습니다.</td></tr>';
    return;
  }

  entries.sort((a, b) => b[1] - a[1]);
  const top = entries.slice(0, 7);

  tbody.innerHTML = "";
  top.forEach(([label, count], idx) => {
    const tr = document.createElement("tr");
    const kr = LABEL_KR_MAP[label] || label;

    appendCell(tr, String(idx + 1));
    appendCell(tr, label);
    appendCell(tr, String(count));
    appendCell(tr, kr);

    tbody.appendChild(tr);
  });
}

// ======= 6. 오늘 고위험 이벤트 타임라인 =======

function renderHighRiskTimeline(stats) {
  const tbody = document.getElementById("score-high-risk-logs-body");
  if (!tbody) return;

  const high = stats.highRiskLogsToday || [];
  if (!high.length) {
    tbody.innerHTML = '<tr><td colspan="7">오늘 고위험 이벤트가 아직 없습니다.</td></tr>';
    return;
  }

  tbody.innerHTML = "";
  high
    .sort((a, b) => {
      const ta = a.log.time || "";
      const tb = b.log.time || "";
      return ta.localeCompare(tb);
    })
    .forEach(({ log, reason }) => {
      const tr = document.createElement("tr");
      const iso = log.time || log.created_at || "";

      appendCell(tr, formatTime(iso));
      appendCell(tr, log.host || "");
      appendCell(tr, log.hostname || "");
      appendCell(tr, log.public_ip || "");
      appendCell(tr, log.action || "");
      appendCell(
        tr,
        (Array.isArray(log.entities) ? log.entities : [])
          .map((e) => e.label || e.type || "")
          .filter(Boolean)
          .join(", ")
      );
      appendCell(tr, reason);

      tbody.appendChild(tr);
    });
}

// ======= 공통 DOM 유틸 =======

function appendCell(tr, text) {
  const td = document.createElement("td");
  td.textContent = text == null ? "" : String(text);
  tr.appendChild(td);
  return td;
}

function formatTime(iso) {
  if (!iso || typeof iso !== "string") return "";
  // "YYYY-MM-DDTHH:MM:SS" → "YYYY-MM-DD HH:MM:SS"
  return iso.replace("T", " ").slice(0, 19);
}
