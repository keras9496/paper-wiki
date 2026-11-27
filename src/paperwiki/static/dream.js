// 위키 정리 화면: 제안을 합치거나 다른 주장으로 정하기, 살펴본 것 합치기, 되돌리기, 검토 마치기.
// 화면은 서버가 그린다. 여기서는 사용자가 정한 것을 보내고, 결과를 알린 뒤 다시 그린다.
// 방금 한 일은 알림에서 바로 되돌릴 수 있다 (합친 기록까지 내려가지 않아도 되게).

(() => {
  const NOTE = "paperwiki-dream-note";
  const FOLDS = "paperwiki-dream-folds";

  // 되돌리는 방법 (알림의 단추가 쓴다)
  const REVERT = {
    undo: (id) => api("POST", "/api/dream/undo", { id }).then(() => "되돌렸습니다. 합쳤던 주장들이 합치기 전의 자리로 돌아갔습니다."),
    forget: (groups) => api("POST", "/api/dream/forget", { groups }).then((r) => (r.forgotten ? "‘다른 주장’으로 정한 것을 되돌렸습니다. 다시 정할 수 있습니다." : "되돌릴 것이 없었습니다. 이미 되돌렸거나, 그 사이 위키가 바뀌었습니다.")),
  };

  function done(message, revert, next) {
    try {
      sessionStorage.setItem(NOTE, JSON.stringify({ message, revert, next }));
      // 펼쳐 둔 목록은 다시 그린 뒤에도 펼쳐 둔다
      sessionStorage.setItem(FOLDS, JSON.stringify($$("details.dream-fold[open]").map((d) => d.dataset.fold)));
    } catch { /* 저장소를 쓸 수 없으면 알림 없이 넘어간다 */ }
    location.reload();
  }

  try {
    const folds = JSON.parse(sessionStorage.getItem(FOLDS) || "[]");
    sessionStorage.removeItem(FOLDS);
    $$("details.dream-fold").forEach((d) => { if (folds.includes(d.dataset.fold)) d.open = true; });
    const note = JSON.parse(sessionStorage.getItem(NOTE) || "null");
    sessionStorage.removeItem(NOTE);
    if (note) {
      // 제안 하나를 정하고 나면 다음 제안의 머리로 간다 (다 정했으면 맨 위로). 그 밖에는 보던 자리에 둔다
      if (note.next) {
        const card = $(".dream-item");
        if (card) card.scrollIntoView({ block: "start" });
        else window.scrollTo(0, 0);
      }
      const revert = note.revert && REVERT[note.revert.how];
      toast(note.message, null, revert && {
        label: note.revert.label || "되돌리기",
        run: () => locked(() => revert(note.revert.arg)).then((message) => message && done(message)),
      });
    }
  } catch { /* 위와 같음 */ }

  const BUTTONS = "button[data-apply], button[data-apply-all], button[data-reject], button[data-merge], button[data-undo], button[data-forget], button[data-close], .toast-act";

  /** 보내는 동안 이 화면의 모든 단추를 잠근다 (두 가지를 겹쳐 누르지 못하게). 성공하면 다시 그릴 때까지 잠근 채로 두고, 실패했을 때만 푼다. */
  async function locked(send) {
    const buttons = $$(BUTTONS);
    buttons.forEach((b) => { b.disabled = true; });
    try {
      return await send();
    } catch (err) {
      buttons.forEach((b) => { b.disabled = false; });
      toast(err.message, "err");
      return undefined;
    }
  }

  // 이 화면이 보여 주는 검토안. 결정을 보낼 때 함께 보내, 그 사이 검토안이 바뀌었으면 반영되지 않게 한다
  const review = ($("#dream") || {}).dataset ? $("#dream").dataset.review || undefined : undefined;

  const groups = (text) => String(text || "").split(",").filter(Boolean);
  const numbers = (text) => groups(text).map(Number);

  const ACTIONS = {
    apply: (btn) => ({
      send: () => api("POST", "/api/dream/apply", { only: [Number(btn.dataset.apply)], review }),
      say: (r) => (r.applied.length ? `제안 ${r.applied.join(", ")}번을 같은 주장으로 합쳤습니다.` : "합치지 않았습니다. 이미 정했거나, 그 사이 위키가 바뀐 제안입니다."),
      revert: (r) => r.history && { how: "undo", arg: r.history },
      next: true,
    }),
    applyAll: (btn) => ({
      ask: `확신 높은 제안 ${numbers(btn.dataset.applyAll).length}건을 모두 같은 주장으로 합칠까요? 합친 뒤에도 되돌릴 수 있습니다.`,
      send: () => api("POST", "/api/dream/apply", { only: numbers(btn.dataset.applyAll), review }),
      say: (r) => (r.applied.length ? `제안 ${r.applied.length}건을 같은 주장으로 합쳤습니다.` : "합친 제안이 없습니다.") + (r.stale.length ? ` ${r.stale.length}건은 그 사이 위키가 바뀌어 건너뛰었습니다.` : ""),
      revert: (r) => r.history && { how: "undo", arg: r.history },
      next: true,
    }),
    reject: (btn) => ({
      send: () => api("POST", "/api/dream/reject", { numbers: [Number(btn.dataset.reject)], review }),
      say: (r) => (r.rejected.length ? `제안 ${btn.dataset.reject}번을 다른 주장으로 정했습니다. 다시 제안되지 않습니다.` : "이미 정한 제안입니다. 바뀐 것은 없습니다."),
      revert: (r) => r.rejected.length && { how: "forget", arg: r.apart && r.apart.length ? r.apart : [groups(btn.dataset.groups)] },
      next: true,
    }),
    merge: (btn) => ({
      send: () => api("POST", "/api/dream/merge", { numbers: [Number(btn.dataset.merge)], review }),
      say: (r) => (r.merged.length ? `살펴본 것 ${btn.dataset.merge}번을 같은 주장으로 합쳤습니다.` : "이미 한 주장이 되어 있습니다."),
      revert: (r) => r.history && { how: "undo", arg: r.history },
    }),
    undo: (btn) => ({
      ask: "이 합치기를 되돌릴까요? 주장들이 합치기 전의 묶음과 키워드로 돌아갑니다.",
      send: () => api("POST", "/api/dream/undo", { id: btn.dataset.undo }),
      say: (r) => "되돌렸습니다. 합쳤던 주장들이 합치기 전의 자리로 돌아갔습니다." + (r.skipped ? ` 그 뒤에 따로 달라진 주장 ${r.skipped}개는 건드리지 않았습니다.` : ""),
    }),
    forget: (btn) => ({
      send: () => api("POST", "/api/dream/forget", { groups: [groups(btn.dataset.forget)] }),
      say: (r) => (r.forgotten ? "‘다른 주장’으로 정한 것을 되돌렸습니다. 다음 정리 때 다시 제안될 수 있습니다." : "되돌릴 것이 없었습니다."),
    }),
    close: (btn) => ({
      ask: Number(btn.dataset.close) ? `아직 정하지 않은 제안이 ${btn.dataset.close}건 있습니다. 검토를 마칠까요? 정하지 않은 제안은 위키에 반영되지 않고, 다음 정리 때 다시 나올 수 있습니다.` : null,
      send: () => api("DELETE", "/api/dream" + (review ? `?review=${encodeURIComponent(review)}` : "")),
      say: () => "검토를 마쳤습니다.",
    }),
  };

  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-apply], [data-apply-all], [data-reject], [data-merge], [data-undo], [data-forget], [data-close]");
    if (!btn) return;
    const name = Object.keys(ACTIONS).find((key) => key in btn.dataset);
    const action = ACTIONS[name](btn);
    if (action.ask && !confirm(action.ask)) return;
    locked(action.send).then((result) => result && done(action.say(result), action.revert ? action.revert(result) || null : null, Boolean(action.next)));
  });
})();

// 위키 정리 시작: 이 컴퓨터의 Claude Code 로 정리 에이전트를 뒤에서 돌린다. 제안이 만들어지면 화면을 다시 그린다.
(() => {
  const box = $("#dream-start");
  if (!box) return;
  const btn = $("[data-dream-start]", box);
  const note = $("[data-dream-note]", box);
  const ACTIVE = ["queued", "running"];
  Claude.mount($("#claude-state"));

  function follow(id) {
    btn.disabled = true;
    btn.textContent = "정리하는 중…";
    const tick = async () => {
      let jobs;
      try { jobs = (await api("GET", "/api/jobs")).jobs; } catch { setTimeout(tick, 6000); return; }
      const job = jobs.find((j) => j.id === id);
      if (job && ACTIVE.includes(job.state)) {
        note.textContent = `${job.step}${job.elapsed ? ` · ${Math.max(1, Math.floor(job.elapsed / 60))}분째` : ""}. 끝나면 제안이 이 화면에 나타납니다. Paper Wiki 검은 창은 닫지 마세요.`;
        setTimeout(tick, 4000);
        return;
      }
      if (!job || job.state === "done") {
        location.reload();
        return;
      }
      btn.disabled = false;
      btn.textContent = "다시 정리 시작";
      note.textContent = [job.error, job.hint].filter(Boolean).join(" ");
      if (job.state === "login") Claude.refreshAll(true);
    };
    tick();
  }

  btn.addEventListener("click", () =>
    busy(btn, async () => {
      let job;
      try {
        job = await api("POST", "/api/jobs", { kind: "dream" });
      } catch (err) {
        if (await Claude.explain(err)) return;
        throw err;
      }
      follow(job.id);
    }),
  );

  // 이미 돌고 있는 정리가 있으면 이어서 지켜본다 (화면을 새로 고친 경우)
  api("GET", "/api/jobs").then((r) => {
    const running = r.jobs.find((j) => j.kind === "dream" && ACTIVE.includes(j.state));
    if (running) follow(running.id);
  }).catch(() => {});
})();
