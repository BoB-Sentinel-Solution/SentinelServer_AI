// dashboard/js/login.js
document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("login-form");
  const errorEl = document.getElementById("login-error");

  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorEl.hidden = true;

    const data = new FormData(form);
    const email = (data.get("email") || "").toString().trim();
    const password = (data.get("password") || "").toString().trim();

    if (!email || !password) {
      errorEl.textContent = "이메일과 비밀번호를 모두 입력해 주세요.";
      errorEl.hidden = false;
      return;
    }

    try {
      // 비밀번호를 관리자 키로 사용
      window.SentinelApi.setAdminKey(password);

      // ★ 요약 API는 /api/summary 이므로 여기서는 "/summary" 호출
      await window.SentinelApi.get("/summary");

      // 성공 시 대시보드로 이동
      window.location.href = "./dashboard.html";
    } catch (err) {
      console.error(err);
      window.SentinelApi.setAdminKey("");
      errorEl.textContent =
        "로그인 실패: 관리자 키가 올바르지 않거나 서버에 접근할 수 없습니다.";
      errorEl.hidden = false;
    }
  });
});
