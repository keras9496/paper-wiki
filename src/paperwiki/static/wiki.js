// 키워드 트리, 키워드 문서, 논문 문서의 동작.

(() => {
  // 대화상자 열기/닫기 공통
  document.addEventListener("click", (e) => {
    const open = e.target.closest("[data-open]");
    if (open) $("#" + open.dataset.open).showModal();
    const close = e.target.closest("[data-close]");
    if (close) close.closest("dialog").close();
  });

  // ── 키워드 트리 ──
  const tree = $("#tree");
  if (tree) {
    const items = $$("li", tree);
    const toggle = $("#tree-toggle");
    let expanded = false;
    toggle.addEventListener("click", () => {
      expanded = !expanded;
      items.forEach((li) => li.classList.toggle("open", expanded || li.parentElement === tree));
      toggle.textContent = expanded ? "모두 접기" : "모두 펼치기";
    });

    $("#tree-filter").addEventListener("input", (e) => {
      const q = e.target.value.trim().toLowerCase();
      let shown = 0;
      // 아래에서 위로 훑어, 자신이나 하위 항목이 맞으면 보여준다
      for (const li of items.slice().reverse()) {
        const self = !q || li.dataset.text.includes(q);
        const below = !!$("li:not(.hide)", li);
        li.classList.toggle("hide", !(self || below));
        if (q && below) li.classList.add("open");
        if (self || below) shown++;
      }
      $("#tree-empty").hidden = shown > 0;
      tree.hidden = shown === 0;
    });

    $("#kw-add-open").addEventListener("click", () => {
      $("#kw-add").showModal();
      $("#add-name").focus();
    });
    $("#add-save").addEventListener("click", (e) =>
      busy(e.currentTarget, async () => {
        const res = await api("POST", "/api/keywords", {
          name: $("#add-name").value,
          parent: $("#add-parent").value || null,
          aliases: $("#add-aliases").value,
          description: $("#add-desc").value,
        });
        location.href = `/wiki/k/${res.id}`;
      }),
    );
  }

  // ── 키워드 문서 ──
  const kp = $("#keyword-page");
  if (kp) {
    const id = kp.dataset.id;
    $("#edit-save").addEventListener("click", (e) =>
      busy(e.currentTarget, async () => {
        await api("PUT", `/api/keywords/${id}`, {
          name: $("#edit-name").value,
          parent: $("#edit-parent").value || null,
          aliases: $("#edit-aliases").value,
          description: $("#edit-desc").value,
        });
        location.reload();
      }),
    );
    $("#merge-save").addEventListener("click", (e) => {
      const into = $("#merge-into").value;
      if (!into) return toast("합칠 대상 키워드를 선택해 주세요.", "err");
      busy(e.currentTarget, async () => {
        const res = await api("POST", `/api/keywords/${id}/merge`, { into });
        location.href = `/wiki/k/${res.id}`;
      });
    });
    $("#kw-delete").addEventListener("click", (e) => {
      if (!confirm(`'${kp.dataset.name}' 키워드를 삭제할까요?`)) return;
      busy(e.currentTarget, async () => {
        await api("DELETE", `/api/keywords/${id}`);
        location.href = "/wiki";
      });
    });
  }

  // ── 논문 문서 ──
  const pp = $("#paper-page");
  if (pp) {
    const id = encodeURIComponent(pp.dataset.id);
    if (new URLSearchParams(location.search).has("saved")) {
      let note = "";
      try {
        note = sessionStorage.getItem("pw-zotero-note") || "";
        sessionStorage.removeItem("pw-zotero-note");
      } catch (_) {}
      toast("위키에 저장했습니다." + (note ? ` ${note}` : ""));
      history.replaceState(null, "", location.pathname);
    }
    // 주장 수정·삭제는 읽은 논문에만 있다 (인용 문헌은 그것을 인용한 논문의 주장을 고치면 따라 바뀐다)
    const edit = $("#paper-edit");
    if (edit)
      edit.addEventListener("click", (e) =>
        busy(e.currentTarget, async () => {
          const res = await api("POST", `/api/papers/${id}/edit`);
          location.href = `/review/${encodeURIComponent(res.key)}`;
        }),
      );
    const del = $("#paper-delete");
    if (del)
      del.addEventListener("click", (e) => {
        if (!confirm("이 논문과, 이 논문이 문헌을 인용하며 한 주장들을 위키에서 삭제할까요?\n이 논문만 인용하던 문헌도 함께 사라집니다. PDF 파일은 논문 폴더에 그대로 남습니다.")) return;
        busy(e.currentTarget, async () => {
          const res = await api("DELETE", `/api/papers/${id}`);
          location.href = res.kept_as_cited ? `/wiki/p/${id}` : "/papers?kind=read";
        });
      });
  }
})();
