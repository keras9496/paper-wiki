"""위키 조작: 검토안(draft) 만들기·승인, 문헌 연결, 키워드 편집·병합, 검색.

위키에 쌓이는 것은 '읽은 논문이 문헌을 인용하며 한 주장'이다. 논문 한 편을 등록하면

- 그 논문이 '읽은 논문'으로 등록되고
- 그 논문의 주장마다 인용된 참고문헌이 '인용 문헌'으로 등록되거나, 이미 위키에 있는 문헌에 연결된다.

그래서 같은 문헌이 여러 논문에서, 여러 주장으로 인용된 모습이 문헌 문서에 모인다.
"""

from __future__ import annotations

import copy
import difflib
import json
import platform
import re
import secrets
import time
import unicodedata

from . import biblio, config, extract, library, render
from .store import CLAIM_TYPES, Ontology, OntologyError, Vault, norm, now_iso

# zotero_pdf: "linked" 면 attachment_key 는 Paper Wiki 가 만든 PDF 링크다 (위키에서 PDF 이름이 바뀌면 따라 고친다)
# biblio: DOI 등록 기록에서 온 권·호·쪽 등 (Zotero 항목을 만들 때 쓴다)
PAPER_FIELDS = ("zotero_key", "attachment_key", "zotero_pdf", "title", "authors", "et_al", "year", "venue", "doi", "url", "abstract", "item_type", "biblio", "pdf")
REF_FIELDS = ("title", "authors", "et_al", "year", "venue", "doi")
_GROUP_RE = re.compile(r"^g[0-9a-f]{8}$")
_ID_RE = re.compile(r"^[\w\-]{1,80}$", re.UNICODE)


class WikiError(ValueError):
    """사용자에게 그대로 보여줄 수 있는 오류."""


# ── 검토안 ────────────────────────────────────────────────────────────────


def _text(value, limit: int = 4000) -> str:
    return re.sub(r"[ \t\r\f\v]+", " ", str(value or "")).strip()[:limit]


def clean_claims(raw) -> list[dict]:
    """AI 출력이나 화면에서 온 주장 목록을 정해진 형태로 다듬는다."""
    claims = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        ctype = item.get("type") if item.get("type") in CLAIM_TYPES else "finding"
        ev = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        keywords, seen = [], set()
        for kw in item.get("keywords") or []:
            if not isinstance(kw, dict):
                continue
            path = [_text(p, 120) for p in kw.get("path") or [] if _text(p)]
            if not path or norm(path[-1]) in seen:
                continue
            seen.add(norm(path[-1]))
            keywords.append(
                {
                    "path": path[-6:],
                    "aliases": [_text(a, 120) for a in kw.get("aliases") or [] if _text(a)][:8],
                    "description": _text(kw.get("description"), 400),
                }
            )
        refs = item.get("refs") if isinstance(item.get("refs"), list) else []
        refs = list(dict.fromkeys(label for label in (extract.ref_label(r) for r in refs) if label))
        group = str(item.get("group") or item.get("same_as") or "").strip()
        claims.append(
            {
                "include": item.get("include", True) is not False,
                "statement": _text(item.get("statement"), 1200),
                "type": ctype,
                "refs": refs[:80],
                "evidence": {"quote": _text(ev.get("quote"), 1200), "location": _text(ev.get("location"), 120)},
                "keywords": keywords[:8],
                "group": group if _GROUP_RE.match(group) else "",
            }
        )
    return claims


def clean_references(raw) -> list[dict]:
    """검토안의 참고문헌 목록. 등록된 논문을 고치는 검토안에서는 paper_id 로 기존 문헌에 묶여 있다."""
    out, seen = [], set()
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        ref = extract.clean_reference(item)
        if not ref["ref"] or ref["ref"] in seen:
            continue
        seen.add(ref["ref"])
        pid = item.get("paper_id")
        if isinstance(pid, str) and _ID_RE.match(pid):
            ref["paper_id"] = pid
        out.append(ref)
    return out


def new_draft(draft_id: str, meta: dict) -> dict:
    return {
        "id": draft_id,
        "status": "ready",
        "created": now_iso(),
        "updated": now_iso(),
        "paper": meta,
        "paper_id": None,
        "summary": "",
        "references": [],
        "claims": [],
        "note": "",
        "extraction": {},
    }


def draft_from_paper(vault: Vault, paper: dict) -> dict:
    """이미 등록된 논문을 다시 검토 화면에서 고칠 수 있게 검토안으로 바꾼다."""
    onto, papers = vault.ontology(), vault.papers()
    meta = {k: copy.deepcopy(paper.get(k)) for k in PAPER_FIELDS}
    draft = new_draft(paper["id"], meta)
    draft["paper_id"] = paper["id"]
    draft["summary"] = paper.get("summary", "")
    draft["extraction"] = paper.get("extraction", {})
    labels: dict[str, str] = {}
    for claim in paper.get("claims", []):
        refs = []
        for pid in claim.get("cites", []):
            cited = papers.get(pid)
            if not cited:
                continue
            if pid not in labels:
                labels[pid] = str(len(labels) + 1)
                draft["references"].append({"ref": labels[pid], **{k: copy.deepcopy(cited.get(k)) for k in REF_FIELDS}, "paper_id": pid})
            refs.append(labels[pid])
        draft["claims"].append(
            {
                "include": True,
                "statement": claim.get("statement", ""),
                "type": claim.get("type", "finding"),
                "refs": refs,
                "evidence": copy.deepcopy(claim.get("evidence", {"quote": "", "location": ""})),
                "keywords": [
                    {"path": onto.path_names(k), "aliases": [], "description": ""}
                    for k in claim.get("keywords", [])
                    if k in onto.nodes
                ],
                "group": claim.get("group", ""),
            }
        )
    return draft


# ── 같은 문헌 찾기 ────────────────────────────────────────────────────────
#
# 이 위키의 값은 "한 문헌이 여러 논문에서, 여러 방향으로 인용된다"는 것을 보는 데 있다. 같은 문헌이 표기 차이로
# 두 문서로 갈리면 그것이 보이지 않게 되므로, 같은 문헌을 놓치지 않는 것이 잘못 합치는 것만큼 중요하다.
#   1. DOI 를 기준 식별자로 삼는다 (등록할 때 출판사의 참고문헌 목록과 Crossref 검색으로 DOI 를 채운다).
#   2. DOI 가 없거나 달라도 같은 논문이면 잇는다: 제목이 같은 것, 프리프린트와 출판본, 부제가 잘린 것.
#   3. 한 번 이어진 다른 표기(다른 DOI·다른 제목)는 문헌에 적어 두어 다음에는 바로 잇는다 (known_as).
#   4. 확신할 수 없는 것은 조용히 나누지 않고 '같은 문헌일 수 있음'으로 사람에게 보인다 (candidates, duplicates).

_PREPRINT_DOI = re.compile(r"^10\.(?:1101/(?:\d{4}\.\d{2}\.\d{2}\.|\d{6}(?:v\d+)?$)|48550/|31234/|31219/|31235/|21203/|2139/ssrn|20944/|26434/|36227/|32942/|22541/)", re.I)


_title_key = biblio.title_key  # 구두점·대소문자·띄어쓰기·발음 기호·태그·'&'/'and'·그리스 문자 표기 차이를 지운 제목


def _family_key(meta: dict) -> str:
    authors = meta.get("authors") or []
    if not authors:
        return ""
    first = authors[0]
    who = first.get("family") or (first.get("name") or "").split(",")[0] or first.get("given") or ""
    return _title_key(who)


def _year_key(meta: dict) -> str:
    return re.sub(r"\D", "", str(meta.get("year") or ""))[:4]


def _doi_key(value) -> str:
    return extract.clean_doi(value).casefold()


def is_preprint_doi(doi) -> bool:
    """프리프린트 서버(bioRxiv·medRxiv·arXiv·PsyArXiv·OSF·SSRN·Research Square …)의 DOI 인가."""
    return bool(_PREPRINT_DOI.match(extract.clean_doi(doi)))


def _known(paper: dict) -> dict:
    known = paper.get("known_as") if isinstance(paper.get("known_as"), dict) else {}
    return {"dois": list(known.get("dois") or []), "titles": list(known.get("titles") or [])}


MATCH_LABELS = {
    "doi": "DOI 가 같음",
    "title": "제목이 같음",
    "version": "같은 논문의 프리프린트와 출판본",
    "twin": "제목·제1저자·연도가 같고 DOI 만 다름 (한 논문에 DOI 가 둘)",
    "similar": "제1저자·연도가 같고 제목이 거의 같음",
    "forced": "사용자가 같은 문헌으로 지정",
}


class PaperMatcher:
    """서지 정보로 '같은 문헌'을 찾는다.

    match: 같은 문헌이라고 볼 수 있는 것 (자동으로 잇는다).
      DOI 가 같다 → 제목이 같다 → 제1저자와 연도가 같고 제목이 거의 같다 (부제가 잘렸거나 표기가 조금 다른 참고문헌).
      DOI 가 서로 다르면 다른 문헌으로 보되, 긴 제목과 제1저자가 같고 한쪽만 프리프린트 DOI 이거나(같은 논문의 두 판)
      연도까지 같으면(한 논문에 DOI 가 둘 등록된 것) 같은 문헌으로 본다.
    candidates: 같은 문헌일 수 있지만 확신할 수 없는 것 (잇지 않고 사람에게 보인다).
    """

    def __init__(self, papers: dict[str, dict]):
        self.papers: dict[str, dict] = {}
        self.by_doi: dict[str, list[str]] = {}
        self.by_title: dict[str, list[str]] = {}
        self.by_author_year: dict[tuple[str, str], list[str]] = {}
        self.by_family: dict[str, list[str]] = {}
        self.by_head: dict[str, list[str]] = {}
        self._titles: dict[str, list[str]] = {}
        self._dois: dict[str, set[str]] = {}
        for paper in papers.values():
            self.add(paper)

    def add(self, paper: dict) -> None:
        pid = paper["id"]
        known = _known(paper)
        self.papers[pid] = paper
        self._dois[pid] = {d for d in map(_doi_key, [paper.get("doi"), *known["dois"]]) if d}
        for doi in self._dois[pid]:
            self.by_doi.setdefault(doi, []).append(pid)
        self._titles[pid] = list(dict.fromkeys(k for k in map(_title_key, [paper.get("title"), *known["titles"]]) if k))
        for key in self._titles[pid]:
            self.by_title.setdefault(key, []).append(pid)
            self.by_head.setdefault(key[:18], []).append(pid)
        family, year = _family_key(paper), _year_key(paper)
        if family:
            self.by_family.setdefault(family, []).append(pid)
        if family and year:
            self.by_author_year.setdefault((family, year), []).append(pid)

    def _conflict(self, doi: str, pid: str) -> bool:
        """양쪽에 DOI 가 있는데 서로 다르다."""
        return bool(doi and self._dois[pid] and doi not in self._dois[pid])

    def _authors_agree(self, family: str, pid: str) -> bool:
        return biblio.same_family(family, _family_key(self.papers[pid]))

    def match(self, meta: dict, exclude: tuple[str, ...] = ()) -> tuple[str | None, str]:
        """같은 문헌의 id 와 그렇게 본 근거 (MATCH_LABELS 의 열쇠). 없으면 (None, "")."""
        doi = _doi_key(meta.get("doi"))
        for pid in self.by_doi.get(doi, []) if doi else []:
            if pid not in exclude:
                return pid, "doi"
        key = _title_key(meta.get("title"))
        if not key:
            return None, ""
        family, year = _family_key(meta), _year_key(meta)
        for pid in self.by_title.get(key, []):
            if pid in exclude:
                continue
            if self._conflict(doi, pid):
                # DOI 가 다르면 보통 다른 문헌이다. 다만 제목과 저자가 같고 한쪽만 프리프린트면 같은 논문의 두 판이다.
                main = _doi_key(self.papers[pid].get("doi")) or next(iter(self._dois[pid]))
                other_family = _family_key(self.papers[pid])
                if len(key) >= 30 and family and other_family and biblio.same_family(family, other_family):
                    if is_preprint_doi(doi) != is_preprint_doi(main):
                        return pid, "version"
                    if year and year == _year_key(self.papers[pid]):
                        return pid, "twin"
                continue
            # 짧고 흔한 제목('Editorial' 등)은 저자까지 같아야 같은 문헌으로 본다
            if len(key) >= 20 or self._authors_agree(family, pid):
                return pid, "title"
        if family and year:
            for pid in self.by_author_year.get((family, year), []):
                if pid in exclude or self._conflict(doi, pid):
                    continue
                for other in self._titles[pid]:
                    if biblio.title_overlap(key, other) or difflib.SequenceMatcher(None, key, other).ratio() >= 0.93:
                        return pid, "similar"
        return None, ""

    def find(self, meta: dict, exclude: tuple[str, ...] = ()) -> str | None:
        return self.match(meta, exclude)[0]

    def candidates(self, meta: dict, exclude: tuple[str, ...] = ()) -> list[tuple[str, str]]:
        """같은 문헌일 수 있지만 자동으로 잇기에는 확신이 부족한 것: [(id, 이유)]."""
        key = _title_key(meta.get("title"))
        if not key:
            return []
        doi, family, year = _doi_key(meta.get("doi")), _family_key(meta), _year_key(meta)
        out: dict[str, str] = {}
        for pid in self.by_title.get(key, []):
            if pid not in exclude:
                out[pid] = "제목이 같고 DOI 가 다름 (다른 판·재수록·정정본일 수 있음)" if self._conflict(doi, pid) else "제목이 같지만 짧은 제목이고 제1저자가 다름"
        pool = dict.fromkeys(self.by_family.get(family, []) + self.by_head.get(key[:18], []))
        for pid in pool:
            if pid in exclude or pid in out:
                continue
            other_year = _year_key(self.papers[pid])
            near = not year or not other_year or abs(int(year) - int(other_year)) <= 1
            same_family = bool(family) and _family_key(self.papers[pid]) == family
            best, prefix = 0.0, False
            for other in self._titles[pid]:
                prefix = prefix or biblio.title_overlap(key, other)
                matcher = difflib.SequenceMatcher(None, key, other)
                if matcher.quick_ratio() >= 0.8:
                    best = max(best, matcher.ratio())
            if prefix and (near or same_family):
                out[pid] = "한쪽 제목에 말이 더 붙어 있음 (부제나 분류어가 빠진 표기일 수 있음)"
            elif same_family and near and best >= 0.8:
                out[pid] = "제1저자가 같고 연도가 가깝고 제목이 비슷함"
            elif best >= 0.9:
                out[pid] = "제목이 거의 같음"
        return list(out.items())


def _remember(paper: dict, ref: dict) -> bool:
    """같은 문헌의 다른 표기(다른 DOI·다른 제목)를 적어 둔다. 다음에 그 표기로 인용되면 바로 같은 문헌으로 이어진다.

    프리프린트로만 알던 문헌에 출판본의 DOI 가 오면 출판본을 대표로 삼고 프리프린트 DOI 는 다른 표기로 남긴다.
    """
    known, changed = _known(paper), False
    mine, theirs = extract.clean_doi(paper.get("doi")), extract.clean_doi(ref.get("doi"))
    if mine and theirs and _doi_key(theirs) != _doi_key(mine) and _doi_key(theirs) not in map(_doi_key, known["dois"]):
        if is_preprint_doi(mine) and not is_preprint_doi(theirs) and not render.is_read(paper):
            known["dois"].append(mine)
            paper["doi"] = theirs
            for field in ("venue", "year"):
                if ref.get(field):
                    paper[field] = ref[field]
        else:
            known["dois"].append(theirs)
        changed = True
    title = _title_key(ref.get("title"))
    if title and title != _title_key(paper.get("title")) and title not in map(_title_key, known["titles"]) and len(known["titles"]) < 8:
        known["titles"].append(str(ref["title"]))
        changed = True
    if changed:
        paper["known_as"] = known
    return changed


def _target(vault: Vault, draft: dict, papers: dict, matcher: PaperMatcher) -> dict | None:
    """이 검토안이 등록되면 내용이 바뀌는 기존 문서: 다시 분석하는 논문이거나, 인용 문헌으로만 위키에 있던 논문."""
    if draft.get("paper_id") and draft["paper_id"] in papers:
        return papers[draft["paper_id"]]
    meta = draft.get("paper") or {}
    same_file = vault.paper_by_sha((meta.get("pdf") or {}).get("sha256") or "") or vault.paper_by_zotero(meta.get("zotero_key") or "")
    if same_file:
        return papers.get(same_file["id"])
    pid, how = matcher.match(meta)
    # 이미 읽은 논문의 내용을 통째로 바꾸는 일이므로, DOI 가 다른데 같은 논문으로 '추정'한 것만으로는 바꾸지 않는다
    # (인용 문헌으로만 있던 문헌은 읽은 논문으로 올려도 잃는 것이 없다). 둘은 따로 등록되고 duplicates 에 나온다.
    if pid and how in ("version", "twin") and render.is_read(papers[pid]):
        return None
    return papers.get(pid) if pid else None


def _plan(vault: Vault, draft: dict, claims: list[dict] | None = None) -> dict:
    """검토안을 등록하면 무엇이 생기는지 계산한다 (검토 요약과 등록이 같은 계산을 쓴다).

    - target: 내용이 바뀔 기존 문서 (없으면 새 논문), paper_id: 등록될 인용 키
    - resolved: 참고문헌 번호 → {"id", "status": existing | new | self, "paper"}
    """
    papers = vault.papers()
    matcher = PaperMatcher(papers)
    meta = draft.get("paper") or {}
    target = _target(vault, draft, papers, matcher)
    taken = set(papers)
    paper_id = target["id"] if target else make_citekey(meta, taken)
    taken.add(paper_id)
    if not target:
        matcher.add({"id": paper_id, **{k: meta.get(k) for k in REF_FIELDS}})
    claims = clean_claims(draft.get("claims")) if claims is None else claims
    included = [c for c in claims if c["include"]]
    refs = {r["ref"]: r for r in clean_references(draft.get("references"))}
    used = list(dict.fromkeys(label for c in included for label in c["refs"] if label in refs))
    resolved: dict[str, dict] = {}
    for label in used:
        ref = refs[label]
        # 사용자가 정해 준 것이 먼저다: paper_id(이 문헌과 같다) · separate(위키의 비슷한 문헌과 다른 문헌이다)
        if ref.get("paper_id") in papers:
            pid, how = ref["paper_id"], "forced"
        elif ref.get("separate"):
            pid, how = None, ""
        else:
            pid, how = matcher.match(ref)
        if pid == paper_id:  # 참고문헌 목록에 이 논문 자신이 있는 경우
            resolved[label] = {"id": pid, "status": "self", "paper": None}
        elif pid:
            resolved[label] = {"id": pid, "status": "existing" if pid in papers else "new", "paper": matcher.papers[pid], "how": how}
        else:
            near = [(c, why) for c, why in matcher.candidates(ref) if c in papers and c != paper_id]
            hit = matcher.find(ref) if ref.get("separate") else None
            apart = ([hit] if hit in papers else []) + [c for c, _ in near]
            pid = make_citekey(ref, taken)
            taken.add(pid)
            new = {"id": pid, "kind": "cited", **{k: copy.deepcopy(ref.get(k)) for k in REF_FIELDS}}
            if ref.get("separate") and apart:
                new["apart"] = apart  # 다른 문헌이라고 확인한 것은 다시 묻지 않는다
            matcher.add(new)  # 같은 검토안 안에 같은 문헌이 두 번 적혀 있으면 하나로 모인다
            resolved[label] = {"id": pid, "status": "new", "paper": new, "maybe": [] if ref.get("separate") else near}
    return {
        "papers": papers,
        "target": target,
        "paper_id": paper_id,
        "claims": claims,
        "included": included,
        "refs": refs,
        "resolved": resolved,
        "unused": [refs[label] for label in refs if label not in used],
    }


def annotate_draft(vault: Vault, draft: dict) -> dict:
    """화면 표시용: 키워드가 기존 것인지 새것인지, 참고문헌이 위키의 어느 문헌에 연결되는지 표시한다."""
    onto = vault.ontology()
    plan = _plan(vault, draft)
    stats = render.paper_stats(plan["papers"], onto)
    groups = render.claim_groups(plan["papers"])
    out = copy.deepcopy(draft)
    out["claims"] = plan["claims"]
    for claim in out["claims"]:
        for kw in claim.get("keywords", []):
            leaf = onto.find(kw["path"][-1]) if kw.get("path") else None
            if leaf:
                kw["status"] = "existing"
                kw["id"] = leaf["id"]
                kw["path"] = onto.path_names(leaf["id"])
            else:
                kw["status"] = "new"
                kw["new_parts"] = [onto.find(p) is None for p in kw["path"]]
        members = [(src, c) for src, c in groups.get(claim["group"], []) if src["id"] != plan["paper_id"]] if claim["group"] else []
        claim["same"] = {"statement": render.one_line(members[0][1].get("statement")), "sources": [render.cite_short(src) for src, _ in members]} if members else None
    references = []
    for label, ref in plan["refs"].items():
        hit = plan["resolved"].get(label)
        paper = (hit or {}).get("paper") or ref
        references.append(
            {
                **ref,
                "cite": render.cite_short(paper),
                "status": hit["status"] if hit else "unused",
                "id": hit["id"] if hit else None,
                "known": stats.get(hit["id"]) if hit and hit["status"] == "existing" else None,
                "read": bool(hit and hit["status"] == "existing" and render.is_read(hit["paper"])),
                "match": (hit or {}).get("how", ""),
                "linked_title": hit["paper"].get("title", "") if hit and hit["status"] == "existing" else "",
                "maybe": [
                    {"id": c, "cite": render.cite_short(plan["papers"][c]), "title": plan["papers"][c].get("title", ""), "doi": plan["papers"][c].get("doi") or "", "why": why}
                    for c, why in (hit or {}).get("maybe", [])
                ],
            }
        )
    out["references"] = references
    out["citekey"] = plan["paper_id"]
    out["replaces"] = plan["target"]["id"] if plan["target"] else None
    out["replaces_kind"] = ("read" if render.is_read(plan["target"]) else "cited") if plan["target"] else None
    return out


def _search_dois(refs: list[dict], search, cache: dict | None = None, budget: float = 75) -> tuple[int, int]:
    """DOI 가 없는 참고문헌의 DOI 를 찾아 채운다. (찾은 수, 아직 찾아보지 못한 수)를 돌려준다.

    한 편에 1~2초가 걸리므로(Crossref 의 한도) 시간 한도(budget 초) 안에서만 찾는다. 찾아본 결과는 cache 에 남겨,
    다시 실행하면 이어서 찾는다. 연결이 안 되면 거기서 멈춘다 — DOI 가 없어도 등록은 할 수 있다.
    """
    cache = {} if cache is None else cache
    started, found, left = time.monotonic(), 0, 0
    for i, ref in enumerate(refs):
        key = "|".join((_title_key(ref.get("title")), _family_key(ref), _year_key(ref)))
        if key not in cache:
            if time.monotonic() - started > budget:
                left += 1
                continue
            try:
                cache[key] = extract.clean_doi(search(ref))
            except Exception:
                left += len(refs) - i
                break
        if cache[key]:
            ref["doi"] = cache[key]
            found += 1
    return found, left


def propose(vault: Vault, draft_id: str, text: str | None = None, zotero=None, lookup=None, search=None) -> dict:
    """Claude Code 가 논문을 읽고 써 준 제안을 검토안으로 저장한다. 위키에는 아직 아무것도 들어가지 않는다.

    zotero 를 넘기면 같은 논문이 Zotero 에 있는지 찾아, 있으면 그 서지 정보와 인용 키를 쓴다.
    lookup(DOI → 등록된 서지 정보, biblio.lookup)을 넘기면 논문의 서지 정보를 DOI 등록 기록으로 확인하고,
    출판사가 등록한 참고문헌 목록에서 인용 문헌의 DOI 를 찾아 붙인다.
    search(참고문헌 → DOI, biblio.find_doi)를 넘기면 그래도 DOI 가 없는 참고문헌을 제목·저자·연도로 찾아 붙인다.
    DOI 는 서로 다른 논문이 다른 표기로 인용한 같은 문헌을 하나로 잇는 기준이다.
    """
    job = library.load_job(draft_id)
    if text is None:
        data = extract.parse_proposal(library.proposal_text(draft_id), library.proposal_more(draft_id))
    else:
        data = extract.parse_proposal(text)
    with vault.lock:
        vault.check_readable()
        if not (vault.root / job["pdf"]).is_file():
            raise WikiError(f"논문 폴더에서 PDF 를 찾을 수 없습니다: {job['pdf']}. 파일을 옮겼다면 prepare 를 다시 실행해 주세요.")
        meta = {**data["paper"], "et_al": False, "zotero_key": None, "attachment_key": None, "zotero_pdf": "", "url": "", "abstract": "", "item_type": "", "biblio": None, "citekey_hint": ""}
        linked = job.get("zotero")
        state = "linked" if linked else "off"
        if not linked and zotero is not None:
            try:
                linked = zotero.find(doi=meta["doi"], title=meta["title"])
                state = "linked" if linked else "not_found"
            except Exception:  # Zotero 가 꺼져 있어도 등록은 할 수 있다
                state = "unreachable"
        if linked:
            for key in ("title", "authors", "year", "venue", "doi", "url", "abstract", "item_type", "citekey_hint"):
                if linked.get(key):
                    meta[key] = linked[key]
            meta["zotero_key"], meta["attachment_key"] = linked.get("zotero_key"), linked.get("attachment_key")
        bib, bib_title, ref_dois = ("zotero" if linked else "pdf"), "", 0
        if lookup is not None and meta["doi"]:
            try:
                found = lookup(meta["doi"])
            except Exception:  # 확인하지 못해도 등록은 할 수 있다
                found = {"status": "unreachable"}
            if found.get("status") != "ok":
                bib = bib if linked else ("doi_not_found" if found.get("status") == "not_found" else "doi_unreachable")
            elif not biblio.same_title(found["title"], meta["title"]):
                bib, bib_title = (bib if linked else "doi_mismatch"), found["title"]
            else:
                if not linked:  # Zotero 에 있는 논문은 Zotero 의 서지 정보가 기준이다
                    for key in ("title", "authors", "year", "venue", "doi", "url", "abstract", "item_type", "biblio"):
                        if found.get(key):
                            meta[key] = found[key]
                    bib = "doi"
                for ref in data["references"]:
                    if not ref.get("doi"):
                        ref["doi"] = extract.clean_doi(biblio.reference_doi(ref, found.get("references") or []))
                        ref_dois += bool(ref["doi"])
        ref_searched = ref_failed = 0
        if search is not None:
            todo = [r for r in data["references"] if not r.get("doi") and len(_title_key(r.get("title"))) >= 20]
            memo = library.work_dir(draft_id) / "doi_search.json"  # 다시 실행하면 이어서 찾도록
            try:
                cache = json.loads(memo.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                cache = {}
            ref_searched, ref_failed = _search_dois(todo, search, cache)
            try:
                memo.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            except OSError:
                pass
        meta["pdf"] = {k: job.get(v) for k, v in (("path", "pdf"), ("sha256", "sha256"), ("size", "size"), ("pages", "pages"), ("original_name", "original_name"))}
        earlier = vault.pending(draft_id)
        draft = new_draft(draft_id, meta)
        if earlier:
            draft["created"] = earlier.get("created", draft["created"])
        draft.update(
            paper_id=job.get("paper_id"),
            summary=data["summary"],
            references=data["references"],
            claims=clean_claims(data["claims"]),
            note=data["note"],
            extraction={"engine": "claude_code", "source": "pdf", "pages": job.get("pages"), "at": now_iso(), "zotero": state, "bib": bib, "bib_title": bib_title, "ref_dois": ref_dois, "ref_searched": ref_searched, "ref_search_failed": ref_failed, "claim_files": data.get("claim_files") or [], "host": platform.node()},
        )
        vault.save_pending(draft_id, draft)
    return review(vault, draft_id)


def review(vault: Vault, draft_id: str) -> dict:
    """검토안을 사람이 확인하기 좋게 정리한다: 무엇이 등록되고, 무엇이 새로 만들어지고, 무엇을 확인해야 하는지."""
    draft = vault.pending(draft_id)
    if not draft:
        raise WikiError("검토안을 찾을 수 없습니다. 이미 등록되었거나 폐기되었을 수 있습니다.")
    onto = vault.ontology()
    annotated = annotate_draft(vault, draft)
    meta = draft.get("paper") or {}
    paper_id = annotated["citekey"]
    by_label = {r["ref"]: r for r in annotated["references"]}
    warnings: list[str] = []
    new_keywords, seen = [], set()
    included = [c for c in annotated["claims"] if c["include"]]
    for claim in included:
        claim["cites"] = [by_label[label] for label in claim["refs"] if label in by_label and by_label[label]["status"] != "self"]
        for kw in claim["keywords"]:
            if kw.get("status") != "new":
                continue
            for idx, (name, is_new) in enumerate(zip(kw["path"], kw["new_parts"])):
                if not is_new or norm(name) in seen:
                    continue
                seen.add(norm(name))
                new_keywords.append({"name": name, "under": kw["path"][:idx]})
                if idx == 0:
                    roots = ", ".join(r["name"] for r in onto.roots())
                    warnings.append(f"'{name}' 이(가) 새 최상위 분류로 만들어집니다. 기존 분류({roots}) 아래에 두려던 것이 아닌지 확인해 주세요.")
    if annotated["replaces"] and not draft.get("paper_id"):
        if annotated["replaces_kind"] == "cited":
            warnings.append(f"이 논문은 다른 논문의 참고문헌으로 이미 위키에 있습니다 (@{annotated['replaces']}). 등록하면 그 문서가 '읽은 논문'으로 바뀌고, 지금까지 인용된 기록은 그대로 이어집니다.")
        else:
            warnings.append(f"같은 논문이 이미 위키에 읽은 논문으로 등록되어 있습니다 (@{annotated['replaces']}). 등록하면 그 문서의 주장이 이 검토안의 내용으로 바뀝니다.")
    for field, label in (("authors", "저자"), ("year", "출판 연도")):
        if not meta.get(field):
            warnings.append(f"{label} 정보가 비어 있습니다.")
    ext = draft.get("extraction") or {}
    bib = ext.get("bib") or ("zotero" if meta.get("zotero_key") else "pdf")
    if bib == "doi_not_found":
        warnings.append(f"DOI {meta.get('doi')} 는 doi.org 에 등록되어 있지 않습니다. PDF 에서 DOI 를 잘못 읽었을 수 있으니 확인해 주세요.")
    elif bib == "doi_mismatch":
        warnings.append(f"DOI {meta.get('doi')} 에 등록된 논문은 제목이 다릅니다: “{ext.get('bib_title', '')}”. DOI 나 제목을 확인해 주세요.")
    empty = sum(1 for c in included if not c["cites"])
    if empty:
        warnings.append(f"인용 문헌이 없는 주장이 {empty}개 있습니다. 이 주장은 등록되지 않습니다.")
    used = [r for r in annotated["references"] if r["status"] in ("existing", "new")]
    maybe = [r for r in used if r.get("maybe")]
    if maybe:
        warnings.append(f"위키에 이미 있는 문헌과 같은 문헌일 수 있는 참고문헌이 {len(maybe)}편 있습니다 ('같은 문헌일 수 있는 것' 목록). 같은 문헌이면 이어야 여러 논문이 인용한 문헌으로 잡힙니다.")
    if ext_failed := (draft.get("extraction") or {}).get("ref_search_failed"):
        warnings.append(f"참고문헌 {ext_failed}편은 아직 DOI 를 찾아보지 못했습니다 (한 편에 1~2초가 걸려 시간 한도에 걸렸거나 Crossref 에 연결하지 못함). 'paperwiki propose {draft_id}' 를 다시 실행하면 이어서 찾습니다. 그대로 등록해도 제목·저자·연도로 같은 문헌을 잇습니다.")
    weak = [r["ref"] for r in used if not r["authors"] or not r["year"]]
    if weak:
        warnings.append("저자나 연도가 비어 있는 참고문헌: " + ", ".join(weak[:30]) + (" …" if len(weak) > 30 else ""))
    pdf = meta.get("pdf") or {}
    preview = {**meta, "id": paper_id}
    return {
        "id": draft_id,
        "citekey": paper_id,
        "replaces": annotated["replaces"],
        "replaces_kind": annotated["replaces_kind"],
        "paper": {
            "title": meta.get("title", ""),
            "authors": "; ".join(render.author_name(a, full=True) for a in meta.get("authors") or []),
            "year": meta.get("year", ""),
            "venue": meta.get("venue", ""),
            "doi": meta.get("doi", ""),
            "cite": render.cite_short(preview),
        },
        "zotero": {"key": meta.get("zotero_key"), "state": ext.get("zotero", "linked" if meta.get("zotero_key") else "off")},
        "zotero_add": bool(config.load().get("zotero_add")),
        "bib": {"source": bib, "more": meta.get("biblio") or {}, "ref_dois": ext.get("ref_dois", 0), "ref_searched": ext.get("ref_searched", 0)},
        "maybe": maybe,
        "pdf": {"current": pdf.get("path"), "will_be": library.pdf_filename(preview, library.name_pattern(vault)) if pdf.get("path") else None, "pages": pdf.get("pages")},
        "summary": draft.get("summary", ""),
        "claims": annotated["claims"],
        "references": {
            "new": [r for r in used if r["status"] == "new"],
            "existing": [r for r in used if r["status"] == "existing"],
            "unused": [r for r in annotated["references"] if r["status"] == "unused"],
        },
        "new_keywords": new_keywords,
        "warnings": warnings,
        "note": draft.get("note", ""),
        # 프로그램이 검토안에서 직접 센 것. 읽은 쪽(에이전트)이 메모에 적은 숫자는 쓰지 않는다
        "counts": {
            "references": sum(1 for r in annotated["references"] if r["status"] != "self"),
            "references_used": len(used),
            "claims": len(annotated["claims"]),
            "claims_included": len(included),
            "claim_files": [int(n) for n in ext.get("claim_files") or []],
            "same": sum(1 for c in included if c.get("same")),
        },
    }


def counts_text(info: dict) -> str:
    """검토안의 개수를 한 줄로 — 프로그램이 직접 센 것이다 (읽은 쪽의 메모에 적힌 숫자와 다르면 이쪽이 맞다)."""
    c = info.get("counts") or {}
    if not c:
        return ""
    refs, used = c["references"], c["references_used"]
    parts = [f"참고문헌 목록 {refs}편 — " + ("모두 주장에 연결됨" if used == refs else f"{used}편이 주장에 연결됨, {refs - used}편은 연결되지 않음")]
    files = c.get("claim_files") or []
    per_file = f" (파일 {len(files)}개에 {' · '.join(str(n) for n in files)})" if len(files) > 1 and sum(files) == c["claims"] else ""
    parts.append(f"주장 {c['claims']}개{per_file}" + (f", 그중 {c['claims_included']}개가 등록 대상" if c["claims_included"] != c["claims"] else ""))
    if c.get("same"):
        parts.append(f"기존 위키의 주장과 같은 주장으로 묶인 것 {c['same']}개")
    return "프로그램이 직접 센 것 (아래 메모의 숫자와 다르면 이쪽이 맞습니다): " + " · ".join(parts)


def review_status(info: dict) -> dict:
    """검토안의 서지 정보가 어디서 왔는지, Zotero 에는 어떻게 되는지를 한 줄씩으로."""
    zotero, doi = info["zotero"], info["paper"].get("doi")
    adds = info.get("zotero_add", True)
    zstate = {
        "linked": "이미 Zotero 에 있는 논문 — 그 항목과 연결합니다 (서지 정보와 인용 키는 Zotero 의 것)",
        "not_found": "Zotero 에 없는 논문 — 등록하면 Zotero 에 새 항목으로 넣습니다" if adds else "Zotero 에 없는 논문 (Zotero 에 넣기는 꺼져 있습니다)",
        "unreachable": "Zotero 가 꺼져 있어 확인하지 못함"
        + (" — 등록 전에 Zotero 를 켜 주세요 (꺼진 채 등록하면 위키에만 들어가고, 나중에 'paperwiki zotero sync' 로 Zotero 에 넣습니다)" if adds else ""),
        "off": "확인하지 않음",
    }.get(zotero["state"], zotero["state"])
    bib = info.get("bib") or {"source": "pdf", "more": {}, "ref_dois": 0}
    more = bib.get("more") or {}
    detail = " · ".join(f"{label} {more[key]}" for key, label in (("volume", "권"), ("issue", "호"), ("pages", "쪽")) if more.get(key))
    bstate = {
        "zotero": "Zotero 항목의 것",
        "doi": "DOI 등록 기록으로 확인 (doi.org)" + (f" — {detail}" if detail else ""),
        "pdf": "PDF 에서 읽은 것 (DOI 가 없어 등록 기록으로 확인하지 못함)" if not doi else "PDF 에서 읽은 것 (DOI 등록 기록으로 확인하지 않음)",
        "doi_unreachable": "PDF 에서 읽은 것 (doi.org 에 연결하지 못해 확인하지 못함)",
        "doi_not_found": "PDF 에서 읽은 것 — 이 DOI 가 등록되어 있지 않아 확인하지 못함",
        "doi_mismatch": "PDF 에서 읽은 것 — 이 DOI 에 등록된 논문과 제목이 달라 등록 기록을 쓰지 않음",
    }.get(bib["source"], bib["source"])
    return {"bib": bstate, "zotero": zstate, "verified": bib["source"] in ("doi", "zotero"), "ref_dois": bib.get("ref_dois", 0), "ref_searched": bib.get("ref_searched", 0)}


def review_text(info: dict, url: str = "", compact: bool = False) -> str:
    """검토 요약을 글로 (명령줄 출력 · Claude Code 가 사용자에게 보여 주는 용도).

    compact 면 주장마다 한 줄(문장 · 인용 문헌 · 위치 · 키워드)로 줄인다. 인용문과 참고문헌의 제목 목록은 빠지므로,
    그것은 전체 출력이나 웹 검토 화면에서 대조한다. 주장이 수십 개인 논문을 대화에서 훑어볼 때 쓴다.
    """
    labels = render.LABELS["ko"]["types"]
    paper, pdf, zotero, refs = info["paper"], info["pdf"], info["zotero"], info["references"]
    status = review_status(info)
    bstate, zstate, bib = status["bib"], status["zotero"], status
    if info["replaces"] and info["replaces_kind"] == "cited":
        head = "인용 문헌으로만 있던 @%s 을(를) 읽은 논문으로 등록하는 검토안" % info["replaces"]
    elif info["replaces"]:
        head = "이미 등록된 @%s 의 내용을 바꾸는 검토안" % info["replaces"]
    else:
        head = "아직 위키에 등록되지 않았습니다"
    lines = [f"## 검토안 {info['id']} — {head}", ""]
    lines.append(f"- 제목: {paper['title']}")
    lines.append("- 저자: " + (paper["authors"] or "(없음)") + f" · 연도: {paper['year'] or '(없음)'}" + (f" · 게재: {paper['venue']}" if paper["venue"] else ""))
    if paper["doi"]:
        lines.append(f"- DOI: {paper['doi']}")
    lines.append(f"- 서지 정보: {bstate}")
    lines.append(f"- 인용 키: @{info['citekey']}")
    lines.append(f"- Zotero: {zstate}")
    if pdf["current"]:
        current = pdf["current"].rsplit("/", 1)[-1]
        lines.append(f"- PDF: {current}" + (f" → 등록하면 이름이 `{pdf['will_be']}` 로 바뀝니다" if pdf["will_be"] != current else " (이름 규칙에 이미 맞음)"))
    if info["summary"]:
        lines += ["", f"요약: {info['summary']}"]

    included = [c for c in info["claims"] if c["include"]]
    n_refs = len(refs["new"]) + len(refs["existing"])
    lines += ["", f"### 등록되는 것: 주장 {len(included)}개 · 인용 문헌 {n_refs}편 (새 문헌 {len(refs['new'])} · 이미 위키에 있는 문헌 {len(refs['existing'])})"]
    lines.append("주장은 이 논문이 문헌을 인용하며 한 말입니다. 읽은 것은 이 논문이며, 인용된 문헌의 원문은 확인하지 않았습니다.")
    with_doi = sum(1 for r in refs["new"] + refs["existing"] if r.get("doi"))
    if n_refs:
        via = [f"{bib['ref_dois']}편은 출판사가 등록한 참고문헌 목록에서" if bib.get("ref_dois") else "", f"{bib['ref_searched']}편은 Crossref 검색으로" if bib.get("ref_searched") else ""]
        via = ", ".join(v for v in via if v)
        lines.append(f"인용 문헌 {n_refs}편 중 {with_doi}편은 DOI 가 있습니다" + (f" ({via} 찾음)." if via else ".") + " DOI 는 다른 논문이 다른 표기로 인용한 같은 문헌을 잇는 기준입니다.")
        if with_doi < n_refs:
            lines.append("DOI 가 없는 문헌은 제목·제1저자·연도로 잇습니다: " + ", ".join(f"[{r['ref']}] {r['cite']}" for r in refs["new"] + refs["existing"] if not r.get("doi"))[:600])
    if refs["existing"]:
        lines += ["", "이미 위키에 있어 이번에 인용 기록이 더해지는 문헌:"]
        for r in refs["existing"]:
            known = r.get("known") or {}
            seen = f"지금까지 논문 {known.get('sources', 0)}편이 주장 {known.get('claims', 0)}개에 인용" if known else ("읽은 논문" if r.get("read") else "아직 인용 기록 없음")
            lines.append(f"- [{r['ref']}] {r['cite']} {r['title']} (@{r['id']}) — {seen}")
            if r.get("match") in ("version", "twin", "similar", "forced"):  # 표기가 다른데 같은 문헌으로 이은 것은 근거를 보인다
                lines.append(f"  같은 문헌으로 본 근거: {MATCH_LABELS[r['match']]} — 위키에는 “{r.get('linked_title', '')}” 로 있음")
    if info.get("maybe"):
        lines += ["", f"### 같은 문헌일 수 있는 것 {len(info['maybe'])}편 — 확인해 주세요 (지금은 서로 다른 문헌으로 등록됩니다)"]
        for r in info["maybe"]:
            lines.append(f"- [{r['ref']}] {r['cite']} {r['title']}" + (f" doi:{r['doi']}" if r.get("doi") else ""))
            for m in r["maybe"]:
                lines.append(f"  ↔ @{m['id']} {m['cite']} {m['title']}" + (f" doi:{m['doi']}" if m.get("doi") else "") + f" — {m['why']}")

    lines += ["", f"### 주장 {len(included)}개" + (" (인용문은 줄였습니다 — 전체 출력이나 웹 검토 화면에서 원문과 대조하세요)" if compact else "")]
    for i, claim in enumerate(included, 1):
        if compact:
            cites = "; ".join(f"[{r['ref']}] {r['cite']}" + ("" if r["status"] == "new" else " (위키에 있음)") for r in claim.get("cites", [])) or "(인용 문헌 없음 — 등록되지 않습니다)"
            where = (claim.get("evidence") or {}).get("location") or "위치 없음"
            kws = " / ".join(kw["path"][-1] + ("*" if kw.get("status") == "new" else "") for kw in claim["keywords"]) or "(키워드 없음)"
            same = f" · 같은 주장: {', '.join(claim['same']['sources'])}" if claim.get("same") else ""
            lines.append(f"{i}. [{labels.get(claim['type'], claim['type'])}] {claim['statement']} — {cites} · {where} · {kws}{same}")
            continue
        lines.append(f"{i}. [{labels.get(claim['type'], claim['type'])}] {claim['statement']}")
        cites = "; ".join(f"[{r['ref']}] {r['cite']}" + ("" if r["status"] == "new" else " (위키에 있음)") for r in claim.get("cites", []))
        lines.append("   - 인용 문헌: " + (cites or "(없음 — 등록되지 않습니다)"))
        ev = claim.get("evidence") or {}
        if ev.get("quote") or ev.get("location"):
            lines.append("   - 근거: " + (f"“{ev['quote']}” " if ev.get("quote") else "") + (f"({ev['location']})" if ev.get("location") else ""))
        kws = [" › ".join(kw["path"]) + (" (새 키워드)" if kw.get("status") == "new" else "") for kw in claim["keywords"]]
        lines.append("   - 키워드: " + (" / ".join(kws) or "(없음)"))
        if claim.get("same"):
            lines.append(f"   - 같은 주장으로 묶임: “{claim['same']['statement']}” — {', '.join(claim['same']['sources'])}")

    if compact:
        lines += ["", "키워드 끝의 * 는 새로 만들어질 키워드입니다."]
    else:
        lines += ["", f"### 인용 문헌 {n_refs}편 (참고문헌 번호순)"]
    for r in [] if compact else sorted(refs["new"] + refs["existing"], key=lambda r: (not r["ref"].isdigit(), int(r["ref"]) if r["ref"].isdigit() else 0, r["ref"])):
        n = sum(1 for c in included if r["ref"] in c["refs"])
        venue = f" {r['venue']}." if r.get("venue") else ""
        doi = f" doi:{r['doi']}" if r.get("doi") else ""
        lines.append(f"- [{r['ref']}] {r['cite']}. {r['title']}.{venue}{doi} → @{r['id']}" + ("" if r["status"] == "new" else " (위키에 있음)") + f" · 주장 {n}개")

    if info["new_keywords"]:
        lines += ["", f"### 새로 만들어질 키워드 {len(info['new_keywords'])}개"]
        lines += [f"- {k['name']}" + (f" — {' › '.join(k['under'])} 아래" if k["under"] else " — 최상위 분류") for k in info["new_keywords"]]
    else:
        lines += ["", "새로 만들어질 키워드는 없습니다 (모두 기존 키워드에 정리됩니다)."]
    notes = list(info["warnings"])
    if refs["unused"]:
        notes.append("어느 주장에도 연결되지 않아 등록되지 않는 참고문헌: " + ", ".join(f"[{r['ref']}] {r['cite']}" for r in refs["unused"][:40]) + (" …" if len(refs["unused"]) > 40 else ""))
    if counts_text(info):
        notes.append(counts_text(info))
    if info["note"]:
        notes.append(f"읽은 쪽의 메모: {info['note']}")
    if notes:
        lines += ["", "### 확인할 점"] + [f"- {n}" for n in notes]
    if url:
        lines += ["", f"웹에서 고치며 검토: {url}"]
    return "\n".join(lines)


_HANGUL_OR_WORD = re.compile(r"[^\w\-]+", re.UNICODE)
_STOP = {"a", "an", "the", "of", "on", "in", "and", "for", "to", "with", "is", "are", "by", "from", "at"}


def _fold(text: str) -> str:
    """Žiga → Ziga. 발음 구별 기호를 떼어 인용 키와 저자 비교가 표기 차이에 흔들리지 않게 한다 (한글은 그대로)."""
    decomposed = unicodedata.normalize("NFKD", str(text or ""))
    return unicodedata.normalize("NFC", "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn"))


def make_citekey(meta: dict, taken: set[str]) -> str:
    """Zotero 인용 키가 있으면 그대로, 없으면 kim2023working 형태로 만든다."""
    hint = _HANGUL_OR_WORD.sub("", unicodedata.normalize("NFC", meta.get("citekey_hint") or ""))
    if hint:
        base = hint[:60]
    else:
        authors = meta.get("authors") or []
        first = authors[0] if authors else {}
        who = first.get("family") or first.get("name") or "anon"
        who = _HANGUL_OR_WORD.sub("", _fold(who).split(",")[0]).casefold() or "anon"
        year = re.sub(r"\D", "", str(meta.get("year") or ""))[:4]
        words = [w for w in _HANGUL_OR_WORD.split(_fold(meta.get("title") or "").casefold()) if w and w not in _STOP]
        base = f"{who}{year}{words[0] if words else ''}"[:60]
    key, n = base, 0
    lowered = {t.casefold() for t in taken}
    while key.casefold() in lowered:  # 같은 키가 있으면 a, b, c … 를 붙인다
        n += 1
        key = f"{base}{chr(96 + n)}" if n <= 26 else f"{base}{n}"
    return key


def _new_group(known: set[str]) -> str:
    gid = "g" + secrets.token_hex(4)
    while gid in known:
        gid = "g" + secrets.token_hex(4)
    known.add(gid)
    return gid


def _fill_blanks(paper: dict, ref: dict) -> bool:
    """이미 있는 문헌에 비어 있던 서지 정보만 채운다 (있는 값은 바꾸지 않는다)."""
    changed = False
    for key in ("doi", "venue", "year", "authors"):
        if not paper.get(key) and ref.get(key):
            paper[key] = copy.deepcopy(ref[key])
            if key == "authors":
                paper["et_al"] = bool(ref.get("et_al"))
            changed = True
    # 참고문헌 목록에서 부제가 잘려 있던 제목은, 더 길게 적힌 것이 나오면 그것으로 바꾼다
    old, new = _title_key(paper.get("title")), _title_key(ref.get("title"))
    if not render.is_read(paper) and old and len(new) > len(old) and new.startswith(old):
        known = _known(paper)
        if len(known["titles"]) < 8:  # 짧게 적혀 있던 표기도 같은 문헌의 다른 표기로 남긴다
            known["titles"].append(str(paper["title"]))
            paper["known_as"] = known
        paper["title"] = ref["title"]
        changed = True
    return changed


def _prune_orphans(vault: Vault) -> list[str]:
    """어느 주장에도 인용되지 않게 된 인용 문헌을 지운다 (읽은 논문은 지우지 않는다)."""
    papers = vault.papers()
    cited = {pid for p in papers.values() for c in p.get("claims", []) for pid in c.get("cites", [])}
    removed = [p["id"] for p in papers.values() if not render.is_read(p) and p["id"] not in cited]
    for pid in removed:
        vault.delete_paper(pid)
    return removed


def approve(vault: Vault, draft_id: str, body: dict | None = None) -> dict:
    """검토가 끝난 검토안을 위키에 반영한다. 여기서만 위키 데이터가 늘어난다.

    body 를 주면 그 내용(검토 화면에서 고친 것)으로, 없으면 저장되어 있는 검토안 그대로 등록한다.
    논문이 '읽은 논문'으로 등록되고, 주장에 인용된 참고문헌이 '인용 문헌'으로 등록되거나 기존 문헌에 연결된다.
    논문 폴더의 PDF 는 이때 이름 규칙에 맞게 바뀐다.
    """
    with vault.lock:
        vault.check_readable()
        pending = vault.pending(draft_id)
        if not pending:
            raise WikiError("검토안을 찾을 수 없습니다. 이미 승인되었거나 폐기되었을 수 있습니다.")
        if body is None:
            body = {"summary": pending.get("summary", ""), "claims": pending.get("claims", [])}
        plan = _plan(vault, pending, clean_claims(body.get("claims")))
        included, resolved, papers = plan["included"], plan["resolved"], plan["papers"]
        if not included:
            raise WikiError("위키에 저장할 주장이 없습니다. 주장을 하나 이상 선택해 주세요.")
        for i, claim in enumerate(included, 1):
            if not claim["statement"]:
                raise WikiError(f"선택한 {i}번째 주장의 문장이 비어 있습니다.")
            if not claim["keywords"]:
                raise WikiError(f"선택한 {i}번째 주장에 키워드가 없습니다. 키워드를 하나 이상 지정해 주세요.")
            if not any(label in resolved for label in claim["refs"]):
                raise WikiError(f"선택한 {i}번째 주장에 인용 문헌이 없습니다. 이 위키는 '주장 → 인용된 문헌'을 모으므로 문헌이 하나 이상 필요합니다.")

        onto = vault.ontology()
        known_groups = {c.get("group") for p in papers.values() for c in p.get("claims", []) if c.get("group")}
        created: list[str] = []
        final_claims = []
        try:
            for claim in included:
                cites = list(dict.fromkeys(resolved[label]["id"] for label in claim["refs"] if label in resolved and resolved[label]["status"] != "self"))
                if not cites:
                    continue  # 이 논문 자신만 인용한 문장
                ids = []
                for kw in claim["keywords"]:
                    kid, new_ids = onto.ensure_path(kw["path"], kw["aliases"], kw["description"])
                    created += new_ids
                    if kid not in ids:
                        ids.append(kid)
                final_claims.append(
                    {
                        "id": f"c{len(final_claims) + 1}",
                        "statement": claim["statement"],
                        "type": claim["type"],
                        "evidence": claim["evidence"],
                        "cites": cites,
                        "keywords": ids,
                        "group": claim["group"] if claim["group"] in known_groups else _new_group(known_groups),
                    }
                )
        except OntologyError as exc:
            raise WikiError(str(exc)) from exc
        if not final_claims:
            raise WikiError("위키에 저장할 주장이 없습니다. 인용 문헌이 있는 주장이 하나 이상 필요합니다.")

        meta = pending["paper"]
        previous = plan["target"]
        was_read = bool(previous) and render.is_read(previous)
        paper = {
            "id": plan["paper_id"],
            "kind": "read",
            **{k: copy.deepcopy(meta.get(k)) for k in PAPER_FIELDS},
            "summary": _text(body.get("summary", pending.get("summary", "")), 3000),
            "claims": final_claims,
            "added": previous.get("added") if was_read else now_iso(),
            "updated": now_iso(),
            "extraction": pending.get("extraction", {}),
        }
        if previous:  # 다시 분석할 때 Zotero 가 꺼져 있었다고 기존 연결이 사라지면 안 된다
            for key in ("zotero_key", "attachment_key", "zotero_pdf", "biblio"):
                paper[key] = paper[key] or previous.get(key)
        renamed_from, pdf_note = None, ""
        if (paper.get("pdf") or {}).get("path"):
            before = paper["pdf"]["path"]
            after, pdf_note = library.place_pdf(vault, paper)
            paper["pdf"]["path"] = after
            renamed_from = before if after != before else None

        # 인용 문헌: 새 문헌은 만들고, 이미 있는 문헌에는 비어 있던 서지 정보만 채운다
        used = {pid for c in final_claims for pid in c["cites"]}
        new_ids, linked_ids = [], []
        for label, hit in resolved.items():
            pid = hit["id"]
            if pid not in used or pid in new_ids or pid in linked_ids:
                continue
            if hit["status"] == "new":
                vault.save_paper({**hit["paper"], "url": "", "abstract": "", "item_type": "", "zotero_key": None, "attachment_key": None, "pdf": None, "summary": "", "claims": [], "added": now_iso(), "updated": now_iso()})
                new_ids.append(pid)
            else:
                linked_ids.append(pid)
                existing = copy.deepcopy(papers[pid])
                filled = _fill_blanks(existing, plan["refs"][label])
                if _remember(existing, plan["refs"][label]) or filled:
                    existing["updated"] = now_iso()
                    vault.save_paper(existing)
        vault.save_ontology(onto)
        vault.save_paper(paper)
        vault.delete_pending(draft_id)
        _prune_orphans(vault)  # 다시 분석해서 더는 인용되지 않게 된 문헌
        render.sync(vault)
        library.cleanup_work(draft_id)
        return {
            "paper": paper,
            "created_keywords": [onto.nodes[i]["name"] for i in created],
            "pdf": (paper.get("pdf") or {}).get("path"),
            "pdf_renamed_from": renamed_from,
            "pdf_note": pdf_note,
            "new_cited": new_ids,
            "linked_cited": linked_ids,
            "maybe_same": [{"new": hit["id"], "existing": c, "why": why} for hit in resolved.values() if hit["id"] in new_ids for c, why in hit.get("maybe", [])],
        }


def discard(vault: Vault, draft_id: str) -> None:
    """검토안을 버린다. 위키에는 아무것도 저장되지 않고, PDF 는 논문 폴더에 그대로 남는다."""
    vault.delete_pending(draft_id)
    library.cleanup_work(draft_id)


def delete_paper(vault: Vault, paper_id: str) -> dict:
    """읽은 논문과 그 주장을 위키에서 뺀다. PDF 파일은 논문 폴더에 그대로 둔다.

    다른 논문이 이 논문을 인용하고 있으면 문헌 기록은 남긴다 (읽은 논문 → 인용 문헌).
    이 논문만 인용하던 문헌은 함께 사라진다.
    """
    with vault.lock:
        vault.check_readable()
        paper = vault.paper(paper_id)
        if not paper:
            raise WikiError("논문을 찾을 수 없습니다.")
        cited_by = render.citations(vault.papers()).get(paper_id, [])
        kept = False
        if not render.is_read(paper):
            if cited_by:
                raise WikiError(f"이 문헌은 주장 {len(cited_by)}개에 인용되어 있어 따로 지울 수 없습니다. 인용한 논문의 주장에서 빼면 함께 사라집니다.")
            vault.delete_paper(paper_id)
        elif cited_by:
            kept = True
            vault.save_paper({**paper, "kind": "cited", "pdf": None, "summary": "", "claims": [], "updated": now_iso()})
        else:
            vault.delete_paper(paper_id)
        removed = _prune_orphans(vault)
        render.sync(vault)
        return {"kept_as_cited": kept, "removed_cited": removed}


def merge_papers(vault: Vault, src_id: str, dst_id: str) -> dict:
    """같은 문헌이 두 문서로 나뉘었을 때 src 를 dst 로 합친다: src 를 인용하던 주장이 모두 dst 를 인용하게 된다."""
    with vault.lock:
        vault.check_readable()
        papers = vault.papers()
        src, dst = papers.get(src_id), papers.get(dst_id)
        if not src or not dst:
            raise WikiError("문헌을 찾을 수 없습니다.")
        if src_id == dst_id:
            raise WikiError("같은 문헌으로는 합칠 수 없습니다.")
        if render.is_read(src) and render.is_read(dst):
            raise WikiError("둘 다 읽은 논문입니다. 한쪽을 위키에서 삭제한 뒤 다시 시도해 주세요.")
        if render.is_read(src):  # 읽은 논문 쪽을 남긴다
            src, dst, src_id, dst_id = dst, src, dst_id, src_id
        for paper in papers.values():
            if not any(src_id in c.get("cites", []) for c in paper.get("claims", [])):
                continue
            paper = copy.deepcopy(paper)
            for claim in paper["claims"]:
                claim["cites"] = list(dict.fromkeys(dst_id if pid == src_id else pid for pid in claim.get("cites", []) if not (pid == src_id and paper["id"] == dst_id)))
            paper["updated"] = now_iso()
            vault.save_paper(paper)
        merged = copy.deepcopy(vault.paper(dst_id))
        filled = _fill_blanks(merged, src)
        remembered = _remember(merged, src)
        for doi in _known(src)["dois"]:  # 없어지는 쪽이 알고 있던 다른 표기도 넘겨받는다
            remembered = _remember(merged, {"doi": doi}) or remembered
        for title in _known(src)["titles"]:
            remembered = _remember(merged, {"title": title}) or remembered
        if filled or remembered:
            merged["updated"] = now_iso()
            vault.save_paper(merged)
        vault.delete_paper(src_id)
        render.sync(vault)
        return {"kept": dst_id, "removed": src_id}


def duplicates(vault: Vault) -> list[dict]:
    """위키 안에서 같은 문헌이 두 문서로 갈렸을 수 있는 쌍을 찾는다.

    certain 이 참이면 자동으로 이었을 근거(같은 DOI·같은 제목 등)가 있는 쌍이고, 아니면 사람이 봐야 하는 쌍이다.
    '다른 문헌'이라고 확인해 둔 쌍(apart)은 빼고, 인용이 많이 걸린 쌍부터 돌려준다.
    """
    papers, onto = vault.papers(), vault.ontology()
    matcher = PaperMatcher(papers)
    stats = render.paper_stats(papers, onto)
    pairs: dict[tuple[str, str], dict] = {}
    for paper in papers.values():
        pid = paper["id"]
        hit, how = matcher.match(paper, exclude=(pid,))
        found = ([(hit, MATCH_LABELS[how], True)] if hit else []) + [(c, why, False) for c, why in matcher.candidates(paper, exclude=(pid,))]
        for other, why, certain in found:
            pair = tuple(sorted((pid, other)))
            if other in (paper.get("apart") or []) or pid in (papers[other].get("apart") or []):
                continue
            if pair in pairs and (pairs[pair]["certain"] or not certain):
                continue
            pairs[pair] = {"why": why, "certain": certain}

    def side(pid: str) -> dict:
        p, st = papers[pid], stats.get(pid) or {}
        return {"citekey": pid, "cite": render.cite_short(p), "title": p.get("title", ""), "doi": p.get("doi") or "", "status": "read" if render.is_read(p) else "cited", "cited_by": st.get("sources", 0), "cited_claims": st.get("claims", 0)}

    out = [{"a": side(a), "b": side(b), **info} for (a, b), info in pairs.items()]
    out.sort(key=lambda d: (not d["certain"], -(d["a"]["cited_by"] + d["b"]["cited_by"]), d["a"]["citekey"]))
    return out


def merge_certain(vault: Vault) -> list[dict]:
    """같은 문헌이라는 근거가 분명한 쌍(같은 DOI 등)을 합친다. 인용이 더 많이 걸린 쪽(읽은 논문이 있으면 그쪽)을 남긴다."""
    merged = []
    for _ in range(500):  # 합칠 때마다 다시 찾는다 (셋 이상이 같은 문헌일 수 있다)
        pair = next((d for d in duplicates(vault) if d["certain"] and not (d["a"]["status"] == "read" and d["b"]["status"] == "read")), None)
        if not pair:
            break
        keep, drop = sorted((pair["a"], pair["b"]), key=lambda x: (x["status"] != "read", -x["cited_by"], not x["doi"], x["citekey"]))
        merged.append({**merge_papers(vault, drop["citekey"], keep["citekey"]), "why": pair["why"]})
    return merged


def keep_apart(vault: Vault, a: str, b: str) -> None:
    """비슷해 보이지만 다른 문헌인 쌍을 적어 둔다. 다시 '같은 문헌일 수 있음'으로 나오지 않는다."""
    with vault.lock:
        vault.check_readable()
        first, second = vault.paper(a), vault.paper(b)
        if not first or not second or a == b:
            raise WikiError("문헌 두 편의 인용 키를 주세요.")
        first["apart"] = list(dict.fromkeys([*(first.get("apart") or []), b]))
        vault.save_paper(first)


def find_dois(vault: Vault, search, limit: int = 300) -> list[dict]:
    """DOI 없이 등록된 인용 문헌의 DOI 를 다시 찾는다 (등록할 때 연결이 안 됐거나, 그 뒤에 등록된 DOI)."""
    with vault.lock:
        vault.check_readable()
        todo = [copy.deepcopy(p) for p in vault.papers().values() if not p.get("doi") and len(_title_key(p.get("title"))) >= 20][:limit]
        found, failed = _search_dois(todo, search, budget=240)
        changed = [p for p in todo if p.get("doi")]
        for paper in changed:
            paper["updated"] = now_iso()
            vault.save_paper(paper)
        if changed:
            render.sync(vault)
        return [{"paper": p["id"], "doi": p["doi"]} for p in changed] + ([{"paper": "", "failed": failed}] if failed else [])


def same_claims(vault: Vault, group_ids: list[str]) -> dict:
    """서로 다른 논문의 주장을 '같은 주장'으로 묶는다 (첫 번째 묶음으로 나머지를 합친다)."""
    with vault.lock:
        vault.check_readable()
        papers = vault.papers()
        known = {c.get("group") for p in papers.values() for c in p.get("claims", [])}
        ids = list(dict.fromkeys(group_ids))
        missing = [g for g in ids if g not in known]
        if missing:
            raise WikiError("주장을 찾을 수 없습니다: " + ", ".join(missing))
        if len(ids) < 2:
            raise WikiError("묶을 주장을 둘 이상 주세요.")
        keep, rest, moved = ids[0], set(ids[1:]), 0
        for paper in papers.values():
            if not any(c.get("group") in rest for c in paper.get("claims", [])):
                continue
            paper = copy.deepcopy(paper)
            for claim in paper["claims"]:
                if claim.get("group") in rest:
                    claim["group"] = keep
                    moved += 1
            paper["updated"] = now_iso()
            vault.save_paper(paper)
        render.sync(vault)
        return {"group": keep, "moved": moved}


def split_claim(vault: Vault, group_id: str, paper_id: str) -> dict:
    """잘못 묶인 주장을 떼어 낸다: 그 묶음에서 이 논문의 주장만 따로 떨어진다."""
    with vault.lock:
        vault.check_readable()
        paper = vault.paper(paper_id)
        if not paper or not any(c.get("group") == group_id for c in paper.get("claims", [])):
            raise WikiError("그 논문에는 이 묶음에 속한 주장이 없습니다.")
        known = {c.get("group") for p in vault.papers().values() for c in p.get("claims", [])}
        for claim in paper["claims"]:
            if claim.get("group") == group_id:
                claim["group"] = _new_group(known)
        paper["updated"] = now_iso()
        vault.save_paper(paper)
        render.sync(vault)
        return {"paper": paper_id}


def parse_authors(text: str) -> list[dict]:
    """'Kim, Jisoo; Lee, Sang' → 저자 목록."""
    authors = []
    for part in re.split(r"\s*;\s*", text or ""):
        part = re.sub(r"\s+", " ", part).strip()
        if not part:
            continue
        if "," in part:
            family, given = (p.strip() for p in part.split(",", 1))
            authors.append({"family": family, "given": given})
        else:
            authors.append({"name": part})
    return authors


def update_paper_meta(vault: Vault, paper_id: str, changes: dict) -> dict:
    """등록된 논문·문헌의 서지 정보를 고친다 (주장·키워드는 그대로). PDF 이름도 따라 바뀐다."""
    with vault.lock:
        vault.check_readable()
        paper = vault.paper(paper_id)
        if not paper:
            raise WikiError("논문을 찾을 수 없습니다.")
        for key in ("title", "year", "venue", "doi"):
            if changes.get(key) is not None:
                paper[key] = extract.clean_doi(changes[key]) if key == "doi" else _text(changes[key], 500)
        if changes.get("authors") is not None:
            paper["authors"] = changes["authors"] if isinstance(changes["authors"], list) else parse_authors(changes["authors"])
            paper["et_al"] = False  # 직접 적어 준 저자 목록은 전체로 본다
        if not paper.get("title"):
            raise WikiError("제목은 비워 둘 수 없습니다.")
        note = ""
        if (paper.get("pdf") or {}).get("path"):
            paper["pdf"]["path"], note = library.place_pdf(vault, paper)
        paper["updated"] = now_iso()
        vault.save_paper(paper)
        render.sync(vault)
        return {"paper": paper, "pdf_note": note}


def tidy(vault: Vault, zotero=None, dry_run: bool = False, include_cited: bool = False, **zotero_options) -> list[dict]:
    """논문 폴더를 위키 기록과 맞춘다.

    - 등록된 논문의 PDF 이름을 이름 규칙대로 바꾼다 (규칙을 바꿨거나, 전에 바꾸지 못한 파일)
    - 사용자가 옮기거나 이름을 바꾼 PDF 를 내용으로 찾아 다시 연결한다
    - zotero 를 넘기면 이어서 Zotero 와 맞춘다 (zotero_sync 참고. zotero_options 는 add·collection·pdf_mode)
    """
    with vault.lock:
        vault.check_readable()
        pattern = library.name_pattern(vault)
        changes, dirty = [], False
        for paper in [copy.deepcopy(p) for p in vault.papers().values()]:
            changed = False
            info = paper.get("pdf") or {}
            if info.get("path"):
                if not (vault.root / info["path"]).is_file():
                    moved = library.find_moved(vault, paper)
                    if moved:
                        changes.append({"paper": paper["id"], "action": "relinked", "from": info["path"], "to": moved})
                        info["path"], changed = moved, True
                    else:
                        changes.append({"paper": paper["id"], "action": "missing", "from": info["path"]})
                if (vault.root / info["path"]).is_file():
                    wanted = library.pdf_filename(paper, pattern)
                    current = info["path"].rsplit("/", 1)[-1]
                    if unicodedata.normalize("NFC", current) != wanted:
                        if dry_run:
                            changes.append({"paper": paper["id"], "action": "would_rename", "from": current, "to": wanted})
                        else:
                            after, note = library.place_pdf(vault, paper)
                            if after != info["path"]:
                                changes.append({"paper": paper["id"], "action": "renamed", "from": current, "to": after.rsplit("/", 1)[-1]})
                                info["path"], changed = after, True
                            else:
                                changes.append({"paper": paper["id"], "action": "rename_failed", "from": current, "note": note})
            if changed and not dry_run:
                paper["updated"] = now_iso()
                vault.save_paper(paper)
                dirty = True
        if dirty:
            render.sync(vault)
    if zotero is not None:
        changes += zotero_sync(vault, zotero, include_cited=include_cited, dry_run=dry_run, **zotero_options)
    return changes


def zotero_options(cfg: dict | None = None) -> dict:
    """설정에서 zotero_sync 에 넘길 값."""
    cfg = cfg or config.load()
    return {"add": bool(cfg.get("zotero_add")), "collection": str(cfg.get("zotero_collection") or "").strip(), "pdf_mode": cfg.get("zotero_pdf") or "link"}


_ZOTERO_TEXT = {
    "zotero_linked": "Zotero 에 이미 있던 항목과 연결했습니다 ({to})",
    "zotero_added": "Zotero 에 새 항목으로 넣었습니다 ({to})",
    "zotero_would_add": "Zotero 에 없음 → 새 항목으로 넣을 예정",
    "zotero_collected": "Zotero 컬렉션 '{to}' 에 넣었습니다",
    "zotero_relinked": "Zotero 의 PDF 링크를 바뀐 파일 이름으로 고쳤습니다 ({to})",
    "zotero_failed": "Zotero 에 반영하지 못했습니다: {note}",
}


def zotero_report(changes: list[dict], one_paper: bool = False) -> list[str]:
    """zotero_sync 의 결과를 사람이 읽는 줄로 (one_paper 면 논문 이름을 앞에 붙이지 않는다)."""
    lines = []
    for change in changes:
        action = change["action"]
        if action == "zotero_unreachable":
            lines.append(f"Zotero 에 연결하지 못했습니다 ({change.get('note') or '이유를 알 수 없음'}). Zotero 를 켠 뒤 'paperwiki zotero sync' 를 실행하면 이어서 넣습니다.")
        elif action == "zotero_need_connect":
            lines.append(change.get("note") or "Zotero 가 항목 추가를 허용하지 않았습니다.")
        elif action in _ZOTERO_TEXT:
            text = _ZOTERO_TEXT[action].format(**{"to": "", "note": "", **change})
            if action == "zotero_added":
                text += " · PDF 링크 포함" if change.get("pdf") else ""
                text += f" · {change['note']}" if change.get("note") else ""
            lines.append(text if one_paper else f"- @{change['paper']}  {text}")
    return lines


def zotero_sync(vault: Vault, zotero, paper_ids=None, *, add: bool = False, collection: str = "", pdf_mode: str = "link", include_cited: bool = False, dry_run: bool = False) -> list[dict]:
    """위키의 읽은 논문을 Zotero 와 맞춘다. 바뀐 것(또는 dry_run 이면 바뀔 것)의 목록을 돌려준다.

    - Zotero 와 연결되지 않은 논문: 같은 논문이 Zotero 에 있으면 그 항목과 연결한다 (zotero_linked).
      없으면 add 일 때 새 항목으로 넣는다 (zotero_added) — 위키의 인용 키를 Zotero 의 인용 키로,
      pdf_mode 가 link 면 논문 폴더의 PDF 를 링크된 파일로 붙인다.
    - collection 을 주면 위키에 있는 논문을 Zotero 의 그 컬렉션에 모은다.
    - Paper Wiki 가 붙인 PDF 링크는 위키에서 PDF 이름이 바뀌면 따라 고친다 (zotero_relinked).
    - 인용 문헌은 Zotero 에 넣지 않는다. include_cited 면 Zotero 에 이미 있는 것과 연결만 한다.

    Zotero 에 연결하지 못하면 거기서 멈추고 (zotero_unreachable), 항목 추가를 허용받지 못했으면
    연결만 하고 넣지는 않는다 (zotero_need_connect). 어느 경우에도 위키의 내용은 그대로다.
    """
    from .zotero import ZoteroError, ZoteroNotAuthorized

    changes: list[dict] = []
    with vault.lock:
        vault.check_readable()
        dirty, can_write = False, True

        def write(paper_id: str, fn, *args):
            """Zotero 에 쓰는 일 하나. 허용이 없으면 그 뒤로는 쓰지 않고, 그 밖의 실패는 그 논문만의 일로 적는다."""
            nonlocal can_write
            if not can_write:
                return None
            try:
                return fn(*args)
            except ZoteroNotAuthorized as exc:
                can_write = False
                changes.append({"paper": "", "action": "zotero_need_connect", "note": str(exc)})
            except ZoteroError as exc:
                changes.append({"paper": paper_id, "action": "zotero_failed", "note": str(exc)})
            return None

        for paper in [copy.deepcopy(p) for p in vault.papers().values()]:
            read = render.is_read(paper)
            if (paper_ids is not None and paper["id"] not in paper_ids) or not (read or include_cited):
                continue
            path = (paper.get("pdf") or {}).get("path")
            pdf = vault.root / path if path and (vault.root / path).is_file() else None
            changed = added = False
            if not paper.get("zotero_key"):
                try:
                    found = zotero.find(doi=paper.get("doi") or "", title=paper.get("title") or "")
                except Exception as exc:  # 연결이 안 되면 나머지 논문은 더 묻지 않는다
                    changes.append({"paper": "", "action": "zotero_unreachable", "note": str(exc)})
                    break
                if found:
                    paper["zotero_key"], paper["attachment_key"], paper["zotero_pdf"] = found.get("zotero_key"), found.get("attachment_key"), ""
                    changes.append({"paper": paper["id"], "action": "zotero_linked", "to": found.get("zotero_key")})
                    changed = True
                elif read and add and dry_run:
                    changes.append({"paper": paper["id"], "action": "zotero_would_add"})
                elif read and add:
                    made = write(paper["id"], zotero.add_paper, paper, pdf if pdf_mode == "link" else None, collection)
                    if made:
                        paper["zotero_key"], paper["attachment_key"] = made["zotero_key"], made["attachment_key"]
                        paper["zotero_pdf"] = "linked" if made["attachment_key"] else ""
                        changes.append({"paper": paper["id"], "action": "zotero_added", "to": made["zotero_key"], "pdf": bool(made["attachment_key"]), "note": made.get("note", "")})
                        changed = added = True
            if paper.get("zotero_key") and read and not added and not dry_run:
                if collection and write(paper["id"], zotero.add_to_collection, paper["zotero_key"], collection):
                    changes.append({"paper": paper["id"], "action": "zotero_collected", "to": collection})
                if paper.get("zotero_pdf") == "linked" and paper.get("attachment_key") and pdf is not None:
                    if write(paper["id"], zotero.relink_pdf, paper["attachment_key"], pdf):
                        changes.append({"paper": paper["id"], "action": "zotero_relinked", "to": pdf.name})
            if changed and not dry_run:
                paper["updated"] = now_iso()
                vault.save_paper(paper)
                dirty = True
        if dirty:
            render.sync(vault)
    return changes


# ── 키워드 ────────────────────────────────────────────────────────────────


def add_keyword(vault: Vault, name: str, parent: str | None, aliases=(), description: str = "") -> dict:
    with vault.lock:
        vault.check_readable()
        onto = vault.ontology()
        try:
            node = onto.add(name, parent or None, aliases, description)
        except OntologyError as exc:
            raise WikiError(str(exc)) from exc
        vault.save_ontology(onto)
        render.sync(vault)
        return node


def update_keyword(vault: Vault, node_id: str, *, name=None, aliases=None, description=None, parent="__keep__") -> dict:
    with vault.lock:
        vault.check_readable()
        onto = vault.ontology()
        node = onto.get(node_id)
        if not node:
            raise WikiError("키워드를 찾을 수 없습니다.")
        old_file = node["file"]
        try:
            onto.update(node_id, name=name, aliases=aliases, description=description)
            if parent != "__keep__":
                onto.move(node_id, parent or None)
        except OntologyError as exc:
            raise WikiError(str(exc)) from exc
        vault.save_ontology(onto)
        render.move_keyword_file(vault, old_file, onto.nodes[node_id]["file"])
        render.sync(vault)
        return onto.nodes[node_id]


def merge_keywords(vault: Vault, src_id: str, dst_id: str) -> dict:
    """src 키워드를 dst 로 합친다: 주장·하위 키워드·별칭·메모가 모두 dst 로 옮겨진다."""
    with vault.lock:
        vault.check_readable()
        onto = vault.ontology()
        src, dst = onto.get(src_id), onto.get(dst_id)
        if not src or not dst:
            raise WikiError("키워드를 찾을 수 없습니다.")
        if src_id == dst_id:
            raise WikiError("같은 키워드로는 병합할 수 없습니다.")
        if dst_id in onto.descendants(src_id):
            raise WikiError("자신의 하위 키워드로는 병합할 수 없습니다. 먼저 대상 키워드를 다른 위치로 옮겨 주세요.")
        for paper in vault.papers().values():
            if not any(src_id in c.get("keywords", []) for c in paper.get("claims", [])):
                continue
            paper = copy.deepcopy(paper)
            for claim in paper["claims"]:
                claim["keywords"] = list(dict.fromkeys(dst_id if k == src_id else k for k in claim.get("keywords", [])))
            paper["updated"] = now_iso()
            vault.save_paper(paper)
        for child in onto.children(src_id):
            onto.move(child["id"], dst_id)
        src_names = [src["name"], *src.get("aliases", [])]
        src_file = src["file"]
        _, src_notes = render.split_notes(vault.keywords_md / f"{src_file}.md")
        onto.remove(src_id)
        onto.update(dst_id, aliases=[*dst.get("aliases", []), *src_names])
        vault.save_ontology(onto)
        render.sync(vault)  # dst 문서를 먼저 최신으로 만든 뒤 메모를 덧붙인다
        render.append_notes(vault, onto.nodes[dst_id]["file"], src_notes)
        orphan = vault.root / "_orphans" / f"{src_file}.md"
        if src_notes.strip() and orphan.exists():
            orphan.unlink()  # 메모는 dst 로 옮겼으므로 보관본은 필요 없다
        return onto.nodes[dst_id]


def delete_keyword(vault: Vault, node_id: str) -> None:
    with vault.lock:
        vault.check_readable()
        onto = vault.ontology()
        if not onto.get(node_id):
            raise WikiError("키워드를 찾을 수 없습니다.")
        usage = render.build_usage(vault.papers(), onto)
        if usage.get(node_id):
            raise WikiError("이 키워드에 정리된 주장이 있어 삭제할 수 없습니다. 다른 키워드로 병합해 주세요.")
        try:
            onto.remove(node_id)
        except OntologyError as exc:
            raise WikiError(str(exc)) from exc
        vault.save_ontology(onto)
        render.sync(vault)


# ── 통계·인사이트·검색 ─────────────────────────────────────────────────


def stats(vault: Vault) -> dict:
    papers, onto = vault.papers(), vault.ontology()
    read = sum(1 for p in papers.values() if render.is_read(p))
    return {
        "papers": read,
        "cited": len(papers) - read,
        "claims": len(render.claim_groups(papers)),
        "keywords": len(onto.nodes),
        "pending": len(vault.pending_all()),
        "new_pdfs": len(library.list_new(vault)),
    }


def reference(paper: dict) -> dict:
    """글에 인용할 때 필요한 서지 정보."""
    return {
        "citekey": paper["id"],
        "cite": render.cite_short(paper),
        "authors": [render.author_name(a, full=True) for a in paper.get("authors") or []] + (["et al."] if paper.get("et_al") else []),
        "year": paper.get("year") or "",
        "title": render.one_line(paper.get("title")),
        "venue": paper.get("venue") or "",
        "doi": paper.get("doi") or "",
        "status": "read" if render.is_read(paper) else "cited",
        "pdf": (paper.get("pdf") or {}).get("path") or "",
        "zotero": render.zotero_select_uri(paper),
        "file": f"papers/{paper['id']}.md",
    }


def paper_rows(vault: Vault) -> list[dict]:
    """위키의 모든 문헌과, 각 문헌이 인용된 정도 (목록 화면·명령 공용)."""
    papers, onto = vault.papers(), vault.ontology()
    stats_ = render.paper_stats(papers, onto)
    rows = []
    for p in papers.values():
        s = stats_.get(p["id"], {"claims": 0, "sources": 0, "keywords": 0, "keyword_ids": []})
        rows.append(
            {
                **reference(p),
                "own_claims": len(p.get("claims", [])),
                "cited_claims": s["claims"],
                "cited_by": s["sources"],
                "directions": s["keywords"],
                "keyword_ids": s["keyword_ids"],
                "added": (p.get("added") or "")[:10],
            }
        )
    return rows


def _entry_json(entry: dict, papers: dict, onto: Ontology) -> dict:
    """'같은 주장' 한 항목을 JSON 으로 (검색·인사이트 공용)."""
    return {
        "group": entry["group"],
        "statement": entry["statement"],
        "type": entry["type"],
        "cites": [
            {"citekey": pid, "cite": render.cite_short(papers[pid]), "title": render.one_line(papers[pid].get("title")), "cited_in": len(srcs)}
            for pid, srcs in entry["cites"].items()
            if pid in papers
        ],
        "sources": [
            {
                "citekey": src["id"],
                "cite": render.cite_short(src),
                "quote": render.one_line((claim.get("evidence") or {}).get("quote")),
                "location": render.one_line((claim.get("evidence") or {}).get("location")),
                "cites": [pid for pid in claim.get("cites", []) if pid in papers],
            }
            for src, claim in entry["members"]
        ],
        "keywords": [onto.nodes[k]["name"] for k in entry["keywords"] if k in onto.nodes],
        "keyword_ids": [k for k in entry["keywords"] if k in onto.nodes],
    }


def insights(vault: Vault, limit: int = 30) -> dict:
    """위키에서 눈여겨볼 것: 여러 논문이 인용한 문헌, 여러 방향으로 인용된 문헌, 여러 논문이 같은 주장에 인용한 문헌."""
    papers, onto = vault.papers(), vault.ontology()
    rows = paper_rows(vault)
    names = lambda ids: [onto.nodes[k]["name"] for k in ids if k in onto.nodes]  # noqa: E731

    def top(key: str) -> list[dict]:
        hit = sorted((r for r in rows if r[key] >= 2), key=lambda r: (-r[key], -r["cited_claims"], r["cite"].casefold()))
        return [{**{k: r[k] for k in ("citekey", "cite", "title", "status", "cited_by", "cited_claims", "directions")}, "keywords": names(r["keyword_ids"])} for r in hit[:limit]]

    groups = render.claim_groups(papers)
    shared = []
    for key, members in groups.items():
        if len({src["id"] for src, _ in members}) < 2:
            continue
        entry = render.grouped(members[:1], groups)[0]
        item = _entry_json(entry, papers, onto)
        item["common"] = [c for c in item["cites"] if c["cited_in"] >= 2]  # 같은 주장에 여러 논문이 똑같이 인용한 문헌
        shared.append(item)
    shared.sort(key=lambda e: (-len(e["sources"]), -len(e["common"])))
    return {"multi_source": top("cited_by"), "multi_direction": top("directions"), "shared_claims": shared[:limit]}


def search(vault: Vault, query: str, limit: int = 40) -> dict:
    """키워드·주장·문헌을 한 번에 찾는다. 모든 검색어가 포함된 항목만 나온다.

    주장은 '같은 주장'끼리 묶여 나오고, 주장마다 인용된 문헌(cites)과 그 주장을 한 논문(sources)이 붙는다.
    """
    tokens = norm(query).split()
    papers, onto = vault.papers(), vault.ontology()
    if not tokens:
        return {"query": query, "keywords": [], "claims": [], "papers": [], "references": {}}

    def hit(*fields: str) -> bool:
        hay = norm(" ".join(f for f in fields if f))
        return all(t in hay for t in tokens)

    usage = render.build_usage(papers, onto)
    counts = render.subtree_counts(onto, usage)
    groups = render.claim_groups(papers)
    stats_ = render.paper_stats(papers, onto)

    kw_hits = []
    matched_kw: set[str] = set()
    for n in onto.nodes.values():
        names = [n["name"], *n.get("aliases", [])]
        score = 0
        if any(norm(x) == norm(query) for x in names):
            score = 100
        elif hit(n["name"]):
            score = 70
        elif hit(*names):
            score = 55
        elif hit(*names, n.get("description", "")):
            score = 25
        if score:
            if score >= 55:
                matched_kw.add(n["id"])
            kw_hits.append((score + min(counts[n["id"]]["claims"], 20), n))
    kw_hits.sort(key=lambda x: (-x[0], x[1]["name"]))

    # 검색어가 키워드 이름과 맞으면 그 키워드(와 하위 키워드)에 정리된 주장도 결과에 넣는다
    kw_scope = set(matched_kw)
    for k in matched_kw:
        kw_scope.update(onto.descendants(k))

    scored: dict[str, tuple[int, dict, dict]] = {}
    for p in papers.values():
        for c in p.get("claims", []):
            cited_text = " ".join(f"{render.cite_short(papers[pid])} {papers[pid].get('title', '')}" for pid in c.get("cites", []) if pid in papers)
            score = 0
            if hit(c.get("statement", "")):
                score = 60
            elif hit(c.get("statement", ""), (c.get("evidence") or {}).get("quote", "")):
                score = 45
            elif hit(c.get("statement", ""), cited_text):
                score = 35
            elif kw_scope.intersection(c.get("keywords", [])):
                score = 30
            key = render.group_key(p, c)
            if score and score > scored.get(key, (0, None, None))[0]:
                scored[key] = (score, p, c)
    ranked = sorted(scored.values(), key=lambda x: (-x[0], -len(groups.get(render.group_key(x[1], x[2]), []))))
    entries = render.grouped([(p, c) for _, p, c in ranked[:limit]], groups)

    paper_hits = []
    for p in papers.values():
        authors = " ".join(render.author_name(a, full=True) for a in p.get("authors", []))
        score = 0
        if hit(p["id"]):
            score = 80
        elif hit(p.get("title", "")):
            score = 60
        elif hit(p.get("title", ""), authors, str(p.get("year") or ""), p.get("venue") or ""):
            score = 45
        elif hit(p.get("summary", ""), p.get("abstract") or ""):
            score = 20
        if score:
            paper_hits.append((score + min(stats_.get(p["id"], {}).get("sources", 0), 10), p))
    paper_hits.sort(key=lambda x: (-x[0], x[1]["id"]))

    claims = [_entry_json(e, papers, onto) for e in entries]
    involved = {pid for c in claims for pid in [x["citekey"] for x in c["cites"]] + [s["citekey"] for s in c["sources"]]}
    involved.update(p["id"] for _, p in paper_hits[:limit])
    return {
        "query": query,
        "keywords": [
            {
                "id": n["id"],
                "name": n["name"],
                "aliases": n.get("aliases", []),
                "path": onto.path_names(n["id"]),
                "description": n.get("description", ""),
                "claims": counts[n["id"]]["claims"],
                "papers": counts[n["id"]]["papers"],
                "file": f"keywords/{n['file']}.md",
            }
            for _, n in kw_hits[:limit]
        ],
        "claims": claims,
        "papers": [
            {
                "id": p["id"],
                "cite": render.cite_short(p),
                "title": render.one_line(p.get("title")),
                "year": p.get("year"),
                "venue": p.get("venue"),
                "doi": p.get("doi"),
                "status": "read" if render.is_read(p) else "cited",
                "cited_by": stats_.get(p["id"], {}).get("sources", 0),
                "cited_claims": stats_.get(p["id"], {}).get("claims", 0),
                "directions": stats_.get(p["id"], {}).get("keywords", 0),
                "own_claims": len(p.get("claims", [])),
                "zotero": render.zotero_select_uri(p),
                "file": f"papers/{p['id']}.md",
            }
            for _, p in paper_hits[:limit]
        ],
        # 결과에 나온 문헌들의 서지 정보 (인용·참고문헌 작성용)
        "references": {pid: reference(papers[pid]) for pid in sorted(involved) if pid in papers},
    }
