// 키워드·논문 그래프. 외부 라이브러리 없이 캔버스에 직접 그리는 단순한 힘 기반 배치.

(async () => {
  const canvas = $("#graph");
  const tip = $("#graph-tip");
  const ctx = canvas.getContext("2d");
  const COLOR = { keyword: "#1e40af", root: "#131a2b", paper: "#0b7f9c", read: "#b45309", edge: "rgba(19,26,43,0.13)", cite: "rgba(11,127,156,0.2)", label: "#131a2b" };

  let nodes = [];
  let edges = [];
  let neighbors = new Map();
  let view = { x: 0, y: 0, k: 1 };
  let alpha = 1;
  let hover = null;
  let drag = null;
  let moved = false;
  let width = 0;
  let height = 0;

  function resize() {
    const ratio = window.devicePixelRatio || 1;
    width = canvas.clientWidth;
    height = canvas.clientHeight;
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    draw();
  }

  // 문헌 노드: paper = 읽은 논문, cited = 인용 문헌 (크기는 인용된 주장 수)
  const isPaper = (n) => n.kind === "paper" || n.kind === "cited";
  const radius = (n) => (isPaper(n) ? (n.kind === "paper" ? 5.5 : 3 + Math.sqrt(n.weight || 0) * 0.9) : 5 + Math.sqrt(n.weight || 0) * 1.7 + (n.depth === 0 ? 3 : 0));

  async function load() {
    const data = await api("GET", `/api/graph?papers=${$("#graph-papers").value}`);
    const old = new Map(nodes.map((n) => [n.id, n]));
    nodes = data.nodes.map((n, i) => {
      const prev = old.get(n.id);
      const angle = (i / data.nodes.length) * Math.PI * 2;
      const spread = 120 + (n.depth || 3) * 60;
      return { ...n, x: prev ? prev.x : Math.cos(angle) * spread, y: prev ? prev.y : Math.sin(angle) * spread, vx: 0, vy: 0 };
    });
    const byId = new Map(nodes.map((n) => [n.id, n]));
    edges = data.edges.map((e) => ({ ...e, s: byId.get(e.source), t: byId.get(e.target) })).filter((e) => e.s && e.t);
    neighbors = new Map(nodes.map((n) => [n.id, new Set()]));
    for (const e of edges) {
      neighbors.get(e.s.id).add(e.t.id);
      neighbors.get(e.t.id).add(e.s.id);
    }
    alpha = 1;
    requestAnimationFrame(tick);
  }

  function step() {
    const repel = 2600;
    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[i];
      for (let j = i + 1; j < nodes.length; j++) {
        const b = nodes[j];
        let dx = a.x - b.x;
        let dy = a.y - b.y;
        let d2 = dx * dx + dy * dy;
        if (d2 < 1) {
          dx = Math.random() - 0.5;
          dy = Math.random() - 0.5;
          d2 = 1;
        }
        if (d2 > 250000) continue;
        const f = (repel / d2) * alpha;
        const d = Math.sqrt(d2);
        a.vx += (dx / d) * f;
        a.vy += (dy / d) * f;
        b.vx -= (dx / d) * f;
        b.vy -= (dy / d) * f;
      }
    }
    for (const e of edges) {
      const rest = e.kind === "tree" ? 70 : 95;
      const dx = e.t.x - e.s.x;
      const dy = e.t.y - e.s.y;
      const d = Math.sqrt(dx * dx + dy * dy) || 1;
      const f = (d - rest) * (e.kind === "tree" ? 0.06 : 0.025) * alpha;
      e.s.vx += (dx / d) * f;
      e.s.vy += (dy / d) * f;
      e.t.vx -= (dx / d) * f;
      e.t.vy -= (dy / d) * f;
    }
    for (const n of nodes) {
      n.vx -= n.x * 0.004 * alpha;
      n.vy -= n.y * 0.004 * alpha;
      if (drag && drag.node === n) {
        n.vx = n.vy = 0;
        continue;
      }
      n.vx *= 0.82;
      n.vy *= 0.82;
      n.x += n.vx;
      n.y += n.vy;
    }
    alpha *= 0.985;
  }

  function tick() {
    if (alpha > 0.02) {
      step();
      draw();
      requestAnimationFrame(tick);
    } else {
      draw();
    }
  }

  function draw() {
    ctx.clearRect(0, 0, width, height);
    if (!nodes.length) return;
    ctx.save();
    ctx.translate(width / 2 + view.x, height / 2 + view.y);
    ctx.scale(view.k, view.k);
    const near = hover ? neighbors.get(hover.id) : null;
    const lit = (n) => !hover || n === hover || near.has(n.id);

    for (const e of edges) {
      const on = !hover || e.s === hover || e.t === hover;
      ctx.globalAlpha = on ? 1 : 0.15;
      ctx.strokeStyle = e.kind === "tree" ? COLOR.edge : COLOR.cite;
      ctx.lineWidth = (e.kind === "tree" ? 1.4 : 1) / view.k;
      ctx.beginPath();
      ctx.moveTo(e.s.x, e.s.y);
      ctx.lineTo(e.t.x, e.t.y);
      ctx.stroke();
    }
    for (const n of nodes) {
      ctx.globalAlpha = lit(n) ? 1 : 0.18;
      ctx.fillStyle = n.kind === "paper" ? COLOR.read : n.kind === "cited" ? COLOR.paper : n.depth === 0 ? COLOR.root : COLOR.keyword;
      ctx.beginPath();
      ctx.arc(n.x, n.y, radius(n), 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    for (const n of nodes) {
      const always = n.kind === "keyword" && (n.depth <= 1 || n.weight >= 3);
      const show = n === hover || (near && near.has(n.id)) || (n.kind === "keyword" && (always || view.k > 1.15)) || (isPaper(n) && view.k > 1.9);
      if (!show) continue;
      ctx.globalAlpha = lit(n) ? 1 : 0.18;
      const size = (isPaper(n) ? 11 : n.depth === 0 ? 14 : 12) / Math.max(view.k, 0.7);
      ctx.font = `${n.depth === 0 ? 700 : 560} ${size}px "Pretendard Variable", Pretendard, "Malgun Gothic", sans-serif`;
      ctx.fillStyle = COLOR.label;
      ctx.fillText(n.label, n.x, n.y + radius(n) + 3 / view.k);
    }
    ctx.restore();
    ctx.globalAlpha = 1;
  }

  const toWorld = (e) => {
    const rect = canvas.getBoundingClientRect();
    return { x: (e.clientX - rect.left - width / 2 - view.x) / view.k, y: (e.clientY - rect.top - height / 2 - view.y) / view.k, sx: e.clientX - rect.left, sy: e.clientY - rect.top };
  };
  const pick = (p) => {
    let best = null;
    for (const n of nodes) {
      const r = radius(n) + 4 / view.k;
      if ((n.x - p.x) ** 2 + (n.y - p.y) ** 2 <= r * r) best = n;
    }
    return best;
  };

  canvas.addEventListener("pointerdown", (e) => {
    const p = toWorld(e);
    const node = pick(p);
    drag = { node, x: e.clientX, y: e.clientY, vx: view.x, vy: view.y };
    moved = false;
    canvas.setPointerCapture(e.pointerId);
    canvas.classList.add("dragging");
  });
  canvas.addEventListener("pointermove", (e) => {
    const p = toWorld(e);
    if (drag) {
      if (Math.abs(e.clientX - drag.x) + Math.abs(e.clientY - drag.y) > 4) moved = true;
      if (drag.node) {
        drag.node.x = p.x;
        drag.node.y = p.y;
        if (alpha < 0.25) {
          alpha = 0.25;
          requestAnimationFrame(tick);
        }
      } else {
        view.x = drag.vx + (e.clientX - drag.x);
        view.y = drag.vy + (e.clientY - drag.y);
      }
      draw();
      return;
    }
    const node = pick(p);
    if (node !== hover) {
      hover = node;
      canvas.style.cursor = node ? "pointer" : "";
      draw();
    }
    if (node) {
      tip.textContent = isPaper(node) ? `${node.label} — ${node.title} · ${node.kind === "paper" ? "읽은 논문" : `인용된 주장 ${node.weight}`}` : `${node.label} · 주장 ${node.weight}`;
      tip.style.left = Math.min(p.sx + 14, width - 330) + "px";
      tip.style.top = p.sy + 16 + "px";
      tip.style.opacity = 1;
    } else {
      tip.style.opacity = 0;
    }
  });
  canvas.addEventListener("pointerup", () => {
    canvas.classList.remove("dragging");
    if (drag && drag.node && !moved) location.href = drag.node.url;
    drag = null;
  });
  canvas.addEventListener("pointerleave", () => {
    tip.style.opacity = 0;
    if (hover && !drag) {
      hover = null;
      draw();
    }
  });
  canvas.addEventListener(
    "wheel",
    (e) => {
      e.preventDefault();
      const p = toWorld(e);
      const k = Math.min(4, Math.max(0.25, view.k * (e.deltaY < 0 ? 1.12 : 0.89)));
      view.x += p.x * (view.k - k); // 커서 아래 지점이 제자리에 있도록
      view.y += p.y * (view.k - k);
      view.k = k;
      draw();
    },
    { passive: false },
  );

  $("#graph-papers").addEventListener("change", () => load().catch((err) => toast(err.message, "err")));
  window.addEventListener("resize", resize);
  resize();
  try {
    await load();
  } catch (err) {
    toast(err.message, "err");
  }
})();
