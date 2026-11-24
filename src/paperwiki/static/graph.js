// 주제 지도: 계층 개요 · 주제 지도 · 근거 패널이 선택과 필터를 함께 쓰고, 주장을 고르면 지도 자리에 초점 뷰가 열린다.
// 화면은 /api/map 이 내준 graph(분류·주제·연결·좌표)와 evidence(주장·문헌)만 읽는다. 외부 라이브러리는 쓰지 않는다.
//
// 시각 채널 하나에 뜻 하나:
//   위치 = 함께 인용되는 정도로 계산해 저장해 둔 배치 · 영역 = 분류 · 크기 = 인용된 문헌 수 · 선 굵기 = 두 주제 모두에서 인용된 문헌 수
//   색 = 분류 (바꾸면 같은 배치 위에서 '원문을 읽은 비율')

(async () => {
  const CAT_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]; // 색맹 안전성 검사를 거친 순서. 범례·영역·계층 개요가 함께 구분해 준다
  const CAT_OTHER = "#8790a6";
  const SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#1c5cab", "#0d366b"]; // 한 색의 옅음 → 짙음
  const INK = "#131a2b", INK2 = "#4d5670", SURFACE = "#fdfdfe", ACCENT = "#1e40af";
  const FONT = '"Pretendard Variable", Pretendard, "Malgun Gothic", sans-serif';
  const TYPES = Object.keys(TYPE_LABELS);
  const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const canvas = $("#map");
  const ctx = canvas.getContext("2d");
  const stage = canvas.parentElement;
  const tip = $("#map-tip");
  const focusEl = $("#focus");
  const panel = $("#panel");

  let data;
  try {
    data = await api("GET", "/api/map");
  } catch (err) {
    toast(err.message, "err");
    return;
  }
  let G = data.graph;
  const E = data.evidence;
  if (!G.nodes.length) {
    fill($("#map-grid"), h("div", { class: "card empty map-empty" }, h("h3", null, "아직 지도에 올릴 주장이 없습니다"), h("p", null, "논문을 읽혀 주장이 위키에 등록되면, 키워드가 주제가 되어 여기에 나타납니다."), h("a", { class: "btn btn-primary", href: "/inbox" }, "새 논문 · 검토로 가기")));
    $(".map-bar").hidden = true;
    return;
  }

  // ── 데이터 색인 ──────────────────────────────────────────────────────────
  const papers = E.papers;
  const claimByKey = new Map(E.claims.map((c) => [c.key, c]));
  const claimsOf = new Map(); // 주제 → 주장들
  const citedIn = new Map(); // 문헌 → 그 문헌을 인용한 주장들
  for (const c of E.claims) {
    for (const t of c.topics) (claimsOf.get(t) || claimsOf.set(t, []).get(t)).push(c);
    for (const w of c.cites) (citedIn.get(w.id) || citedIn.set(w.id, []).get(w.id)).push(c);
  }
  let nodeById, catById, links, maxNorm, catLinks, maxPapers;

  function index() {
    nodeById = new Map(G.nodes.map((n) => [n.id, n]));
    catById = new Map(G.categories.map((c) => [c.id, c]));
    links = new Map(G.nodes.map((n) => [n.id, []]));
    maxNorm = Math.max(0.001, ...G.edges.map((e) => e.weight_norm));
    maxPapers = Math.max(1, ...G.nodes.map((n) => n.n_papers));
    for (const e of G.edges) {
      e.s = nodeById.get(e.source);
      e.t = nodeById.get(e.target);
      if (!e.s || !e.t) continue;
      links.get(e.source).push({ other: e.t, edge: e });
      links.get(e.target).push({ other: e.s, edge: e });
    }
    for (const list of links.values()) list.sort((a, b) => b.edge.weight - a.edge.weight || b.edge.weight_norm - a.edge.weight_norm);
    // 같은 분류의 가까운 주제끼리 이어 한 영역으로 칠한다 (멀리 떨어진 주제는 따로 섬이 된다)
    catLinks = new Map();
    for (const cat of G.categories) {
      const mine = G.nodes.filter((n) => n.category_id === cat.id);
      const pairs = [];
      const inTree = new Set(mine.slice(0, 1));
      while (inTree.size < mine.length) {
        let best = null;
        for (const a of inTree) for (const b of mine) {
          if (inTree.has(b)) continue;
          const d = Math.hypot(a.x - b.x, a.y - b.y) - a.r - b.r;
          if (!best || d < best.d) best = { a, b, d };
        }
        inTree.add(best.b);
        if (best.d < 150) pairs.push([best.a, best.b]);
      }
      catLinks.set(cat.id, { nodes: mine, pairs });
    }
  }
  index();

  const catColor = (cat) => (cat && cat.color >= 0 ? CAT_COLORS[cat.color % CAT_COLORS.length] : CAT_OTHER);
  const mix = (hex, t) => {
    const a = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
    const b = [253, 253, 254];
    return `rgb(${a.map((v, i) => Math.round(v + (b[i] - v) * t)).join(",")})`;
  };
  const pct = (x) => `${Math.round(x * 100)}%`;
  const clip = (text, n) => (text.length > n ? text.slice(0, n - 1).trimEnd() + "…" : text);

  // ── 상태 ────────────────────────────────────────────────────────────────
  const state = {
    sel: null, // { kind: "topic" | "cat" | "claim" | "paper", id, focus }
    ctxTopic: null, // 주장을 어느 주제에서 골랐는지 (탐색 경로에 쓴다)
    hover: null,
    hoverEdge: null,
    colorMode: "cat",
    filter: { types: new Set(TYPES), read: "all", y0: null, y1: null },
    view: { x: 0, y: 0, k: 1 },
    baseK: 1,
    depth: 0,
  };

  // ── 필터: 인용 사건(주장 × 인용된 문헌) 단위로 거른다 ────────────────────
  const paperFilterOn = () => state.filter.read !== "all" || state.filter.y0 != null || state.filter.y1 != null;
  const filterOn = () => paperFilterOn() || state.filter.types.size < TYPES.length;
  function workOk(pid) {
    const p = papers[pid];
    const f = state.filter;
    if (!p) return false;
    if (f.read !== "all" && p.read !== (f.read === "read")) return false;
    if (f.y0 != null || f.y1 != null) {
      if (p.year == null) return false;
      if (f.y0 != null && p.year < f.y0) return false;
      if (f.y1 != null && p.year > f.y1) return false;
    }
    return true;
  }
  const citesOk = (c) => c.cites.filter((w) => workOk(w.id));
  const claimOk = (c) => state.filter.types.has(c.type) && (paperFilterOn() ? citesOk(c).length > 0 : true);
  let fstat = new Map(); // 주제 → 필터에 맞는 { papers, read, claims }
  function refilter() {
    fstat = new Map();
    for (const n of G.nodes) {
      const works = new Set();
      let claims = 0;
      for (const c of claimsOf.get(n.id) || []) {
        if (!claimOk(c)) continue;
        claims++;
        for (const w of citesOk(c)) works.add(w.id);
      }
      fstat.set(n.id, { papers: works.size, read: [...works].filter((id) => papers[id].read).length, claims });
    }
  }
  refilter();
  const alive = (n) => fstat.get(n.id).claims > 0;

  // ── 지도 (캔버스) ───────────────────────────────────────────────────────
  let W = 0, H = 0;
  const regions = document.createElement("canvas");
  const rctx = regions.getContext("2d");
  let regionsDirty = true;
  let frame = 0;
  const redraw = (all) => {
    if (all) regionsDirty = true;
    if (!frame) frame = requestAnimationFrame(() => { frame = 0; draw(); });
  };
  const sx = (x) => W / 2 + state.view.x + x * state.view.k;
  const sy = (y) => H / 2 + state.view.y + y * state.view.k;
  const sr = (n) => Math.max(3, n.r * state.view.k);

  function resize() {
    const ratio = window.devicePixelRatio || 1;
    const first = !W;
    W = stage.clientWidth;
    H = stage.clientHeight;
    for (const cv of [canvas, regions]) {
      cv.width = W * ratio;
      cv.height = H * ratio;
    }
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    rctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    if (first) fit(G.nodes, false, true);
    redraw(true);
  }

  /** 주어진 주제들이 화면에 들어오게 맞춘다. */
  function fit(nodes, animate = true, base = false) {
    if (!nodes.length || !W) return;
    const pad = 46;
    const x0 = Math.min(...nodes.map((n) => n.x - n.r)), x1 = Math.max(...nodes.map((n) => n.x + n.r));
    const y0 = Math.min(...nodes.map((n) => n.y - n.r)), y1 = Math.max(...nodes.map((n) => n.y + n.r));
    const top = 14, bottom = 74; // 아래는 범례가 놓이는 자리
    const k = Math.min((W - pad * 2) / Math.max(x1 - x0, 1), (H - top - bottom - pad) / Math.max(y1 - y0, 1), base ? 1.25 : 1.45);
    const target = { k, x: -((x0 + x1) / 2) * k, y: -((y0 + y1) / 2) * k + (top - bottom) / 2 };
    if (base) state.baseK = k;
    if (!animate || calm) {
      state.view = target;
      return redraw(true);
    }
    const from = { ...state.view };
    const t0 = performance.now();
    const tickTo = (now) => {
      const t = Math.min(1, (now - t0) / 380);
      const e = 1 - (1 - t) ** 3;
      state.view = { k: from.k + (target.k - from.k) * e, x: from.x + (target.x - from.x) * e, y: from.y + (target.y - from.y) * e };
      redraw(true);
      if (t < 1) requestAnimationFrame(tickTo);
    };
    requestAnimationFrame(tickTo);
  }

  function seqColor(n) {
    const top = readTop();
    return SEQ[Math.min(SEQ.length - 1, Math.floor((n.read_ratio / top) * (SEQ.length - 1) + 0.999))];
  }
  const readTop = () => Math.max(0.1, Math.ceil(Math.max(...G.nodes.map((n) => n.read_ratio)) * 10) / 10);
  const fillOf = (n) => (state.colorMode === "read" ? (n.read_ratio > 0 ? seqColor(n) : SEQ[0]) : catColor(catById.get(n.category_id)));

  /** 지금 진하게 남길 주제들. null 이면 전부. */
  function litSet() {
    const pick = state.hover || (state.sel && state.sel.kind === "topic" ? nodeById.get(state.sel.id) : null);
    if (pick) return new Set([pick.id, ...links.get(pick.id).map((l) => l.other.id)]);
    if (state.sel && state.sel.kind === "cat") return new Set(G.nodes.filter((n) => n.category_id === state.sel.id).map((n) => n.id));
    if (state.sel && state.sel.kind === "paper") return new Set((citedIn.get(state.sel.id) || []).flatMap((c) => c.topics));
    return null;
  }

  function paintRegions() {
    const k = state.view.k;
    rctx.clearRect(0, 0, W, H);
    rctx.lineCap = "round";
    for (const cat of G.categories) {
      const { nodes, pairs } = catLinks.get(cat.id);
      const color = state.colorMode === "cat" ? mix(catColor(cat), 0.86) : "#eef0f5";
      rctx.fillStyle = rctx.strokeStyle = color;
      for (const [a, b] of pairs) {
        rctx.lineWidth = (Math.min(a.r, b.r) + 20) * 2 * k;
        rctx.beginPath();
        rctx.moveTo(sx(a.x), sy(a.y));
        rctx.lineTo(sx(b.x), sy(b.y));
        rctx.stroke();
      }
      for (const n of nodes) {
        rctx.beginPath();
        rctx.arc(sx(n.x), sy(n.y), (n.r + 24) * k, 0, Math.PI * 2);
        rctx.fill();
      }
    }
    regionsDirty = false;
  }

  function draw() {
    if (!W) return;
    if (regionsDirty) paintRegions();
    const k = state.view.k;
    ctx.clearRect(0, 0, W, H);
    ctx.globalAlpha = 1;
    ctx.drawImage(regions, 0, 0, W, H);

    const lit = litSet();
    const pick = state.hover || (state.sel && state.sel.kind === "topic" ? nodeById.get(state.sel.id) : null);
    const on = (n) => alive(n) && (!lit || lit.has(n.id));

    // 선: 평소에는 주제마다 가장 강한 연결만, 주제를 가리키면 그 주제의 연결을 모두
    ctx.lineCap = "round";
    for (const e of G.edges) {
      if (!e.s || !e.t) continue;
      const mine = pick && (e.s === pick || e.t === pick);
      if (!mine && !e.is_backbone) continue;
      const live = alive(e.s) && alive(e.t);
      let alpha = 0.2;
      if (pick) alpha = mine ? 0.6 : 0.05;
      else if (lit) alpha = lit.has(e.s.id) && lit.has(e.t.id) ? 0.3 : 0.05;
      if (!live) alpha = Math.min(alpha, 0.05);
      if (e === state.hoverEdge) alpha = 0.8;
      ctx.globalAlpha = alpha;
      ctx.strokeStyle = INK;
      ctx.lineWidth = (0.8 + 4.4 * (e.weight_norm / maxNorm)) * Math.min(1.5, Math.max(0.7, Math.sqrt(k)));
      ctx.beginPath();
      ctx.moveTo(sx(e.s.x), sy(e.s.y));
      ctx.lineTo(sx(e.t.x), sy(e.t.y));
      ctx.stroke();
    }

    // 노드: 큰 것부터 그려 작은 것이 가려지지 않게
    const order = [...G.nodes].sort((a, b) => b.r - a.r);
    for (const n of order) {
      const r = sr(n);
      ctx.globalAlpha = on(n) ? 1 : 0.2;
      ctx.beginPath();
      ctx.arc(sx(n.x), sy(n.y), r, 0, Math.PI * 2);
      ctx.fillStyle = fillOf(n);
      ctx.fill();
      ctx.lineWidth = 2;
      ctx.strokeStyle = state.colorMode === "read" && n.read_ratio === 0 ? "#9ec5f4" : SURFACE;
      ctx.stroke();
      const chosen = state.sel && ((state.sel.kind === "topic" && state.sel.id === n.id) || (state.sel.kind === "paper" && lit && lit.has(n.id)));
      if (chosen || n === state.hover) {
        ctx.globalAlpha = 1;
        ctx.beginPath();
        ctx.arc(sx(n.x), sy(n.y), r + 3.5, 0, Math.PI * 2);
        ctx.lineWidth = chosen ? 3 : 2;
        ctx.strokeStyle = chosen ? ACCENT : INK2;
        ctx.stroke();
      }
    }

    // 이름표: 겹치지 않는 것만. 고른 것·가리킨 것 → 근거가 많은 순
    const taken = [];
    const free = (b) => b.x >= 4 && b.y >= 4 && b.x + b.w <= W - 4 && b.y + b.h <= H - 4 && !taken.some((t) => b.x < t.x + t.w && t.x < b.x + b.w && b.y < t.y + t.h && t.y < b.y + b.h);
    for (const n of G.nodes) {
      const r = sr(n) * 0.82;
      taken.push({ x: sx(n.x) - r, y: sy(n.y) - r, w: r * 2, h: r * 2 });
    }
    const write = (text, x, y, weight, size, color, alpha) => {
      ctx.globalAlpha = alpha;
      ctx.font = `${weight} ${size}px ${FONT}`;
      ctx.lineJoin = "round";
      ctx.lineWidth = 3.5;
      ctx.strokeStyle = "rgba(253,253,254,0.92)";
      ctx.strokeText(text, x, y);
      ctx.fillStyle = color;
      ctx.fillText(text, x, y);
    };
    ctx.textBaseline = "middle";
    ctx.textAlign = "left";

    const forced = new Set();
    if (pick) forced.add(pick.id);
    if (state.sel && state.sel.kind === "topic") forced.add(state.sel.id);
    const ranked = [...G.nodes].sort((a, b) => (forced.has(b.id) ? 1 : 0) - (forced.has(a.id) ? 1 : 0) || (lit ? (lit.has(b.id) ? 1 : 0) - (lit.has(a.id) ? 1 : 0) : 0) || a.label_rank - b.label_rank);
    const budget = Math.round(18 * Math.max(1, (k / state.baseK) ** 2)); // 첫 화면에는 18개까지, 확대할수록 더
    let shown = 0;
    for (const n of ranked) {
      const must = forced.has(n.id);
      if (!must && (!on(n) || shown >= budget)) continue;
      const big = must;
      const size = big ? 13 : 12;
      const text = big ? n.full_name : n.display_name;
      ctx.font = `${big ? 680 : 560} ${size}px ${FONT}`;
      const w = ctx.measureText(text).width;
      const r = sr(n);
      const x = sx(n.x), y = sy(n.y);
      const spots = [
        { x: x - w / 2, y: y + r + 3 }, // 아래
        { x: x + r + 5, y: y - 8 }, // 오른쪽
        { x: x - w / 2, y: y - r - 19 }, // 위
        { x: x - r - 5 - w, y: y - 8 }, // 왼쪽
      ].map((s) => ({ x: s.x - 2, y: s.y, w: w + 4, h: 16 }));
      const spot = spots.find(free) || (must ? spots[0] : null);
      if (!spot) continue;
      taken.push(spot);
      if (!must) shown++;
      write(text, spot.x + 2, spot.y + 8.5, big ? 680 : 560, size, INK, 1);
    }
    ctx.globalAlpha = 1;
  }

  // ── 지도 조작 ────────────────────────────────────────────────────────────
  const at = (e) => {
    const rect = canvas.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };
  function pickNode(p) {
    let best = null;
    for (const n of G.nodes) {
      const r = sr(n) + 4;
      const d = (sx(n.x) - p.x) ** 2 + (sy(n.y) - p.y) ** 2;
      if (d <= r * r && (!best || n.r < best.r)) best = n;
    }
    return best;
  }
  function pickEdge(p) {
    const hot = state.sel && state.sel.kind === "topic" ? nodeById.get(state.sel.id) : null;
    let best = null;
    for (const e of G.edges) {
      if (!e.s || !e.t || !(e.is_backbone || (hot && (e.s === hot || e.t === hot)))) continue;
      const ax = sx(e.s.x), ay = sy(e.s.y), bx = sx(e.t.x), by = sy(e.t.y);
      const len = (bx - ax) ** 2 + (by - ay) ** 2 || 1;
      const t = Math.max(0, Math.min(1, ((p.x - ax) * (bx - ax) + (p.y - ay) * (by - ay)) / len));
      const d = Math.hypot(p.x - ax - t * (bx - ax), p.y - ay - t * (by - ay));
      if (d < 5 && (!best || d < best.d)) best = { e, d };
    }
    return best && best.e;
  }
  function showTip(p, ...kids) {
    fill(tip, ...kids);
    tip.style.left = Math.max(8, Math.min(p.x + 16, W - tip.offsetWidth - 8)) + "px";
    tip.style.top = Math.min(p.y + 18, H - tip.offsetHeight - 8) + "px";
    tip.style.opacity = 1;
  }
  function nodeTip(n) {
    const f = fstat.get(n.id);
    return [
      h("b", null, n.full_name),
      h("div", null, `인용된 문헌 ${n.n_papers}편 · 주장 ${n.n_claims}개`),
      h("div", null, n.n_read ? `원문을 읽은 문헌 ${n.n_read}편 (${pct(n.read_ratio)})` : "원문을 읽은 문헌은 아직 없음"),
      filterOn() && h("div", { class: "tip-note" }, `필터에 맞는 것: 문헌 ${f.papers}편 · 주장 ${f.claims}개`),
    ];
  }

  let drag = null;
  canvas.addEventListener("pointerdown", (e) => {
    $("#map-hint").classList.add("used"); // 조작 안내는 처음 한 번만
    drag = { x: e.clientX, y: e.clientY, vx: state.view.x, vy: state.view.y, moved: false };
    canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener("pointermove", (e) => {
    const p = at(e);
    if (drag) {
      if (Math.abs(e.clientX - drag.x) + Math.abs(e.clientY - drag.y) > 4) drag.moved = true;
      if (drag.moved) {
        canvas.classList.add("dragging");
        state.view.x = drag.vx + (e.clientX - drag.x);
        state.view.y = drag.vy + (e.clientY - drag.y);
        tip.style.opacity = 0;
        redraw(true);
      }
      return;
    }
    const node = pickNode(p);
    const edge = node ? null : pickEdge(p);
    canvas.style.cursor = node ? "pointer" : "";
    if (node !== state.hover || edge !== state.hoverEdge) {
      state.hover = node;
      state.hoverEdge = edge;
      redraw();
    }
    if (node) showTip(p, nodeTip(node));
    else if (edge) showTip(p, h("b", null, `${edge.s.full_name} ↔ ${edge.t.full_name}`), h("div", null, `두 주제 모두에서 인용된 문헌 ${edge.weight}편`));
    else tip.style.opacity = 0;
  });
  canvas.addEventListener("pointerup", (e) => {
    canvas.classList.remove("dragging");
    const was = drag;
    drag = null;
    if (!was || was.moved) return;
    const p = at(e);
    const node = pickNode(p);
    if (node) go({ kind: "topic", id: node.id });
    else if (state.sel) go(null);
  });
  canvas.addEventListener("dblclick", (e) => {
    const node = pickNode(at(e));
    if (node) go({ kind: "topic", id: node.id, focus: true });
  });
  canvas.addEventListener("pointerleave", () => {
    tip.style.opacity = 0;
    if ((state.hover || state.hoverEdge) && !drag) {
      state.hover = state.hoverEdge = null;
      redraw();
    }
  });
  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    const p = at(e);
    const k = Math.min(5, Math.max(state.baseK * 0.6, state.view.k * (e.deltaY < 0 ? 1.14 : 0.877)));
    const wx = (p.x - W / 2 - state.view.x) / state.view.k, wy = (p.y - H / 2 - state.view.y) / state.view.k;
    state.view = { k, x: p.x - W / 2 - wx * k, y: p.y - H / 2 - wy * k }; // 커서 아래 지점이 제자리에 있도록
    tip.style.opacity = 0;
    redraw(true);
  }, { passive: false });
  canvas.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && state.sel && state.sel.kind === "topic") go({ ...state.sel, focus: true });
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && state.sel && state.sel.focus && !/^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName)) back();
  });

  // ── 선택 · 이동 기록 ─────────────────────────────────────────────────────
  const encode = (sel) => (sel ? `#${sel.kind}=${encodeURIComponent(sel.id)}${sel.focus ? "&focus" : ""}` : location.pathname);
  function decode() {
    const m = /^#(topic|cat|claim|paper)=([^&]+)(&focus)?$/.exec(location.hash);
    if (!m) return null;
    const sel = { kind: m[1], id: decodeURIComponent(m[2]), focus: !!m[3] || m[1] === "claim" };
    const known = { topic: nodeById, cat: catById, claim: claimByKey }[sel.kind];
    return (known ? known.has(sel.id) : sel.id in papers) ? sel : null;
  }
  const same = (a, b) => (!a && !b) || (a && b && a.kind === b.kind && a.id === b.id && !!a.focus === !!b.focus);

  function go(sel, opts = {}) {
    if (sel && sel.kind === "claim") sel.focus = true;
    if (same(sel, state.sel)) return;
    state.depth++;
    history.pushState({ depth: state.depth }, "", encode(sel));
    apply(sel, opts);
  }
  function back() {
    if (state.depth > 0) history.back();
    else go(null);
  }
  window.addEventListener("popstate", (e) => {
    state.depth = (e.state && e.state.depth) || 0;
    apply(decode(), { fit: true });
  });

  function apply(sel, opts = {}) {
    state.sel = sel;
    state.hover = state.hoverEdge = null;
    if (sel && sel.kind === "topic") state.ctxTopic = sel.id;
    const focus = !!(sel && sel.focus);
    stage.classList.toggle("is-focus", focus);
    focusEl.hidden = !focus;
    $("#stage-tools").hidden = focus;
    if (focus) renderFocus();
    else if (opts.fit && sel) {
      const lit = litSet();
      const nodes = lit ? G.nodes.filter((n) => lit.has(n.id)) : [];
      if (nodes.length) fit(nodes);
    } else if (opts.fit) fit(G.nodes, true, true);
    renderCrumbs();
    renderOverview();
    renderPanel();
    redraw();
  }

  function renderCrumbs() {
    const sel = state.sel;
    const parts = [{ label: "전체 지도", to: null }];
    const pushTopic = (id) => {
      const n = nodeById.get(id);
      if (!n) return;
      const cat = catById.get(n.category_id);
      parts.push({ label: cat.name, to: { kind: "cat", id: cat.id } }, { label: n.full_name, to: { kind: "topic", id } });
    };
    if (sel) {
      if (sel.kind === "cat") parts.push({ label: catById.get(sel.id).name, to: sel });
      if (sel.kind === "topic") pushTopic(sel.id);
      if (sel.kind === "claim") {
        const c = claimByKey.get(sel.id);
        pushTopic(c.topics.includes(state.ctxTopic) ? state.ctxTopic : c.topics[0]);
        parts.push({ label: clip(c.statement, 26), to: sel });
      }
      if (sel.kind === "paper") parts.push({ label: `문헌: ${papers[sel.id].cite}`, to: sel });
      if (sel.kind === "topic" && sel.focus) parts.push({ label: "초점 뷰", to: sel });
    }
    $("#map-back").hidden = !sel;
    fill(
      $("#map-crumbs"),
      parts.map((part, i) => [
        i > 0 && h("span", { class: "sep", "aria-hidden": "true" }, "›"),
        i === parts.length - 1 ? h("span", { class: "here", title: part.label }, part.label) : h("button", { type: "button", title: part.label, onclick: () => go(part.to, { fit: true }) }, part.label),
      ]),
    );
  }
  $("#map-back").addEventListener("click", back);
  $("#map-fit").addEventListener("click", () => fit(G.nodes, true, true));

  // ── ① 계층 개요 ─────────────────────────────────────────────────────────
  function renderOverview() {
    const sel = state.sel;
    const lit = sel && sel.kind === "paper" ? litSet() : null;
    fill(
      $("#overview"),
      G.categories.map((cat) => {
        const color = catColor(cat);
        return h(
          "div",
          { class: "ov-cat" + (sel && sel.kind === "cat" && sel.id === cat.id ? " on" : ""), style: `--c:${color};--c-soft:${mix(color, 0.82)};--c-faint:${mix(color, 0.9)}` },
          h(
            "button",
            { class: "ov-cat-name", type: "button", title: `${cat.name} — 주제 ${cat.n_topics}개 · 인용된 문헌 ${cat.n_papers}편`, onclick: () => go({ kind: "cat", id: cat.id }, { fit: true }) },
            h("span", { class: "ov-cat-in" }, h("b", null, cat.name), h("small", null, `문헌 ${cat.n_papers}`)),
          ),
          h(
            "div",
            { class: "ov-rows" },
            cat.rows.map((row) => {
              const pad = `padding-left:${10 + row.depth * 13}px`;
              if (!row.topic) return h("div", { class: "ov-group", style: pad, title: row.name }, h("span", { class: "ov-name" }, row.name), h("span", { class: "ov-n" }, row.n_papers));
              const n = nodeById.get(row.id);
              const f = fstat.get(n.id);
              const on = sel && sel.kind === "topic" && sel.id === n.id;
              return h(
                "button",
                {
                  class: "ov-row" + (on ? " on" : "") + (alive(n) ? "" : " dim") + (lit && lit.has(n.id) ? " hit" : ""),
                  type: "button",
                  style: pad,
                  dataset: { id: n.id },
                  title: `${n.full_name} — 인용된 문헌 ${n.n_papers}편 (원문 읽음 ${n.n_read}편) · 주장 ${n.n_claims}개`,
                  onclick: () => go({ kind: "topic", id: n.id }, { fit: true }),
                  ondblclick: () => go({ kind: "topic", id: n.id, focus: true }),
                },
                h("span", { class: "ov-bar", style: `width:${Math.max(3, (f.papers / maxPapers) * 100)}%` }, f.read > 0 && h("i", { style: `width:${(f.read / Math.max(f.papers, 1)) * 100}%` })),
                h("span", { class: "ov-name" }, n.full_name),
                h("span", { class: "ov-n" }, f.papers),
              );
            }),
          ),
        );
      }),
    );
    const chosen = $(".ov-row.on", $("#overview"));
    if (chosen) chosen.scrollIntoView({ block: "nearest" });
  }

  // ── ③ 근거 패널 ─────────────────────────────────────────────────────────
  const typeBadge = (type) => h("span", { class: `type ${type}` }, TYPE_LABELS[type]);
  const byStrength = (a, b) => b.sources.length - a.sources.length || b.cites.length - a.cites.length;
  const openClaim = (c) => go({ kind: "claim", id: c.key });

  /** 인용된 문헌 한 줄: 이름(누르면 이 문헌이 인용된 방향) · 원문 읽음 여부 · 인용 키 복사 · 위키 문서 */
  function workRow(w) {
    const p = papers[w.id];
    return h(
      "li",
      { class: "ev-work" + (p.read ? " read" : "") },
      h("span", { class: "ev-mark", title: p.read ? "원문을 읽은 문헌" : "원문은 아직 읽지 않음 (인용한 논문의 말을 옮긴 것)" }),
      h(
        "span",
        { class: "ev-work-main" },
        h("button", { class: "ev-work-name", type: "button", title: "이 문헌이 인용된 방향을 지도에서 보기", onclick: () => go({ kind: "paper", id: w.id }, { fit: true }) }, p.cite, w.n > 1 && h("span", { class: "ev-x", title: `읽은 논문 ${w.n}편이 이 주장에 이 문헌을 인용` }, `×${w.n}`)),
        h("span", { class: "ev-work-title", title: p.title }, p.title),
      ),
      h("button", { class: "cite-key", type: "button", dataset: { copy: w.id }, title: "인용 키 복사" }, "@"),
      h("a", { class: "ev-open", href: `/wiki/p/${w.id}`, title: "위키 문서 열기", "aria-label": `${p.cite} 위키 문서 열기` }, "↗"),
    );
  }
  function quotes(c) {
    const withQuote = c.sources.filter((s) => s.quote);
    if (!withQuote.length) return null;
    return h(
      "details",
      { class: "ev-quotes" },
      h("summary", null, `원문 인용 문장 ${withQuote.length}`),
      withQuote.map((s) => h("blockquote", { class: "claim-quote" }, h("a", { class: "src", href: `/wiki/p/${s.id}` }, papers[s.id] ? papers[s.id].cite : s.id), s.quote, s.location && h("span", { class: "loc" }, s.location))),
    );
  }
  function claimCard(c, open) {
    const works = citesOk(c);
    return h(
      "article",
      { class: "ev-claim" },
      h("div", { class: "ev-claim-head" }, typeBadge(c.type), c.sources.length > 1 && h("span", { class: "badge ok", title: "서로 다른 읽은 논문이 같은 주장을 했습니다" }, `논문 ${c.sources.length}편이 같은 주장`)),
      open ? h("p", { class: "ev-statement" }, c.statement) : h("button", { class: "ev-statement", type: "button", title: "초점 뷰로 보기", onclick: () => openClaim(c) }, c.statement),
      works.length ? h("ul", { class: "ev-works" }, works.map(workRow)) : null,
      works.length < c.cites.length && h("p", { class: "hint" }, `필터에 맞지 않는 인용 문헌 ${c.cites.length - works.length}편은 숨겼습니다.`),
      open ? openQuotes(c) : quotes(c),
    );
  }
  function openQuotes(c) {
    return h(
      "div",
      { class: "ev-said" },
      h("h4", null, `이렇게 쓴 논문 ${c.sources.length}편`),
      c.sources.map((s) =>
        h("blockquote", { class: "claim-quote" }, h("a", { class: "src", href: `/wiki/p/${s.id}` }, papers[s.id] ? papers[s.id].cite : s.id), s.quote || "(인용 문장 기록 없음)", s.location && h("span", { class: "loc" }, s.location)),
      ),
    );
  }
  function typeBar(counts) {
    const total = TYPES.reduce((s, t) => s + counts[t], 0) || 1;
    return h(
      "div",
      { class: "ev-types" },
      h("div", { class: "ev-typebar", role: "img", "aria-label": TYPES.map((t) => `${TYPE_LABELS[t]} ${counts[t]}`).join(", ") }, TYPES.filter((t) => counts[t]).map((t) => h("i", { class: t, style: `flex:${counts[t]}`, title: `${TYPE_LABELS[t]} ${counts[t]}` }))),
      h("div", { class: "ev-typekey" }, TYPES.filter((t) => counts[t]).map((t) => h("span", { class: `type ${t}` }, `${TYPE_LABELS[t]} ${counts[t]}`))),
    );
  }
  const stat = (num, label) => h("div", { class: "ev-stat" }, h("b", null, num), h("span", null, label));
  const hiddenNote = (shown, total) => shown < total && h("p", { class: "hint ev-hidden" }, `필터에 맞지 않는 주장 ${total - shown}개는 숨겼습니다.`);

  function panelHome() {
    const top = [...G.nodes].sort((a, b) => a.label_rank - b.label_rank).slice(0, 8);
    const shared = E.claims.filter((c) => c.sources.length > 1 && claimOk(c)).sort(byStrength).slice(0, 5);
    return [
      h("div", { class: "pane-head" }, h("h2", null, h("span", { class: "pane-n" }, "3"), "근거 패널"), h("p", { class: "pane-sub" }, "주제를 고르면 그 주제의 주장과 인용된 문헌이 여기에 나옵니다.")),
      h("div", { class: "ev-stats" }, stat(G.totals.topics, "주제"), stat(G.totals.claims, "주장"), stat(G.totals.works, "인용된 문헌"), stat(G.totals.read, "읽은 논문")),
      h("h3", { class: "ev-h" }, "근거가 많이 쌓인 주제"),
      h("div", { class: "ev-list" }, top.map((n) => h("button", { type: "button", class: "ev-pick", onclick: () => go({ kind: "topic", id: n.id }, { fit: true }) }, h("i", { style: `background:${catColor(catById.get(n.category_id))}` }), h("span", null, n.full_name), h("small", null, `문헌 ${n.n_papers}`)))),
      shared.length ? [h("h3", { class: "ev-h" }, "여러 논문이 같은 말을 한 주장"), h("div", { class: "ev-list" }, shared.map((c) => h("button", { type: "button", class: "ev-pick wrap", onclick: () => openClaim(c) }, h("span", null, c.statement), h("small", null, `논문 ${c.sources.length}`))))] : null,
    ];
  }

  function panelCat(cat) {
    const nodes = G.nodes.filter((n) => n.category_id === cat.id).sort((a, b) => a.label_rank - b.label_rank);
    return [
      h("div", { class: "ev-head" }, h("div", { class: "eyebrow" }, "분류"), h("h2", null, h("i", { class: "ev-dot", style: `background:${catColor(cat)}` }), cat.name)),
      h("div", { class: "ev-stats" }, stat(cat.n_topics, "주제"), stat(cat.n_claims, "주장"), stat(cat.n_papers, "인용된 문헌")),
      h("h3", { class: "ev-h" }, "이 분류의 주제"),
      h("div", { class: "ev-list" }, nodes.map((n) => h("button", { type: "button", class: "ev-pick" + (alive(n) ? "" : " dim"), onclick: () => go({ kind: "topic", id: n.id }, { fit: true }) }, h("span", null, n.full_name), h("small", null, `문헌 ${fstat.get(n.id).papers}`)))),
    ];
  }

  function panelTopic(n) {
    const all = claimsOf.get(n.id) || [];
    const shown = all.filter(claimOk).sort(byStrength);
    const near = links.get(n.id).slice(0, 6);
    const mine = new Set(all.flatMap((c) => c.cites.map((w) => w.id)));
    return [
      h(
        "div",
        { class: "ev-head" },
        h("div", { class: "eyebrow" }, [...n.path].join(" › ") || "주제"),
        h("h2", null, h("i", { class: "ev-dot", style: `background:${catColor(catById.get(n.category_id))}` }), n.full_name),
        n.aliases.length ? h("p", { class: "hint" }, n.aliases.join(" · ")) : null,
        h("div", { class: "ev-actions" }, h("button", { class: "btn btn-sm btn-primary", type: "button", onclick: () => go({ kind: "topic", id: n.id, focus: true }) }, "초점 뷰"), h("a", { class: "btn btn-sm", href: `/wiki/k/${n.id}` }, "위키 문서 열기")),
      ),
      h("div", { class: "ev-stats" }, stat(n.n_papers, "인용된 문헌"), stat(n.n_claims, "주장"), stat(n.n_read, "원문 읽음")),
      typeBar(n.types),
      n.leans_to && h("p", { class: "note" }, `이 주제는 '${n.leans_to}' 분류의 주제들과 문헌을 더 많이 나눠 씁니다. 분류를 다시 볼 만합니다.`),
      near.length
        ? [
            h("h3", { class: "ev-h" }, "함께 인용되는 주제"),
            h(
              "div",
              { class: "ev-list" },
              near.map(({ other, edge }) => {
                const both = (claimsOf.get(other.id) || []).flatMap((c) => c.cites.map((w) => w.id)).filter((id, i, arr) => mine.has(id) && arr.indexOf(id) === i);
                return h(
                  "details",
                  { class: "ev-near" },
                  h("summary", null, h("i", { style: `background:${catColor(catById.get(other.category_id))}` }), h("span", null, other.full_name), h("small", null, `같은 문헌 ${edge.weight}`)),
                  h("div", { class: "ev-near-body" }, h("div", { class: "works" }, both.map((id) => h("a", { class: "work" + (papers[id].read ? " read" : ""), href: `/wiki/p/${id}`, title: papers[id].title }, papers[id].cite))), h("button", { class: "link-btn", type: "button", onclick: () => go({ kind: "topic", id: other.id }, { fit: true }) }, "이 주제로 가기 →")),
                );
              }),
            ),
          ]
        : null,
      h("h3", { class: "ev-h" }, "주장과 근거 ", h("span", { class: "n" }, shown.length)),
      hiddenNote(shown.length, all.length),
      shown.length ? h("div", { class: "ev-claims" }, shown.map((c) => claimCard(c))) : h("p", { class: "hint" }, "필터에 맞는 주장이 없습니다."),
    ];
  }

  function panelClaim(c) {
    return [
      h("div", { class: "ev-head" }, h("div", { class: "eyebrow" }, "주장"), h("div", { class: "chips" }, c.topics.map((t) => h("button", { class: "chip", type: "button", onclick: () => go({ kind: "topic", id: t }, { fit: true }) }, nodeById.get(t).full_name)))),
      h("div", { class: "ev-claims solo" }, claimCard(c, true)),
      h("p", { class: "hint" }, "@ 를 누르면 인용 키가 복사됩니다. 문헌 이름을 누르면 그 문헌이 인용된 다른 방향을 지도에서 봅니다."),
    ];
  }

  function panelPaper(id) {
    const p = papers[id];
    const claims = (citedIn.get(id) || []).filter(claimOk).sort(byStrength);
    const topics = [...new Set((citedIn.get(id) || []).flatMap((c) => c.topics))].map((t) => nodeById.get(t)).filter(Boolean);
    return [
      h(
        "div",
        { class: "ev-head" },
        h("div", { class: "eyebrow" }, p.read ? "읽은 논문" : "인용 문헌 · 원문은 아직 읽지 않음"),
        h("h2", null, p.cite),
        h("p", { class: "ev-title" }, p.title),
        h("div", { class: "ev-actions" }, h("button", { class: "cite-key", type: "button", dataset: { copy: id }, title: "인용 키 복사" }, `@${id}`), h("a", { class: "btn btn-sm", href: `/wiki/p/${id}` }, "위키 문서 열기")),
      ),
      h("h3", { class: "ev-h" }, "인용된 방향 ", h("span", { class: "n" }, topics.length)),
      h("div", { class: "chips" }, topics.map((n) => h("button", { class: "chip", type: "button", onclick: () => go({ kind: "topic", id: n.id }, { fit: true }) }, h("i", { class: "ev-dot", style: `background:${catColor(catById.get(n.category_id))}` }), n.full_name))),
      h("h3", { class: "ev-h" }, "이 문헌을 인용한 주장 ", h("span", { class: "n" }, claims.length)),
      claims.length ? h("div", { class: "ev-claims" }, claims.map((c) => h("article", { class: "ev-claim" }, h("div", { class: "ev-claim-head" }, typeBadge(c.type), h("span", { class: "hint" }, c.topics.map((t) => nodeById.get(t).display_name).join(" · "))), h("button", { class: "ev-statement", type: "button", onclick: () => openClaim(c) }, c.statement), quotes(c)))) : h("p", { class: "hint" }, "필터에 맞는 주장이 없습니다."),
    ];
  }

  function renderPanel() {
    const sel = state.sel;
    let body;
    if (!sel) body = panelHome();
    else if (sel.kind === "cat") body = panelCat(catById.get(sel.id));
    else if (sel.kind === "topic") body = panelTopic(nodeById.get(sel.id));
    else if (sel.kind === "claim") body = panelClaim(claimByKey.get(sel.id));
    else body = panelPaper(sel.id);
    fill(panel, body);
    panel.scrollTop = 0;
  }

  // ── ④ 초점 뷰: 관계 종류마다 방향이 고정돼 있다 ──────────────────────────
  // 위 = 키워드(상위) · 왼쪽 = 인용할 문헌 · 오른쪽 = 한계·논점 · 아래 = 이어지는 주장 · 옆 = 같은 자리의 다른 것
  const sharedWith = (c, ids) => c.cites.filter((w) => ids.has(w.id)).length;
  const workBox = (w, sub) => ({ kind: "work", title: papers[w.id].cite, sub: sub || papers[w.id].title, read: papers[w.id].read, weight: w.n, to: { kind: "paper", id: w.id }, tip: papers[w.id].read ? "원문을 읽은 문헌" : "원문은 아직 읽지 않음" });
  const claimBox = (c, kind) => ({ kind, title: c.statement, sub: `${TYPE_LABELS[c.type]} · 인용 문헌 ${c.cites.length}${c.sources.length > 1 ? ` · 논문 ${c.sources.length}편` : ""}`, to: { kind: "claim", id: c.key } });
  const topicBox = (n) => ({ kind: "topic", title: n.full_name, sub: `인용된 문헌 ${n.n_papers} · 주장 ${n.n_claims}`, to: { kind: "topic", id: n.id } });

  function focusSpec() {
    const sel = state.sel;
    if (sel.kind === "claim") {
      const c = claimByKey.get(sel.id);
      const ids = new Set(c.cites.map((w) => w.id));
      const peers = [...new Set(c.topics.flatMap((t) => claimsOf.get(t) || []))].filter((o) => o !== c && claimOk(o));
      const limits = peers.filter((o) => o.type === "limitation").sort((a, b) => sharedWith(b, ids) - sharedWith(a, ids) || byStrength(a, b));
      const skip = new Set([c, ...limits]);
      const linked = [...new Set(c.cites.flatMap((w) => citedIn.get(w.id) || []))].filter((o) => !skip.has(o) && claimOk(o)).sort((a, b) => sharedWith(b, ids) - sharedWith(a, ids) || byStrength(a, b));
      for (const o of linked) skip.add(o);
      return {
        center: { title: c.statement, sub: `${TYPE_LABELS[c.type]} · 읽은 논문 ${c.sources.length}편이 이렇게 씀`, type: c.type },
        top: { label: "위 · 이 주장이 정리된 키워드", items: c.topics.map((t) => topicBox(nodeById.get(t))) },
        left: { label: "왼쪽 · 이 주장에 인용할 문헌", items: citesOk(c).map((w) => workBox(w)), empty: "필터에 맞는 인용 문헌이 없습니다" },
        right: { label: "오른쪽 · 같은 주제의 한계·논점", items: limits.map((o) => claimBox(o, "limit")), empty: "같은 주제에 정리된 한계·논점이 없습니다" },
        bottom: { label: "아래 · 같은 문헌을 인용한 다른 주장", items: linked.map((o) => claimBox(o, "claim")) },
        side: { label: "옆 · 같은 주제의 다른 주장", items: peers.filter((o) => !skip.has(o)).sort(byStrength).map((o) => claimBox(o, "claim")) },
      };
    }
    const n = nodeById.get(sel.id);
    const claims = (claimsOf.get(n.id) || []).filter(claimOk).sort(byStrength);
    const count = new Map();
    for (const c of claims) for (const w of citesOk(c)) count.set(w.id, (count.get(w.id) || 0) + 1);
    const works = [...count].sort((a, b) => b[1] - a[1] || papers[a[0]].cite.localeCompare(papers[b[0]].cite)).map(([id, k]) => workBox({ id, n: k }, k > 1 ? `이 주제의 주장 ${k}개에 인용 · ${papers[id].title}` : null));
    const parent = n.path[n.path.length - 1];
    const parentNode = parent && G.nodes.find((x) => x.full_name === parent);
    return {
      center: { title: n.full_name, sub: `인용된 문헌 ${n.n_papers}편 · 주장 ${n.n_claims}개`, type: "topic" },
      top: { label: "위 · 상위 키워드", items: parent ? [parentNode ? topicBox(parentNode) : { kind: "topic", title: parent, sub: "분류", to: { kind: "cat", id: n.category_id }, toMap: true }] : [] },
      left: { label: "왼쪽 · 이 주제에서 자주 인용되는 문헌", items: works, empty: "필터에 맞는 인용 문헌이 없습니다" },
      right: { label: "오른쪽 · 이 주제의 한계·논점", items: claims.filter((c) => c.type === "limitation").map((c) => claimBox(c, "limit")), empty: "이 주제에 정리된 한계·논점이 없습니다" },
      bottom: { label: "아래 · 이 주제의 주장", items: claims.filter((c) => c.type !== "limitation").map((c) => claimBox(c, "claim")) },
      side: { label: "옆 · 함께 인용되는 주제", items: links.get(n.id).map((l) => topicBox(l.other)) },
    };
  }

  const LIMITS = { top: 4, left: 7, right: 5, bottom: 6, side: 3 };
  const expanded = new Set(); // "선택#자리" — 더 펼친 자리
  function renderFocus() {
    const spec = focusSpec();
    const tag = `${state.sel.kind}=${state.sel.id}`;
    const box = (item, where) =>
      h(
        "button",
        {
          class: `fx-box k-${item.kind}` + (item.kind === "work" ? (item.read ? " read" : " unread") : ""),
          type: "button",
          title: [item.title, item.tip].filter(Boolean).join(" — "),
          dataset: { where, weight: item.weight || 1, dashed: item.kind === "work" && !item.read ? "1" : "" },
          onclick: () => go(item.to, { fit: true }),
        },
        h("span", { class: "fx-t" }, item.title),
        item.sub && h("span", { class: "fx-s" }, item.sub),
      );
    const zone = (where) => {
      const part = spec[where];
      const open = expanded.has(`${tag}#${where}`);
      const items = open ? part.items : part.items.slice(0, LIMITS[where]);
      const more = part.items.length - items.length;
      return h(
        "div",
        { class: `fx-zone fx-${where}` },
        (part.items.length || part.empty) && h("div", { class: "fx-label" }, part.label, part.items.length > LIMITS[where] && h("span", { class: "n" }, ` ${part.items.length}`)),
        h("div", { class: "fx-items" }, items.map((item) => box(item, where)), !part.items.length && part.empty && h("div", { class: "fx-none" }, part.empty)),
        more > 0 && h("button", { class: "link-btn fx-more", type: "button", onclick: () => { expanded.add(`${tag}#${where}`); renderFocus(); } }, `+ ${more}개 더 펼치기`),
      );
    };
    const lines = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    lines.setAttribute("class", "fx-lines");
    lines.setAttribute("aria-hidden", "true");
    fill(
      focusEl,
      h(
        "div",
        { class: "fx" },
        lines,
        zone("top"),
        zone("side"),
        zone("left"),
        h("div", { class: "fx-zone fx-center" }, h("div", { class: `fx-box center ${spec.center.type}` }, h("span", { class: "fx-t" }, spec.center.title), h("span", { class: "fx-s" }, spec.center.sub))),
        zone("right"),
        zone("bottom"),
        h(
          "div",
          { class: "fx-key" },
          h("span", null, h("i", { class: "k-line" }), "실선 = 원문을 읽은 문헌"),
          h("span", null, h("i", { class: "k-line dashed" }), "점선 = 원문은 아직 읽지 않음"),
          h("span", null, h("i", { class: "k-line thick" }), "선 굵기 = 인용한 횟수"),
          h("span", null, h("i", { class: "k-box cited" }), h("i", { class: "k-box limits" }), "청록 = 인용할 문헌 · 주황 = 한계·논점"),
        ),
      ),
    );
    requestAnimationFrame(() => wire(true));
  }

  /** 초점 뷰의 연결선: 가운데 상자에서 각 방향의 상자로. */
  function wire(center_it) {
    const root = $(".fx", focusEl);
    const lines = $(".fx-lines", focusEl);
    const center = $(".fx-box.center", focusEl);
    if (!root || !center) return;
    const base = root.getBoundingClientRect();
    const rect = (el) => {
      const r = el.getBoundingClientRect();
      return { x0: r.left - base.left, x1: r.right - base.left, y0: r.top - base.top, y1: r.bottom - base.top, cx: (r.left + r.right) / 2 - base.left, cy: (r.top + r.bottom) / 2 - base.top };
    };
    lines.setAttribute("width", root.scrollWidth);
    lines.setAttribute("height", root.scrollHeight);
    const c = rect(center);
    if (center_it === true) focusEl.scrollTop = Math.max(0, c.cy - focusEl.clientHeight / 2); // 가운데 상자가 먼저 보이게
    const paths = [];
    for (const el of $$(".fx-box[data-where]", focusEl)) {
      const where = el.dataset.where;
      const r = rect(el);
      let d;
      if (where === "left") d = `M${r.x1},${r.cy} C${(r.x1 + c.x0) / 2},${r.cy} ${(r.x1 + c.x0) / 2},${c.cy} ${c.x0},${c.cy}`;
      else if (where === "right") d = `M${r.x0},${r.cy} C${(r.x0 + c.x1) / 2},${r.cy} ${(r.x0 + c.x1) / 2},${c.cy} ${c.x1},${c.cy}`;
      else if (where === "top") d = `M${r.cx},${r.y1} C${r.cx},${(r.y1 + c.y0) / 2} ${c.cx},${(r.y1 + c.y0) / 2} ${c.cx},${c.y0}`;
      else if (where === "bottom") d = `M${r.cx},${r.y0} C${r.cx},${(r.y0 + c.y1) / 2} ${c.cx},${(r.y0 + c.y1) / 2} ${c.cx},${c.y1}`;
      else continue; // 옆 자리는 선 없이 둔다 (가운데 것과 직접 이어진 관계가 아니다)
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", d);
      path.setAttribute("stroke-width", where === "left" ? Math.min(1.4 + (Number(el.dataset.weight) - 1) * 1.3, 6) : 1.4);
      if (el.dataset.dashed) path.setAttribute("stroke-dasharray", "5 5");
      paths.push(path);
    }
    lines.replaceChildren(...paths);
  }

  // ── 범례 (늘 보인다) ────────────────────────────────────────────────────
  function renderLegend() {
    const color =
      state.colorMode === "cat"
        ? h("div", { class: "lg-row" }, G.categories.map((cat) => h("button", { type: "button", class: "legend lg-cat", onclick: () => go({ kind: "cat", id: cat.id }, { fit: true }) }, h("i", { style: `background:${catColor(cat)}` }), cat.name)))
        : h("div", { class: "lg-row" }, h("span", { class: "legend" }, "원문을 읽은 문헌의 비율"), h("span", { class: "lg-ramp" }, "0%", SEQ.map((c) => h("i", { style: `background:${c}` })), pct(readTop())));
    fill(
      $("#map-legend"),
      color,
      h(
        "div",
        { class: "lg-row lg-how" },
        h("span", { class: "legend" }, h("i", { class: "lg-size s" }), h("i", { class: "lg-size l" }), "크기 = 인용된 문헌 수"),
        h("span", { class: "legend" }, h("i", { class: "lg-line" }), "선 = 함께 인용된 문헌"),
        h("span", { class: "legend" }, h("i", { class: "lg-area" }), "영역 = 분류"),
        h("button", { class: "link-btn", type: "button", title: "저장해 둔 배치를 버리고 처음부터 다시 계산합니다. 주제들의 자리가 바뀝니다.", onclick: relayout }, "배치 다시 계산"),
      ),
    );
  }
  /** 배치는 위키 폴더에 저장되어 논문이 늘어도 자리를 지킨다. 그 자리를 버리고 새로 계산한다. */
  async function relayout(e) {
    if (!confirm("주제들의 자리를 처음부터 다시 계산할까요? 지금 눈에 익은 배치가 바뀝니다.")) return;
    await busy(e.currentTarget, async () => {
      G = (await api("POST", "/api/map/layout")).graph;
      index();
      fit(G.nodes, false, true);
      renderOverview();
      redraw(true);
    });
  }
  $("#color-mode").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-mode]");
    if (!btn) return;
    state.colorMode = btn.dataset.mode;
    for (const b of $$("#color-mode button")) b.classList.toggle("on", b === btn);
    renderLegend();
    redraw(true);
  });

  // ── 필터 조작: 세 뷰에 함께 적용된다. 걸러진 주제는 지우지 않고 흐리게 남긴다 ──
  function filterChanged() {
    refilter();
    $("#f-reset").hidden = !filterOn();
    renderOverview();
    renderPanel();
    if (state.sel && state.sel.focus) renderFocus();
    redraw();
  }
  $("#f-types").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-type]");
    if (!btn) return;
    const types = state.filter.types;
    if (types.has(btn.dataset.type)) {
      if (types.size === 1) return; // 하나는 남긴다
      types.delete(btn.dataset.type);
    } else types.add(btn.dataset.type);
    btn.setAttribute("aria-pressed", types.has(btn.dataset.type));
    filterChanged();
  });
  $("#f-read").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-read]");
    if (!btn) return;
    state.filter.read = btn.dataset.read;
    for (const b of $$("#f-read button")) b.classList.toggle("on", b === btn);
    filterChanged();
  });
  for (const [id, key] of [["#f-y0", "y0"], ["#f-y1", "y1"]]) {
    const input = $(id);
    if (G.years) {
      input.placeholder = G.years[key === "y0" ? 0 : 1];
      input.min = G.years[0];
      input.max = G.years[1];
    }
    input.addEventListener("input", () => {
      const v = parseInt(input.value, 10);
      state.filter[key] = input.value.length === 4 && Number.isFinite(v) ? v : null;
      filterChanged();
    });
  }
  $("#f-reset").addEventListener("click", () => {
    state.filter = { types: new Set(TYPES), read: "all", y0: null, y1: null };
    for (const b of $$("#f-types button")) b.setAttribute("aria-pressed", "true");
    for (const b of $$("#f-read button")) b.classList.toggle("on", b.dataset.read === "all");
    $("#f-y0").value = $("#f-y1").value = "";
    filterChanged();
  });

  // ── 찾기: 주제·문헌은 이름으로, 주장은 문장이 얼마나 비슷한지로 (원고 문장을 붙여 넣어도 된다) ──
  const STOP = new Set("the of and in to a an is are was were for that with by on as at from or be this these those it its which can has have had not but we our their".split(" "));
  function tokens(text) {
    const out = [];
    for (const word of text.toLowerCase().normalize("NFKC").split(/[^\p{L}\p{N}]+/u)) {
      if (word.length < 2 || STOP.has(word)) continue;
      if (/[가-힣]/.test(word)) {
        for (let i = 0; i < word.length - 1; i++) out.push(word.slice(i, i + 2)); // 조사·어미가 붙어도 걸리도록 두 글자씩
      } else out.push(word.length > 4 ? word.replace(/(ies|es|s|ing|ed)$/, "") : word);
    }
    return out;
  }
  const df = new Map();
  const docs = E.claims.map((c) => {
    const set = new Set(tokens(c.statement + " " + c.sources.map((s) => s.quote).join(" ")));
    for (const t of set) df.set(t, (df.get(t) || 0) + 1);
    return { c, set };
  });
  const idf = (t) => Math.log(1 + E.claims.length / (df.get(t) || 0.5));
  for (const d of docs) d.norm = Math.sqrt([...d.set].reduce((s, t) => s + idf(t) ** 2, 0)) || 1;

  function search(query) {
    const q = query.trim();
    if (q.length < 2) return null;
    const words = q.toLowerCase().split(/\s+/);
    const has = (...fields) => words.every((w) => fields.some((f) => f && f.toLowerCase().includes(w)));
    const sentence = q.length >= 30 || words.length >= 5;
    const qset = new Set(tokens(q));
    const qnorm = Math.sqrt([...qset].reduce((s, t) => s + idf(t) ** 2, 0)) || 1;
    const claims = docs
      .map((d) => {
        let dot = 0;
        for (const t of qset) if (d.set.has(t)) dot += idf(t) ** 2;
        return { c: d.c, score: dot / (qnorm * d.norm) + (has(d.c.statement) ? 1 : 0) };
      })
      .filter((x) => x.score > (sentence ? 0.08 : 0.16))
      .sort((a, b) => b.score - a.score)
      .slice(0, sentence ? 8 : 5);
    return {
      sentence,
      topics: sentence ? [] : G.nodes.filter((n) => has(n.full_name, ...n.aliases)).sort((a, b) => a.label_rank - b.label_rank).slice(0, 5),
      claims,
      papers: sentence ? [] : Object.keys(papers).filter((id) => has(papers[id].cite, papers[id].title, id)).sort((a, b) => (citedIn.get(b) || []).length - (citedIn.get(a) || []).length).slice(0, 5),
    };
  }
  const qInput = $("#map-q");
  const results = $("#map-results");
  let cursor = -1;
  function renderResults() {
    const found = search(qInput.value);
    cursor = -1;
    if (!found) return void (results.hidden = true);
    const item = (cls, onpick, ...kids) => h("button", { type: "button", class: `mr-item ${cls}`, onclick: () => { results.hidden = true; qInput.blur(); onpick(); } }, kids);
    const groups = [
      found.topics.length && [h("div", { class: "mr-h" }, "주제"), found.topics.map((n) => item("", () => go({ kind: "topic", id: n.id }, { fit: true }), h("i", { style: `background:${catColor(catById.get(n.category_id))}` }), h("span", null, n.full_name), h("small", null, `문헌 ${n.n_papers}`)))],
      found.claims.length && [h("div", { class: "mr-h" }, found.sentence ? "이 문장과 가까운 주장" : "주장"), found.claims.map(({ c }) => item("wrap", () => openClaim(c), h("span", { class: `type ${c.type}` }), h("span", null, c.statement), h("small", null, `인용 문헌 ${c.cites.length}`)))],
      found.papers.length && [h("div", { class: "mr-h" }, "문헌"), found.papers.map((id) => item("", () => go({ kind: "paper", id }, { fit: true }), h("span", null, papers[id].cite), h("small", { class: "mr-sub" }, papers[id].title)))],
    ].filter(Boolean);
    fill(results, groups.length ? groups : h("div", { class: "mr-none" }, "맞는 것이 없습니다. 위쪽 검색창에서는 위키 전체를 찾습니다."));
    results.hidden = false;
  }
  let typing = 0;
  qInput.addEventListener("input", () => {
    clearTimeout(typing);
    typing = setTimeout(renderResults, 110);
  });
  qInput.addEventListener("focus", () => qInput.value.trim().length >= 2 && renderResults());
  qInput.addEventListener("keydown", (e) => {
    const items = $$(".mr-item", results);
    if (e.key === "Escape") return void (results.hidden = true);
    if (results.hidden || !items.length) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      cursor = (cursor + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
      items.forEach((el, i) => el.classList.toggle("on", i === cursor));
      items[cursor].scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter") {
      e.preventDefault();
      items[Math.max(cursor, 0)].click();
    }
  });
  document.addEventListener("pointerdown", (e) => {
    if (!e.target.closest(".map-search")) results.hidden = true;
  });

  // ── 시작 ────────────────────────────────────────────────────────────────
  new ResizeObserver(() => {
    resize();
    if (state.sel && state.sel.focus) wire();
  }).observe(stage);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => redraw());
  renderLegend();
  resize();
  state.depth = (history.state && history.state.depth) || 0;
  apply(decode(), { fit: true });
})();
