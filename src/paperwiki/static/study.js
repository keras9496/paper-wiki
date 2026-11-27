// 학습 화면: 파트마다 본문(원문 PDF · 한국어 번역 · 나란히) → 용어 → 퀴즈 → 이 파트의 인용 문장.
// 답 · 스스로 매긴 결과 · 마지막으로 본 파트는 위키 폴더에 저장되어 다른 컴퓨터에서도 이어진다.

(() => {
  const root = $("#study");
  if (!root) return;
  const KEY = encodeURIComponent(root.dataset.key);
  const ACTIVE = ["queued", "running"];
  const LANGS = { en: "영어 원문", ko: "한국어 번역", both: "나란히" };
  const KINDS = { recall: "확인", why: "이유", apply: "적용" };
  const RATINGS = { right: "맞음", unsure: "애매", wrong: "틀림" };
  const VERDICTS = { correct: ["맞음", "ok"], partial: ["부분적으로 맞음", "warn"], wrong: ["틀림", "err"] };

  let view = null;
  let cur = 0; // 지금 보는 파트 (0부터). 파트 수와 같으면 '마치며'
  let lang = "en";
  let watch = null; // 기다리는 작업 (채점 · 번역)
  const saveTimers = new Map();

  async function load(keepPlace) {
    view = await api("GET", `/api/study/${KEY}`);
    if (!keepPlace) {
      const last = Number(view.last) || 0;
      cur = last >= 1 && last <= view.sections.length ? last - 1 : firstOpen();
    }
    lang = view.translated ? view.lang : "en";
    const running = (view.jobs || []).find((j) => ACTIVE.includes(j.state));
    if (running && !watch) follow(running);
    render();
  }

  const firstOpen = () => Math.max(0, view.sections.findIndex((s) => !s.done));
  const remember = (body) => api("POST", `/api/study/${KEY}/view`, body).catch(() => {});

  // ── 그리기 ──
  function render() {
    const scrollY = window.scrollY;
    fill(root, head(), toolbar(), notice(), h("div", { class: "study-grid" }, nav(), h("div", { class: "study-main" }, cur < view.sections.length ? part(view.sections[cur]) : finish())));
    window.scrollTo(0, scrollY);
  }

  function head() {
    const s = view.summary;
    return h(
      "header",
      { class: "page-head study-head" },
      h("nav", { class: "crumbs", "aria-label": "경로" }, h("a", { href: "/study" }, "학습"), h("span", {}, "›"), h("span", {}, view.cite || "논문")),
      h("div", { class: "eyebrow" }, "학습하며 정리"),
      h("h1", {}, view.title || "(제목 없음)"),
      h(
        "div",
        { class: "doc-meta" },
        view.cite ? h("span", {}, view.cite) : null,
        { pending: h("span", { class: "badge wait" }, "인용 문장 검토 대기"), registered: h("span", { class: "badge ok" }, "위키에 등록됨"), missing: h("span", { class: "badge" }, "검토안 없음") }[view.status],
        h("span", {}, `파트 ${s.done}/${s.parts}`),
        s.right + s.unsure + s.wrong ? h("span", {}, `맞음 ${s.right} · 애매 ${s.unsure} · 틀림 ${s.wrong}`) : null,
        view.status === "pending" ? h("a", { class: "link", href: `/review/${KEY}` }, "검토 화면") : null,
        view.paper_id ? h("a", { class: "link", href: `/wiki/p/${encodeURIComponent(view.paper_id)}` }, "문헌 문서") : null,
      ),
    );
  }

  function toolbar() {
    const seg = h(
      "div",
      { class: "seg", role: "radiogroup", "aria-label": "읽기 언어" },
      Object.entries(LANGS).map(([k, label]) => {
        const off = k !== "en" && !view.translated;
        return h("button", { type: "button", class: lang === k ? "on" : "", role: "radio", "aria-checked": lang === k, disabled: off, title: off ? "이 학습은 영어 원문으로 만들었습니다. [한국어 번역 추가]로 번역을 만들 수 있습니다." : null, onclick: () => setLang(k) }, label);
      }),
    );
    const translating = watch && watch.kind === "translate";
    return h(
      "div",
      { class: "study-toolbar" },
      h("div", { class: "study-tool" }, h("span", { class: "label" }, "읽기"), seg),
      !view.translated ? h("button", { class: "btn btn-sm", type: "button", disabled: translating, onclick: (e) => translate(e.currentTarget) }, translating ? "번역을 만드는 중…" : "한국어 번역 추가") : null,
      h("span", { class: "grow" }),
      h("div", { class: "study-progress", title: `파트 ${view.summary.done}/${view.summary.parts} 읽음` }, h("span", { style: `width:${Math.round((100 * view.summary.done) / Math.max(1, view.summary.parts))}%` })),
    );
  }

  function notice() {
    const out = [];
    if (watch) {
      out.push(h("div", { class: "callout found study-watch" }, h("div", { class: "t" }, h("span", { class: "spinner" }), " ", watch.kind === "translate" ? "한국어 번역을 만들고 있습니다" : "Claude가 답을 채점하고 있습니다"), h("div", { class: "d" }, watch.kind === "translate" ? "논문 전체를 번역하는 일이라 십여 분 걸릴 수 있습니다. 그동안 원문으로 계속 읽으셔도 됩니다. 끝나면 이 화면에 바로 나타납니다." : "보통 1~2분 걸립니다. 끝나면 문항 아래에 피드백이 나타납니다.")));
    }
    out.push(claudeEl);
    return out;
  }

  const claudeEl = h("div", { id: "claude-state" }); // 채점 · 번역에 필요할 때만 로그인 안내가 나타난다
  Claude.mount(claudeEl);

  function nav() {
    return h(
      "aside",
      { class: "study-nav", "aria-label": "파트" },
      h("div", { class: "label" }, "파트"),
      h(
        "ol",
        {},
        view.sections.map((s, i) =>
          h(
            "li",
            {},
            h(
              "button",
              { type: "button", class: (i === cur ? "on " : "") + (s.done ? "done" : ""), onclick: () => go(i) },
              h("span", { class: "n" }, s.done ? "✓" : i + 1),
              h("span", { class: "t" }, s.title_ko && lang !== "en" ? s.title_ko : s.title),
              s.claims.length ? h("span", { class: "c", title: `이 파트의 인용 문장 ${s.claims.length}개` }, s.claims.length) : null,
            ),
          ),
        ),
        h("li", {}, h("button", { type: "button", class: cur === view.sections.length ? "on" : "", onclick: () => go(view.sections.length) }, h("span", { class: "n" }, "★"), h("span", { class: "t" }, view.status === "pending" ? "마치며 · 위키에 등록" : "마치며"))),
      ),
    );
  }

  function go(i) {
    cur = i;
    if (i < view.sections.length) remember({ last: i + 1 });
    render();
    root.scrollIntoView({ block: "start" });
  }

  function setLang(k) {
    lang = k;
    remember({ lang: k });
    render();
  }

  // ── 파트 하나 ──
  function pdfFrame(page) {
    if (!view.pdf_url) return h("div", { class: "card empty" }, h("h3", {}, "PDF를 찾을 수 없습니다"), h("p", {}, "다른 컴퓨터에서 넣은 논문이면 구글 드라이브 동기화가 끝난 뒤 다시 열어 주세요."));
    return h("iframe", { class: "study-pdf", src: `${view.pdf_url}#page=${page}&view=FitH`, title: "논문 원문 PDF" });
  }

  function paragraphs(sec, frameHolder) {
    if (!sec.paragraphs.length) return h("div", { class: "card empty" }, h("p", {}, "이 파트의 번역이 없습니다."));
    return h(
      "div",
      { class: "study-text" },
      sec.paragraphs.map((p) =>
        h(
          "div",
          { class: "para" },
          p.page || p.starts
            ? h(
                "button",
                { type: "button", class: "para-src", title: frameHolder ? "왼쪽 원문을 이 쪽으로" : "원문의 위치", onclick: frameHolder && p.page ? () => fill(frameHolder, pdfFrame(p.page)) : null },
                p.page ? `p.${p.page}` : "",
                p.starts ? ` · ${p.starts}…` : "",
              )
            : null,
          h("p", {}, p.ko),
        ),
      ),
    );
  }

  function reading(sec) {
    const page = sec.pages[0];
    if (lang === "ko") return paragraphs(sec, null);
    if (lang === "both") {
      const holder = h("div", { class: "study-both-pdf" }, pdfFrame(page));
      return h("div", { class: "study-both" }, holder, paragraphs(sec, holder));
    }
    return pdfFrame(page);
  }

  function part(sec) {
    const pages = sec.pages[0] === sec.pages[1] ? `${sec.pages[0]}쪽` : `${sec.pages[0]}–${sec.pages[1]}쪽`;
    return [
      h(
        "div",
        { class: "study-part-head" },
        h("div", { class: "eyebrow" }, `파트 ${sec.n} / ${view.sections.length} · ${pages}`),
        h("h2", {}, sec.title),
        sec.title_ko && sec.title_ko !== sec.title ? h("p", { class: "muted" }, sec.title_ko) : null,
      ),
      h("div", { class: "study-reading" }, reading(sec)),
      sec.terms.length
        ? h("div", { class: "card study-terms" }, h("div", { class: "label" }, "용어 메모"), h("dl", {}, sec.terms.map((t) => [h("dt", {}, t.term), h("dd", {}, t.note)])))
        : null,
      quiz(sec),
      claims(sec.claims, "이 파트의 인용 문장"),
      h(
        "div",
        { class: "study-foot" },
        sec.n > 1 ? h("button", { class: "btn", type: "button", onclick: () => go(cur - 1) }, "← 이전 파트") : h("span"),
        h("button", { class: "btn btn-primary", type: "button", onclick: (e) => finishPart(e.currentTarget, sec) }, sec.n < view.sections.length ? "다 읽었습니다 · 다음 파트 →" : "다 읽었습니다 · 마치며 →"),
      ),
    ];
  }

  async function finishPart(btn, sec) {
    await busy(btn, async () => {
      await api("POST", `/api/study/${KEY}/section`, { section: sec.n, done: true });
      await flushAnswers();
      await load(true);
      go(cur + 1);
    });
  }

  // ── 퀴즈 ──
  function quiz(sec) {
    const answered = sec.answers.some((a) => (a.text || "").trim());
    return h(
      "section",
      { class: "card study-quiz" },
      h("div", { class: "section-head" }, h("h3", {}, "떠올려 보기"), h("span", { class: "n" }, `${sec.quiz.length}문항`)),
      h("p", { class: "hint", style: "margin:-8px 0 16px" }, "본문을 보지 말고 기억나는 대로 적어 보세요. 떠올리려 애쓰는 순간이 기억을 남깁니다. 그다음 [정답 보기]로 비교합니다."),
      sec.quiz.map((q, i) => quizItem(sec, q, i)),
      h(
        "div",
        { class: "quiz-grade" },
        h("button", { class: "btn btn-sm", type: "button", disabled: !answered || (watch && watch.kind === "grade"), onclick: (e) => grade(e.currentTarget, sec) }, "Claude에게 채점받기"),
        h("span", { class: "hint" }, answered ? "적은 답을 Claude가 모범 답과 견주어 피드백을 줍니다 (이 컴퓨터의 Claude Code, 1~2분)." : "답을 하나 이상 적으면 Claude에게 채점받을 수 있습니다."),
      ),
    );
  }

  function quizItem(sec, q, i) {
    const a = sec.answers[i] || {};
    const shown = !!a.revealed;
    const box = h("textarea", { class: "input", rows: 3, placeholder: "기억나는 대로 적어 보세요", value: a.text || "" });
    box.addEventListener("input", () => {
      a.text = box.value;
      queueSave(sec.n, i + 1, box.value);
    });
    const claude = a.claude;
    return h(
      "div",
      { class: "quiz-item" },
      h("div", { class: "quiz-q" }, h("span", { class: `quiz-kind ${q.kind}` }, KINDS[q.kind] || "확인"), h("span", {}, `${i + 1}. ${q.q}`)),
      box,
      h(
        "div",
        { class: "quiz-actions" },
        h("button", { class: "btn btn-sm" + (shown ? " btn-ghost" : ""), type: "button", onclick: () => reveal(sec, i, !shown) }, shown ? "정답 가리기" : "정답 보기"),
        shown
          ? h(
              "div",
              { class: "seg quiz-rate", role: "radiogroup", "aria-label": "스스로 매기기" },
              Object.entries(RATINGS).map(([k, label]) => h("button", { type: "button", class: a.rating === k ? "on" : "", role: "radio", "aria-checked": a.rating === k, onclick: () => rate(sec, i, a.rating === k ? "" : k) }, label)),
            )
          : null,
      ),
      shown ? h("div", { class: "quiz-answer" }, h("div", { class: "label" }, "모범 답"), h("p", {}, q.answer), q.explain ? h("p", { class: "hint" }, `근거: ${q.explain}`) : null) : null,
      claude && claude.verdict
        ? h(
            "div",
            { class: "quiz-feedback" + (claude.stale ? " stale" : "") },
            h("span", { class: `badge ${VERDICTS[claude.verdict][1]}` }, `Claude · ${VERDICTS[claude.verdict][0]}`),
            h("p", {}, claude.feedback),
            claude.stale ? h("p", { class: "hint" }, "이 채점 뒤에 답을 고쳤습니다. 다시 채점받을 수 있습니다.") : null,
          )
        : null,
    );
  }

  function queueSave(section, question, text) {
    const k = `${section}:${question}`;
    clearTimeout(saveTimers.get(k));
    saveTimers.set(k, setTimeout(() => { saveTimers.delete(k); saveAnswer(section, question, { text }); }, 700));
  }

  async function flushAnswers() {
    // 아직 저장되지 않은 답을 지금 저장한다 (다음 파트로 넘어가거나 채점받기 전에)
    const jobs = [];
    for (const [k, t] of saveTimers) {
      clearTimeout(t);
      const [section, question] = k.split(":").map(Number);
      const sec = view.sections[section - 1];
      jobs.push(saveAnswer(section, question, { text: (sec.answers[question - 1] || {}).text || "" }));
    }
    saveTimers.clear();
    await Promise.all(jobs);
  }

  async function saveAnswer(section, question, body) {
    try {
      return await api("POST", `/api/study/${KEY}/answer`, { section, question, ...body });
    } catch (err) {
      toast(`답을 저장하지 못했습니다: ${err.message}`, "err");
      return null;
    }
  }

  async function reveal(sec, i, show) {
    sec.answers[i] = { ...(sec.answers[i] || {}), revealed: show };
    render();
    await saveAnswer(sec.n, i + 1, { revealed: show });
  }

  async function rate(sec, i, rating) {
    sec.answers[i] = { ...(sec.answers[i] || {}), rating };
    render();
    await saveAnswer(sec.n, i + 1, { rating });
    await load(true);
  }

  async function grade(btn, sec) {
    await busy(btn, async () => {
      await flushAnswers();
      let job;
      try {
        job = await api("POST", `/api/study/${KEY}/grade`, { section: sec.n });
      } catch (err) {
        if (await Claude.explain(err)) return;
        throw err;
      }
      follow(job);
      render();
    });
  }

  async function translate(btn) {
    if (!confirm("이 논문 전체의 한국어 번역을 만듭니다. 십여 분과 Claude 사용량이 꽤 듭니다. 만들까요?")) return;
    await busy(btn, async () => {
      let job;
      try {
        job = await api("POST", `/api/study/${KEY}/translate`);
      } catch (err) {
        if (await Claude.explain(err)) return;
        throw err;
      }
      follow(job);
      render();
    });
  }

  // 채점 · 번역 작업이 끝날 때까지 몇 초마다 본다
  function follow(job) {
    watch = job;
    const tick = async () => {
      let jobs;
      try { jobs = (await api("GET", "/api/jobs")).jobs; } catch { setTimeout(tick, 6000); return; }
      const now = jobs.find((j) => j.id === job.id);
      if (now && ACTIVE.includes(now.state)) { setTimeout(tick, 3000); return; }
      watch = null;
      if (!now || now.state === "done") {
        toast(job.kind === "translate" ? "한국어 번역이 준비되었습니다." : "채점이 끝났습니다. 문항 아래에 피드백이 있습니다.");
        await load(true);
        if (job.kind === "translate" && view.translated) setLang("both");
      } else {
        toast(`${job.kind === "translate" ? "번역" : "채점"}을 끝내지 못했습니다: ${now.error || ""}`, "err");
        render();
      }
    };
    setTimeout(tick, 3000);
  }

  // ── 인용 문장 ──
  function claims(items, title) {
    if (!items.length) {
      return h("section", { class: "study-claims" }, h("div", { class: "section-head" }, h("h3", {}, title), h("span", { class: "n" }, "0")), h("p", { class: "hint" }, view.status === "missing" ? "이 논문의 검토안이 없습니다." : "이 파트에서는 다른 문헌을 인용한 문장이 뽑히지 않았습니다."));
    }
    const editable = view.status === "pending";
    return h(
      "section",
      { class: "study-claims" },
      h("div", { class: "section-head" }, h("h3", {}, title), h("span", { class: "n" }, items.length)),
      h("p", { class: "hint", style: "margin:-8px 0 14px" }, editable ? "이 논문이 여기서 다른 문헌을 인용하며 한 주장입니다. 위키에 넣지 않을 것은 끄세요. 문장 · 키워드를 고치려면 검토 화면에서 합니다." : "위키에 등록된 주장입니다."),
      h(
        "div",
        { class: "card" },
        h(
          "div",
          { class: "claims" },
          items.map((c) =>
            h(
              "div",
              { class: "claim" + (c.include ? "" : " off") },
              h(
                "div",
                { class: "claim-meta" },
                h("span", { class: `type ${c.type}` }, TYPE_LABELS[c.type] || c.type),
                c.keywords && c.keywords.length ? h("span", { class: "hint" }, c.keywords.join(" · ")) : null,
                editable ? h("label", { class: "switch", style: "margin-left:auto" }, h("input", { type: "checkbox", checked: c.include, onchange: (e) => include(c, e.target.checked) }), h("span", {}, "위키에 포함")) : null,
              ),
              h("p", { class: "claim-statement" }, c.statement),
              c.cites.length
                ? h("div", { class: "cite-row" }, h("span", { class: "cite-label" }, "인용 문헌"), h("div", { class: "works" }, c.cites.map((cite, i) => (c.cite_ids ? h("a", { class: "work", href: `/wiki/p/${encodeURIComponent(c.cite_ids[i])}` }, cite) : h("span", { class: "work" }, cite)))))
                : null,
              c.quote || c.location ? h("blockquote", { class: "claim-quote" }, c.quote ? `“${c.quote}”` : "", c.location ? h("span", { class: "loc" }, c.location) : null) : null,
            ),
          ),
        ),
      ),
    );
  }

  async function include(c, on) {
    c.include = on;
    render();
    try {
      await api("POST", `/api/study/${KEY}/claim`, { index: c.index, include: on });
    } catch (err) {
      c.include = !on;
      render();
      toast(err.message, "err");
    }
  }

  // ── 마치며 ──
  function finish() {
    const s = view.summary;
    const all = [...view.sections.flatMap((x) => x.claims), ...view.unplaced];
    const included = all.filter((c) => c.include).length;
    return [
      h("div", { class: "study-part-head" }, h("div", { class: "eyebrow" }, "마치며"), h("h2", {}, "읽은 것을 정리합니다")),
      h(
        "div",
        { class: "stats study-stats" },
        h("div", { class: "stat" }, h("div", { class: "num" }, `${s.done}/${s.parts}`), h("div", { class: "label" }, "읽은 파트")),
        h("div", { class: "stat" }, h("div", { class: "num" }, s.right), h("div", { class: "label" }, "맞음")),
        h("div", { class: "stat" }, h("div", { class: "num" }, s.unsure), h("div", { class: "label" }, "애매")),
        h("div", { class: "stat" }, h("div", { class: "num" }, s.wrong), h("div", { class: "label" }, "틀림")),
      ),
      s.weak.length
        ? h(
            "section",
            { class: "card", style: "margin-top:24px" },
            h("div", { class: "label" }, "다시 볼 문항"),
            h("div", { class: "rows" }, s.weak.map((w) => h("button", { type: "button", class: "row link-row", onclick: () => go(w.section - 1) }, h("div", { class: "grow" }, h("div", { class: "title" }, w.q), h("div", { class: "sub" }, `파트 ${w.section} · ${view.sections[w.section - 1].title}`)), h("div", { class: "side" }, h("span", { class: `badge ${w.result === "wrong" ? "err" : "warn"}` }, RATINGS[w.result]))))),
          )
        : null,
      s.open ? h("p", { class: "hint", style: "margin-top:14px" }, `아직 답을 매기지 않은 문항이 ${s.open}개 있습니다.`) : null,
      view.unplaced.length ? claims(view.unplaced, "어느 파트인지 찾지 못한 인용 문장") : null,
      register(included, all.length),
      h("div", { class: "study-foot" }, h("button", { class: "btn btn-ghost btn-danger btn-sm", type: "button", onclick: (e) => remove(e.currentTarget) }, "학습 자료 지우기"), h("span")),
    ];
  }

  function register(included, total) {
    if (view.status === "registered") {
      return h("div", { class: "card study-register" }, h("div", { class: "label" }, "위키"), h("p", {}, "이 논문은 위키에 등록되어 있습니다. 이 화면은 언제든 복습에 쓸 수 있습니다."), h("div", { class: "inline" }, h("a", { class: "btn btn-sm", href: `/wiki/p/${encodeURIComponent(view.paper_id)}` }, "문헌 문서 보기")));
    }
    if (view.status !== "pending") {
      return h("div", { class: "card study-register" }, h("div", { class: "label" }, "위키"), h("p", {}, "이 논문의 검토안이 없습니다 (폐기했거나, 다른 컴퓨터에서 등록 중일 수 있습니다). 학습 기록은 그대로 남아 있습니다."));
    }
    return h(
      "div",
      { class: "card study-register" },
      h("div", { class: "label" }, "위키에 등록"),
      h("p", {}, `인용 문장 ${total}개 가운데 ${included}개를 위키에 넣습니다. 논문은 ‘읽은 논문’으로, 인용된 문헌은 ‘인용 문헌’으로 등록되고 PDF 이름이 규칙대로 바뀝니다.`),
      h("p", { class: "hint" }, "문장 · 키워드 · 인용 문헌을 고치거나 ‘같은 문헌일 수 있는 것’을 확인하려면 검토 화면에서 합니다. 거기서 승인해도 이 학습 기록은 그대로 이어집니다."),
      h("div", { class: "inline", style: "margin-top:14px" }, h("button", { class: "btn btn-primary", type: "button", disabled: !included, onclick: (e) => approve(e.currentTarget) }, "위키에 등록"), h("a", { class: "btn", href: `/review/${KEY}` }, "검토 화면에서 자세히 보기")),
    );
  }

  async function approve(btn) {
    await busy(btn, async () => {
      const res = await api("POST", `/api/study/${KEY}/approve`);
      try {
        if (res.zotero && res.zotero.length) sessionStorage.setItem("pw-zotero-note", res.zotero.join(" "));
      } catch (_) {}
      location.href = `/wiki/p/${encodeURIComponent(res.paper_id)}?saved=1`;
    });
  }

  async function remove(btn) {
    if (!confirm("이 논문의 학습 자료(번역 · 퀴즈)와 답 · 채점 기록을 지울까요? 위키의 논문과 주장, 검토안은 그대로 남습니다.")) return;
    await busy(btn, async () => {
      await api("DELETE", `/api/study/${KEY}`);
      location.href = "/study";
    });
  }

  window.addEventListener("beforeunload", () => { if (saveTimers.size) flushAnswers(); });

  load(false).catch((err) => fill(root, h("div", { class: "card empty" }, h("h3", {}, "학습 자료를 불러오지 못했습니다"), h("p", {}, err.message))));
})();
