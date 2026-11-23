// 설정(첫 실행 시에는 설치 안내) 화면.

(() => {
  const root = $("#settings");
  let data = null;
  let changingVault = false;
  const results = {}; // 방금 한 일의 결과: {zotero: {ok, text}, claude: {...}, vault: {...}}

  const statusLine = (key) => {
    const r = results[key];
    return h("p", { class: "status-line" + (r ? (r.ok ? " ok" : " err") : "") }, r ? r.text : "");
  };

  // 방금(첫 설정 직후 새로고침 전에) 한 일의 결과를 이어서 보여준다
  const carried = sessionStorage.getItem("paperwiki-vault-msg");
  if (carried) {
    results.vault = { ok: true, text: carried };
    sessionStorage.removeItem("paperwiki-vault-msg");
  }

  async function reload(rescan) {
    data = await api("GET", "/api/settings" + (rescan ? "?rescan=1" : ""));
    render();
  }

  async function run(key, btn, fn, okText) {
    if (btn) btn.disabled = true;
    try {
      const res = await fn();
      results[key] = { ok: true, text: typeof okText === "function" ? okText(res) : okText };
    } catch (err) {
      results[key] = { ok: false, text: err.message };
    }
    await reload();
  }

  function step(n, done, title, desc, ...body) {
    return h(
      "div",
      { class: "step" + (done ? " done" : "") },
      h("div", { class: "step-n" }, done ? "✓" : n),
      h("div", { class: "card" }, h("h2", {}, title), h("p", { class: "desc" }, desc), ...body),
    );
  }

  // ── 1. 저장 위치 ──
  let pickedStorage; // 화면을 다시 그려도 사용자가 고른 선택지를 유지한다 (경로 또는 "custom")
  let customPath = "";
  let driveTimer = null;

  async function recheck(btn) {
    if (btn) btn.disabled = true;
    delete results.gdrive;
    try {
      await reload(true); // 드라이브를 다시 훑어 방금 동기화된 위키도 찾는다
    } catch (err) {
      toast(err.message, "err");
    }
  }

  async function launchDrive(btn) {
    btn.disabled = true;
    try {
      await api("POST", "/api/gdrive/launch");
    } catch (err) {
      btn.disabled = false;
      return toast(err.message, "err");
    }
    results.gdrive = { ok: true, text: "구글 드라이브를 실행했습니다. 연결될 때까지 잠시 기다려 주세요…" };
    render();
    let tries = 0;
    clearInterval(driveTimer);
    driveTimer = setInterval(async () => {
      tries += 1;
      let fresh;
      try {
        fresh = await api("GET", "/api/settings");
      } catch {
        return;
      }
      if (fresh.gdrive.state !== "ready" && tries < 20) return;
      clearInterval(driveTimer);
      data = fresh;
      results.gdrive =
        fresh.gdrive.state === "ready"
          ? { ok: true, text: "구글 드라이브가 연결되었습니다. 사용할 계정을 골라 주세요." }
          : { ok: false, text: "아직 연결되지 않았습니다. 구글 드라이브에 로그인되어 있는지 확인한 뒤 [다시 확인] 을 눌러 주세요." };
      render();
    }, 2000);
  }

  function driveSection(drives, choice) {
    const g = data.gdrive;
    const again = (label) => h("button", { class: "btn btn-sm", type: "button", onclick: (e) => recheck(e.currentTarget) }, label || "다시 확인");
    if (g.state === "ready") {
      const again = (label) => h("button", { class: "link-btn", type: "button", onclick: (e) => recheck(e.currentTarget) }, label);
      const describe = (o) => {
        if (!o.exists) return "이 구글 계정의 내 드라이브에 새 위키를 만듭니다. 같은 계정으로 로그인한 다른 컴퓨터에서 불러와 이어서 쓸 수 있습니다.";
        const s = o.summary || {};
        return [`문헌 ${s.papers ?? "?"}편`, `키워드 ${s.keywords ?? "?"}개`, s.pending ? `검토 대기 ${s.pending}건` : null, s.modified ? `마지막 수정 ${s.modified}` : null].filter(Boolean).join(" · ");
      };
      return [
        h("div", { class: "group-label" }, "구글 드라이브에 저장 ", h("span", { class: "badge ok" }, "권장"), new Set(drives.map((o) => o.base)).size > 1 ? " — 사용할 계정을 고르세요" : ""),
        drives.some((o) => o.exists)
          ? h("div", { class: "callout found" }, h("div", { class: "t" }, "이미 만들어 둔 위키를 찾았습니다"), h("div", { class: "d" }, "다른 컴퓨터에서 쓰던 위키를 그대로 불러와 이어서 씁니다. 불러오기는 위키의 내용을 바꾸지 않습니다."))
          : null,
        drives.map((o) => choice(o.path, o.email || `구글 드라이브${o.mount ? ` (${o.mount})` : ""}`, describe(o), o)),
        drives.some((o) => !o.exists)
          ? h("p", { class: "hint", style: "margin-top:10px" }, "이 계정으로 다른 컴퓨터에서 이미 위키를 만들었는데 ‘기존 위키’로 보이지 않나요? 구글 드라이브 동기화가 아직 끝나지 않았을 수 있습니다. 새로 만들면 위키가 두 개로 갈라지니, 잠시 뒤 ", again("다시 확인"), "을 눌러 주세요.")
          : null,
        h("p", { class: "hint", style: "margin-top:6px" }, "다른 구글 계정을 쓰려면 구글 드라이브 데스크톱에서 계정을 추가하세요 (작업 표시줄의 드라이브 아이콘 → 프로필 사진 → 계정 추가). 추가한 뒤 ", again("다시 확인"), "을 누르면 여기에 나타납니다."),
        statusLine("gdrive"),
      ];
    }
    if (g.state === "not_running") {
      return [
        h(
          "div",
          { class: "callout" },
          h("div", { class: "t" }, "구글 드라이브 데스크톱이 꺼져 있거나 로그인되어 있지 않습니다"),
          h("div", { class: "d" }, "실행한 뒤 쓰려는 구글 계정으로 로그인하면, 여기에서 그 계정의 드라이브를 고를 수 있습니다."),
          h("div", { class: "inline" }, g.can_launch ? h("button", { class: "btn btn-primary btn-sm", type: "button", onclick: (e) => launchDrive(e.currentTarget) }, "구글 드라이브 실행") : null, again()),
        ),
        statusLine("gdrive"),
      ];
    }
    return [
      h(
        "div",
        { class: "callout" },
        h("div", { class: "t" }, "이 컴퓨터에 구글 드라이브 데스크톱이 없습니다"),
        h("div", { class: "d" }, "위키를 구글 드라이브에 두고 다른 컴퓨터에서 이어 쓰려면 먼저 설치해 주세요. 설치한 뒤 쓰려는 구글 계정으로 로그인하고 [설치했어요 · 다시 확인] 을 누르면 계정을 고를 수 있습니다."),
        h("div", { class: "inline" }, h("a", { class: "btn btn-primary btn-sm", href: g.download_url, target: "_blank", rel: "noopener" }, "구글 드라이브 데스크톱 설치하기"), again("설치했어요 · 다시 확인")),
      ),
      statusLine("gdrive"),
    ];
  }

  // PDF 이름 규칙: 보기 · 바꾸기 (바꾸면 이미 등록된 논문의 PDF 에도 적용된다)
  let editingName = false;
  function namingRow() {
    const n = data.pdf_name;
    if (!n) return null;
    if (!editingName) {
      return [
        h("p", { style: "margin-top:14px" }, h("span", { class: "hint" }, "PDF 이름 규칙 "), h("code", { class: "path" }, n.pattern + ".pdf"), " ", h("button", { class: "link-btn", type: "button", onclick: () => { editingName = true; render(); } }, "바꾸기")),
        h("p", { class: "hint", style: "margin-top:4px" }, "예: ", n.example),
        statusLine("naming"),
      ];
    }
    const input = h("input", { class: "input", value: n.pattern, autocomplete: "off", "aria-label": "PDF 이름 규칙" });
    const save = (btn) =>
      run("naming", btn, () => api("POST", "/api/pdf-name", { pattern: input.value }), (r) => {
        editingName = false;
        return `이름 규칙을 바꿨습니다${r.renamed ? ` · 등록된 PDF ${r.renamed}개의 이름을 바꿨습니다` : ""}${r.failed ? ` · ${r.failed}개는 바꾸지 못했습니다 (열려 있는 파일을 닫고 다시 시도해 주세요)` : ""}.`;
      });
    return [
      h("div", { class: "inline", style: "margin-top:14px" }, input, h("button", { class: "btn btn-sm", type: "button", onclick: (e) => save(e.currentTarget) }, "저장"), h("button", { class: "btn btn-ghost btn-sm", type: "button", onclick: () => { editingName = false; delete results.naming; render(); } }, "취소")),
      h("p", { class: "hint", style: "margin-top:6px" }, "쓸 수 있는 항목: {title} 제목 · {author} 제1저자(둘 이상이면 et al.) · {year} 연도 · {citekey} 인용 키. 예: {author} {year} - {title}"),
      statusLine("naming"),
    ];
  }

  function vaultStep() {
    const cfg = data.config;
    const ok = data.vault_state === "ok";
    if (ok && !changingVault) {
      const s = data.stats;
      const where = data.storage_kind === "gdrive" ? `구글 드라이브 · ${data.storage_account || "기기 간 동기화"}` : "이 컴퓨터 (로컬)";
      return step(
        1,
        true,
        "위키 저장 위치",
        "위키는 폴더 하나입니다: 키워드·논문 문서(마크다운)와 논문 PDF가 함께 들어 있습니다. 구글 드라이브에 두면 다른 컴퓨터에서도 같은 위키와 같은 PDF를 이어서 씁니다.",
        h("p", {}, h("span", { class: "badge" + (data.storage_kind === "gdrive" ? " ok" : "") }, where), " ", h("code", { class: "path" }, cfg.vault_path)),
        s
          ? h("p", { class: "hint", style: "margin-top:10px" }, `읽은 논문 ${s.papers} · 인용 문헌 ${s.cited} · 주장 ${s.claims} · 키워드 ${s.keywords} · 언어 ${data.language === "en" ? "English" : "한국어"}`)
          : h("p", { class: "status-line err" }, data.vault_warning),
        h("div", { class: "group-label" }, "논문 폴더"),
        h("p", { class: "muted" }, "읽을 논문 PDF를 이 폴더에 넣습니다. 파일 이름은 무엇이든 괜찮고, 위키에 등록되면 아래 규칙의 이름으로 바뀝니다."),
        h("p", { style: "margin-top:8px" }, h("code", { class: "path" }, data.pdf_dir)),
        namingRow(),
        h("div", { class: "inline", style: "margin-top:18px" }, h("button", { class: "btn btn-sm", type: "button", onclick: () => { changingVault = true; render(); } }, "다른 위치·계정으로 바꾸기")),
        statusLine("vault"),
      );
    }

    const drives = data.storage_options.filter((o) => o.kind === "gdrive");
    const local = data.storage_options.find((o) => o.kind === "local");
    if (pickedStorage === undefined && drives.length) pickedStorage = (drives.find((o) => o.exists) || drives[0]).path; // 드라이브가 없으면 미리 고르지 않는다
    if (pickedStorage && pickedStorage !== "custom" && ![...drives, local].some((o) => o.path === pickedStorage)) pickedStorage = undefined;

    const labelFor = (value) => {
      const o = data.storage_options.find((x) => x.path === value);
      if (o && o.exists) return "이 위키 불러오기";
      return o ? "여기에 새 위키 만들기" : "이 위치 사용";
    };
    const submitBtn = h("button", { class: "btn btn-primary", type: "button", onclick: (e) => submit(e.currentTarget, false) }, labelFor(pickedStorage));
    const pick = (value) => {
      pickedStorage = value;
      submitBtn.textContent = labelFor(value);
    };
    const choice = (value, title, desc, o, extra) =>
      h(
        "label",
        { class: "choice" },
        h("input", { type: "radio", name: "storage", value, checked: pickedStorage === value, onchange: () => pick(value) }),
        h(
          "div",
          { style: "flex:1" },
          h("div", { class: "t" }, title, o && o.exists ? h("span", { class: "badge wait", style: "margin-left:8px" }, "기존 위키") : null),
          h("div", { class: "d" }, desc),
          o ? h("code", {}, o.path) : null,
          extra,
        ),
      );
    const customInput = h("input", { class: "input", value: customPath, placeholder: "예: D:\\Research\\PaperWiki", style: "margin-top:8px", oninput: (e) => { customPath = e.target.value; }, onfocus: () => { pick("custom"); $("input[name=storage][value=custom]").checked = true; } });
    const lang = h("select", { class: "input", style: "max-width:200px" }, h("option", { value: "ko" }, "한국어"), h("option", { value: "en" }, "English"));

    const submit = async (btn, confirmNonEmpty) => {
      if (!pickedStorage) return toast("위키를 저장할 위치를 골라 주세요.", "err");
      const path = pickedStorage === "custom" ? customPath.trim() : pickedStorage;
      if (!path) return toast("폴더 경로를 입력해 주세요.", "err");
      btn.disabled = true;
      try {
        const res = await api("POST", "/api/vault", { path, language: lang.value, confirm_nonempty: confirmNonEmpty });
        const s = res.summary || {};
        const message = res.connected_existing
          ? `기존 위키를 불러왔습니다 · 문헌 ${s.papers ?? "?"}편 · 키워드 ${s.keywords ?? "?"}개. Claude Code 스킬과 Zotero 연결은 컴퓨터마다 따로이므로 아래에서 한 번씩 설정해 주세요.`
          : "새 위키를 만들었습니다.";
        results.vault = { ok: true, text: message };
        changingVault = false;
        clearInterval(driveTimer);
        if (!ok) {
          sessionStorage.setItem("paperwiki-vault-msg", message); // 첫 설정: 새로고침 뒤에도 보이도록
          return location.reload();
        }
        await reload();
      } catch (err) {
        if (err.status === 409 && !confirmNonEmpty && confirm(err.message)) return submit(btn, true);
        btn.disabled = false;
        if (err.status !== 409) toast(err.message, "err");
      }
    };

    return step(
      1,
      false,
      "위키 저장 위치",
      "위키는 폴더 하나입니다: 키워드·논문 문서와 논문 PDF가 함께 들어갑니다. 구글 드라이브에 두면 구글 드라이브 데스크톱이 동기화해 주므로, 다른 컴퓨터에서 같은 계정으로 이어서 쓸 수 있습니다.",
      driveSection(drives, choice),
      h("div", { class: "group-label" }, "다른 방법"),
      choice(local.path, "이 컴퓨터에만 저장", "동기화 없이 이 컴퓨터의 문서 폴더에 둡니다. 다른 컴퓨터에서는 이어 쓸 수 없습니다.", local),
      choice("custom", "폴더 직접 지정", "다른 동기화 폴더나 이미 만들어 둔 위키 폴더의 전체 경로를 입력합니다.", null, customInput),
      h("label", { class: "field", style: "margin-top:20px" }, h("span", {}, "위키에 쓰이는 언어 (새 위키를 만들 때만 적용)"), lang),
      h(
        "div",
        { class: "inline", style: "margin-top:22px" },
        submitBtn,
        ok ? h("button", { class: "btn btn-ghost", type: "button", onclick: () => { changingVault = false; render(); } }, "취소") : null,
      ),
      ok ? h("p", { class: "hint", style: "margin-top:12px" }, "기존 위키 내용을 옮기려면 폴더를 통째로 복사한 다음 새 위치를 지정하세요.") : null,
    );
  }

  // ── 3. Zotero ──
  function zoteroStep() {
    const cfg = data.config;
    const setMode = async (mode) => {
      await api("POST", "/api/settings", { zotero_mode: mode });
      delete results.zotero;
      await reload();
    };
    const keyInput = h("input", { class: "input", type: "password", placeholder: data.secrets.zotero_api_key ? "저장된 키가 있습니다 · 바꾸려면 새 키 입력" : "Zotero API 키", autocomplete: "off" });
    const web = cfg.zotero_mode === "web";
    return step(
      3,
      results.zotero && results.zotero.ok,
      "Zotero 연결",
      "위키에 등록한 읽은 논문은 Zotero에도 있는 논문이 되도록 맞춥니다. 같은 논문이 Zotero에 있으면 그 항목과 연결해 서지 정보와 인용 키를 그대로 쓰고, 없으면 새 항목으로 넣습니다(위키의 인용 키, 논문 폴더의 PDF 링크 포함). 기존 항목을 고치거나 지우지는 않습니다. Zotero가 없어도 논문 폴더의 PDF만으로 위키를 만들 수 있습니다.",
      h("label", { class: "choice" }, h("input", { type: "radio", name: "zmode", checked: !web, onchange: () => setMode("local") }), h("div", {}, h("div", { class: "t" }, "이 컴퓨터의 Zotero 앱", h("span", { class: "badge ok", style: "margin-left:8px" }, "권장")), h("div", { class: "d" }, "API 키가 필요 없습니다. Zotero를 켜 둔 상태에서 사용합니다."), web ? null : h("div", { class: "note" }, data.zotero_local_help))),
      h(
        "label",
        { class: "choice" },
        h("input", { type: "radio", name: "zmode", checked: web, onchange: () => setMode("web") }),
        h(
          "div",
          { style: "flex:1" },
          h("div", { class: "t" }, "Zotero 웹 API"),
          h("div", { class: "d" }, "Zotero 앱을 켜지 않아도 됩니다. zotero.org → Settings → Security → Create new private key 에서 키를 만들어 입력하세요. 논문을 Zotero에 넣으려면 쓰기 권한(Allow write access)을 켠 키여야 합니다."),
          web ? h("div", { class: "inline", style: "margin-top:10px" }, keyInput, h("button", { class: "btn btn-sm", type: "button", onclick: (e) => run("zotero", e.currentTarget, () => api("POST", "/api/secrets", { name: "zotero_api_key", value: keyInput.value }), (r) => (r.username ? `키를 저장했습니다 (${r.username}).` : "키를 저장했습니다.")) }, "키 저장")) : null,
        ),
      ),
      h("div", { class: "inline", style: "margin-top:18px" }, h("button", { class: "btn", type: "button", onclick: (e) => run("zotero", e.currentTarget, () => api("POST", "/api/test/zotero"), (r) => { results.zoteroSync = r.account_linked === false; return `연결되었습니다${r.total != null ? ` · 항목 ${r.total}개` : ""}${r.account_linked ? " · Zotero 계정 동기화 사용 중" : ""}.`; }) }, "연결 테스트")),
      statusLine("zotero"),
      web
        ? null
        : h(
            "div",
            { class: "note", style: "margin-top:14px" },
            h("div", {}, h("b", {}, "논문을 Zotero에 넣기: "), data.secrets.zotero_local_key ? "허용받았습니다." : "아직 허용받지 않았습니다. 아래 단추를 누르면 Zotero가 확인 창을 띄웁니다 — ‘항상 허용(Always Allow)’을 눌러 주세요. 이 컴퓨터에서 한 번만 하면 됩니다."),
            h(
              "div",
              { class: "inline", style: "margin-top:10px" },
              h(
                "button",
                { class: "btn btn-sm", type: "button", onclick: (e) => run("zoteroWrite", e.currentTarget, () => api("POST", "/api/zotero/connect"), (r) => (r.once ? "‘허용’(이번 한 번만)을 고르셨습니다. 다시 눌러 ‘항상 허용’을 선택해 주세요." : "허용받았습니다. 이제 등록하는 읽은 논문이 Zotero에도 들어갑니다.")) },
                data.secrets.zotero_local_key ? "다시 허용받기" : "Zotero에 넣기 허용받기",
              ),
            ),
            statusLine("zoteroWrite"),
          ),
      results.zoteroSync
        ? h("div", { class: "note", style: "margin-top:10px" }, "이 컴퓨터의 Zotero 는 Zotero 계정에 로그인되어 있지 않아, Zotero 라이브러리가 다른 컴퓨터와 동기화되지 않습니다. 위키와 논문 PDF는 구글 드라이브로 동기화되므로 영향이 없지만, 다른 컴퓨터에서도 ‘Zotero에서 열기’ 링크와 같은 인용 키를 쓰려면 Zotero 설정 → 동기화에서 로그인해 주세요 (무료 계정으로 서지 정보는 무제한 동기화됩니다).")
        : null,
    );
  }

  // ── 2. Claude Code 스킬 ──
  function claudeStep() {
    const c = data.claude;
    const ready = c && c.installed && c.current;
    const state = !c ? "저장 위치를 먼저 정해 주세요." : !c.installed ? "아직 설치되지 않았습니다." : c.current ? "설치되어 있습니다." : "위키 위치나 프로그램이 바뀌었습니다. 다시 설치해 주세요.";
    const ask = (text) => h("button", { class: "ask", type: "button", dataset: { copy: text }, title: "눌러서 복사" }, h("span", { class: "ask-mark" }, "Claude Code"), h("span", { class: "ask-text" }, text), h("span", { class: "ask-copy" }, "복사"));
    return step(
      2,
      ready,
      "Claude Code 스킬",
      "논문을 읽어 위키에 넣는 일, 위키를 근거로 선행연구를 쓰는 일, 위키를 탐색하는 일은 모두 Claude Code 안에서 합니다. 스킬을 설치하면 어떤 폴더에서 Claude Code를 열든 이 위키를 쓸 수 있습니다. API 키는 필요 없습니다 — 평소 쓰는 Claude Code가 그대로 일합니다.",
      data.claude_code_installed ? null : h("div", { class: "callout", style: "margin-bottom:16px" }, h("div", { class: "t" }, "이 컴퓨터에서 Claude Code 를 찾지 못했습니다"), h("div", { class: "d" }, "논문을 넣고 글을 쓰려면 Claude Code 가 필요합니다. 설치하고 로그인한 뒤 이 화면을 새로 고쳐 주세요. 위키를 보기만 할 때는 없어도 됩니다."), h("div", { class: "inline" }, h("a", { class: "btn btn-sm", href: "https://claude.com/claude-code", target: "_blank", rel: "noopener" }, "Claude Code 알아보기"))),
      h("p", {}, h("span", { class: "badge" + (ready ? " ok" : " warn") }, state), c ? h("span", {}, " ", h("code", { class: "path" }, c.path)) : null),
      h("p", { class: "hint", style: "margin-top:8px" }, "스킬 파일과 논문 읽기 전용 에이전트 파일, 두 개가 사용자 폴더의 .claude 안에 설치됩니다. 위키 경로가 컴퓨터마다 다르므로 컴퓨터마다 한 번씩 설치합니다."),
      h("div", { class: "inline", style: "margin-top:18px" }, h("button", { class: "btn" + (ready ? "" : " btn-primary"), type: "button", disabled: !c, onclick: (e) => run("claude", e.currentTarget, () => api("POST", "/api/claude/install"), "스킬을 설치했습니다. Claude Code 에서 바로 쓸 수 있습니다.") }, c && c.installed ? "다시 설치" : "스킬 설치")),
      statusLine("claude"),
      ready
        ? [
            h("div", { class: "group-label" }, "Claude Code 에서 이렇게 요청하세요"),
            ask("논문 폴더에 넣은 새 논문을 위키에 정리해줘"),
            ask("이 문단에 위키를 근거로 선행연구를 넣어줘"),
            ask("내 위키에서 작업기억에 대해 정리된 내용을 훑어보고 빈틈을 찾아줘"),
          ]
        : null,
    );
  }

  function obsidianStep() {
    const path = data.config.vault_path;
    return step(
      4,
      false,
      "Obsidian으로 탐색하기 (선택)",
      "위키 폴더는 그대로 Obsidian 보관함(vault)입니다. 그래프 보기와 양방향 링크로 키워드 사이를 돌아다니며 아이디어를 찾을 수 있습니다.",
      h("p", { class: "muted" }, "Obsidian → 보관함 열기 → “폴더를 보관함으로 열기”에서 아래 폴더를 선택하세요. 각 문서 맨 아래 메모 영역에 적은 내용은 앱이 문서를 다시 만들어도 보존됩니다."),
      path ? h("p", { style: "margin-top:10px" }, h("code", { class: "path" }, path)) : null,
      data.vault_state === "ok" ? h("div", { class: "inline", style: "margin-top:18px" }, h("button", { class: "btn btn-sm", type: "button", onclick: (e) => run("rebuild", e.currentTarget, () => api("POST", "/api/rebuild"), (r) => `마크다운을 다시 만들었습니다 · 갱신 ${r.written} · 정리 ${r.removed}`) }, "마크다운 다시 생성")) : null,
      statusLine("rebuild"),
    );
  }

  function render() {
    const ready = data.vault_state === "ok";
    fill(
      root,
      vaultStep(),
      claudeStep(),
      zoteroStep(),
      obsidianStep(),
      ready ? h("div", { class: "inline", style: "margin: 32px 0 0 60px" }, h("a", { class: "btn btn-primary btn-lg", href: "/inbox" }, "논문 넣는 방법 보기"), h("a", { class: "btn btn-lg", href: "/wiki" }, "위키 둘러보기")) : null,
    );
    if (location.hash === "#zotero") {
      const el = $$(".step", root)[2];
      if (el) el.scrollIntoView({ block: "start" });
      history.replaceState(null, "", location.pathname);
    }
  }

  reload().catch((err) => root.replaceChildren(h("div", { class: "card empty" }, h("h3", {}, "설정을 불러오지 못했습니다"), h("p", {}, err.message))));
})();
