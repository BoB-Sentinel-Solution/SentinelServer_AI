// ./js/info-popover.js

(function () {
  const details = document.querySelector(".login-popover");
  if (!details) return;

  const panel = details.querySelector(".popover-panel");
  const closeBtn = details.querySelector(".pop-close");
  if (!panel || !closeBtn) return;

  const close = () => details.removeAttribute("open");

  // X 버튼 클릭
  closeBtn.addEventListener("click", close);

  // 오버레이 바깥 영역 클릭 시 닫기
  panel.addEventListener("click", (e) => {
    if (e.target === panel) close();
  });

  // ESC 키로 닫기
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && details.hasAttribute("open")) {
      close();
    }
  });
})();
