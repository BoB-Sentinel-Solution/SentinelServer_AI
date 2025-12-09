// dashboard/js/api.js
(function (global) {
  const API_BASE = "/api";
  const STORAGE_KEY = "sentinel_admin_key";

  // -------------------------
  // Admin Key 저장/조회
  // -------------------------
  function getAdminKey() {
    try {
      return window.localStorage.getItem(STORAGE_KEY) || "";
    } catch (e) {
      return "";
    }
  }

  function setAdminKey(key) {
    try {
      if (key) {
        window.localStorage.setItem(STORAGE_KEY, key);
      } else {
        window.localStorage.removeItem(STORAGE_KEY);
      }
    } catch (e) {
      // localStorage 사용 불가한 환경이면 조용히 무시
    }
  }

  // -------------------------
  // 공통 GET 호출 유틸
  //   - path: "/summary", "/logs" 등
  //   - params: { interface: "LLM", page: 1 } 형태 (선택)
  // -------------------------
  async function apiGet(path, params) {
    let url = API_BASE + path;

    if (params && Object.keys(params).length > 0) {
      const qs = new URLSearchParams(params);
      url += (url.includes("?") ? "&" : "?") + qs.toString();
    }

    const headers = {
      "Content-Type": "application/json",
    };

    const adminKey = getAdminKey();
    if (adminKey) {
      headers["X-Admin-Key"] = adminKey;
    }

    const res = await fetch(url, { headers });

    if (!res.ok) {
      // 인증 실패(401)이면 키를 지워 버리고 에러를 던짐
      if (res.status === 401) {
        setAdminKey("");
      }
      const text = await res.text();
      throw new Error(`API ${path} failed: ${res.status} ${text}`);
    }

    return res.json();
  }

  // -------------------------
  // /summary 전용 헬퍼
  // -------------------------
  function fetchSummary(params = {}) {
    return apiGet("/summary", params);
  }

  // -------------------------
  // /report/llm/file-summary 전용 헬퍼
  // -------------------------
  function fetchLlmFileSummary() {
    return apiGet("/report/llm/file-summary");
  }

  // -------------------------
  // /logs 전용 헬퍼
  // -------------------------
  function fetchLogs(params = {}) {
    const base = { page: 1, page_size: 20 };
    return apiGet("/logs", Object.assign(base, params || {}));
  }

  // -------------------------
  // /reason/top5 전용 헬퍼
  // -------------------------
  function fetchReasonTop5() {
    return apiGet("/reason/top5");
  }

  // -------------------------
  // /reason/summary 전용 헬퍼
  //   params: { pc_name, host?, interface? }
  // -------------------------
  function fetchReasonSummary(params = {}) {
    return apiGet("/reason/summary", params);
  }

  // 전역 객체로 노출
  const api = {
    getAdminKey,
    setAdminKey,
    // 공통 GET
    get: apiGet,
    // 편의 함수들
    fetchSummary,
    fetchLlmFileSummary,
    fetchLogs,
    fetchReasonTop5,
    fetchReasonSummary,
  };

  global.SentinelApi = api;
  global.SentinelAPI = api; // 오타 대비

  // ---- 기존 코드 호환용: 개별 함수도 전역으로 직접 노출 ----
  global.fetchSummary = fetchSummary;
  global.fetchLlmFileSummary = fetchLlmFileSummary;
  global.fetchLogs = fetchLogs;
  global.fetchReasonTop5 = fetchReasonTop5;
  global.fetchReasonSummary = fetchReasonSummary;
})(window);
