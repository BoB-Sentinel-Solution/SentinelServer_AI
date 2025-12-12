document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("login-form");
  const errorEl = document.getElementById("login-error");

  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (errorEl) errorEl.hidden = true;

    const data = new FormData(form);
    const email = (data.get("email") || "").toString().trim();       // UI 필드명 유지
    const password = (data.get("password") || "").toString().trim();

    if (!email || !password) {
      if (errorEl) {
        errorEl.textContent = "이메일과 비밀번호를 모두 입력해 주세요.";
        errorEl.hidden = false;
      }
      return;
    }

    try {
      // ✅ 기존 "password를 관리자키로 사용" 제거
      // ✅ 서버 auth API로 로그인해서 api_key 받기
      const r = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: email,   // 서버는 username 필드 기대
          password: password
        })
      });

      if (!r.ok) {
        throw new Error("login failed: " + r.status);
      }

      const out = await r.json(); // { api_key, username }

      // ✅ 저장: 기존 대시보드/설정 페이지가 이 키를 X-Admin-Key로 사용
      window.SentinelApi.setAdminKey(out.api_key);

      // ✅ 정상 동작 확인용으로 기존처럼 summary 한번 호출(선택이지만 유지 권장)
      await window.SentinelApi.get("/summary");

      // 성공 시 대시보드로 이동
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
