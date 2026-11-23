// 검토 화면: Claude Code 가 제안한 "주장 → 인용된 문헌"과 키워드를 고치고, 승인한 것만 위키에 저장한다.

(async () => {
  const root = $("#review");
  const KEY = encodeURIComponent(root.dataset.key);
  let draft;
  let nodes = [];
  let index = new Map();
  let refs = new Map(); // 참고문헌 번호 → 참고문헌
  let saveTimer = null;
  let saveState = "saved";
  let leaving = false;

  // 서버(store.norm)와 같은 규칙으로 이름을 비교한다
  const norm = (s) => (s || "").normalize("NFKC").toLowerCase().replace(/[\s\-_‐-―·/]+/g, " ").trim();
  const lookup = (name) => index.get(norm(name));
  const leafOf = (kw) => kw.path[kw.path.length - 1];
  const canon = (kw) => (lookup(leafOf(kw)) ? lookup(leafOf(kw)).id : "new:" + norm(leafOf(kw)));
  const cloneKw = (kw) => ({ path: kw.path.slice(), aliases: kw.aliases.slice(), description: kw.description });
  const refOrder = (a, b) => (parseInt(a.ref, 10) || 1e9) - (parseInt(b.ref, 10) || 1e9) || a.ref.localeCompare(b.ref);

  function buildIndex() {
    index = new Map();
    for (const n of nodes) index.set(norm(n.name), n);
    for (const n of nodes) for (const a of n.aliases) if (!index.has(norm(a))) index.set(norm(a), n);
  }

  function autosize(el) {
    el.style.height = "auto";
    el.style.height = el.scrollHeight + 2 + "px";
  }

  // ── 자동 저장 ──
  function payload() {
    return {
      summary: draft.summary,
      claims: draft.claims.map((c) => ({
        include: c.include,
        statement: c.statement,
        type: c.type,
        refs: c.refs.slice(),
        evidence: c.evidence,
        keywords: c.keywords.map(cloneKw),
        group: c.group || "",
      })),
    };
  }

  function setSaveState(state) {
    saveState = state;
    const el = $("#save-state");
    if (el) el.textContent = { saved: "변경 사항이 자동 저장되었습니다", dirty: "저장 중…", error: "자동 저장 실패 — 연결을 확인해 주세요" }[state];
  }

  function touch() {
    setSaveState("dirty");
    clearTimeout(saveTimer);
    saveTimer = setTimeout(save, 900);
  }

  async function save() {
    clearTimeout(saveTimer);
    try {
      await api("PUT", `/api/pending/${KEY}`, payload());
      setSaveState("saved");
    } catch {
      setSaveState("error");
    }
  }

  window.addEventListener("beforeunload", (e) => {
    if (saveState !== "saved" && !leaving) e.preventDefault();
  });

  // ── 키워드 대화상자 ──
  const dlg = $("#kw-dialog");
  const nameIn = $("#kw-name");
  const parentIn = $("#kw-parent");
  const aliasIn = $("#kw-aliases");
  const descIn = $("#kw-desc");
  let onKwSave = null;
  let onKwRemove = null;

  function fillDatalists() {
    $("#kw-names").replaceChildren(...nodes.map((n) => h("option", { value: n.name }, n.path.slice(0, -1).join(" › "))));
    $("#kw-paths").replaceChildren(...nodes.map((n) => h("option", { value: n.path.join(" > ") })));
  }

  function updateKwDialog() {
    const name = nameIn.value.trim();
    const node = name ? lookup(name) : null;
    $("#kw-existing").hidden = !node;
    $("#kw-new").hidden = !name || !!node;
    if (node) {
      const alias = norm(node.name) !== norm(name) ? ` (‘${name}’ 은 이 키워드의 별칭)` : "";
      $("#kw-existing").textContent = `기존 키워드 · ${node.path.join(" › ")}${alias}`;
    }
  }
  nameIn.addEventListener("input", updateKwDialog);
  $("#kw-cancel").addEventListener("click", () => dlg.close());
  $("#kw-save").addEventListener("click", () => onKwSave && onKwSave());
  $("#kw-remove").addEventListener("click", () => onKwRemove && onKwRemove());
  dlg.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.target.tagName === "INPUT") {
      e.preventDefault();
      onKwSave && onKwSave();
    }
  });

  function dedupe() {
    for (const c of draft.claims) {
      const seen = new Set();
      c.keywords = c.keywords.filter((k) => !seen.has(canon(k)) && seen.add(canon(k)));
    }
  }

  function openKw(claim, ki) {
    const editing = ki != null ? claim.keywords[ki] : null;
    const wasNew = editing && !lookup(leafOf(editing));
    nameIn.value = editing ? (lookup(leafOf(editing)) || { name: leafOf(editing) }).name : "";
    parentIn.value = wasNew ? editing.path.slice(0, -1).join(" > ") : "";
    aliasIn.value = wasNew ? editing.aliases.join(", ") : "";
    descIn.value = wasNew ? editing.description : "";
    $("#kw-remove").hidden = !editing;
    updateKwDialog();

    onKwRemove = () => {
      claim.keywords.splice(ki, 1);
      dlg.close();
      commitStructure();
    };
    onKwSave = () => {
      const name = nameIn.value.trim().replace(/\s+/g, " ");
      if (!name) return nameIn.focus();
      const node = lookup(name);
      let kw;
      if (node) {
        kw = { path: node.path.slice(), aliases: [], description: "" };
      } else {
        const parent = parentIn.value.split(">").map((s) => s.trim()).filter(Boolean);
        const aliases = aliasIn.value.split(",").map((s) => s.trim()).filter(Boolean);
        kw = { path: [...parent, name], aliases, description: descIn.value.trim() };
      }
      if (editing && wasNew) {
        // 제안된 새 키워드를 고치면, 같은 키워드를 쓰는 다른 주장에도 함께 반영한다
        const old = canon(editing);
        for (const c of draft.claims) c.keywords = c.keywords.map((k) => (canon(k) === old ? cloneKw(kw) : k));
      } else if (editing) {
        claim.keywords[ki] = kw;
      } else {
        claim.keywords.push(kw);
      }
      if (!node) {
        const id = canon(kw); // 새 키워드의 정의(경로·별칭·설명)는 검토안 전체에서 하나로 맞춘다
        for (const c of draft.claims) c.keywords = c.keywords.map((k) => (canon(k) === id ? cloneKw(kw) : k));
      }
      dedupe();
      dlg.close();
      commitStructure();
    };
    dlg.showModal();
    nameIn.focus();
    nameIn.select();
  }

  // ── 주장 카드 ──
  function kwChip(claim, kw, ki) {
    const node = lookup(leafOf(kw));
    const title = (node ? node.path : kw.path).join(" › ");
    return h("button", { class: "chip" + (node ? "" : " new"), type: "button", title, onclick: () => openKw(claim, ki) }, node ? node.name : leafOf(kw));
  }

  // 문헌의 짧은 표기 (Kim et al. (2023)). 서버가 주지 않으면 저자와 연도로 만든다 —
  // 프로그램을 업데이트한 뒤 예전 서버가 그대로 떠 있을 때도 화면이 비지 않게.
  function citeOf(r) {
    if (r.cite) return r.cite;
    const name = (a) => (a && (a.family || a.name)) || "";
    const authors = r.authors || [];
    const first = name(authors[0]);
    let who = first || (r.title || "").slice(0, 40);
    if (first && authors.length === 2 && !r.et_al) who = `${first} & ${name(authors[1])}`;
    else if (first && (authors.length > 1 || r.et_al)) who = /[가-힣]/.test(first) ? `${first} 외` : `${first} et al.`;
    return `${who} (${r.year || "n.d."})`;
  }

  // 주장에 인용된 문헌: 참고문헌 번호와 짧은 표기. ×로 빼고, 목록에서 골라 더한다.
  function refChips(claim) {
    const chips = claim.refs.map((label) => {
      const r = refs.get(label);
      const text = r ? `[${label}] ${citeOf(r)}` : `[${label}]`;
      return h(
        "span",
        { class: "work", title: r ? r.title : "참고문헌 목록에 없는 번호" },
        text,
        h("button", { type: "button", title: "이 주장에서 빼기", "aria-label": `${text} 빼기`, onclick: () => { claim.refs = claim.refs.filter((x) => x !== label); commitStructure(); } }, "×"),
      );
    });
    const rest = [...refs.values()].filter((r) => !claim.refs.includes(r.ref)).sort(refOrder);
    const add = h(
      "select",
      { "aria-label": "인용 문헌 추가", onchange: (e) => { if (e.target.value) { claim.refs.push(e.target.value); commitStructure(); } } },
      h("option", { value: "" }, "+ 문헌 추가"),
      rest.map((r) => h("option", { value: r.ref }, `[${r.ref}] ${citeOf(r)} ${r.title}`.slice(0, 90))),
    );
    return h("div", { class: "works" }, chips, rest.length ? add : null);
  }

  function claimCard(claim, i) {
    const cls = () => `rc ${claim.type}${claim.include ? "" : " off"}`;
    const card = h("article", { class: cls() });
    const statement = h("textarea", { class: "input bare statement", rows: 1, value: claim.statement, placeholder: "이 문헌들을 인용하며 쓸 수 있는 주장을 한 문장으로", oninput: (e) => { claim.statement = e.target.value; autosize(e.target); touch(); renderAside(); } });
    const quote = h("textarea", { class: "input", rows: 2, value: claim.evidence.quote, placeholder: "이 논문의 인용 문장 (원문 그대로)", oninput: (e) => { claim.evidence.quote = e.target.value; autosize(e.target); touch(); } });

    card.append(
      h(
        "div",
        { class: "rc-head" },
        h("span", { class: "idx" }, String(i + 1).padStart(2, "0")),
        h("select", { "aria-label": "주장 유형", onchange: (e) => { claim.type = e.target.value; card.className = cls(); touch(); } }, Object.entries(TYPE_LABELS).map(([v, label]) => h("option", { value: v, selected: v === claim.type }, label))),
        h("span", { class: "spacer" }),
        h("label", { class: "switch" }, h("input", { type: "checkbox", checked: claim.include, onchange: (e) => { claim.include = e.target.checked; card.className = cls(); touch(); renderAside(); renderRefs(); } }), h("span", {}, "위키에 포함")),
        h("button", { class: "icon-btn", type: "button", title: "이 주장 삭제", onclick: () => { if (confirm("이 주장을 검토안에서 삭제할까요?")) { draft.claims.splice(draft.claims.indexOf(claim), 1); commitStructure(); } } }, svg(ICON.x)),
      ),
      h(
        "div",
        { class: "rc-body" },
        statement,
        h("div", { class: "sub-label" }, "인용 문헌"),
        refChips(claim),
        h("div", { class: "sub-label" }, "근거 (이 논문의 인용 문장)"),
        h("div", { class: "evidence" }, quote, h("input", { class: "input", value: claim.evidence.location, placeholder: "위치 (예: p.5)", oninput: (e) => { claim.evidence.location = e.target.value; touch(); } })),
        h("div", { class: "sub-label" }, "키워드"),
        h("div", { class: "chips" }, claim.keywords.map((kw, ki) => kwChip(claim, kw, ki)), h("button", { class: "chip add", type: "button", onclick: () => openKw(claim, null) }, "+ 키워드")),
        claim.same && claim.group ? h("p", { class: "same" }, `같은 주장으로 묶임 · ${claim.same.sources.join(", ")}: “${claim.same.statement}”`) : null,
      ),
    );
    requestAnimationFrame(() => { autosize(statement); autosize(quote); });
    return card;
  }

  function renderClaims() {
    $("#claims").replaceChildren(...draft.claims.map(claimCard));
  }

  // ── 참고문헌 목록: 어느 문헌이 등록되고, 이미 위키에 있는 문헌은 무엇인지 ──
  function usedRefs() {
    const used = new Map();
    for (const c of draft.claims) if (c.include) for (const label of c.refs) if (refs.has(label)) used.set(label, (used.get(label) || 0) + 1);
    return used;
  }

  function renderRefs() {
    const used = usedRefs();
    const rows = [...refs.values()].sort(refOrder).map((r) => {
      const n = used.get(r.ref) || 0;
      let state = h("span", { class: "badge" }, "새 문헌");
      if (!n) state = h("span", { class: "badge" }, "주장 없음 · 등록 안 됨");
      else if (r.status === "existing") state = h("a", { class: "badge ok", href: `/wiki/p/${encodeURIComponent(r.id)}`, target: "_blank", rel: "noopener", title: "위키에 이미 있는 문헌 — 새 창에서 보기" }, r.read ? "위키에 있음 · 읽은 논문" : r.known ? `위키에 있음 · 논문 ${r.known.sources}편이 인용` : "위키에 있음");
      else if (r.status === "self") state = h("span", { class: "badge" }, "이 논문 자신");
      return h(
        "li",
        { class: n ? "" : "unused" },
        h("span", { class: "no" }, `[${r.ref}]`),
        h(
          "span",
          { class: "t" },
          h("b", {}, citeOf(r)),
          ` ${r.title}`,
          r.venue ? ` · ${r.venue}` : "",
          r.doi ? h("a", { class: "doi", href: `https://doi.org/${r.doi}`, target: "_blank", rel: "noopener", title: "DOI 로 원문 확인" }, "DOI") : null,
          // 표기가 다른데 같은 문헌으로 이은 것은 근거를, 확신이 없어 따로 두는 것은 후보를 보인다
          ["version", "twin", "similar", "forced"].includes(r.match) ? h("span", { class: "same-note" }, `위키의 “${r.linked_title}” 과 같은 문헌으로 이음 — ${{ version: "프리프린트와 출판본", twin: "제목·제1저자·연도가 같고 DOI만 다름", similar: "제1저자·연도가 같고 제목이 거의 같음", forced: "직접 지정" }[r.match]}`) : null,
          (r.maybe || []).map((m) => h("span", { class: "same-note maybe" }, "같은 문헌일 수 있음: ", h("a", { href: `/wiki/p/${encodeURIComponent(m.id)}`, target: "_blank", rel: "noopener" }, `${m.cite} ${m.title}`), ` — ${m.why}`)),
        ),
        h("span", {}, n ? h("span", { class: "hint", style: "margin-right:8px" }, `주장 ${n}`) : null, state),
      );
    });
    fill($("#refs"), h("ul", { class: "ref-list" }, rows));
    $("#refs-n").textContent = `${used.size} / ${refs.size}`;
  }

  function commitStructure() {
    renderClaims();
    renderRefs();
    renderAside();
    touch();
  }

  // ── 오른쪽 요약 ──
  function renderAside() {
    const included = draft.claims.filter((c) => c.include);
    const fresh = new Map();
    for (const c of included) {
      for (const kw of c.keywords) {
        kw.path.forEach((p, idx) => {
          if (!lookup(p) && !fresh.has(norm(p))) fresh.set(norm(p), { name: p, parent: kw.path.slice(0, idx) });
        });
      }
    }
    const used = usedRefs();
    const known = [...used.keys()].filter((label) => refs.get(label).status === "existing").length;
    const noKw = included.filter((c) => !c.keywords.length).length;
    const noText = included.filter((c) => !c.statement.trim()).length;
    const noRef = included.filter((c) => !c.refs.some((label) => refs.has(label))).length;
    const problems = [];
    if (noText) problems.push(`문장이 빈 주장 ${noText}개`);
    if (noRef) problems.push(`인용 문헌이 없는 주장 ${noRef}개`);
    if (noKw) problems.push(`키워드가 없는 주장 ${noKw}개`);

    fill(
      $("#aside"),
      h("h3", {}, "위키에 저장될 내용"),
      h("div", { class: "big" }, included.length, h("small", {}, `/ ${draft.claims.length} 주장`)),
      h("p", { class: "hint", style: "margin-top:8px" }, `인용 문헌 ${used.size}편` + (known ? ` · 그중 ${known}편은 이미 위키에 있어 인용 기록이 더해집니다` : "")),
      problems.length ? h("p", { class: "status-line err" }, problems.join(" · ")) : null,
      h("hr"),
      h("h3", {}, `새로 만들어질 키워드 ${fresh.size}`),
      fresh.size
        ? h("ul", { class: "new-kw" }, [...fresh.values()].map((f) => h("li", {}, h("b", {}, f.name), h("span", { class: "p" }, f.parent.length ? f.parent.join(" › ") + " 아래" : "최상위 분류로 생성"))))
        : h("p", { class: "hint" }, "모든 주장이 기존 키워드에 정리됩니다."),
      h("hr"),
      h("button", { class: "btn btn-primary btn-lg", type: "button", disabled: !included.length || problems.length > 0, onclick: (e) => approve(e.currentTarget) }, draft.replaces && draft.replaces_kind === "read" ? "승인하고 기존 문서 대체" : "승인하고 위키에 저장"),
      h("button", { class: "btn btn-ghost btn-danger", type: "button", onclick: (e) => discard(e.currentTarget) }, "검토안 폐기"),
      h("p", { class: "hint", id: "save-state", style: "margin-top:14px;text-align:center" }, ""),
    );
    setSaveState(saveState);
  }

  async function approve(btn) {
    await busy(btn, async () => {
      clearTimeout(saveTimer);
      const res = await api("POST", `/api/pending/${KEY}/approve`, payload());
      try {
        if (res.zotero && res.zotero.length) sessionStorage.setItem("pw-zotero-note", res.zotero.join(" "));
      } catch (_) {}
      leaving = true;
      location.href = `/wiki/p/${encodeURIComponent(res.paper_id)}?saved=1`;
    });
  }

  async function discard(btn) {
    if (!confirm("이 검토안을 폐기할까요? 위키에는 아무것도 저장되지 않고, PDF는 논문 폴더에 그대로 남습니다.")) return;
    await busy(btn, async () => {
      clearTimeout(saveTimer);
      await api("DELETE", `/api/pending/${KEY}`);
      leaving = true;
      location.href = "/inbox";
    });
  }

  // ── 첫 화면 ──
  function renderPage() {
    const meta = draft.paper;
    const v = draft.view;
    const links = [
      v.pdf_uri && h("a", { class: "btn btn-sm", href: v.pdf_uri, target: v.pdf_uri.startsWith("/") ? "_blank" : null, rel: "noopener" }, "PDF 열어 대조하기"),
      v.zotero_uri && h("a", { class: "btn btn-sm", href: v.zotero_uri }, "Zotero에서 열기"),
    ];
    const notes = [];
    if (draft.replaces && draft.replaces_kind === "read") notes.push(h("span", { class: "badge warn" }, "이미 위키에 있는 논문 · 승인하면 기존 문서를 대체합니다"));
    if (draft.replaces && draft.replaces_kind === "cited") notes.push(h("span", { class: "badge wait" }, "인용 문헌으로 위키에 있던 논문 · 승인하면 읽은 논문이 됩니다"));

    // 등록되면 생기는 것: 인용 키와, 규칙에 맞게 바뀔 PDF 이름
    const pdf = v.pdf || {};
    const currentName = pdf.current ? pdf.current.split("/").pop() : "";
    const outcome = [h("span", {}, h("span", { class: "hint" }, "인용 키 "), h("code", { class: "path" }, "@" + v.citekey))];
    if (pdf.current) {
      outcome.push(
        h("span", {}, h("span", { class: "hint" }, "PDF "), h("code", { class: "path" }, currentName), pdf.will_be && pdf.will_be !== currentName ? [h("span", { class: "hint" }, " → 승인하면 "), h("code", { class: "path" }, pdf.will_be)] : null),
      );
    }
    // 서지 정보가 어디서 왔는지(DOI 등록 기록으로 확인했는지)와, 등록하면 Zotero 에 어떻게 되는지
    const st = v.status;
    if (st) {
      outcome.push(h("span", {}, h("span", { class: "hint" }, "서지 정보 "), st.bib));
      outcome.push(h("span", {}, h("span", { class: "hint" }, "Zotero "), st.zotero));
    }
    const cautions = [...(v.warnings || []), v.counts || null, v.note ? `읽은 쪽의 메모: ${v.note}` : null].filter(Boolean);

    const summary = h("textarea", { class: "input bare", rows: 1, value: draft.summary, placeholder: "논문 요약", oninput: (e) => { draft.summary = e.target.value; autosize(e.target); touch(); } });

    root.replaceChildren(
      h(
        "header",
        { class: "page-head" },
        h("div", { class: "eyebrow" }, h("a", { href: "/inbox" }, "새 논문 · 검토"), " / 검토"),
        h("h1", {}, meta.title || "(제목 없음)"),
        h("div", { class: "doc-meta" }, h("span", {}, [v.authors, meta.year, meta.venue].filter(Boolean).join(" · "))),
        h("div", { class: "doc-meta" }, outcome),
        h("div", { class: "actions" }, links, notes),
        cautions.length ? h("div", { class: "callout", style: "margin-top:20px" }, h("div", { class: "t" }, "확인할 점"), cautions.map((c) => h("div", { class: "d" }, c))) : null,
      ),
      h(
        "div",
        { class: "review" },
        h(
          "div",
          {},
          h("div", { class: "card", style: "margin-bottom:28px" }, h("div", { class: "label" }, "요약"), summary),
          h("div", { class: "section-head" }, h("h2", {}, "이 논문이 문헌을 인용하며 한 주장"), h("span", { class: "hint" }, "주장·인용 문헌·키워드를 원문의 인용 문장과 대조해 고친 뒤 승인하세요")),
          h("div", { id: "claims" }),
          h("div", { style: "margin-top:16px" }, h("button", { class: "btn", type: "button", onclick: () => { draft.claims.push({ include: true, statement: "", type: "finding", refs: [], evidence: { quote: "", location: "" }, keywords: [], group: "" }); commitStructure(); const cards = $$("#claims .rc"); $("textarea", cards[cards.length - 1]).focus(); } }, svg(ICON.plus), "주장 직접 추가")),
          h("div", { class: "section-head", style: "margin-top:40px" }, h("h2", {}, "참고문헌"), h("span", { class: "n", id: "refs-n" }, ""), h("span", { class: "hint" }, "주장에 인용된 문헌만 위키에 등록됩니다")),
          h("div", { class: "card", id: "refs" }),
        ),
        h("aside", { class: "review-aside" }, h("div", { class: "aside-card", id: "aside" })),
      ),
    );
    requestAnimationFrame(() => autosize(summary));
    renderClaims();
    renderRefs();
    renderAside();
  }

  try {
    const data = await api("GET", `/api/pending/${KEY}`);
    draft = data.draft;
    nodes = data.ontology;
    buildIndex();
    fillDatalists();
    refs = new Map((draft.references || []).map((r) => [r.ref, r]));
    for (const c of draft.claims) {
      c.evidence = c.evidence || { quote: "", location: "" };
      c.refs = c.refs || [];
      c.keywords = c.keywords.map((k) => ({ path: k.path, aliases: k.aliases || [], description: k.description || "" }));
    }
    renderPage();
  } catch (err) {
    root.replaceChildren(h("div", { class: "card empty" }, h("h3", {}, "검토안을 불러오지 못했습니다"), h("p", {}, err.message), h("a", { class: "btn", href: "/inbox" }, "새 논문 · 검토로")));
  }
})();
