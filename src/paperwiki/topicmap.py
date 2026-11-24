"""주제 지도: 위키를 '보는' 화면이 읽는 데이터 두 덩어리(graph · evidence)를 만든다.

한 장의 그래프에 키워드 계층과 문헌을 다 넣으면 최상위 분류가 모든 것을 끌어당기는 허브가 되어 읽을 수 없다.
그래서 화면은 위키 원본을 직접 읽지 않고, 여기서 미리 나누고 집계한 것만 읽는다.

- 분류(category): 키워드 트리의 윗부분. 지도에서는 노드가 아니라 색과 영역이다.
- 주제(topic): 주장이 직접 정리된 키워드. 지도의 노드. 크기는 그 주제의 주장에 인용된 문헌 수.
- 주제 사이의 선: 두 주제 모두에서 인용된 문헌 수 (여러 방향으로 인용된 문헌이 주제를 잇는다).
  읽은 논문이 몇 편 안 될 때 '같은 논문 안에서 함께 다뤄짐'으로 이으면 거의 모든 주제가 서로 이어지므로 쓰지 않는다.
- 좌표는 위키 폴더(.paperwiki/map.json)에 저장한다. 논문이 늘어도 기존 주제는 제자리 근처에 머문다.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter

from . import render
from .store import CLAIM_TYPES, Ontology, Vault, write_json_atomic

MAX_COLORS = 5  # 분류에 쓰는 색 수. 넘는 분류는 '기타'(회색)로 모은다
BACKBONE_K = 3  # 주제마다 가장 강한 연결 몇 개를 기본으로 그릴지
OTHER = "cat:other"
LAYOUT_SCHEMA = 2
APART = 2.8  # 다른 분류의 주제끼리 더 밀어내는 정도
COHESION, GRAVITY = 3.5, 1.8  # 같은 분류끼리 모으는 힘 · 한가운데로 모으는 힘


# ── 이름 ──────────────────────────────────────────────────────────────────


def _width(text: str) -> float:
    """화면에서 차지하는 대략의 너비 (한글 한 자 = 1)."""
    return sum(1.0 if ord(ch) > 0x2E80 else 0.56 for ch in text)


def short_name(name: str, limit: float = 15) -> str:
    """지도에 쓰는 짧은 이름. 긴 이름은 첫 덩어리만 쓰거나 줄인다 (전체 이름은 툴팁과 패널에 나온다)."""
    name = render.one_line(name)
    if _width(name) <= limit:
        return name
    for sep in ("·", "(", ",", ":", " — "):
        head = name.split(sep)[0].strip()
        if head != name and 2 <= _width(head) <= limit:
            return head
    out, used = "", 0.0
    for ch in name:
        used += _width(ch)
        if used > limit - 1:
            break
        out += ch
    return out.rstrip(" -·") + "…"


def _year(paper: dict) -> int | None:
    m = re.match(r"\s*(\d{4})", str(paper.get("year") or ""))
    return int(m.group(1)) if m else None


# ── 분류 정하기 ───────────────────────────────────────────────────────────


def _categories(onto: Ontology, counts: dict, direct: set[str]) -> list[dict]:
    """키워드 트리의 윗부분을 색을 줄 분류로 고른다.

    최상위 키워드에서 시작해, 색 수(MAX_COLORS)를 넘지 않는 동안 주제가 가장 많은 분류를 하위 키워드로 쪼갠다.
    (예: 연구 주제 · 방법론 → 연구 주제 · 연구 설계 · 분석 방법 · 측정·평가 도구 · 데이터·대상)
    반환: [{"id", "name", "members": [키워드 id, ...]}] — members 는 그 분류에 드는 하위 트리의 뿌리들.
    """
    live = lambda nid: counts[nid]["claims"] > 0  # noqa: E731
    kids = lambda nid: [c["id"] for c in onto.children(nid) if live(c["id"])]  # noqa: E731
    topics_under = lambda nid: sum(1 for i in [nid, *onto.descendants(nid)] if i in direct)  # noqa: E731

    cats = [{"id": n["id"], "own": False} for n in onto.roots() if live(n["id"])]
    while True:
        best = None
        for cat in cats:
            if cat["own"]:
                continue
            children = kids(cat["id"])
            grown = len(cats) - 1 + len(children) + (1 if cat["id"] in direct else 0)
            if len(children) >= 2 and grown <= MAX_COLORS and (best is None or topics_under(cat["id"]) > topics_under(best["id"])):
                best = cat
        if best is None:
            break
        at = cats.index(best)
        split = [{"id": c, "own": False} for c in kids(best["id"])]
        if best["id"] in direct:  # 쪼갠 키워드에 직접 정리된 주장이 있으면 그 키워드 혼자 한 분류로 남는다
            split.insert(0, {"id": best["id"], "own": True})
        cats[at : at + 1] = split

    out = [{"id": c["id"], "name": onto.nodes[c["id"]]["name"], "members": [c["id"]], "own": c["own"]} for c in cats]
    if len(out) == 1 and not out[0]["own"] and len(kids(out[0]["id"])) >= 2:
        # 분류가 하나뿐이면 색이 아무것도 말해 주지 못한다: 하위 키워드로 나누고, 색 수를 넘는 것은 '기타'로 모은다
        root = out[0]["id"]
        children = sorted(kids(root), key=lambda i: (-topics_under(i), onto.nodes[i]["name"]))
        keep = MAX_COLORS - (1 if root in direct else 0)
        if len(children) > keep:
            keep -= 1
        out = [{"id": c, "name": onto.nodes[c]["name"], "members": [c], "own": False} for c in children[:keep]]
        if root in direct:
            out.insert(0, {"id": root, "name": onto.nodes[root]["name"], "members": [root], "own": True})
        if children[keep:]:
            out.append({"id": OTHER, "name": "기타", "members": children[keep:], "own": False})
    return out


# ── 군집 (분류와 무관하게, 함께 인용되는 주제끼리) ─────────────────────────


def _communities(ids: list[str], weights: dict[tuple[str, str], float]) -> dict[str, int]:
    """모듈성을 키우는 쪽으로 주제를 옮겨 가며 묶는다 (Louvain 의 첫 단계). 순서가 정해져 있어 결과가 늘 같다."""
    adj: dict[str, dict[str, float]] = {i: {} for i in ids}
    for (a, b), w in weights.items():
        adj[a][b] = w
        adj[b][a] = w
    degree = {i: sum(adj[i].values()) for i in ids}
    total = sum(degree.values()) or 1.0
    comm = {i: i for i in ids}
    mass = dict(degree)
    for _ in range(20):
        moved = False
        for i in ids:
            if not adj[i]:
                continue
            links: Counter = Counter()
            for j, w in adj[i].items():
                links[comm[j]] += w
            home = comm[i]
            mass[home] -= degree[i]
            gain = lambda c: links.get(c, 0.0) - mass.get(c, 0.0) * degree[i] / total  # noqa: E731
            best = max(sorted(set(links) | {home}), key=gain)
            if gain(best) <= gain(home) + 1e-12:
                best = home
            mass[best] = mass.get(best, 0.0) + degree[i]
            if best != home:
                comm[i] = best
                moved = True
        if not moved:
            break
    order: dict[str, int] = {}
    for i in ids:
        order.setdefault(comm[i], len(order))
    return {i: order[comm[i]] for i in ids}


# ── 배치 ──────────────────────────────────────────────────────────────────


def radius(n_papers: int) -> float:
    """노드 반지름. 면적이 인용된 문헌 수에 비례한다."""
    return 5.0 + 3.1 * math.sqrt(max(n_papers, 0))


def _layout(nodes: list[dict], edges: list[dict], cat_order: list[str], saved: dict[str, list[float]]) -> dict[str, tuple[float, float]]:
    """힘 기반 배치 + 겹침 제거. 저장된 좌표가 있으면 거기서 시작해 기존 주제는 조금만 움직인다."""
    ids = [n["id"] for n in nodes]
    n = len(ids)
    if not n:
        return {}
    rad = {x["id"]: radius(x["n_papers"]) for x in nodes}
    cat = {x["id"]: x["category_id"] for x in nodes}
    ideal = 92.0
    links = [(e["source"], e["target"], 0.35 + 0.65 * e["rel"]) for e in edges if e["is_backbone"]]

    pos: dict[str, list[float]] = {i: [float(saved[i][0]), float(saved[i][1])] for i in ids if i in saved}
    warm = len(pos) >= max(2, n // 2)
    if not warm:
        pos = {}
    old = set(pos)
    ring = ideal * 0.9 * math.sqrt(n)
    centers = {c: (ring * math.cos(2 * math.pi * k / max(len(cat_order), 1) - math.pi / 2), ring * math.sin(2 * math.pi * k / max(len(cat_order), 1) - math.pi / 2)) for k, c in enumerate(cat_order)}
    if warm:  # 분류의 중심은 이미 놓인 주제들의 한가운데
        for c in cat_order:
            placed = [pos[i] for i in old if cat[i] == c]
            if placed:
                centers[c] = (sum(p[0] for p in placed) / len(placed), sum(p[1] for p in placed) / len(placed))
    neighbors: dict[str, list[str]] = {i: [] for i in ids}
    for a, b, _ in links:
        neighbors[a].append(b)
        neighbors[b].append(a)
    for k, i in enumerate(ids):
        if i in pos:
            continue
        near = [pos[j] for j in neighbors[i] if j in old]
        cx, cy = (sum(p[0] for p in near) / len(near), sum(p[1] for p in near) / len(near)) if near else centers.get(cat[i], (0.0, 0.0))
        angle, dist = k * 2.399963, (ideal * 0.45 if near else 14.0 * math.sqrt(k + 1))  # 황금각 나선: 난수 없이 고르게 흩는다
        pos[i] = [cx + dist * math.cos(angle), cy + dist * math.sin(angle)]

    rounds = 90 if warm else max(80, min(320, int(3_000_000 / (n * n))))
    heat0 = 9.0 if warm else 46.0
    for step in range(rounds):
        heat = heat0 * (1 - step / rounds) + 0.6
        force = {i: [0.0, 0.0] for i in ids}
        for a in range(n):
            ia = ids[a]
            pa = pos[ia]
            for b in range(a + 1, n):
                ib = ids[b]
                pb = pos[ib]
                dx, dy = pa[0] - pb[0], pa[1] - pb[1]
                d = math.hypot(dx, dy) or 0.01
                gap = max(d - rad[ia] - rad[ib], 4.0)
                f = ideal * ideal / gap / d * (1.0 if cat[ia] == cat[ib] else APART)  # 다른 분류끼리는 조금 더 밀어 영역이 갈리게
                force[ia][0] += dx * f
                force[ia][1] += dy * f
                force[ib][0] -= dx * f
                force[ib][1] -= dy * f
        for a, b, w in links:
            dx, dy = pos[b][0] - pos[a][0], pos[b][1] - pos[a][1]
            d = math.hypot(dx, dy) or 0.01
            f = w * max(d - rad[a] - rad[b], 0.0) / ideal
            force[a][0] += dx * f
            force[a][1] += dy * f
            force[b][0] -= dx * f
            force[b][1] -= dy * f
        if not warm:
            for c in cat_order:  # 같은 분류의 주제들이 한 영역으로 모이도록 그 한가운데로 살짝 끈다
                mine = [i for i in ids if cat[i] == c]
                if mine:
                    centers[c] = (sum(pos[i][0] for i in mine) / len(mine), sum(pos[i][1] for i in mine) / len(mine))
        for i in ids:
            cx, cy = centers.get(cat[i], (0.0, 0.0))
            force[i][0] += (cx - pos[i][0]) * COHESION - pos[i][0] * GRAVITY
            force[i][1] += (cy - pos[i][1]) * COHESION - pos[i][1] * GRAVITY * 1.7  # 화면이 가로로 길어서 세로로 더 모은다
            size = math.hypot(*force[i]) or 0.01
            move = min(size, heat) * (0.12 if warm and i in old else 1.0)
            pos[i][0] += force[i][0] / size * move
            pos[i][1] += force[i][1] / size * move

    for _ in range(80):  # 겹침 제거: 이름표가 들어갈 틈까지 벌린다
        clean = True
        for a in range(n):
            ia = ids[a]
            for b in range(a + 1, n):
                ib = ids[b]
                dx, dy = pos[ia][0] - pos[ib][0], pos[ia][1] - pos[ib][1]
                d = math.hypot(dx, dy) or 0.01
                need = rad[ia] + rad[ib] + 16.0
                if d < need:
                    clean = False
                    push = (need - d) / 2 + 0.5
                    pos[ia][0] += dx / d * push
                    pos[ia][1] += dy / d * push
                    pos[ib][0] -= dx / d * push
                    pos[ib][1] -= dy / d * push
        if clean:
            break
    return {i: (round(pos[i][0], 1), round(pos[i][1], 1)) for i in ids}


def _saved_layout(vault: Vault) -> dict:
    try:
        data = json.loads((vault.meta_dir / "map.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or data.get("schema") != LAYOUT_SCHEMA or not isinstance(data.get("pos"), dict):
        return {}
    return data


def reset_layout(vault: Vault) -> None:
    """저장된 좌표를 지운다. 다음에 지도를 열 때 처음부터 다시 배치한다."""
    with vault.lock:
        try:
            (vault.meta_dir / "map.json").unlink()
        except OSError:
            pass


# ── 내보내기 ──────────────────────────────────────────────────────────────


def export(vault: Vault) -> dict:
    """지도 화면이 읽는 전부: {"graph": 분류·주제·연결, "evidence": 주장·문헌}."""
    with vault.lock:
        papers, onto = vault.papers(), vault.ontology()
        usage = render.build_usage(papers, onto)
        groups = render.claim_groups(papers)
        counts = render.subtree_counts(onto, usage)
        direct = {k for k, pairs in usage.items() if pairs}

        # 주장('같은 주장'은 하나로) → 근거 표
        claims, by_topic = [], {}
        used: set[str] = set()
        for key, members in groups.items():
            entry = render.grouped(members[:1], groups)[0]
            topics = [k for k in entry["keywords"] if k in direct]
            if not topics:
                continue
            cites = sorted(((pid, len(srcs)) for pid, srcs in entry["cites"].items() if pid in papers), key=lambda x: (-x[1], x[0]))
            sources = [
                {
                    "id": src["id"],
                    "quote": render.one_line((claim.get("evidence") or {}).get("quote")),
                    "location": render.one_line((claim.get("evidence") or {}).get("location")),
                    "cites": [pid for pid in dict.fromkeys(claim.get("cites", [])) if pid in papers],
                }
                for src, claim in entry["members"]
            ]
            ctype = entry["type"] if entry["type"] in CLAIM_TYPES else "finding"
            item = {"key": key, "statement": entry["statement"], "type": ctype, "topics": topics, "cites": [{"id": pid, "n": n} for pid, n in cites], "sources": sources}
            claims.append(item)
            used.update(pid for pid, _ in cites)
            used.update(s["id"] for s in sources)
            for t in topics:
                by_topic.setdefault(t, []).append(item)

        # 주제별 집계
        works: dict[str, set[str]] = {t: {c["id"] for item in items for c in item["cites"]} for t, items in by_topic.items()}
        cats = _categories(onto, counts, direct)
        cat_of: dict[str, str] = {}
        for cat in cats:
            for member in cat["members"]:
                for nid in [member] if cat["own"] else [member, *onto.descendants(member)]:
                    cat_of.setdefault(nid, cat["id"])
        nodes = []
        for _, node in onto.walk():
            t = node["id"]
            if t not in by_topic or t not in cat_of:
                continue
            items = by_topic[t]
            nodes.append(
                {
                    "id": t,
                    "display_name": short_name(node["name"]),
                    "full_name": node["name"],
                    "aliases": node.get("aliases", []),
                    "path": onto.path_names(t)[:-1],
                    "category_id": cat_of[t],
                    "n_papers": len(works[t]),
                    "n_read": sum(1 for pid in works[t] if render.is_read(papers[pid])),
                    "n_claims": len(items),
                    "n_events": sum(c["n"] for item in items for c in item["cites"]),
                    "types": {ty: sum(1 for item in items if item["type"] == ty) for ty in CLAIM_TYPES},
                }
            )
        ids = [x["id"] for x in nodes]
        known = set(ids)
        for rank, x in enumerate(sorted(nodes, key=lambda x: (-x["n_papers"], -x["n_claims"], x["full_name"])), 1):
            x["label_rank"] = rank
            x["read_ratio"] = round(x["n_read"] / x["n_papers"], 3) if x["n_papers"] else 0.0

        # 주제 사이의 연결: 두 주제 모두에서 인용된 문헌 수
        shared: Counter = Counter()
        cited_in: dict[str, list[str]] = {}
        for t in ids:
            for pid in works[t]:
                cited_in.setdefault(pid, []).append(t)
        for ts in cited_in.values():
            for a in range(len(ts)):
                for b in range(a + 1, len(ts)):
                    shared[(ts[a], ts[b]) if ts[a] < ts[b] else (ts[b], ts[a])] += 1
        edges = [
            {"source": a, "target": b, "weight": w, "weight_norm": round(w / math.sqrt(len(works[a]) * len(works[b])), 3), "is_backbone": False}
            for (a, b), w in sorted(shared.items())
        ]
        strongest: dict[str, list[dict]] = {t: [] for t in ids}
        for e in edges:
            strongest[e["source"]].append(e)
            strongest[e["target"]].append(e)
        for mine in strongest.values():  # 주제마다 가장 강한 연결만 뼈대로 남긴다
            for e in sorted(mine, key=lambda e: (-e["weight_norm"], -e["weight"], e["source"], e["target"]))[:BACKBONE_K]:
                e["is_backbone"] = True
        top = max((e["weight_norm"] for e in edges), default=1.0) or 1.0
        for e in edges:
            e["rel"] = e["weight_norm"] / top

        # 군집, 그리고 분류와 어긋나는 주제 (분류 점검 대상)
        comm = _communities(ids, {(e["source"], e["target"]): float(e["weight"]) for e in edges})
        by_comm: dict[int, list[dict]] = {}
        for x in nodes:
            x["community_id"] = comm[x["id"]]
            by_comm.setdefault(comm[x["id"]], []).append(x)
        cat_name = {c["id"]: c["name"] for c in cats}
        for members in by_comm.values():
            major, n_major = Counter(x["category_id"] for x in members).most_common(1)[0]
            for x in members:
                off = len(members) >= 3 and n_major * 2 > len(members) and x["category_id"] != major
                x["leans_to"] = cat_name[major] if off else ""

        # 좌표: 저장된 것이 지금 데이터와 맞으면 그대로, 아니면 거기서 시작해 조금만 다시 돌린다
        cat_order = [c["id"] for c in cats]
        sig = hashlib.sha1(
            json.dumps([[(x["id"], x["n_papers"], x["category_id"]) for x in nodes], [(e["source"], e["target"], e["weight"]) for e in edges if e["is_backbone"]]]).encode()
        ).hexdigest()
        saved = _saved_layout(vault)
        if saved.get("sig") == sig and known <= set(saved["pos"]):
            pos = {i: tuple(saved["pos"][i]) for i in ids}
        else:
            pos = _layout(nodes, edges, cat_order, saved.get("pos") or {})
            try:
                write_json_atomic(vault.meta_dir / "map.json", {"schema": LAYOUT_SCHEMA, "sig": sig, "pos": {i: list(p) for i, p in pos.items()}})
            except OSError:
                pass  # 저장하지 못해도 지도는 보인다
        for x in nodes:
            x["x"], x["y"] = pos[x["id"]]
            x["r"] = round(radius(x["n_papers"]), 1)
        for e in edges:
            del e["rel"]

        # 계층 개요: 분류 → 그 아래 키워드 줄
        by_id = {x["id"]: x for x in nodes}
        categories = []
        for color, cat in enumerate(cats):
            rows = []

            def walk(nid: str, depth: int) -> None:
                if counts[nid]["claims"] == 0:
                    return
                node = onto.nodes[nid]
                if nid in by_id:
                    rows.append({"id": nid, "name": node["name"], "depth": depth, "topic": True})
                elif not (depth == 0 and nid == cat["id"]):
                    rows.append({"id": nid, "name": node["name"], "depth": depth, "topic": False, "n_papers": counts[nid]["papers"]})
                else:
                    depth -= 1  # 분류 자신은 왼쪽 칸에 이름이 있으므로 줄을 만들지 않는다
                if not cat["own"]:
                    for child in onto.children(nid):
                        walk(child["id"], depth + 1)

            for member in cat["members"]:
                walk(member, 0)
            inside = [by_id[r["id"]] for r in rows if r["topic"]]
            cat_works = set().union(*(works[x["id"]] for x in inside)) if inside else set()
            categories.append(
                {
                    "id": cat["id"],
                    "name": cat["name"],
                    "display_name": short_name(cat["name"], 9),
                    "color": -1 if cat["id"] == OTHER else color,
                    "n_topics": len(inside),
                    "n_papers": len(cat_works),
                    "n_claims": len({item["key"] for x in inside for item in by_topic[x["id"]]}),
                    "rows": rows,
                }
            )

        years = [y for y in (_year(papers[pid]) for pid in used) if y]
        return {
            "graph": {
                "categories": categories,
                "nodes": nodes,
                "edges": edges,
                "totals": {"topics": len(nodes), "claims": len(claims), "works": len({c["id"] for item in claims for c in item["cites"]}), "read": sum(1 for p in papers.values() if render.is_read(p))},
                "years": [min(years), max(years)] if years else None,
            },
            "evidence": {
                "claims": claims,
                "papers": {
                    pid: {"cite": render.cite_short(papers[pid]), "title": render.one_line(papers[pid].get("title")), "year": _year(papers[pid]), "read": render.is_read(papers[pid])}
                    for pid in sorted(used)
                },
            },
        }
