// 새 논문 · 검토 화면: 검토안 폐기.

(() => {
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-discard]");
    if (!btn) return;
    const row = btn.closest("[data-key]");
    if (!confirm(`'${row.dataset.title || "이 논문"}' 의 검토안을 폐기할까요? 위키에는 아무것도 저장되지 않고, PDF는 논문 폴더에 그대로 남습니다.`)) return;
    busy(btn, async () => {
      await api("DELETE", `/api/pending/${encodeURIComponent(row.dataset.key)}`);
      location.reload();
    });
  });
})();
