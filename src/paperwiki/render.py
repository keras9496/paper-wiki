"""원본 데이터(JSON) → 마크다운 위키.

위키가 모으는 것은 '읽은 논문이 다른 문헌을 인용하며 한 주장'이다. 그래서 문서는 세 방향으로 읽힌다.

- 키워드 문서: 그 주제의 주장들과, 주장마다 인용된 문헌 · 그 주제에서 자주 인용되는 문헌
- 문헌 문서(인용된 쪽): 이 문헌이 어떤 주장·어떤 키워드로 인용되었는지 (여러 방향으로 인용된 문헌이 드러난다)
- 논문 문서(읽은 쪽): 이 논문이 문헌을 인용하며 한 주장 목록

생성되는 문서의 끝에는 '메모' 영역이 있다. 표식(<!-- paperwiki:notes ... -->) 아래에
사용자가 Obsidian 등에서 적은 내용은 문서가 다시 생성되어도 그대로 보존된다.
내용이 실제로 바뀐 파일만 다시 쓰므로 동기화 부담이 작다.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

from .store import CLAIM_TYPES, Ontology, Vault, write_text_atomic

NOTES_MARKER = "<!-- paperwiki:notes"

LABELS = {
    "ko": {
        "types": {"finding": "결과·발견", "method": "방법론", "background": "배경·개념", "limitation": "한계·논점"},
        "cited_for": "이 문헌을 인용해 할 수 있는 주장",
        "cited_for_none": "아직 이 문헌을 인용한 주장이 위키에 없습니다.",
        "cited_for_line": "읽은 논문 {sources}편이 주장 {claims}개에서 인용 · 인용된 방향(키워드) {keywords}개",
        "directions": "인용된 방향",
        "own_claims": "이 논문이 문헌을 인용하며 한 주장",
        "kind_read": "읽은 논문",
        "kind_cited": "인용 문헌 (원문은 아직 읽지 않음)",
        "type": "유형",
        "cites": "인용 문헌",
        "cited_with": "함께 인용된 문헌",
        "source": "출처",
        "cited_in": "인용한 논문",
        "evidence": "근거",
        "keywords": "키워드",
        "notes": "메모",
        "notes_hint": "이 줄 아래에 자유롭게 적으세요. 위 내용이 다시 생성되어도 아래 메모는 보존됩니다.",
        "open_zotero": "Zotero에서 열기",
        "open_pdf": "PDF 열기",
        "parent": "상위",
        "children": "하위 키워드",
        "related": "같은 문헌이 인용된 다른 키워드",
        "aliases": "별칭",
        "no_claims": "아직 이 키워드에 직접 정리된 주장이 없습니다.",
        "top_cited": "이 키워드에서 자주 인용되는 문헌",
        "col_paper": "문헌",
        "col_claims": "주장",
        "col_sources": "인용한 논문",
        "claims_n": "주장 {n}",
        "papers_n": "문헌 {n}",
        "read_n": "읽은 논문 {n}",
        "index_title": "Paper Wiki",
        "index_intro": "읽은 논문이 다른 문헌을 인용하며 한 주장을 키워드별로 모은 개인 문헌 위키입니다. 어떤 주장을 할 때 어떤 문헌을 인용하는지를 찾는 데 씁니다.",
        "recent": "최근 읽은 논문",
        "multi_source": "여러 논문이 인용한 문헌",
        "multi_direction": "여러 방향으로 인용된 문헌",
        "ontology": "키워드 온톨로지",
        "et_al": "et al.",
    },
    "en": {
        "types": {"finding": "Findings", "method": "Methods", "background": "Background", "limitation": "Limitations"},
        "cited_for": "Claims this work is cited for",
        "cited_for_none": "No claim in the wiki cites this work yet.",
        "cited_for_line": "Cited by {sources} read papers in {claims} claims · {keywords} directions (keywords)",
        "directions": "Directions",
        "own_claims": "Claims this paper makes while citing other work",
        "kind_read": "Read paper",
        "kind_cited": "Cited work (not read yet)",
        "type": "Type",
        "cites": "Cited works",
        "cited_with": "Cited together with",
        "source": "Source",
        "cited_in": "Cited in",
        "evidence": "Evidence",
        "keywords": "Keywords",
        "notes": "Notes",
        "notes_hint": "Write freely below this line. Your notes are kept when the content above is regenerated.",
        "open_zotero": "Open in Zotero",
        "open_pdf": "Open PDF",
        "parent": "Parent",
        "children": "Child keywords",
        "related": "Other keywords citing the same works",
        "aliases": "Aliases",
        "no_claims": "No claims are filed directly under this keyword yet.",
        "top_cited": "Most cited works under this keyword",
        "col_paper": "Work",
        "col_claims": "Claims",
        "col_sources": "Cited in",
        "claims_n": "{n} claims",
        "papers_n": "{n} works",
        "read_n": "{n} read papers",
        "index_title": "Paper Wiki",
        "index_intro": "A personal literature wiki of the claims that read papers make while citing other work, organized by keyword: which works to cite for which claim.",
        "recent": "Recently read papers",
        "multi_source": "Works cited by several papers",
        "multi_direction": "Works cited in several directions",
        "ontology": "Keyword ontology",
        "et_al": "et al.",
    },
}


def labels(lang: str) -> dict:
    return LABELS.get(lang, LABELS["ko"])


# ── 표시용 헬퍼 (서버 화면과 공유) ─────────────────────────────────────────

_HANGUL = re.compile(r"[가-힣]")


def one_line(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def author_name(author: dict, full: bool = False) -> str:
    if author.get("name"):
        return author["name"]
    family, given = author.get("family", ""), author.get("given", "")
    if _HANGUL.search(family):
        return f"{family}{given}"
    if full:
        return f"{family}, {given}".strip(", ")
    return family or given


def cite_short(paper: dict) -> str:
    """Kim et al. (2023) 형태의 짧은 인용 표기.

    참고문헌 목록에서 온 문헌은 저자가 일부만 적혀 있을 수 있다 (et_al 표시) — 그때는 한두 명이어도 'et al.' 을 붙인다.
    """
    authors = paper.get("authors") or []
    year = paper.get("year") or "n.d."
    if not authors:
        who = one_line(paper.get("title", ""))[:40] or paper.get("id", "")
    elif len(authors) == 1 and not paper.get("et_al"):
        who = author_name(authors[0])
    elif len(authors) == 2 and not paper.get("et_al"):
        who = f"{author_name(authors[0])} & {author_name(authors[1])}"
    else:
        first = author_name(authors[0])
        who = f"{first} 외" if _HANGUL.search(first) else f"{first} et al."
    return f"{who} ({year})"


def is_read(paper: dict) -> bool:
    """PDF 를 읽어 인용을 정리한 논문인지 (아니면 다른 논문의 참고문헌으로만 위키에 있는 문헌)."""
    return paper.get("kind", "read") != "cited"


def zotero_select_uri(paper: dict) -> str:
    return f"zotero://select/library/items/{paper['zotero_key']}" if paper.get("zotero_key") else ""


def zotero_pdf_uri(paper: dict) -> str:
    return f"zotero://open-pdf/library/items/{paper['attachment_key']}" if paper.get("attachment_key") else ""


def pdf_path(paper: dict) -> str:
    """논문 폴더에 있는 이 논문의 PDF (위키 폴더 기준 경로). 없으면 빈 문자열."""
    return (paper.get("pdf") or {}).get("path") or ""


# ── 색인: 주장을 키워드·문헌·'같은 주장' 기준으로 모은다 ──────────────────────


def _by_added(papers: dict[str, dict]) -> list[dict]:
    return sorted(papers.values(), key=lambda p: (p.get("added", ""), p.get("id", "")))


def build_usage(papers: dict[str, dict], onto: Ontology) -> dict[str, list[tuple[dict, dict]]]:
    """키워드 id → [(읽은 논문, 주장), ...]"""
    usage: dict[str, list[tuple[dict, dict]]] = {}
    for paper in _by_added(papers):
        for claim in paper.get("claims", []):
            for kid in dict.fromkeys(claim.get("keywords", [])):
                if kid in onto.nodes:
                    usage.setdefault(kid, []).append((paper, claim))
    return usage


def citations(papers: dict[str, dict]) -> dict[str, list[tuple[dict, dict]]]:
    """문헌 id → [(그 문헌을 인용한 논문, 주장), ...]"""
    out: dict[str, list[tuple[dict, dict]]] = {}
    for paper in _by_added(papers):
        for claim in paper.get("claims", []):
            for pid in dict.fromkeys(claim.get("cites", [])):
                if pid in papers:
                    out.setdefault(pid, []).append((paper, claim))
    return out


def group_key(paper: dict, claim: dict) -> str:
    """같은 주장끼리 공유하는 값. 묶이지 않은 주장은 자기만의 값을 가진다."""
    return claim.get("group") or f"{paper['id']}#{claim.get('id')}"


def claim_groups(papers: dict[str, dict]) -> dict[str, list[tuple[dict, dict]]]:
    """'같은 주장' 묶음 → [(읽은 논문, 주장), ...] (먼저 등록된 논문부터)"""
    out: dict[str, list[tuple[dict, dict]]] = {}
    for paper in _by_added(papers):
        for claim in paper.get("claims", []):
            out.setdefault(group_key(paper, claim), []).append((paper, claim))
    return out


def grouped(pairs: list[tuple[dict, dict]], groups: dict[str, list[tuple[dict, dict]]]) -> list[dict]:
    """(논문, 주장) 목록을 '같은 주장'끼리 묶어 한 항목씩으로 만든다.

    한 항목에는 그 주장을 한 모든 논문이 들어간다 (다른 키워드에 정리된 것도 포함) —
    같은 주장에 서로 다른 논문이 어떤 문헌을 인용했는지 한눈에 보이도록.
    cites 는 문헌 id → 그 문헌을 이 주장에 인용한 논문 id 목록.
    """
    out, seen = [], set()
    for paper, claim in pairs:
        key = group_key(paper, claim)
        if key in seen:
            continue
        seen.add(key)
        members = groups.get(key) or [(paper, claim)]
        cites: dict[str, list[str]] = {}
        keywords: list[str] = []
        for src, c in members:
            for pid in dict.fromkeys(c.get("cites", [])):
                cites.setdefault(pid, [])
                if src["id"] not in cites[pid]:
                    cites[pid].append(src["id"])
            for kid in c.get("keywords", []):
                if kid not in keywords:
                    keywords.append(kid)
        first = members[0][1]
        out.append(
            {
                "key": key,
                "group": first.get("group") or "",
                "statement": one_line(first.get("statement")),
                "type": first.get("type", "finding"),
                "members": members,
                "sources": list(dict.fromkeys(src["id"] for src, _ in members)),
                "cites": cites,
                "keywords": keywords,
            }
        )
    return out


def paper_stats(papers: dict[str, dict], onto: Ontology | None = None, cited: dict | None = None) -> dict[str, dict]:
    """문헌 id → 인용된 정도: claims(주장 수), sources(인용한 논문 수), keywords(인용된 방향 = 키워드 수)."""
    cited = citations(papers) if cited is None else cited
    out = {}
    for pid, pairs in cited.items():
        keywords = {k for _, c in pairs for k in c.get("keywords", []) if onto is None or k in onto.nodes}
        out[pid] = {
            "claims": len({group_key(src, c) for src, c in pairs}),
            "sources": len({src["id"] for src, _ in pairs}),
            "keywords": len(keywords),
            "keyword_ids": sorted(keywords),
        }
    return out


def subtree_counts(onto: Ontology, usage: dict) -> dict[str, dict]:
    """키워드별 (자신 + 하위 전체) 주장 수 · 인용된 문헌 수 · 읽은 논문 수."""
    out = {}
    for node_id in onto.nodes:
        ids = [node_id, *onto.descendants(node_id)]
        claims, cited, sources = set(), set(), set()
        for i in ids:
            for paper, claim in usage.get(i, []):
                claims.add(group_key(paper, claim))
                cited.update(claim.get("cites", []))
                sources.add(paper["id"])
        out[node_id] = {
            "claims": len(claims),
            "papers": len(cited),
            "sources": len(sources),
            "direct": len({group_key(p, c) for p, c in usage.get(node_id, [])}),
        }
    return out


def keyword_cited(node_id: str, usage: dict, papers: dict[str, dict]) -> list[dict]:
    """이 키워드의 주장에 인용된 문헌을 많이 인용된 순으로: [{paper, claims, sources}]"""
    claims: dict[str, set] = {}
    sources: dict[str, set] = {}
    for paper, claim in usage.get(node_id, []):
        for pid in claim.get("cites", []):
            if pid in papers:
                claims.setdefault(pid, set()).add(group_key(paper, claim))
                sources.setdefault(pid, set()).add(paper["id"])
    rows = [{"paper": papers[pid], "claims": len(claims[pid]), "sources": len(sources[pid])} for pid in claims]
    rows.sort(key=lambda r: (-r["sources"], -r["claims"], cite_short(r["paper"]).casefold()))
    return rows


def related_keywords(node_id: str, papers: dict[str, dict], onto: Ontology, limit: int = 12) -> list[tuple[dict, int]]:
    """같은 문헌이 인용된 다른 키워드 (상·하위 관계는 제외). 수는 함께 인용된 문헌 수."""
    lineage = set(onto.path_ids(node_id)) | set(onto.descendants(node_id))
    by_paper: dict[str, set] = {}
    for paper in papers.values():
        for claim in paper.get("claims", []):
            for pid in claim.get("cites", []):
                by_paper.setdefault(pid, set()).update(claim.get("keywords", []))
    counter: Counter = Counter()
    for kws in by_paper.values():
        if node_id not in kws:
            continue
        for other in kws:
            if other not in lineage and other in onto.nodes:
                counter[other] += 1
    ranked = sorted(counter.items(), key=lambda kv: (-kv[1], onto.nodes[kv[0]]["name"]))
    return [(onto.nodes[k], n) for k, n in ranked[:limit]]


def claims_listing(papers: dict[str, dict], onto: Ontology, exclude: str | None = None) -> tuple[str, int]:
    """위키에 이미 있는 주장 목록 (읽기 에이전트가 '같은 주장'을 찾아 묶을 때 읽는 글). 반환: (글, 주장 수)"""
    usage = build_usage({pid: p for pid, p in papers.items() if pid != exclude}, onto)
    groups = claim_groups(papers)
    lines, seen = [], set()
    for _, node in onto.walk():
        entries = [e for e in grouped(usage.get(node["id"], []), groups) if e["group"] and e["key"] not in seen]
        if not entries:
            continue
        lines += ["", "## " + " > ".join(onto.path_names(node["id"])), ""]
        for entry in entries:
            seen.add(entry["key"])
            cited = "; ".join(cite_short(papers[pid]) for pid in entry["cites"] if pid in papers)
            lines.append(f"- {entry['group']} | {entry['statement']} | cited: {cited}")
    head = "# Claims already in the wiki\n\nEach line: id | claim | works cited for it. Use the id as `same_as` only when a statement makes the same point.\n"
    return head + "\n".join(lines) + "\n", len(seen)


# ── 마크다운 조각 ─────────────────────────────────────────────────────────


def _yaml(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _wikilink(target: str, display: str | None = None) -> str:
    if display is None or display == target:
        return f"[[{target}]]"
    display = display.replace("|", "¦").replace("[", "(").replace("]", ")")
    return f"[[{target}|{display}]]"


def kw_link(node: dict) -> str:
    return _wikilink(node["file"], node["name"])


def paper_link(paper: dict) -> str:
    return _wikilink(paper["id"], cite_short(paper))


def _notes_block(L: dict) -> str:
    return f"\n## {L['notes']}\n\n{NOTES_MARKER} · {L['notes_hint']} -->\n"


def _evidence_line(claim: dict) -> str:
    ev = claim.get("evidence") or {}
    quote, loc = one_line(ev.get("quote")), one_line(ev.get("location"))
    if quote and loc:
        return f"“{quote}” ({loc})"
    return f"“{quote}”" if quote else loc


def _cite_links(ids, papers: dict, skip: str | None = None) -> str:
    return " · ".join(paper_link(papers[i]) for i in ids if i in papers and i != skip)


def _entry_lines(entry: dict, papers: dict, onto: Ontology, L: dict, focus: str | None = None, keyword: str | None = None) -> list[str]:
    """'같은 주장' 한 항목을 목록 줄로. focus 는 지금 보고 있는 문헌(그 문헌 문서에서는 자신을 뺀 나머지를 '함께 인용된 문헌'으로 보인다)."""
    kind = L["types"].get(entry["type"], entry["type"])
    head = f"- **{entry['statement']}**" + ("" if keyword is not None else f" *({kind})*")  # 키워드 문서에서는 유형별 제목 아래에 놓인다
    if focus is None:
        head += f" — {L['cites']}: " + (_cite_links(entry["cites"], papers) or "-")
    lines = [head]
    for src, claim in entry["members"]:
        if focus is not None and focus not in claim.get("cites", []):
            continue
        ev = _evidence_line(claim)
        line = f"    - {L['cited_in'] if focus is not None else L['source']}: {paper_link(src)}" + (f" {ev}" if ev else "")
        if len(entry["members"]) > 1 and focus is None:
            line += f" — {L['cites']}: " + (_cite_links(claim.get("cites", []), papers) or "-")
        lines.append(line)
    if focus is not None:
        others = _cite_links(entry["cites"], papers, skip=focus)
        if others:
            lines.append(f"    - {L['cited_with']}: {others}")
    kws = [onto.nodes[k] for k in entry["keywords"] if k in onto.nodes and k != keyword]
    if kws and (focus is not None or keyword is not None):
        lines.append(f"    - {L['keywords']}: " + " · ".join(kw_link(n) for n in kws))
    return lines


def render_paper(paper: dict, onto: Ontology, lang: str, papers: dict | None = None, cited: dict | None = None, groups: dict | None = None, stats: dict | None = None) -> str:
    L = labels(lang)
    papers = papers if papers is not None else {paper["id"]: paper}
    cited = cited if cited is not None else citations(papers)
    groups = groups if groups is not None else claim_groups(papers)
    mine = (stats if stats is not None else paper_stats(papers, onto, cited)).get(paper["id"], {"claims": 0, "sources": 0, "keywords": 0, "keyword_ids": []})
    read = is_read(paper)
    short = cite_short(paper)
    authors_full = [author_name(a, full=True) for a in paper.get("authors", [])]
    front = [
        "---",
        "type: paper",
        f"status: {'read' if read else 'cited'}",
        f"citekey: {_yaml(paper['id'])}",
        f"title: {_yaml(one_line(paper.get('title')))}",
        f"authors: {_yaml(authors_full + (['et al.'] if paper.get('et_al') else []))}",
        f"year: {_yaml(paper.get('year') or '')}",
        f"venue: {_yaml(one_line(paper.get('venue')))}",
        f"doi: {_yaml(paper.get('doi') or '')}",
        f"pdf: {_yaml(pdf_path(paper))}",
        f"zotero: {_yaml(zotero_select_uri(paper))}",
        f"cited_by: {mine['sources']}",
        f"cited_claims: {mine['claims']}",
        f"cited_directions: {mine['keywords']}",
        f"aliases: {_yaml([short])}",
        f"tags: {_yaml(['paperwiki/paper', 'paperwiki/read' if read else 'paperwiki/cited'])}",
        "---",
        "",
    ]
    body = [f"# {one_line(paper.get('title')) or paper['id']}", ""]
    meta = [f"**{short}**"]
    if paper.get("venue"):
        meta.append(f"*{one_line(paper['venue'])}*")
    meta += [f"`@{paper['id']}`", L["kind_read"] if read else L["kind_cited"]]
    body += [" · ".join(meta), ""]
    links = []
    if pdf_path(paper):  # 논문 폴더의 PDF (Obsidian 에서 바로 열린다)
        links.append(_wikilink(pdf_path(paper), L["open_pdf"]))
    if zotero_select_uri(paper):
        links.append(f"[{L['open_zotero']}]({zotero_select_uri(paper)})")
    if zotero_pdf_uri(paper) and not pdf_path(paper):
        links.append(f"[{L['open_pdf']}]({zotero_pdf_uri(paper)})")
    if paper.get("doi"):
        links.append(f"[DOI](https://doi.org/{paper['doi']})")
    elif paper.get("url"):
        links.append(f"[URL]({paper['url']})")
    if links:
        body += [" · ".join(links), ""]
    if paper.get("summary"):
        body += [f"> {one_line(paper['summary'])}", ""]

    # 이 문헌이 인용된 주장 — 어떤 방향(키워드)으로, 어떤 논문에서
    uses = cited.get(paper["id"], [])
    if uses or not read:
        body += [f"## {L['cited_for']} ({mine['claims']})", ""]
        if not uses:
            body += [f"*{L['cited_for_none']}*", ""]
        else:
            body += [L["cited_for_line"].format(sources=mine["sources"], claims=mine["claims"], keywords=mine["keywords"]), ""]
            per_kw = Counter(k for src, c in uses for k in dict.fromkeys(c.get("keywords", [])) if k in onto.nodes)
            if per_kw:
                ranked = sorted(per_kw.items(), key=lambda kv: (-kv[1], onto.nodes[kv[0]]["name"]))
                body += [f"**{L['directions']}**: " + " · ".join(f"{kw_link(onto.nodes[k])} ({n})" for k, n in ranked), ""]
            for entry in grouped(uses, groups):
                body += _entry_lines(entry, papers, onto, L, focus=paper["id"])
            body.append("")

    # 이 논문이 문헌을 인용하며 한 주장 (읽은 논문만)
    if read:
        own = paper.get("claims", [])
        body += [f"## {L['own_claims']} ({len(own)})", ""]
        for i, claim in enumerate(own, 1):
            body += [f"### {i}. {one_line(claim.get('statement'))}", ""]
            body.append(f"- **{L['type']}**: {L['types'].get(claim.get('type'), claim.get('type', ''))}")
            body.append(f"- **{L['cites']}**: " + (_cite_links(claim.get("cites", []), papers) or "-"))
            if _evidence_line(claim):
                body.append(f"- **{L['evidence']}**: {_evidence_line(claim)}")
            kws = [onto.nodes[k] for k in claim.get("keywords", []) if k in onto.nodes]
            if kws:
                body.append(f"- **{L['keywords']}**: " + " · ".join(kw_link(n) for n in kws))
            body.append("")
    return "\n".join(front + body) + _notes_block(L)


def render_keyword(node: dict, onto: Ontology, usage: dict, counts: dict, papers: dict, lang: str, groups: dict | None = None) -> str:
    L = labels(lang)
    groups = groups if groups is not None else claim_groups(papers)
    path = onto.path_ids(node["id"])[:-1]
    mine = grouped(usage.get(node["id"], []), groups)
    c = counts.get(node["id"], {"claims": 0, "papers": 0, "sources": 0})
    front = [
        "---",
        "type: keyword",
        f"id: {node['id']}",
        f"aliases: {_yaml(node.get('aliases', []))}",
        f"path: {_yaml(' / '.join(onto.path_names(node['id'])))}",
        f"claims: {c['claims']}",
        f"cited_works: {c['papers']}",
        f"read_papers: {c.get('sources', 0)}",
        'tags: ["paperwiki/keyword"]',
        "---",
        "",
    ]
    body = [f"# {node['name']}", ""]
    if node.get("description"):
        body += [f"> {one_line(node['description'])}", ""]
    if node.get("aliases"):
        body += [f"**{L['aliases']}**: " + ", ".join(node["aliases"]), ""]
    if path:
        body += [f"**{L['parent']}**: " + " › ".join(kw_link(onto.nodes[i]) for i in path), ""]

    if not mine:
        body += [f"*{L['no_claims']}*", ""]
    top = keyword_cited(node["id"], usage, papers)
    if len(top) > 1:
        body += [f"## {L['top_cited']}", "", f"| {L['col_paper']} | {L['col_claims']} | {L['col_sources']} |", "|---|---|---|"]
        for row in top[:15]:
            title = one_line(row["paper"].get("title")).replace("|", "¦")
            body.append(f"| {paper_link(row['paper']).replace('|', chr(92) + '|')} — {title} | {row['claims']} | {row['sources']} |")
        body.append("")
    by_type: dict[str, list] = {}
    for entry in mine:
        by_type.setdefault(entry["type"], []).append(entry)
    for t in (*CLAIM_TYPES, *[t for t in by_type if t not in CLAIM_TYPES]):
        items = by_type.get(t)
        if not items:
            continue
        body += [f"## {L['types'].get(t, t)} ({len(items)})", ""]
        for entry in items:
            body += _entry_lines(entry, papers, onto, L, keyword=node["id"])
        body.append("")

    children = onto.children(node["id"])
    if children:
        body += [f"## {L['children']}", ""]
        for child in children:
            cc = counts.get(child["id"], {"claims": 0, "papers": 0})
            body.append(
                f"- {kw_link(child)} — {L['claims_n'].format(n=cc['claims'])} · {L['papers_n'].format(n=cc['papers'])}"
            )
        body.append("")

    related = related_keywords(node["id"], papers, onto)
    if related:
        body += [f"## {L['related']}", ""]
        body.append(" · ".join(f"{kw_link(n)} ({count})" for n, count in related))
        body.append("")
    return "\n".join(front + body) + _notes_block(L)


def render_index(vault: Vault, onto: Ontology, papers: dict, counts: dict, lang: str, stats: dict | None = None) -> str:
    L = labels(lang)
    stats = stats if stats is not None else paper_stats(papers, onto)
    read = [p for p in papers.values() if is_read(p)]
    n_claims = len(claim_groups(papers))
    body = [
        f"# {L['index_title']}",
        "",
        L["index_intro"],
        "",
        f"{L['read_n'].format(n=len(read))} · {L['papers_n'].format(n=len(papers) - len(read))} · "
        f"{L['claims_n'].format(n=n_claims)} · {L['keywords']} {len(onto.nodes)}",
        "",
        f"## {L['ontology']}",
        "",
    ]
    for depth, node in onto.walk():
        c = counts.get(node["id"], {"claims": 0})
        suffix = f" ({c['claims']})" if c["claims"] else ""
        body.append(f"{'    ' * depth}- {kw_link(node)}{suffix}")

    def top(key: str) -> list[tuple[dict, dict]]:
        rows = [(papers[pid], s) for pid, s in stats.items() if pid in papers and s[key] >= 2]
        rows.sort(key=lambda r: (-r[1][key], -r[1]["claims"], cite_short(r[0]).casefold()))
        return rows[:15]

    for key, heading in (("sources", "multi_source"), ("keywords", "multi_direction")):
        rows = top(key)
        if rows:
            body += ["", f"## {L[heading]}", ""]
            body += [
                f"- {paper_link(p)} — {one_line(p.get('title'))} ({L['col_sources']} {s['sources']} · {L['col_claims']} {s['claims']} · {L['keywords']} {s['keywords']})"
                for p, s in rows
            ]
    body += ["", f"## {L['recent']}", ""]
    recent = sorted(read, key=lambda p: p.get("added", ""), reverse=True)[:15]
    for paper in recent:
        body.append(f"- {paper_link(paper)} — {one_line(paper.get('title'))}")
    if not recent:
        body.append("-")
    body.append("")
    return "\n".join(body) + _notes_block(L)


CLAUDE_MD = {
    "ko": """# Paper Wiki — Claude Code 안내

이 폴더는 개인 문헌 위키입니다. 사용자가 읽은 논문이 **다른 문헌을 인용하며 한 주장**을, 검토를 거쳐 키워드별로 모아 둔 것입니다.
글을 쓸 때 "이런 주장을 하려면 어떤 문헌을 인용하는가"를 찾고, 같은 문헌이 여러 방향으로 인용된 것이나 여러 논문이 같은 주장에 인용한 문헌을 보며 아이디어를 얻는 데 씁니다.

Claude Code 에 `paper-wiki` 스킬이 설치되어 있으면 그 스킬을 쓰세요 (논문 추가·검색·선행연구 작성 절차가 들어 있습니다).
이 문서는 스킬 없이 이 폴더를 직접 열었을 때를 위한 안내입니다.

## 구조

- `index.md` — 전체 목차 (키워드 온톨로지, 여러 논문이 인용한 문헌, 최근 읽은 논문)
- `keywords/<키워드>.md` — 키워드 한 개당 한 문서. 그 키워드의 주장과, 주장마다 인용된 문헌·그 주장을 한 논문(출처). 별칭은 frontmatter `aliases`.
- `papers/<citekey>.md` — 문헌 한 편당 한 문서. frontmatter `status` 가 `read` 면 PDF 를 읽어 인용을 정리한 논문, `cited` 면 다른 논문의 참고문헌으로만 위키에 있는 문헌.
  - "이 문헌을 인용해 할 수 있는 주장": 이 문헌이 어떤 주장·어떤 키워드로 인용되었는지.
  - "이 논문이 문헌을 인용하며 한 주장" (`read` 만): 이 논문의 인용 문장에서 뽑은 주장과 인용 문헌.
- `pdf/` — 논문 저장소. 새 논문 PDF 를 여기에 넣습니다. 등록된 논문의 PDF 는 정해진 규칙의 이름으로 바뀌어 있습니다.
- `.paperwiki/` — 원본 데이터(JSON). 직접 수정하지 않습니다.

## 논문 작성에 활용하는 방법

1. 쓰려는 주장의 주제어로 `keywords/` 를 검색합니다. 한국어·영어 용어와 약어를 모두 시도하세요 (별칭이 frontmatter 에 있습니다).
2. 키워드 문서에서 비슷한 주장을 찾고, 그 주장에 **인용된 문헌**을 인용합니다. 인용 표기는 그 문헌 문서의 `citekey` 를 씁니다 (예: `[@citekey]`).
3. 주장은 '출처 논문이 그 문헌을 그렇게 인용했다'는 기록입니다. 사용자가 그 문헌의 원문을 읽은 것이 아니므로, `status: cited` 인 문헌은
   원문 확인이 필요할 수 있다고 알려 주세요. 여러 논문이 같은 주장에 인용한 문헌은 더 믿을 만한 근거입니다.
4. 위키에 없는 내용을 특정 문헌의 주장인 것처럼 쓰지 않습니다. 근거가 부족하면 그렇게 말합니다.

## 지킬 것

- 새 논문을 위키에 넣는 일은 `paper-wiki` 스킬(`paperwiki` 명령)로만 하고, 사용자가 검토·승인한 것만 등록합니다.
- 각 문서에서 메모 표식(`<!-- paperwiki:notes`) 위쪽은 프로그램이 다시 생성합니다. 표식 아래 메모 영역은 자유롭게 편집해도 됩니다.
- `pdf/` 안의 등록된 PDF 는 손으로 이름을 바꾸지 않습니다 (바꿨다면 `paperwiki tidy` 로 다시 맞춥니다).
""",
    "en": """# Paper Wiki — guide for Claude Code

This folder is a personal literature wiki. It collects, by keyword, the **claims that papers the user read make
while citing other work**, each reviewed by the user. Use it to find which works to cite for a claim, and to notice
works cited in several directions or cited by several papers for the same claim.

If the `paper-wiki` skill is installed in Claude Code, use it (it has the procedures for adding papers,
searching, and writing related-work passages). This page is for when the folder is opened without the skill.

## Layout

- `index.md` — table of contents (keyword ontology, works cited by several papers, recently read papers)
- `keywords/<keyword>.md` — one page per keyword: its claims, the works cited for each claim, and the paper that made the claim. Aliases are in the frontmatter.
- `papers/<citekey>.md` — one page per work. Frontmatter `status` is `read` for a paper whose PDF was read, `cited` for a work known only from another paper's reference list.
  - "Claims this work is cited for": which claims and keywords this work is cited under.
  - "Claims this paper makes while citing other work" (`read` only).
- `pdf/` — the paper store. New PDFs go here. PDFs of registered papers have been renamed to the wiki's naming rule.
- `.paperwiki/` — source data (JSON). Do not edit by hand.

## Using it while writing

1. Search `keywords/` for the topic of the claim. Try synonyms and abbreviations (aliases are in the frontmatter).
2. Find a similar claim on the keyword page and cite the **works cited for it**, using the work page's `citekey` (e.g. `[@citekey]`).
3. A claim records that a source paper cited the work that way. The user has not necessarily read the cited work, so say
   when a `status: cited` work may need checking. Works cited for the same claim by several papers are stronger support.
4. Do not attribute to a work anything the wiki does not record. If support is thin, say so.

## Rules

- Add papers only through the `paper-wiki` skill (the `paperwiki` command); register only what the user has reviewed and approved.
- Everything above the notes marker (`<!-- paperwiki:notes`) is regenerated. The notes area below the marker is free to edit.
- Do not rename registered PDFs in `pdf/` by hand (if that happened, `paperwiki tidy` reconnects them).
""",
}


# ── 파일 동기화 ───────────────────────────────────────────────────────────

_file_cache: dict[str, tuple[tuple[int, int], str, str]] = {}


def split_notes(path: Path) -> tuple[str | None, str]:
    """기존 파일을 (생성 영역, 사용자 메모) 로 나눈다. 파일이 없으면 (None, '')."""
    key = str(path)
    try:
        st = path.stat()
    except OSError:
        _file_cache.pop(key, None)
        return None, ""
    sig = (st.st_mtime_ns, st.st_size)
    cached = _file_cache.get(key)
    if cached and cached[0] == sig:
        return cached[1], cached[2]
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None, ""
    text = text.replace("\r\n", "\n")
    idx = text.find(NOTES_MARKER)
    if idx < 0:
        head, notes = text, ""
    else:
        end = text.find("\n", idx)
        end = len(text) if end < 0 else end + 1
        head, notes = text[:end], text[end:]
    _file_cache[key] = (sig, head, notes)
    return head, notes


def _name_key(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def sync(vault: Vault) -> dict:
    """데이터에 맞춰 마크다운을 갱신한다. 바뀐 파일만 쓴다."""
    with vault.lock:
        onto = vault.ontology()
        papers = vault.papers()
        lang = vault.settings().get("language", "ko")
        usage = build_usage(papers, onto)
        counts = subtree_counts(onto, usage)
        cited = citations(papers)
        groups = claim_groups(papers)
        stats = paper_stats(papers, onto, cited)

        desired: dict[Path, str] = {}
        for paper in papers.values():
            desired[vault.papers_md / f"{paper['id']}.md"] = render_paper(paper, onto, lang, papers, cited, groups, stats)
        for node in onto.nodes.values():
            desired[vault.keywords_md / f"{node['file']}.md"] = render_keyword(
                node, onto, usage, counts, papers, lang, groups
            )
        desired[vault.root / "index.md"] = render_index(vault, onto, papers, counts, lang, stats)
        desired[vault.root / "CLAUDE.md"] = CLAUDE_MD.get(lang, CLAUDE_MD["ko"]) + _notes_block(labels(lang))

        written = removed = 0
        for path, head in desired.items():
            old_head, notes = split_notes(path)
            if old_head == head:
                continue
            write_text_atomic(path, head + notes)
            _file_cache.pop(str(path), None)
            written += 1

        # 더 이상 해당하는 데이터가 없는 생성 문서 정리 (메모가 있으면 _orphans 로 옮겨 보존)
        for directory in (vault.papers_md, vault.keywords_md):
            wanted = {_name_key(p.name) for p in desired if p.parent == directory}
            try:
                existing = list(directory.glob("*.md"))
            except OSError:
                existing = []
            for path in existing:
                if _name_key(path.name) in wanted:
                    continue
                head, notes = split_notes(path)
                if head is None or NOTES_MARKER not in head:
                    continue  # 사용자가 직접 만든 문서는 건드리지 않는다
                if notes.strip():
                    orphan_dir = vault.root / "_orphans"
                    orphan_dir.mkdir(exist_ok=True)
                    path.replace(orphan_dir / path.name)
                else:
                    path.unlink()
                _file_cache.pop(str(path), None)
                removed += 1
        _ensure_obsidian_defaults(vault)
        return {"written": written, "removed": removed}


def _ensure_obsidian_defaults(vault: Vault) -> None:
    """Obsidian 그래프에서 논문/키워드가 색으로 구분되도록 기본값을 한 번만 넣는다."""
    obsidian = vault.root / ".obsidian"
    if obsidian.exists():
        return
    try:
        obsidian.mkdir()
        graph = {
            "colorGroups": [
                {"query": "path:keywords", "color": {"a": 1, "rgb": 0x1E40AF}},
                {"query": "path:papers", "color": {"a": 1, "rgb": 0x0891B2}},
            ],
            "showTags": False,
        }
        (obsidian / "graph.json").write_text(json.dumps(graph, indent=2), encoding="utf-8")
    except OSError:
        pass


def move_keyword_file(vault: Vault, old_file: str, new_file: str) -> None:
    """키워드 이름이 바뀔 때 문서 파일도 옮겨서 메모가 따라가게 한다."""
    if old_file == new_file:
        return
    old, new = vault.keywords_md / f"{old_file}.md", vault.keywords_md / f"{new_file}.md"
    try:
        if old.exists() and not new.exists():
            old.replace(new)
    except OSError:
        pass
    _file_cache.pop(str(old), None)
    _file_cache.pop(str(new), None)


def append_notes(vault: Vault, file: str, extra: str) -> None:
    """다른 문서에서 넘어온 메모를 덧붙인다 (키워드 병합 시)."""
    if not extra.strip():
        return
    path = vault.keywords_md / f"{file}.md"
    head, notes = split_notes(path)
    if head is None:
        return
    write_text_atomic(path, head + notes.rstrip("\n") + "\n\n" + extra.strip("\n") + "\n")
    _file_cache.pop(str(path), None)
