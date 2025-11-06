// /dashboard/regul.js
(function () {
  var btn = document.getElementById('openRegul');
  var pop = document.getElementById('regulPopover');
  if (!btn || !pop) return;

  var closeBtn = pop.querySelector('[data-close]');

  function open()  { pop.classList.add('show'); btn.setAttribute('aria-expanded','true'); }
  function close() { pop.classList.remove('show'); btn.setAttribute('aria-expanded','false'); }
  function toggle(){ pop.classList.contains('show') ? close() : open(); }

  btn.addEventListener('click', function (e) {
    e.preventDefault();
    e.stopPropagation();
    toggle();
  });

  if (closeBtn) {
    closeBtn.addEventListener('click', function (e) {
      e.preventDefault();
      close();
    });
  }

  // 바깥 클릭/ESC/스크롤/리사이즈 시 닫기
  document.addEventListener('click', function () {
    if (pop.classList.contains('show')) close();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') close();
  });
  window.addEventListener('scroll', close, true);
  window.addEventListener('resize', close);
})();