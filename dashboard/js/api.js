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
  //   - 사용 예: fetchSummary({ interface: "LLM" })
  // -------------------------
  function fetchSummary(params = {}) {
    return apiGet("/summary", params);
  }

  // -------------------------
  // /report/llm/file-summary 전용 헬퍼
  //   - 사용 예: fetchLlmFileSummary()
  // -------------------------
  function fetchLlmFileSummary() {
    return apiGet("/report/llm/file-summary");
  }

  // -------------------------
  // /logs 전용 헬퍼
  //   - 사용 예: fetchLogs({ page: 1, page_size: 20, q: "chatgpt.com", category: "host" })
  // -------------------------
  function fetchLogs(params = {}) {
    const base = { page: 1, page_size: 20 };
    return apiGet("/logs", Object.assign(base, params || {}));
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
  };

  // 우리가 주로 쓸 이름
  global.SentinelApi = api;
  // 혹시 다른 파일에서 SentinelAPI 로 잘못 쓴 경우도 대응
  global.SentinelAPI = api;
})(window);
