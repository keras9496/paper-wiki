// 이 컴퓨터의 Claude Code: 설치 · 로그인 상태를 보여 주고, 로그인이 필요하면 로그인 창을 여는 방법을 안내한다.
// 논문을 읽고 학습 자료를 만드는 일은 Claude Code 가 사용자의 Claude 요금제로 한다. 로그인은 사용자가 직접 한다.

const Claude = (() => {
  let status = null;
  let watching = null;
  const mounts = new Set();

  async function check(refresh) {
    status = await api("GET", "/api/claude" + (refresh ? "?refresh=1" : ""));
    return status;
  }

  const ready = () => !!status && status.installed && status.logged_in !== false;

  function commandBox(cmd) {
    return h("button", { class: "ask", type: "button", dataset: { copy: cmd }, title: "눌러서 복사" }, h("span", { class: "ask-mark" }, "터미널"), h("span", { class: "ask-text" }, cmd), h("span", { class: "ask-copy" }, "복사"));
  }

  function banner() {
    if (!status) return null;
    const recheck = h("button", { class: "btn btn-sm", type: "button", onclick: (e) => busy(e.currentTarget, () => refreshAll(true)) }, "다시 확인");
    if (!status.installed) {
      return h(
        "div",
        { class: "callout claude-callout", role: "status" },
        h("div", { class: "t" }, "이 컴퓨터에서 Claude Code를 찾지 못했습니다"),
        h("div", { class: "d" }, "논문을 읽고 학습 자료를 만드는 일은 Claude Code가 합니다. 설치하고 로그인한 뒤 [다시 확인]을 눌러 주세요. 위키를 보기만 할 때는 없어도 됩니다."),
        h("div", { class: "inline" }, h("a", { class: "btn btn-sm btn-primary", href: status.install_url, target: "_blank", rel: "noopener" }, "Claude Code 설치 안내"), recheck),
      );
    }
    if (status.logged_in === false) {
      return h(
        "div",
        { class: "callout claude-callout", role: "status" },
        h("div", { class: "t" }, "Claude Code 로그인이 필요합니다"),
        h("div", { class: "d" }, "논문을 읽는 일은 이 컴퓨터의 Claude Code가 사용자의 Claude 요금제로 합니다. API 키는 필요 없고, 컴퓨터마다 한 번 로그인하면 됩니다."),
        h(
          "ol",
          { class: "claude-steps" },
          h("li", {}, h("b", {}, "[로그인 창 열기]"), "를 누르면 검은 창이 열립니다."),
          h("li", {}, "브라우저가 열리면 Claude 계정(구독 중인 계정)으로 로그인하고, 창의 안내를 따릅니다."),
          h("li", {}, "끝나면 이 화면이 저절로 알아챕니다. 안 바뀌면 ", h("b", {}, "[다시 확인]"), "을 눌러 주세요."),
        ),
        h("div", { class: "inline" }, h("button", { class: "btn btn-sm btn-primary", type: "button", onclick: (e) => login(e.currentTarget) }, "로그인 창 열기"), recheck),
        h("p", { class: "hint", style: "margin-top:12px" }, "창이 열리지 않으면 터미널에서 직접 실행하세요 (또는 Claude Code를 열고 /login):"),
        commandBox(status.login_command || "claude auth login"),
      );
    }
    return null;
  }

  function line() {
    if (!ready()) return null;
    const who = [status.email, status.plan && status.plan.toUpperCase()].filter(Boolean).join(" · ");
    return h("p", { class: "hint claude-line" }, h("span", { class: "dot ok" }), "Claude Code 로그인됨", who ? ` (${who})` : "", status.logged_in === null ? " · 상태를 확인하지 못했습니다" : "");
  }

  function paint(el) {
    fill(el, el.dataset.compact ? (banner() || line()) : banner());
    el._painted = true;
    if (el._onChange) el._onChange(status);
  }

  async function refreshAll(refresh) {
    try {
      await check(refresh);
    } catch {
      return status;
    }
    for (const el of [...mounts]) {
      if (el._painted && !el.isConnected) mounts.delete(el); // 화면을 다시 그리며 버려진 자리
      else paint(el);
    }
    return status;
  }

  /** el 안에 상태를 그린다. compact 면 로그인되어 있을 때 한 줄 상태를 보여 준다. */
  async function mount(el, { compact = false, onChange = null } = {}) {
    if (!el) return;
    if (compact) el.dataset.compact = "1";
    el._onChange = onChange;
    mounts.add(el);
    if (status) paint(el);
    else await refreshAll(false);
  }

  async function login(btn) {
    await busy(btn, async () => {
      const res = await api("POST", "/api/claude/login");
      if (!res.ok) {
        toast(`로그인 창을 열지 못했습니다. 터미널에서 직접 실행해 주세요: ${res.command}`, "err");
        return;
      }
      toast("로그인 창을 열었습니다. 브라우저에서 로그인을 마쳐 주세요.");
      watch();
    });
  }

  // 로그인 창을 연 뒤: 로그인이 끝났는지 몇 초마다 확인한다 (최대 5분)
  function watch() {
    clearInterval(watching);
    const until = Date.now() + 5 * 60 * 1000;
    watching = setInterval(async () => {
      const st = await refreshAll(true);
      if ((st && st.logged_in) || Date.now() > until) {
        clearInterval(watching);
        if (st && st.logged_in) toast("Claude Code에 로그인되었습니다. 이제 정리를 시작할 수 있습니다.");
      }
    }, 4000);
  }

  /** 작업을 시작하려다 409 를 받았을 때: 로그인 · 설치가 필요한 경우면 안내를 띄우고 true. */
  async function explain(err) {
    if (err && (err.code === "login" || err.code === "not_installed")) {
      await refreshAll(true);
      const el = [...mounts].find((m) => m.isConnected);
      if (el) el.scrollIntoView({ block: "center", behavior: "smooth" });
      toast(err.message, "err");
      return true;
    }
    return false;
  }

  return { check, mount, ready, explain, refreshAll, get status() { return status; } };
})();
