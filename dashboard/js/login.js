// dashboard/js/login.js
document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("login-form");
  const errorEl = document.getElementById("login-error");

  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (errorEl) errorEl.hidden = true;

    const data = new FormData(form);
    const username = (data.get("username") || "").toString().trim(); // ✅ 변경: username
    const password = (data.get("password") || "").toString().trim();

    if (!username || !password) {
      if (errorEl) {
        errorEl.textContent = "아이디와 비밀번호를 모두 입력해 주세요.";
        errorEl.hidden = false;
      }
      return;
    }

    try {
      // ✅ 서버 auth API로 로그인해서 api_key 받기
      const r = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });

      if (!r.ok) {
        let msg = "";
        try { msg = await r.text(); } catch {}
        throw new Error("login failed: " + r.status + (msg ? ("\n" + msg) : ""));
      }

      const out = await r.json(); // { api_key, username }
      if (!out || !out.api_key) {
        throw new Error("login failed: api_key missing");
      }

      // ✅ 저장: 이후 모든 API 호출은 X-Admin-Key로 이 값을 사용
      window.SentinelApi.setAdminKey(out.api_key);

      // ✅ 정상 동작 확인용(유지 권장)
      await window.SentinelApi.get("/summary");

      // ✅ 성공 시 대시보드로 이동
      window.location.href = "./dashboard.html";
    } catch (err) {
      console.error(err);
      window.SentinelApi.setAdminKey("");

      if (errorEl) {
        errorEl.textContent =
          "로그인 실패: 아이디/비밀번호가 올바르지 않거나 서버에 접근할 수 없습니다.";
        errorEl.hidden = false;
      }
    }
  });
});
