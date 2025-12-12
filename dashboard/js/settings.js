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
    // 계정 변경 쪽에서 400/403 같은 에러 메시지 받을 수 있어서 본문도 같이 보여줌
    if (!r.ok) {
      let msg = "";
      try { msg = await r.text(); } catch {}
      throw new Error("PUT " + path + " failed: " + r.status + (msg ? ("\n" + msg) : ""));
    }
    // settings는 json 반환, account도 json 반환 전제
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
    document.documentElement.dataset.theme = saved;
  }

  function saveUiTheme() {
    const t = readRadio("ui_theme") || "light";
    localStorage.setItem("sentinel_theme", t);
    document.documentElement.dataset.theme = t;
  }

  function setCheck(id, v) {
    const el = document.getElementById(id);
    if (el) el.checked = !!v;
  }
  function getCheck(id) {
    const el = document.getElementById(id);
    return !!(el && el.checked);
  }

  // =========================
  // 서버 설정 구조에 맞춰 적용
  // =========================
  // 서버(db_logging.py)가 기대:
  // config = {
  //   response_method: "mask" | "allow" | "block",
  //   service_filters: {
  //     llm: { gpt, gemini, claude, deepseek, groq },
  //     mcp: { gpt_desktop, claude_desktop, vscode_copilot }
  //   }
  // }
  function applySettingsToUI(payload) {
    const cfg = payload?.config || {};

    // ✅ 서버키: service_filters
    const sf = cfg.service_filters || {};
    const llm = sf.llm || {};
    const mcp = sf.mcp || {};

    // response_method
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
    // ✅ 서버키: vscode_copilot (UI id는 mcp-vscode 그대로)
    setCheck("mcp-vscode", !!mcp.vscode_copilot);
  }

  function collectSettingsFromUI(currentVersion) {
    const response_method = readRadio("response_method") || "mask";

    const config = {
      response_method,
      // ✅ 서버키: service_filters
      service_filters: {
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
          // ✅ 서버키: vscode_copilot
          vscode_copilot: getCheck("mcp-vscode"),
        }
      }
    };

    return { config, version: currentVersion };
  }

  // =========================
  // Account panel (ID / Password)
  // =========================
  function getVal(id) {
    const el = document.getElementById(id);
    return (el && typeof el.value === "string") ? el.value.trim() : "";
  }
  function clearVal(id) {
    const el = document.getElementById(id);
    if (el && typeof el.value === "string") el.value = "";
  }

  // ✅ 비밀번호 변경: 서버에 실제 반영되게 하려면 서버에 이 API가 있어야 함
  // PUT /api/account/password
  // body: { current_password: "...", new_password: "..." }
  async function changePassword() {
    const cur = getVal("acc-current-password");
    const p1  = getVal("acc-new-password");
    const p2  = getVal("acc-new-password2");

    if (!cur) throw new Error("현재 비밀번호를 입력해줘.");
    if (!p1 || !p2) throw new Error("새 비밀번호를 입력해줘.");
    if (p1 !== p2) throw new Error("새 비밀번호 확인이 일치하지 않아.");
    if (p1.length < 8) throw new Error("새 비밀번호는 8자 이상으로 해줘.");

    // 서버 반영
    await apiPut("/account/password", {
      current_password: cur,
      new_password: p1,
    });

    clearVal("acc-current-password");
    clearVal("acc-new-password");
    clearVal("acc-new-password2");
    alert("비밀번호 변경 완료");
  }

  // (선택) 아이디 변경까지 하려면 서버에 API가 필요함
  // PUT /api/account/username
  // body: { new_username: "...", current_password: "..." }
  async function changeUsername() {
    const newId = getVal("acc-new-id");
    const curPw = getVal("acc-current-password-for-id"); // HTML에서 따로 둘 때

    if (!newId) throw new Error("새 아이디를 입력해줘.");
    if (!curPw) throw new Error("현재 비밀번호를 입력해줘.");

    await apiPut("/account/username", {
      new_username: newId,
      current_password: curPw,
    });

    clearVal("acc-new-id");
    clearVal("acc-current-password-for-id");
    alert("아이디 변경 완료");
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
    saveUiTheme(); // UI만 로컬 저장

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

    // Account panel buttons
    const btnPw = document.getElementById("btn-change-password");
    if (btnPw) btnPw.addEventListener("click", () => changePassword().catch(e => alert(e.message)));

    // 아이디 변경까지 UI에 넣는 경우에만 사용
    const btnId = document.getElementById("btn-change-id");
    if (btnId) btnId.addEventListener("click", () => changeUsername().catch(e => alert(e.message)));
  }

  // init
  bind();
  loadUiTheme();
  refresh().catch(e => alert(e.message));
})();
