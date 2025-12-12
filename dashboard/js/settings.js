// dashboard/js/settings.js
(function () {
  const API_BASE = "/api";
  const STORAGE_KEY = "sentinel_admin_key";

  function getAdminKey() {
    try { return localStorage.getItem(STORAGE_KEY) || ""; }
    catch { return ""; }
  }

  async function apiGet(path) {
    const r = await fetch(API_BASE + path, {
      method: "GET",
      headers: { "X-Admin-Key": getAdminKey() }
    });
    if (r.status === 401) {
      location.href = "./index.html";
      return null;
    }
    if (!r.ok) throw new Error("GET " + path + " failed: " + r.status);
    return await r.json();
  }

  async function apiPut(path, body) {
    const r = await fetch(API_BASE + path, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "X-Admin-Key": getAdminKey()
      },
      body: JSON.stringify(body)
    });
    if (r.status === 401) {
      location.href = "./index.html";
      return null;
    }
    if (r.status === 409) {
      const msg = await r.text();
      throw new Error("버전 충돌(다른 곳에서 설정이 바뀜). 새로고침 후 다시 저장.\n" + msg);
    }
    if (!r.ok) throw new Error("PUT " + path + " failed: " + r.status);
    return await r.json();
  }

  function setUpdatedAtKST() {
    const el = document.getElementById("top-updated-at");
    if (!el) return;
    const now = new Date();
    el.textContent = now.toLocaleTimeString("ko-KR", { hour12: false }) + " KST";
  }

  function readRadio(name) {
    const el = document.querySelector(`input[name="${name}"]:checked`);
    return el ? el.value : "";
  }
  function writeRadio(name, value) {
    const el = document.querySelector(`input[name="${name}"][value="${value}"]`);
    if (el) el.checked = true;
  }

  function loadUiTheme() {
    const saved = (localStorage.getItem("sentinel_theme") || "light");
    writeRadio("ui_theme", saved);
    document.documentElement.dataset.theme = saved; // CSS에서 [data-theme="dark"] 같은 식으로 쓰기 좋음
  }

  function saveUiTheme() {
    const t = readRadio("ui_theme") || "light";
    localStorage.setItem("sentinel_theme", t);
    document.documentElement.dataset.theme = t;
  }

  function applySettingsToUI(payload) {
    const cfg = payload?.config || {};
    const services = cfg.services || {};
    const llm = services.llm || {};
    const mcp = services.mcp || {};

    writeRadio("response_method", cfg.response_method || "mask");

    // LLM
    setCheck("llm-gpt", !!llm.gpt);
    setCheck("llm-gemini", !!llm.gemini);
    setCheck("llm-claude", !!llm.claude);
    setCheck("llm-deepseek", !!llm.deepseek);
    setCheck("llm-groq", !!llm.groq);

    // MCP
    setCheck("mcp-gpt-desktop", !!mcp.gpt_desktop);
    setCheck("mcp-claude-desktop", !!mcp.claude_desktop);
    setCheck("mcp-vscode", !!mcp.vscode);
  }

  function setCheck(id, v) {
    const el = document.getElementById(id);
    if (el) el.checked = !!v;
  }
  function getCheck(id) {
    const el = document.getElementById(id);
    return !!(el && el.checked);
  }

  function collectSettingsFromUI(currentVersion) {
    const response_method = readRadio("response_method") || "mask";

    const config = {
      response_method,
      services: {
        llm: {
          gpt: getCheck("llm-gpt"),
          gemini: getCheck("llm-gemini"),
          claude: getCheck("llm-claude"),
          deepseek: getCheck("llm-deepseek"),
          groq: getCheck("llm-groq"),
        },
        mcp: {
          gpt_desktop: getCheck("mcp-gpt-desktop"),
          claude_desktop: getCheck("mcp-claude-desktop"),
          vscode: getCheck("mcp-vscode"),
        }
      }
    };

    return { config, version: currentVersion };
  }

  let serverVersion = null;

  async function refresh() {
    setUpdatedAtKST();
    const data = await apiGet("/settings");
    if (!data) return;
    serverVersion = data.version;
    applySettingsToUI(data);
  }

  async function onSave() {
    saveUiTheme(); // UI는 로컬 저장

    const body = collectSettingsFromUI(serverVersion);
    const saved = await apiPut("/settings", body);
    if (!saved) return;

    serverVersion = saved.version;
    applySettingsToUI(saved);
    alert("저장 완료");
  }

  function bind() {
    const btnRefresh = document.getElementById("btn-refresh");
    if (btnRefresh) btnRefresh.addEventListener("click", refresh);

    const btnSave = document.getElementById("btn-save");
    if (btnSave) btnSave.addEventListener("click", () => onSave().catch(e => alert(e.message)));

    const btnLogout = document.getElementById("btn-logout");
    if (btnLogout) btnLogout.addEventListener("click", () => {
      try { localStorage.removeItem(STORAGE_KEY); } catch {}
      location.href = "./index.html";
    });
  }

  // init
  bind();
  loadUiTheme();
  refresh().catch(e => alert(e.message));
})();
