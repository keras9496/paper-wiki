// 모든 화면이 함께 쓰는 작은 도구들.

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

/** DOM 요소를 만든다. 문자열은 항상 텍스트로 들어가므로 따로 이스케이프할 필요가 없다. */
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (k === "class") el.className = v;
    else if (k === "dataset") Object.assign(el.dataset, v);
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k in el && k !== "list" && k !== "form") el[k] = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

/** 요소의 내용을 통째로 바꾼다. null·false 는 건너뛴다 (replaceChildren 은 null 을 글자로 넣는다). */
function fill(el, ...kids) {
  el.replaceChildren(...kids.flat(Infinity).filter((k) => k != null && k !== false));
}

function svg(pathD, cls) {
  const ns = "http://www.w3.org/2000/svg";
  const el = document.createElementNS(ns, "svg");
  el.setAttribute("viewBox", "0 0 24 24");
  if (cls) el.setAttribute("class", cls);
  for (const d of [].concat(pathD)) {
    const p = document.createElementNS(ns, "path");
    p.setAttribute("d", d);
    el.append(p);
  }
  return el;
}
const ICON = { x: "m6 6 12 12M18 6 6 18", plus: "M12 5v14M5 12h14", chev: "m9 6 6 6-6 6" };

async function api(method, url, body) {
  const res = await fetch(url, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try { data = await res.json(); } catch { /* 본문 없음 */ }
  if (!res.ok) {
    const err = new Error((data && (data.error || data.detail)) || `요청에 실패했습니다 (${res.status})`);
    err.status = res.status;
    err.code = data && data.code; // 작업을 시작할 수 없을 때의 이유 (login · not_installed · busy)
    throw err;
  }
  return data;
}

/** 화면 아래에 잠깐 뜨는 알림. action = { label, run(button) } 을 주면 단추가 붙고 더 오래 떠 있다 (방금 한 일을 되돌리는 용도). */
function toast(message, kind, action) {
  const el = h("div", { class: "toast" + (kind === "err" ? " err" : "") }, h("span", null, message));
  if (action) el.append(h("button", { class: "toast-act", type: "button", onclick: (e) => action.run(e.currentTarget) }, action.label));
  $("#toasts").append(el);
  setTimeout(() => el.remove(), kind === "err" ? 7000 : action ? 12000 : 3200);
}

/** 버튼을 누른 동안 중복 클릭을 막고, 실패하면 알림을 띄운다. */
async function busy(button, fn) {
  if (button) button.disabled = true;
  try { return await fn(); }
  catch (err) { toast(err.message, "err"); }
  finally { if (button) button.disabled = false; }
}

const TYPE_LABELS = { finding: "결과·발견", method: "방법론", background: "배경·개념", limitation: "한계·논점" };

document.addEventListener("keydown", (e) => {
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
  if (e.key === "/" && !typing && $("#global-search")) {
    e.preventDefault();
    $("#global-search").focus();
    $("#global-search").select();
  }
});

document.addEventListener("click", (e) => {
  const copy = e.target.closest("[data-copy]");
  if (copy) {
    navigator.clipboard.writeText(copy.dataset.copy).then(() => toast(`복사했습니다: ${copy.dataset.copy}`));
    return;
  }
  const twist = e.target.closest(".tree .twist");
  if (twist) twist.closest("li").classList.toggle("open");
  const row = e.target.closest("tr.link[data-href]");
  if (row && !e.target.closest("a, button")) location.href = row.dataset.href;
});
