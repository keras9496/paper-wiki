// 새 논문 · 검토 화면: PDF 를 끌어다 놓아 올리고, 뒤에서 Claude Code 로 정리를 시작하고, 진행을 지켜본다.
// 검토 대기 목록과 논문 폴더의 새 PDF 목록도 여기서 다시 그린다 (새로 고치지 않아도 되게).

(() => {
  const root = $("#inbox");
  if (!root) return;
  const ACTIVE = ["queued", "running"];
  const LANGS = { en: "영어 원문", ko: "한국어 번역", both: "나란히" };
  const MODES = { read: "바로 정리", study: "학습하며 정리", upload: "올리기만" };
  const MODE_NOTE = {
    read: "올리면 Claude Code가 바로 읽고, 인용 문장마다 주장과 인용된 문헌을 제안합니다. 끝나면 [검토하기]가 나옵니다.",
    study: "인용 정리와 함께 학습 자료를 만듭니다: 논문을 파트로 나누고, 파트마다 퀴즈 2~3개와 (한국어를 고르면) 문단별 번역. 번역은 논문 전체를 새로 쓰는 일이라 시간과 사용량이 꽤 더 듭니다.",
    upload: "논문 폴더에 저장만 합니다. 아래 '논문 폴더의 새 PDF'에서 나중에 정리를 시작할 수 있습니다.",
  };
  const PART = { reader: "인용 정리", tutor: "학습 자료" };
  const PART_STATE = { waiting: "기다리는 중", running: "진행 중", done: "끝남", failed: "실패" };

  // ── 올린 뒤 할 일 · 읽기 언어 (고른 것은 기억한다) ──
  let mode = localStorage.getItem("pw-upload-mode") || "read";
  let lang = localStorage.getItem("pw-study-lang") || "both";
  if (!MODES[mode]) mode = "read";
  if (!LANGS[lang]) lang = "both";

  function paintChoice() {
    $$("#mode button").forEach((b) => { b.classList.toggle("on", b.dataset.mode === mode); b.setAttribute("aria-checked", b.dataset.mode === mode); });
    $$("#lang button").forEach((b) => { b.classList.toggle("on", b.dataset.lang === lang); b.setAttribute("aria-checked", b.dataset.lang === lang); });
    $("#lang-option").hidden = mode !== "study";
    $("#mode-note").textContent = MODE_NOTE[mode];
  }
  $("#mode").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-mode]");
    if (!b) return;
    mode = b.dataset.mode;
    localStorage.setItem("pw-upload-mode", mode);
    paintChoice();
  });
  $("#lang").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-lang]");
    if (!b) return;
    lang = b.dataset.lang;
    localStorage.setItem("pw-study-lang", lang);
    paintChoice();
  });
  paintChoice();

  const claudeEl = $("#claude-state");
  Claude.mount(claudeEl);

  // ── 끌어다 놓기 ──
  const input = $("#file-input");
  const overlay = $("#drop-overlay");
  const zone = $("#dropzone");
  let depth = 0;
  const hasFiles = (e) => e.dataTransfer && [...(e.dataTransfer.types || [])].includes("Files");
  document.addEventListener("dragenter", (e) => {
    if (!hasFiles(e)) return;
    depth += 1;
    overlay.hidden = false;
    zone.classList.add("over");
  });
  document.addEventListener("dragleave", (e) => {
    if (!hasFiles(e)) return;
    depth = Math.max(0, depth - 1);
    if (!depth) { overlay.hidden = true; zone.classList.remove("over"); }
  });
  document.addEventListener("dragover", (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
  });
  document.addEventListener("drop", (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    depth = 0;
    overlay.hidden = true;
    zone.classList.remove("over");
    handle([...e.dataTransfer.files]);
  });
  input.addEventListener("change", () => {
    handle([...input.files]);
    input.value = "";
  });

  // ── 올리기 ──
  const uploads = []; // 올리는 중이거나, 올렸지만 작업이 시작되지 않은 파일: {name, size, sent, state, note, link}

  async function handle(files) {
    const pdfs = files.filter((f) => /\.pdf$/i.test(f.name) || f.type === "application/pdf");
    if (files.length > pdfs.length) toast(`PDF가 아닌 파일 ${files.length - pdfs.length}개는 건너뛰었습니다.`, "err");
    if (!pdfs.length) return;
    const how = mode;
    for (const file of pdfs) await uploadOne(file, how); // 한 편씩: 드라이브 동기화와 Claude Code 를 한꺼번에 몰아붙이지 않게
    await refreshLists();
  }

  function send(file, item) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `/api/upload?name=${encodeURIComponent(file.name)}`);
      xhr.setRequestHeader("Content-Type", "application/pdf");
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) { item.sent = e.loaded / e.total; renderJobs(); }
      };
      xhr.onload = () => {
        let data = null;
        try { data = JSON.parse(xhr.responseText); } catch { /* 본문 없음 */ }
        if (xhr.status >= 200 && xhr.status < 300) resolve(data);
        else reject(new Error((data && data.error) || `올리지 못했습니다 (${xhr.status})`));
      };
      xhr.onerror = () => reject(new Error("올리지 못했습니다. Paper Wiki 검은 창이 켜져 있는지 확인해 주세요."));
      xhr.send(file);
    });
  }

  async function uploadOne(file, how) {
    const item = { name: file.name, size: file.size, sent: 0, state: "sending", note: "" };
    uploads.unshift(item);
    renderJobs();
    try {
      const res = await send(file, item);
      item.sent = 1;
      if (res.registered) {
        Object.assign(item, { state: "done", note: `이미 위키에 등록된 논문입니다 — ${res.registered.title || "@" + res.registered.id}`, link: { href: `/wiki/p/${encodeURIComponent(res.registered.id)}`, label: "문서 보기" } });
      } else if (res.pending) {
        Object.assign(item, { state: "done", note: "이미 검토를 기다리는 논문입니다.", link: { href: `/review/${encodeURIComponent(res.pending)}`, label: "검토하기" } });
      } else if (how === "upload") {
        Object.assign(item, { state: "done", note: res.existed ? "같은 PDF가 이미 논문 폴더에 있습니다." : `논문 폴더에 저장했습니다: ${res.name}` });
      } else {
        await start(res.path, how, item);
      }
    } catch (err) {
      Object.assign(item, { state: "error", note: err.message });
    }
    renderJobs();
  }

  async function start(path, how, item) {
    try {
      const job = await api("POST", "/api/jobs", { kind: "paper", pdf: path, mode: how, lang });
      if (item) uploads.splice(uploads.indexOf(item), 1);
      jobs = [job, ...jobs.filter((j) => j.id !== job.id)];
      renderJobs();
      schedule(1500);
      return job;
    } catch (err) {
      const told = await Claude.explain(err);
      const note = told ? "논문 폴더에 저장했습니다. Claude Code에 로그인한 뒤 아래 '논문 폴더의 새 PDF'에서 정리를 시작해 주세요." : err.message;
      if (item) Object.assign(item, { state: "error", note });
      else if (!told) toast(err.message, "err");
      return null;
    }
  }

  // ── 작업 (뒤에서 도는 Claude Code) ──
  let jobs = [];
  let timer = null;

  async function loadJobs() {
    let res;
    try {
      res = await api("GET", "/api/jobs");
    } catch {
      schedule(8000);
      return;
    }
    const before = new Map(jobs.map((j) => [j.id, j.state]));
    jobs = res.jobs.filter((j) => j.kind === "paper");
    let finished = false;
    for (const j of jobs) {
      if (ACTIVE.includes(before.get(j.id)) && !ACTIVE.includes(j.state)) {
        finished = true;
        if (j.state === "done") toast(`정리가 끝났습니다: ${j.title}`, null, j.result && (j.result.study || j.result.review) ? { label: j.result.study ? "학습 시작" : "검토하기", run: () => (location.href = j.result.study || j.result.review) } : null);
        else toast(`정리하지 못했습니다: ${j.title}`, "err");
      }
    }
    renderJobs();
    if (finished) refreshLists();
    schedule();
  }

  function schedule(ms) {
    clearTimeout(timer);
    if (ms || jobs.some((j) => ACTIVE.includes(j.state))) timer = setTimeout(loadJobs, ms || 3000);
  }

  const minutes = (s) => (s < 60 ? `${s}초째` : `${Math.floor(s / 60)}분째`);
  const sizeText = (n) => (n >= 1e5 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1e3))} KB`);

  function stateMark(state) {
    if (ACTIVE.includes(state) || state === "sending") return h("span", { class: "spinner", "aria-label": "진행 중" });
    if (state === "done") return h("span", { class: "job-mark ok", "aria-label": "끝남" }, "✓");
    if (state === "canceled") return h("span", { class: "job-mark", "aria-label": "취소됨" }, "–");
    return h("span", { class: "job-mark err", "aria-label": "멈춤" }, "!");
  }

  function uploadRow(u) {
    const pct = Math.round((u.sent || 0) * 100);
    return h(
      "div",
      { class: "row job" },
      stateMark(u.state),
      h(
        "div",
        { class: "grow" },
        h("div", { class: "title" }, u.name),
        h("div", { class: "sub" }, u.state === "sending" ? `올리는 중 · ${pct}% · ${sizeText(u.size)}` : u.note),
        u.state === "sending" ? h("div", { class: "bar" }, h("span", { style: `width:${pct}%` })) : null,
      ),
      h(
        "div",
        { class: "side" },
        u.link ? h("a", { class: "btn btn-sm", href: u.link.href }, u.link.label) : null,
        u.state !== "sending" ? h("button", { class: "btn btn-ghost btn-sm", type: "button", onclick: () => { uploads.splice(uploads.indexOf(u), 1); renderJobs(); } }, "닫기") : null,
      ),
    );
  }

  function jobRow(j) {
    const active = ACTIVE.includes(j.state);
    const how = MODES[j.mode] + (j.mode === "study" ? ` · ${LANGS[j.lang] || ""}` : "");
    const sub = active ? [how, j.step, j.elapsed != null ? minutes(j.elapsed) : null] : [how, { done: "끝남", canceled: "취소함", login: "로그인 필요", limit: "사용 한도", failed: "멈춤" }[j.state]];
    const parts = Object.entries(j.parts || {}).filter(([p]) => PART[p]);
    const r = j.result || {};
    return h(
      "div",
      { class: "row job" + (active ? "" : ` ${j.state}`), dataset: { job: j.id } },
      stateMark(j.state),
      h(
        "div",
        { class: "grow" },
        h("div", { class: "title" }, r.title || j.title),
        h("div", { class: "sub" }, sub.filter(Boolean).join(" · ")),
        parts.length > 1 || (active && parts.length)
          ? h("div", { class: "job-parts" }, parts.map(([p, s]) => h("span", { class: `job-part ${s}` }, `${PART[p]} · ${p === "tutor" && s === "running" && j.sections_ready ? `${j.sections_ready}개 파트 준비됨` : PART_STATE[s] || s}`)))
          : null,
        j.error ? h("p", { class: "job-error" }, j.error) : null,
        j.hint ? h("p", { class: "hint" }, j.hint) : null,
      ),
      h(
        "div",
        { class: "side" },
        active ? h("button", { class: "btn btn-ghost btn-sm", type: "button", onclick: (e) => cancel(e.currentTarget, j) }, "취소") : null,
        j.state === "login" ? h("button", { class: "btn btn-sm", type: "button", onclick: () => Claude.refreshAll(true).then(() => claudeEl.scrollIntoView({ block: "center", behavior: "smooth" })) }, "로그인 안내") : null,
        ["failed", "login", "limit", "canceled"].includes(j.state) ? h("button", { class: "btn btn-sm btn-primary", type: "button", onclick: (e) => retry(e.currentTarget, j) }, "다시 시도") : null,
        r.study ? h("a", { class: "btn btn-sm" + (j.state === "done" ? " btn-primary" : ""), href: r.study }, "학습 시작") : null,
        r.review ? h("a", { class: "btn btn-sm" + (j.state === "done" && !r.study ? " btn-primary" : ""), href: r.review }, "검토하기") : null,
      ),
    );
  }

  function renderJobs() {
    const rows = [...uploads.map(uploadRow), ...jobs.map(jobRow)];
    $("#jobs-section").hidden = !rows.length;
    fill($("#jobs"), rows);
    const running = jobs.filter((j) => ACTIVE.includes(j.state)).length + uploads.filter((u) => u.state === "sending").length;
    $("#jobs-n").textContent = running ? `${running}건 진행 중` : "";
    $("#jobs-title").textContent = running ? "정리하는 중" : "최근 정리";
    $("#jobs-hint").hidden = !jobs.some((j) => ACTIVE.includes(j.state));
    $("#jobs-clear").hidden = !jobs.some((j) => !ACTIVE.includes(j.state));
  }

  async function cancel(btn, j) {
    if (!confirm(`'${j.title}' 의 정리를 멈출까요? 논문 PDF는 논문 폴더에 그대로 남습니다.`)) return;
    await busy(btn, async () => { await api("POST", `/api/jobs/${j.id}/cancel`); await loadJobs(); });
  }

  async function retry(btn, j) {
    await busy(btn, async () => {
      try {
        await api("POST", `/api/jobs/${j.id}/retry`);
      } catch (err) {
        if (await Claude.explain(err)) return;
        throw err;
      }
      await loadJobs();
    });
  }

  $("#jobs-clear").addEventListener("click", (e) => busy(e.currentTarget, async () => { await api("DELETE", "/api/jobs"); await loadJobs(); }));

  // ── 검토 대기 · 새 PDF 목록 ──
  async function refreshLists() {
    let res;
    try { res = await api("GET", "/api/inbox"); } catch { return; }
    $("#pending-section").hidden = !res.pending.length;
    $("#pending-n").textContent = res.pending.length;
    fill(
      $("#pending-list"),
      res.pending.map((item) =>
        h(
          "div",
          { class: "row", dataset: { key: item.key, title: item.title } },
          h("div", { class: "grow" }, h("div", { class: "title" }, item.title || "(제목 없음)"), h("div", { class: "sub" }, [item.cite, item.editing ? "등록된 문서를 고치는 중" : null, item.created].filter(Boolean).join(" · "))),
          h(
            "div",
            { class: "side" },
            h("span", { class: "badge wait" }, `주장 ${item.claims}`),
            item.study ? h("a", { class: "btn btn-sm", href: `/study/${encodeURIComponent(item.key)}` }, "학습 이어 하기") : null,
            h("a", { class: "btn btn-primary btn-sm", href: `/review/${encodeURIComponent(item.key)}` }, item.editing ? "이어서 수정" : "검토하기"),
            h("button", { class: "btn btn-ghost btn-sm", type: "button", dataset: { discard: "" } }, "폐기"),
          ),
        ),
      ),
    );
    const busyPaths = new Set(jobs.filter((j) => ACTIVE.includes(j.state)).map((j) => j.pdf));
    const fresh = res.new.filter((f) => !busyPaths.has(f.path));
    $("#new-section").hidden = !fresh.length;
    $("#new-n").textContent = fresh.length;
    fill(
      $("#new-list"),
      fresh.map((f) =>
        h(
          "div",
          { class: "row", dataset: { path: f.path, name: f.name } },
          h("div", { class: "grow" }, h("div", { class: "title" }, f.name), h("div", { class: "sub" }, f.detail)),
          h("div", { class: "side" }, h("button", { class: "btn btn-sm", type: "button", dataset: { start: "study" } }, "학습하며 정리"), h("button", { class: "btn btn-primary btn-sm", type: "button", dataset: { start: "read" } }, "정리 시작")),
        ),
      ),
    );
  }

  root.addEventListener("click", async (e) => {
    const startBtn = e.target.closest("[data-start]");
    if (startBtn) {
      const row = startBtn.closest("[data-path]");
      await busy(startBtn, async () => {
        const job = await start(row.dataset.path, startBtn.dataset.start, null);
        if (job) row.remove();
      });
      return;
    }
    const discard = e.target.closest("[data-discard]");
    if (discard) {
      const row = discard.closest("[data-key]");
      if (!confirm(`'${row.dataset.title || "이 논문"}' 의 검토안을 폐기할까요? 위키에는 아무것도 저장되지 않고, PDF는 논문 폴더에 그대로 남습니다.`)) return;
      await busy(discard, async () => {
        await api("DELETE", `/api/pending/${encodeURIComponent(row.dataset.key)}`);
        await refreshLists();
      });
    }
  });

  loadJobs();
})();
