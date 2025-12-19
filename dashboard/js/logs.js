// dashboard/js/logs.js
document.addEventListener("DOMContentLoaded", () => {
  const updatedAtEl = document.getElementById("top-updated-at");
  const btnRefreshTop = document.getElementById("btn-refresh");
  const btnLogout = document.getElementById("btn-logout");

  const searchInput = document.getElementById("logs-search-input");
  const searchBtn = document.getElementById("logs-search-btn");
  const categorySelect = document.getElementById("logs-category-select");

  const tableBody = document.getElementById("logs-table-body");
  const checkAll = document.getElementById("logs-check-all");

  const btnPrev = document.getElementById("logs-page-prev");
  const btnNext = document.getElementById("logs-page-next");
  const pageCurrentEl = document.getElementById("logs-page-current");
  const pageTotalEl = document.getElementById("logs-page-total");

  const btnExportCsv = document.getElementById("logs-export-csv");

  // ✅ (추가) 전체 로그 보기 토글
  const sensitiveOnlyEl = document.getElementById("logs-sensitive-only");

  let currentPage = 1;
  const pageSize = 20;
  let totalPages = 1;
  let currentQuery = "";
  let currentCategory = "";

  function formatTime(timeStr) {
    if (!timeStr) return "";
    try {
      const d = new Date(timeStr);
      if (Number.isNaN(d.getTime())) return timeStr;
      const pad = (n) => n.toString().padStart(2, "0");
      return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(
        d.getDate()
      )} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    } catch {
      return timeStr;
    }
  }

  function setUpdatedNow() {
    const now = new Date();
    const pad = (n) => n.toString().padStart(2, "0");
    if (updatedAtEl) {
      updatedAtEl.textContent = `${pad(now.getHours())}:${pad(
        now.getMinutes()
      )}:${pad(now.getSeconds())} KST`;
    }
  }

  function renderRows(items) {
    tableBody.innerHTML = "";

    if (!items || items.length === 0) {
      const tr = document.createElement("tr");
      tr.innerHTML =
        '<td colspan="12" class="logs-empty">표시할 로그가 없습니다.</td>';
      tableBody.appendChild(tr);
      return;
    }

    for (const log of items) {
      const tr = document.createElement("tr");

      const entities = (log.entities || [])
        .map((e) => e.label || e.type || "")
        .filter(Boolean)
        .join(", ");

      const sensitivity = log.has_sensitive ? "Y" : "N";
      const blocked =
        log.allow === false || log.action?.startsWith("block") || log.file_blocked
          ? "Y"
          : "N";

      tr.innerHTML = `
        <td class="col-checkbox">
          <input type="checkbox" class="logs-row-check" data-id="${log.id || ""}">
        </td>
        <td class="col-prompt" title="${(log.prompt || "").replace(/"/g, "&quot;")}">
          ${(log.prompt || "").length > 40
            ? log.prompt.slice(0, 40) + "…"
            : log.prompt || ""}
        </td>
        <td>${formatTime(log.created_at || log.time)}</td>
        <td>${log.host || ""}</td>
        <td>${log.hostname || log.pc_name || ""}</td>
        <td>${log.public_ip || ""}</td>
        <td>${log.internal_ip || log.private_ip || ""}</td>
        <td>${log.interface || log.source || ""}</td>
        <td>${log.action || ""}</td>
        <td>${sensitivity}</td>
        <td>${blocked}</td>
        <td>${entities || ""}</td>
      `;

      tableBody.appendChild(tr);
    }
  }

  async function fetchLogs(page = 1) {
    // 관리자 키 없으면 로그인 페이지로
    if (!window.SentinelApi.getAdminKey()) {
      window.location.href = "./index.html";
      return;
    }

    const params = new URLSearchParams();
    params.set("page", String(page));
    params.set("page_size", String(pageSize));

    // ✅ 최소 수정:
    // - 기본(체크 해제): 민감 로그만(sensitive_only=true) = 기존 동작 유지
    // - 체크(전체 로그 보기): 전체 로그(sensitive_only=false)
    params.set("sensitive_only", sensitiveOnlyEl?.checked ? "false" : "true");

    if (currentQuery) params.set("q", currentQuery);
    if (currentCategory) params.set("category", currentCategory);

    const res = await window.SentinelApi.get(`/logs?${params.toString()}`);

    const items = res.items || [];
    const total = res.total ?? items.length;
    const pageSizeResp = res.page_size || pageSize;

    currentPage = res.page || page;
    totalPages = Math.max(1, Math.ceil(total / pageSizeResp));

    renderRows(items);

    pageCurrentEl.textContent = String(currentPage);
    pageTotalEl.textContent = String(totalPages);

    btnPrev.disabled = currentPage <= 1;
    btnNext.disabled = currentPage >= totalPages;

    setUpdatedNow();
  }

  function applySearch() {
    currentQuery = (searchInput.value || "").trim();
    currentCategory = categorySelect.value || "";
    currentPage = 1;
    fetchLogs(currentPage).catch((err) => {
      console.error(err);
      alert("로그를 불러오는 중 오류가 발생했습니다.");
    });
  }

  function exportSelectedToCsv() {
    const checks = Array.from(
      document.querySelectorAll(".logs-row-check")
    ).filter((el) => el.checked);

    if (checks.length === 0) {
      alert("CSV로 내보낼 로그를 먼저 선택해 주세요.");
      return;
    }

    const rows = [];
    rows.push([
      "Prompt",
      "Time",
      "Host",
      "PC Name",
      "Public IP",
      "Internal IP",
      "Interface",
      "Action",
      "Sensitivity",
      "Block flag",
      "Entity",
    ]);

    checks.forEach((chk) => {
      const tr = chk.closest("tr");
      if (!tr) return;
      const tds = tr.querySelectorAll("td");
      const cols = Array.from(tds)
        .slice(1)
        .map((td) => `"${(td.textContent || "").replace(/"/g, '""').trim()}"`);
      rows.push(cols);
    });

    const csvContent = rows.map((r) => r.join(",")).join("\r\n");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = "sentinel_logs.csv";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  if (btnRefreshTop) {
    btnRefreshTop.addEventListener("click", () => {
      fetchLogs(currentPage).catch((err) => {
        console.error(err);
        alert("로그를 새로고침하는 중 오류가 발생했습니다.");
      });
    });
  }

  if (btnLogout) {
    btnLogout.addEventListener("click", () => {
      window.SentinelApi.setAdminKey("");
      window.location.href = "./index.html";
    });
  }

  if (searchBtn) searchBtn.addEventListener("click", applySearch);

  if (searchInput) {
    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") applySearch();
    });
  }

  // ✅ (추가) 전체 로그 보기 토글 변경 시 재조회
  if (sensitiveOnlyEl) {
    sensitiveOnlyEl.addEventListener("change", () => {
      currentPage = 1;
      fetchLogs(currentPage).catch((err) => {
        console.error(err);
        alert("로그를 불러오는 중 오류가 발생했습니다.");
      });
    });
  }

  if (btnPrev) {
    btnPrev.addEventListener("click", () => {
      if (currentPage > 1) {
        fetchLogs(currentPage - 1).catch((err) => {
          console.error(err);
          alert("로그를 불러오는 중 오류가 발생했습니다.");
        });
      }
    });
  }

  if (btnNext) {
    btnNext.addEventListener("click", () => {
      if (currentPage < totalPages) {
        fetchLogs(currentPage + 1).catch((err) => {
          console.error(err);
          alert("로그를 불러오는 중 오류가 발생했습니다.");
        });
      }
    });
  }

  if (checkAll) {
    checkAll.addEventListener("change", () => {
      const checked = checkAll.checked;
      document
        .querySelectorAll(".logs-row-check")
        .forEach((el) => (el.checked = checked));
    });
  }

  if (btnExportCsv) {
    btnExportCsv.addEventListener("click", exportSelectedToCsv);
  }

  fetchLogs(currentPage).catch((err) => {
    console.error(err);
    alert("로그를 불러오는 중 오류가 발생했습니다.");
  });

  setInterval(setUpdatedNow, 1000);
});
