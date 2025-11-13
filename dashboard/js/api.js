// dashboard/js/api.js
(function (global) {
  const API_BASE = "/api";
  const STORAGE_KEY = "sentinel_admin_key";

  function getAdminKey() {
    return window.localStorage.getItem(STORAGE_KEY) || "";
  }

  function setAdminKey(key) {
    if (key) {
      window.localStorage.setItem(STORAGE_KEY, key);
    } else {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  }

  async function apiGet(path) {
    const headers = {
      "Content-Type": "application/json",
    };
    const adminKey = getAdminKey();
    if (adminKey) {
      headers["X-Admin-Key"] = adminKey;
    }

    const res = await fetch(API_BASE + path, { headers });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`API ${path} failed: ${res.status} ${text}`);
    }
    return res.json();
  }

  global.SentinelApi = {
    getAdminKey,
    setAdminKey,
    get: apiGet,
  };
})(window);
