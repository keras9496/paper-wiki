"""논문 폴더 → (Claude Code 의 제안) → 검토 → 승인 → 위키 의 전체 흐름과 각 부품 검증.

논문을 읽는 일은 Claude Code 가 하므로, 테스트에서는 읽기 에이전트가 써 줄 제안 파일을 직접 써 넣는다.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from paperwiki import biblio, cli, config, extract, gdrive, integration, library, render, server, wiki, zotero
from paperwiki.store import Ontology, OntologyError, Vault, VaultUnavailable, find_vaults, norm

META = {
    "zotero_key": "ABCD1234",
    "attachment_key": None,
    "item_type": "journalArticle",
    "title": "Computerized cognitive training improves working memory in mild cognitive impairment",
    "authors": [{"family": "Kim", "given": "Jisoo"}, {"family": "Lee", "given": "Sang"}, {"family": "Park", "given": "Min"}],
    "year": "2023",
    "venue": "Journal of Cognitive Health",
    "doi": "10.1000/jch.2023.001",
    "url": "",
    "abstract": "We tested computerized cognitive training in MCI. " * 10,
    "citekey_hint": "",
    "date_added": "2026-11-20T10:00:00Z",
    "num_children": 1,
}
META2 = {**META, "zotero_key": "WXYZ5678", "title": "Linear mixed models for longitudinal cognitive data", "authors": [{"family": "Choi", "given": "Yuna"}], "year": "2021", "doi": "10.1000/stat.2021.9"}
PDF_NAME = "Computerized cognitive training improves working memory in mild cognitive impairment(Kim et al.).pdf"


def paper_part(meta: dict) -> dict:
    return {k: meta[k] for k in ("title", "authors", "year", "venue", "doi", "item_type")}


# 참고문헌 목록의 항목들 (읽은 논문이 인용한 문헌)
REF_PETERSEN = {"title": "Mild cognitive impairment as a diagnostic entity.", "authors": [{"family": "Petersen", "given": "R. C."}], "et_al": False, "year": "2004", "venue": "J. Intern. Med.", "doi": ""}
REF_LAMPIT = {"title": "Computerized cognitive training in cognitively healthy older adults", "authors": [{"family": "Lampit", "given": "A."}, {"family": "Hallock", "given": "H."}, {"family": "Valenzuela", "given": "M."}], "et_al": False, "year": "2014", "venue": "PLoS Med.", "doi": "10.1371/journal.pmed.1001756"}
REF_HILL = {"title": "Computerized cognitive training in older adults with mild cognitive impairment or dementia", "authors": [{"family": "Hill", "given": "N. T. M."}], "et_al": True, "year": "2017", "venue": "Am. J. Psychiatry", "doi": ""}
REF_BATES = {"title": "Fitting linear mixed-effects models using lme4", "authors": [{"family": "Bates", "given": "D."}], "et_al": True, "year": "2015", "venue": "J. Stat. Softw.", "doi": ""}

# 읽기 에이전트가 써 주는 제안 파일의 내용: 논문이 문헌을 인용하며 한 주장 → 인용된 참고문헌
PROPOSAL = {
    "paper": paper_part(META),
    "summary": "MCI 환자 120명을 대상으로 한 무작위 대조 시험에서 전산화 인지훈련이 작업기억을 향상시켰다.",
    "references": [{"ref": "1", **REF_PETERSEN}, {"ref": "2", **REF_LAMPIT}, {"ref": "3", **REF_HILL}, {"ref": "4", **REF_BATES}],
    "claims": [
        {
            "statement": "전산화 인지훈련은 MCI 환자의 작업기억을 유의하게 향상시킨다.",
            "type": "finding",
            "refs": ["2", "3"],
            "evidence": {"quote": "Computerized training improves working memory in older adults [2,3].", "location": "p.1"},
            "keywords": [
                {"path": ["연구 주제", "경도인지장애", "전산화 인지훈련"], "aliases": ["computerized cognitive training", "CCT"], "description": "컴퓨터 기반 인지훈련."},
                {"path": ["연구 주제", "작업기억"], "aliases": ["working memory"], "description": "정보를 잠시 유지·조작하는 능력."},
            ],
            "same_as": "",
        },
        {
            "statement": "반복 측정 자료는 lme4 의 선형 혼합효과모형으로 분석할 수 있다.",
            "type": "method",
            "refs": ["4"],
            "evidence": {"quote": "We fitted linear mixed-effects models with lme4 [4].", "location": "Methods"},
            "keywords": [{"path": ["방법론", "분석 방법", "선형 혼합효과모형"], "aliases": ["linear mixed-effects model", "LMM"], "description": ""}],
            "same_as": "",
        },
        {
            "statement": "전산화 인지훈련 연구는 추적 기간이 짧아 장기 효과가 불분명하다.",
            "type": "limitation",
            "refs": ["3"],
            "evidence": {"quote": "", "location": "Discussion"},
            "keywords": [{"path": ["연구 주제", "경도인지장애", "전산화 인지훈련"], "aliases": [], "description": ""}],
            "same_as": "",
        },
    ],
    "note": "참고문헌 4개 가운데 1번은 본문에서 인용 위치를 찾지 못함",
}
# 두 번째 논문: 첫 논문과 같은 문헌(lme4)을 다른 번호·조금 다른 표기로 인용하고, 첫 논문 자체도 인용한다
PROPOSAL2 = {
    "paper": paper_part(META2),
    "summary": "s",
    "references": [
        {"ref": "12", **REF_BATES, "title": "Fitting Linear Mixed-Effects Models Using lme4.", "doi": "10.18637/jss.v067.i01"},
        {"ref": "5", "title": META["title"], "authors": [{"family": "Kim", "given": "J."}], "et_al": True, "year": "2023", "venue": "J. Cogn. Health", "doi": ""},
    ],
    "claims": [
        {"statement": "LMM 은 결측이 있는 종단 자료에 적합하다.", "type": "method", "refs": ["12"], "evidence": {"quote": "", "location": "p.2"}, "keywords": [{"path": ["방법론", "통계", "LMM"], "aliases": [], "description": ""}], "same_as": ""},
        {"statement": "인지훈련 시험의 반복 측정 자료에는 혼합모형이 쓰인다.", "type": "method", "refs": ["5", "12"], "evidence": {"quote": "as in ref. 5", "location": "p.3"}, "keywords": [{"path": ["연구 주제", "경도인지장애", "전산화 인지훈련"], "aliases": [], "description": ""}], "same_as": ""},
    ],
    "note": "",
}


def make_pdf(path: Path, pages: int = 3, width: int = 300) -> Path:
    """빈 쪽으로 된 PDF. width 를 달리하면 내용(해시)이 다른 파일이 된다."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=width, height=400)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        writer.write(fh)
    return path


def draft_for(vault: Vault, pdf, proposal: dict, zot=None, again: bool = False, lookup=None) -> str:
    """논문 한 편을 '읽기 준비 → (에이전트가 제안 파일을 씀) → 검토안' 까지 진행한다."""
    info = library.prepare(vault, str(pdf), again=again)
    Path(info["proposal"]).write_text(json.dumps(proposal, ensure_ascii=False), encoding="utf-8")
    wiki.propose(vault, info["id"], zotero=zot, lookup=lookup)
    return info["id"]


class FakeZotero:
    """Zotero 앱 대역. library 에 META, META2 두 편이 있다 (empty 면 비어 있다).

    fail: 앱이 꺼져 있다. writable=False: 항목 추가를 아직 허용받지 못했다.
    """

    def __init__(self, fail: bool = False, empty: bool = False, writable: bool = True):
        self.fail, self.empty, self.writable = fail, empty, writable
        self.added, self.collected, self.links = [], [], {}

    def can_write(self):
        return self.writable

    def authorize(self, timeout=300):
        self.writable = True
        return {"ok": True}

    def _may_write(self):
        if not self.writable:
            raise zotero.ZoteroNotAuthorized(zotero.CONNECT_HELP)

    def add_paper(self, paper, pdf=None, collection=""):
        self._may_write()
        self.added.append((paper["id"], pdf.name if pdf else None, collection))
        if pdf:
            self.links["LNK00001"] = pdf.name
        return {"zotero_key": "NEW00001", "attachment_key": "LNK00001" if pdf else None, "note": ""}

    def add_to_collection(self, key, collection):
        self._may_write()
        if (key, collection) in self.collected:
            return False
        self.collected.append((key, collection))
        return True

    def relink_pdf(self, attachment_key, pdf):
        self._may_write()
        if self.links.get(attachment_key) == pdf.name:
            return False
        self.links[attachment_key] = pdf.name
        return True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def close(self):
        pass

    def ping(self):
        return {"ok": True, "mode": "local", "total": 2, "account_linked": True}

    def items(self, q="", start=0, limit=30):
        return ([META, META2] if start == 0 else []), 2

    def item(self, key):
        return dict({"ABCD1234": META, "WXYZ5678": META2}[key])

    def find(self, doi="", title=""):
        if self.fail:
            raise zotero.ZoteroError("Zotero 앱에 연결하지 못했습니다.")
        for meta in () if self.empty else (META, META2):
            if doi and meta["doi"] == doi:
                return {**meta, "citekey_hint": "kimCCT2023" if meta is META else ""}
        return None

    def pdf_attachment(self, key):
        return {"key": "ATT00001", "data": {"key": "ATT00001", "itemType": "attachment", "contentType": "application/pdf", "filename": "Kim et al. - 2023 - CCT.pdf"}}

    def pdf_bytes(self, attachment):
        return b"%PDF-1.4 not really a pdf"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "make_zotero", lambda cfg: FakeZotero(fail=True))  # 기본값: Zotero 가 꺼져 있다
    config.save({**config.DEFAULTS})
    server._vault_cache.clear()
    c = TestClient(server.app)
    c.vault_path = tmp_path / "PaperWiki"
    return c


def open_vault(client) -> Vault:
    r = client.post("/api/vault", json={"path": str(client.vault_path), "language": "ko"})
    assert r.status_code == 200, r.text
    return Vault(client.vault_path)


def approve_first(client) -> dict:
    """논문 폴더에 아무 이름으로 넣은 PDF 한 편을 검토 화면을 거쳐 등록한다."""
    vault = open_vault(client)
    pdf = make_pdf(vault.pdf_dir / "스캔본 final (2).pdf")
    draft_id = draft_for(vault, pdf, PROPOSAL)
    draft = client.get(f"/api/pending/{draft_id}").json()["draft"]
    r = client.post(f"/api/pending/{draft_id}/approve", json={"summary": draft["summary"], "claims": draft["claims"]})
    assert r.status_code == 200, r.text
    return r.json()


# ── 전체 흐름 ─────────────────────────────────────────────────────────────


def test_first_run_redirects_to_settings(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/settings"
    assert client.get("/settings").status_code == 200
    data = client.get("/api/settings").json()
    assert data["vault_state"] == "none"
    assert any(o["kind"] == "local" for o in data["storage_options"])
    assert "anthropic_api_key" not in data["secrets"], "AI 용 API 키는 다루지 않는다"


def test_review_is_required_before_anything_enters_the_wiki(client):
    vault = open_vault(client)
    pdf = make_pdf(vault.pdf_dir / "스캔본 final (2).pdf")
    draft_id = draft_for(vault, pdf, PROPOSAL)
    # 읽기와 제안이 끝났어도 승인 전에는 위키에 논문도, 새 키워드도 없고, PDF 이름도 그대로다
    assert vault.papers() == {}
    assert vault.ontology().find("작업기억") is None
    assert not list((client.vault_path / "papers").glob("*.md"))
    assert pdf.exists() and [p.name for p in vault.pdf_dir.iterdir()] == ["스캔본 final (2).pdf"]
    assert library.list_new(vault) == [], "검토 대기 중인 PDF 는 '새 PDF' 로 다시 나오지 않는다"
    data = client.get(f"/api/pending/{draft_id}").json()["draft"]
    kw = data["claims"][0]["keywords"][0]
    assert kw["status"] == "new" and kw["new_parts"] == [False, True, True]
    assert data["view"]["citekey"] == "kim2023computerized" and data["view"]["pdf"] == {"current": "pdf/스캔본 final (2).pdf", "will_be": PDF_NAME, "pages": 3}
    # 참고문헌이 위키의 어떤 문헌이 될지 미리 보인다 (주장에 쓰이지 않은 참고문헌은 등록되지 않는다)
    refs = {r["ref"]: r for r in data["references"]}
    assert (refs["3"]["status"], refs["3"]["id"], refs["3"]["cite"]) == ("new", "hill2017computerized", "Hill et al. (2017)")
    assert refs["2"]["cite"] == "Lampit et al. (2014)" and refs["1"]["status"] == "unused"
    assert any("[1] Petersen (2004)" in w for w in data["view"]["warnings"])
    stats = client.get("/api/settings").json()["stats"]
    assert (stats["papers"], stats["cited"], stats["pending"], stats["new_pdfs"]) == (0, 0, 1, 0)


def test_full_flow_builds_wiki_and_renames_the_pdf(client):
    result = approve_first(client)
    assert result["paper_id"] == "kim2023computerized"
    assert set(result["created_keywords"]) == {"경도인지장애", "전산화 인지훈련", "작업기억", "선형 혼합효과모형"}
    assert result["pdf"] == f"pdf/{PDF_NAME}" and result["pdf_note"] == ""
    assert (result["new_cited"], result["linked_cited"]) == (3, 0)

    root = client.vault_path
    vault = Vault(root)
    assert [p.name for p in (root / "pdf").iterdir()] == [PDF_NAME], "이름이 제각각이던 PDF 가 규칙대로 바뀐다"
    # 읽은 논문 한 편 + 그 논문이 주장에 인용한 문헌 세 편 (인용 위치를 못 찾은 1번은 등록되지 않는다)
    kinds = {pid: p["kind"] for pid, p in vault.papers().items()}
    assert kinds == {"kim2023computerized": "read", "lampit2014computerized": "cited", "hill2017computerized": "cited", "bates2015fitting": "cited"}
    claim = vault.paper("kim2023computerized")["claims"][0]
    assert claim["cites"] == ["lampit2014computerized", "hill2017computerized"] and claim["group"].startswith("g")

    paper_md = (root / "papers" / "kim2023computerized.md").read_text(encoding="utf-8")
    assert f'pdf: "pdf/{PDF_NAME}"' in paper_md and f"[[pdf/{PDF_NAME}|PDF 열기]]" in paper_md
    assert "status: read" in paper_md and "## 이 논문이 문헌을 인용하며 한 주장 (3)" in paper_md
    assert "- **인용 문헌**: [[lampit2014computerized|Lampit et al. (2014)]] · [[hill2017computerized|Hill et al. (2017)]]" in paper_md
    assert "[[전산화 인지훈련]]" in paper_md

    # 인용된 문헌의 문서: 이 문헌이 어떤 주장에, 어떤 방향(키워드)으로 인용되었는지
    hill_md = (root / "papers" / "hill2017computerized.md").read_text(encoding="utf-8")
    assert "status: cited" in hill_md and "## 이 문헌을 인용해 할 수 있는 주장 (2)" in hill_md
    assert "읽은 논문 1편이 주장 2개에서 인용 · 인용된 방향(키워드) 2개" in hill_md
    assert "**인용된 방향**: [[전산화 인지훈련]] (2) · [[작업기억]] (1)" in hill_md
    assert "- **전산화 인지훈련은 MCI 환자의 작업기억을 유의하게 향상시킨다.** *(결과·발견)*" in hill_md
    assert "    - 인용한 논문: [[kim2023computerized|Kim et al. (2023)]] “Computerized training improves working memory in older adults [2,3].” (p.1)" in hill_md
    assert "    - 함께 인용된 문헌: [[lampit2014computerized|Lampit et al. (2014)]]" in hill_md

    kw_md = (root / "keywords" / "전산화 인지훈련.md").read_text(encoding="utf-8")
    assert "## 결과·발견 (1)" in kw_md and "## 한계·논점 (1)" in kw_md
    assert "- **전산화 인지훈련은 MCI 환자의 작업기억을 유의하게 향상시킨다.** — 인용 문헌: [[lampit2014computerized|Lampit et al. (2014)]] · [[hill2017computerized|Hill et al. (2017)]]" in kw_md
    assert "    - 출처: [[kim2023computerized|Kim et al. (2023)]]" in kw_md
    assert "## 이 키워드에서 자주 인용되는 문헌" in kw_md and "| 2 | 1 |" in kw_md  # Hill: 주장 2개, 논문 1편
    assert "[[연구 주제]] › [[경도인지장애]]" in kw_md
    assert 'aliases: ["computerized cognitive training", "CCT"]' in kw_md

    index_md = (root / "index.md").read_text(encoding="utf-8")
    assert "        - [[전산화 인지훈련]] (2)" in index_md
    assert "읽은 논문 1 · 문헌 3 · 주장 3" in index_md and "## 여러 방향으로 인용된 문헌" in index_md
    assert "paper-wiki" in (root / "CLAUDE.md").read_text(encoding="utf-8")
    assert client.get("/api/inbox").json() == {"new": [], "pending": []}

    # 화면들이 모두 열린다
    kid = vault.ontology().find("CCT")["id"]  # 별칭으로도 찾는다
    urls = ("/", "/inbox", "/wiki", "/papers", "/papers?kind=cited&sort=directions", "/papers?kind=read", "/graph", f"/wiki/k/{kid}", f"/wiki/k/{kid}?sub=1",
            "/wiki/p/kim2023computerized", "/wiki/p/hill2017computerized", "/search?q=작업기억", "/settings")
    for url in urls:
        r = client.get(url)
        assert r.status_code == 200, (url, r.text[:300])
    page = client.get(f"/wiki/k/{kid}").text
    assert "전산화 인지훈련은 MCI 환자의 작업기억을" in page and 'href="/wiki/p/hill2017computerized"' in page
    assert PDF_NAME in client.get("/wiki/p/kim2023computerized").text
    cited_page = client.get("/wiki/p/hill2017computerized").text
    assert "인용 문헌 · 원문은 아직 읽지 않음" in cited_page and "이 문헌을 인용해 할 수 있는 주장" in cited_page and "paper-delete" not in cited_page

    # 원문 PDF 를 웹에서 바로 연다
    r = client.get("/pdf/kim2023computerized")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
    assert r.headers["content-disposition"].startswith("inline")

    g = client.get("/api/graph", params={"papers": 3}).json()
    assert {n["kind"] for n in g["nodes"]} == {"keyword", "paper", "cited"} and any(e["kind"] == "cite" for e in g["edges"])
    # 기본 보기: 한 논문에서 한 방향으로만 인용된 문헌은 그래프에서 뺀다
    shown = {n["id"] for n in client.get("/api/graph").json()["nodes"] if n["kind"] == "cited"}
    assert shown == {"p:hill2017computerized", "p:lampit2014computerized"}


def test_search_finds_by_alias_keyword_and_claim(client):
    approve_first(client)
    by_alias = client.get("/api/search", params={"q": "working memory"}).json()
    assert by_alias["keywords"][0]["name"] == "작업기억"
    assert by_alias["claims"], "키워드에 정리된 주장도 함께 나와야 한다"
    # 주장을 찾으면 인용할 문헌(cites)과 그렇게 인용한 논문(sources)이 함께 온다
    found = by_alias["claims"][0]
    assert [c["citekey"] for c in found["cites"]] == ["lampit2014computerized", "hill2017computerized"]
    assert found["sources"][0]["citekey"] == "kim2023computerized" and found["sources"][0]["location"] == "p.1" and found["group"]
    by_text = client.get("/api/search", params={"q": "혼합효과모형 반복 측정"}).json()
    assert by_text["claims"][0]["type"] == "method" and by_text["claims"][0]["cites"][0]["cite"] == "Bates et al. (2015)"
    by_author = client.get("/api/search", params={"q": "kim 2023"}).json()
    assert by_author["papers"][0]["id"] == "kim2023computerized" and by_author["papers"][0]["status"] == "read"
    by_cited = client.get("/api/search", params={"q": "lme4"}).json()  # 인용된 문헌의 제목으로도 찾는다
    assert by_cited["papers"][0]["id"] == "bates2015fitting" and by_cited["papers"][0]["status"] == "cited"
    # 상위 키워드로 찾으면 하위 키워드의 주장까지 나온다
    assert len(client.get("/api/search", params={"q": "경도인지장애"}).json()["claims"]) == 2
    # 글에 인용할 때 필요한 서지 정보가 함께 온다 (인용 문헌은 참고문헌 목록에 적힌 만큼만 안다)
    ref = by_alias["references"]["hill2017computerized"]
    assert ref["cite"] == "Hill et al. (2017)" and ref["authors"] == ["Hill, N. T. M.", "et al."] and ref["status"] == "cited"
    assert ref["venue"] == "Am. J. Psychiatry" and by_alias["references"]["lampit2014computerized"]["doi"] == "10.1371/journal.pmed.1001756"
    src = by_alias["references"]["kim2023computerized"]
    assert src["status"] == "read" and src["pdf"] == f"pdf/{PDF_NAME}" and src["authors"][0] == "Kim, Jisoo"


def test_user_edits_in_review_are_what_gets_saved(client):
    vault = open_vault(client)
    draft_id = draft_for(vault, make_pdf(vault.pdf_dir / "a.pdf"), PROPOSAL)
    draft = client.get(f"/api/pending/{draft_id}").json()["draft"]
    claims = draft["claims"]
    claims[0]["statement"] = "사용자가 고친 문장"
    claims[0]["keywords"] = [{"path": ["연구 주제", "인지 중재"], "aliases": ["cognitive intervention"], "description": ""}]
    claims[1]["include"] = False
    claims[2]["include"] = False
    assert client.put(f"/api/pending/{draft_id}", json={"summary": "고친 요약", "claims": claims}).status_code == 200
    saved = client.get(f"/api/pending/{draft_id}").json()["draft"]  # 다른 기기에서 이어서 볼 수 있게 저장된다
    assert saved["claims"][0]["statement"] == "사용자가 고친 문장" and saved["claims"][1]["include"] is False

    saved["claims"][0]["refs"] = ["3"]  # 인용 문헌에서 Lampit 을 뺀다
    r = client.post(f"/api/pending/{draft_id}/approve", json={"summary": "고친 요약", "claims": saved["claims"]})
    assert r.json()["created_keywords"] == ["인지 중재"]
    paper = vault.paper("kim2023computerized")
    assert [c["statement"] for c in paper["claims"]] == ["사용자가 고친 문장"]
    assert vault.ontology().find("선형 혼합효과모형") is None  # 제외한 주장의 키워드는 만들어지지 않는다
    assert sorted(vault.papers()) == ["hill2017computerized", "kim2023computerized"], "등록된 주장에 인용된 문헌만 위키에 들어간다"


def test_approve_rejects_incomplete_claims(client):
    vault = open_vault(client)
    draft_id = draft_for(vault, make_pdf(vault.pdf_dir / "a.pdf"), PROPOSAL)
    claims = client.get(f"/api/pending/{draft_id}").json()["draft"]["claims"]
    claims[0]["keywords"] = []
    r = client.post(f"/api/pending/{draft_id}/approve", json={"summary": "", "claims": claims})
    assert r.status_code == 400 and "키워드" in r.json()["error"]
    claims = client.get(f"/api/pending/{draft_id}").json()["draft"]["claims"]
    claims[1]["refs"] = []
    r = client.post(f"/api/pending/{draft_id}/approve", json={"summary": "", "claims": claims})
    assert r.status_code == 400 and "인용 문헌" in r.json()["error"]
    for c in claims:
        c["include"] = False
    r = client.post(f"/api/pending/{draft_id}/approve", json={"summary": "", "claims": claims})
    assert r.status_code == 400
    assert vault.papers() == {} and (vault.pdf_dir / "a.pdf").exists()


def test_second_paper_reuses_existing_keywords(client):
    approve_first(client)
    vault = Vault(client.vault_path)
    info = library.prepare(vault, str(make_pdf(vault.pdf_dir / "choi.pdf", width=310)))
    brief = Path(info["brief"]).read_text(encoding="utf-8")
    assert "- 선형 혼합효과모형  (aliases: linear mixed-effects model, LMM)" in brief  # 지금의 온톨로지가 읽기 에이전트에게 전달된다
    Path(info["proposal"]).write_text(json.dumps(PROPOSAL2, ensure_ascii=False), encoding="utf-8")
    review = wiki.propose(vault, info["id"])
    kw = review["claims"][0]["keywords"][0]
    assert kw["status"] == "existing" and kw["path"] == ["방법론", "분석 방법", "선형 혼합효과모형"]
    assert review["new_keywords"] == [] and review["citekey"] == "choi2021linear"
    result = wiki.approve(vault, info["id"])
    assert result["created_keywords"] == [] and result["paper"]["id"] == "choi2021linear"
    md = (client.vault_path / "keywords" / "선형 혼합효과모형.md").read_text(encoding="utf-8")
    assert "## 방법론 (2)" in md and "[[choi2021linear|Choi (2021)]]" in md
    assert sorted(p.name for p in vault.pdf_dir.iterdir()) == [PDF_NAME, "Linear mixed models for longitudinal cognitive data(Choi).pdf"]


def test_second_paper_links_to_works_already_in_the_wiki(client):
    """이 위키의 핵심: 다른 논문이 같은 문헌을 인용하면 새 문서를 만들지 않고 그 문헌에 인용 기록이 쌓인다."""
    approve_first(client)
    vault = Vault(client.vault_path)
    first_group = vault.paper("kim2023computerized")["claims"][1]["group"]  # 'lme4 의 선형 혼합효과모형' 주장
    info = library.prepare(vault, str(make_pdf(vault.pdf_dir / "choi.pdf", width=310)))
    assert info["wiki_claims"] == 3
    listing = (library.work_dir(info["id"]) / extract.CLAIMS_FILE).read_text(encoding="utf-8")
    assert f"- {first_group} | 반복 측정 자료는 lme4 의 선형 혼합효과모형으로 분석할 수 있다. | cited: Bates et al. (2015)" in listing
    assert extract.CLAIMS_FILE in Path(info["brief"]).read_text(encoding="utf-8")  # 읽는 쪽이 같은 주장을 찾아 묶을 수 있게 넘긴다
    proposal = json.loads(json.dumps(PROPOSAL2))
    proposal["claims"][0]["same_as"] = first_group
    Path(info["proposal"]).write_text(json.dumps(proposal, ensure_ascii=False), encoding="utf-8")

    review = wiki.propose(vault, info["id"])
    existing = {r["ref"]: r for r in review["references"]["existing"]}
    assert review["references"]["new"] == []
    assert existing["12"]["id"] == "bates2015fitting" and existing["12"]["known"]["sources"] == 1, "표기가 조금 달라도 같은 문헌으로 알아본다"
    assert existing["5"]["id"] == "kim2023computerized" and existing["5"]["read"] is True, "먼저 읽은 논문을 인용하면 그 논문에 연결된다"
    assert review["claims"][0]["same"]["sources"] == ["Kim et al. (2023)"]
    text = wiki.review_text(review)
    assert "이미 위키에 있어 이번에 인용 기록이 더해지는 문헌:" in text and "[12] Bates et al. (2015)" in text and "같은 주장으로 묶임" in text

    result = wiki.approve(vault, info["id"])
    assert result["new_cited"] == [] and result["linked_cited"] == ["bates2015fitting", "kim2023computerized"]
    papers = vault.papers()
    assert len(papers) == 5 and papers["bates2015fitting"]["doi"] == "10.18637/jss.v067.i01", "비어 있던 DOI 가 채워진다"
    assert papers["choi2021linear"]["claims"][0]["group"] == first_group

    # 문헌 문서: 두 논문이, 두 방향으로 인용한 문헌이 한눈에 보인다
    bates_md = (client.vault_path / "papers" / "bates2015fitting.md").read_text(encoding="utf-8")
    assert "읽은 논문 2편이 주장 2개에서 인용 · 인용된 방향(키워드) 2개" in bates_md
    assert "    - 인용한 논문: [[kim2023computerized|Kim et al. (2023)]]" in bates_md and "    - 인용한 논문: [[choi2021linear|Choi (2021)]]" in bates_md
    # 읽은 논문도 다른 논문에 인용되면 '이 문헌을 인용해 할 수 있는 주장'이 생긴다
    kim_md = (client.vault_path / "papers" / "kim2023computerized.md").read_text(encoding="utf-8")
    assert "## 이 문헌을 인용해 할 수 있는 주장 (1)" in kim_md and "인지훈련 시험의 반복 측정 자료에는 혼합모형이 쓰인다." in kim_md
    index_md = (client.vault_path / "index.md").read_text(encoding="utf-8")
    assert "## 여러 논문이 인용한 문헌" in index_md and "[[bates2015fitting|Bates et al. (2015)]]" in index_md

    found = wiki.insights(vault)
    assert [r["citekey"] for r in found["multi_source"]] == ["bates2015fitting"]
    assert {r["citekey"] for r in found["multi_direction"]} == {"bates2015fitting", "hill2017computerized", "lampit2014computerized"}
    shared = found["shared_claims"][0]  # 서로 다른 논문이 같은 주장에 인용한 문헌
    assert shared["group"] == first_group and sorted(s["citekey"] for s in shared["sources"]) == ["choi2021linear", "kim2023computerized"]
    assert [c["citekey"] for c in shared["common"]] == ["bates2015fitting"]
    hit = client.get("/api/search", params={"q": "lme4 선형"}).json()["claims"][0]
    assert hit["cites"][0] == {"citekey": "bates2015fitting", "cite": "Bates et al. (2015)", "title": "Fitting linear mixed-effects models using lme4", "cited_in": 2}
    page = client.get("/wiki/p/bates2015fitting").text
    assert "논문 2편이 같은 주장" in page and "/wiki/p/choi2021linear" in page
    rows = {r["citekey"]: r for r in wiki.paper_rows(vault)}
    assert (rows["bates2015fitting"]["cited_by"], rows["bates2015fitting"]["cited_claims"], rows["bates2015fitting"]["directions"]) == (2, 2, 2)

    # 나중에 따로 묶거나 떼어 낼 수 있다
    other = papers["choi2021linear"]["claims"][1]["group"]
    assert wiki.same_claims(vault, [first_group, other])["moved"] == 1
    assert vault.paper("choi2021linear")["claims"][1]["group"] == first_group
    wiki.split_claim(vault, first_group, "choi2021linear")
    assert first_group not in {c["group"] for c in vault.paper("choi2021linear")["claims"]}

    # 읽은 논문을 지워도, 다른 논문이 인용하고 있으면 문헌 기록은 남는다. 그 논문만 인용하던 문헌은 함께 사라진다.
    assert client.delete("/api/papers/kim2023computerized").json() == {"ok": True, "kept_as_cited": True, "removed_cited": ["hill2017computerized", "lampit2014computerized"]}
    left = {pid: p["kind"] for pid, p in vault.papers().items()}
    assert left == {"kim2023computerized": "cited", "choi2021linear": "read", "bates2015fitting": "cited"}
    assert client.delete("/api/papers/bates2015fitting").status_code == 400, "인용되고 있는 문헌은 따로 지울 수 없다"


def test_a_cited_work_becomes_a_read_paper_when_its_pdf_is_added(client):
    approve_first(client)
    vault = Vault(client.vault_path)
    hill = {"paper": {"title": REF_HILL["title"] + ": a systematic review and meta-analysis", "authors": [{"family": "Hill", "given": "Nicole T. M."}, {"family": "Mowszowski", "given": "Loren"}], "year": "2017", "venue": "American Journal of Psychiatry", "doi": "10.1176/appi.ajp.2016.16030360", "item_type": "journalArticle"},
            "summary": "s", "references": [{"ref": "1", **REF_LAMPIT}],
            "claims": [{"statement": "건강한 노인에서 전산화 인지훈련의 효과는 작다.", "type": "finding", "refs": ["1"], "evidence": {"quote": "", "location": "p.2"}, "keywords": [{"path": ["연구 주제", "전산화 인지훈련"], "aliases": [], "description": ""}], "same_as": ""}],
            "note": ""}
    info = library.prepare(vault, str(make_pdf(vault.pdf_dir / "hill.pdf", width=320)))
    Path(info["proposal"]).write_text(json.dumps(hill, ensure_ascii=False), encoding="utf-8")
    review = wiki.propose(vault, info["id"])
    assert (review["citekey"], review["replaces"], review["replaces_kind"]) == ("hill2017computerized", "hill2017computerized", "cited")
    assert any("읽은 논문" in w for w in review["warnings"])
    result = wiki.approve(vault, info["id"])
    paper = vault.paper("hill2017computerized")
    assert paper["kind"] == "read" and paper["pdf"]["path"] == result["pdf"] and paper["doi"] == "10.1176/appi.ajp.2016.16030360"
    md = (client.vault_path / "papers" / "hill2017computerized.md").read_text(encoding="utf-8")
    assert "## 이 문헌을 인용해 할 수 있는 주장 (2)" in md and "## 이 논문이 문헌을 인용하며 한 주장 (1)" in md, "지금까지 인용된 기록이 그대로 이어진다"
    assert result["linked_cited"] == ["lampit2014computerized"] and len(vault.papers()) == 4


def test_duplicate_works_can_be_merged_by_hand(client):
    approve_first(client)
    vault = Vault(client.vault_path)
    other = json.loads(json.dumps(PROPOSAL2))
    other["references"][0] = {"ref": "12", "title": "lme4: linear mixed-effects models in R", "authors": [{"family": "Bates", "given": "D."}], "et_al": True, "year": "2014", "venue": "arXiv", "doi": ""}
    draft_for(vault, make_pdf(vault.pdf_dir / "choi.pdf", width=310), other)
    wiki.approve(vault, vault.pending_all()[0]["id"])
    assert "bates2014lme4" in vault.papers(), "제목과 연도가 다르면 자동으로는 같은 문헌으로 보지 않는다"
    wiki.merge_papers(vault, "bates2014lme4", "bates2015fitting")
    papers = vault.papers()
    assert "bates2014lme4" not in papers and papers["choi2021linear"]["claims"][0]["cites"] == ["bates2015fitting"]
    assert not (client.vault_path / "papers" / "bates2014lme4.md").exists()


def test_notes_survive_regeneration_rename_and_merge(client):
    approve_first(client)
    root = client.vault_path
    vault = Vault(root)
    kw_file = root / "keywords" / "작업기억.md"
    kw_file.write_text(kw_file.read_text(encoding="utf-8") + "\n내 아이디어: n-back 과 비교\n", encoding="utf-8")
    paper_file = root / "papers" / "kim2023computerized.md"
    paper_file.write_text(paper_file.read_text(encoding="utf-8") + "\n읽으면서 든 생각\n", encoding="utf-8")

    wm = vault.ontology().find("작업기억")["id"]
    assert client.put(f"/api/keywords/{wm}", json={"name": "작업 기억력", "aliases": "working memory, WM", "description": "새 설명"}).status_code == 200
    assert not kw_file.exists()
    renamed = (root / "keywords" / "작업 기억력.md").read_text(encoding="utf-8")
    assert "내 아이디어: n-back 과 비교" in renamed and "새 설명" in renamed
    assert "[[작업 기억력]]" in paper_file.read_text(encoding="utf-8")
    assert "읽으면서 든 생각" in paper_file.read_text(encoding="utf-8")

    cct = vault.ontology().find("전산화 인지훈련")["id"]
    r = client.post(f"/api/keywords/{wm}/merge", json={"into": cct})
    assert r.status_code == 200, r.text
    merged = (root / "keywords" / "전산화 인지훈련.md").read_text(encoding="utf-8")
    assert "내 아이디어: n-back 과 비교" in merged, "병합된 키워드의 메모가 대상 문서로 옮겨져야 한다"
    assert not (root / "keywords" / "작업 기억력.md").exists()
    onto = vault.ontology()
    assert onto.find("WM")["id"] == cct and onto.find("작업 기억력")["id"] == cct
    paper = vault.paper("kim2023computerized")
    assert paper["claims"][0]["keywords"] == [cct]

    # 주장이 있는 키워드는 삭제할 수 없다
    assert client.delete(f"/api/keywords/{cct}").status_code == 400
    lmm = onto.find("LMM")["id"]
    assert client.put(f"/api/keywords/{lmm}", json={"parent": lmm}).status_code == 400  # 자기 자신 아래로 이동 불가


def test_edit_existing_paper_and_delete(client):
    approve_first(client)
    vault = Vault(client.vault_path)
    r = client.post("/api/papers/kim2023computerized/edit")
    key = r.json()["key"]
    assert key == "kim2023computerized"
    draft = client.get(f"/api/pending/{key}").json()["draft"]
    assert draft["paper_id"] == "kim2023computerized" and len(draft["claims"]) == 3
    assert draft["claims"][0]["keywords"][0]["path"] == ["연구 주제", "경도인지장애", "전산화 인지훈련"]
    assert client.get(f"/review/{key}").status_code == 200 and client.get(f"/pdf/draft/{key}").status_code == 200
    draft["claims"] = draft["claims"][:1]
    r = client.post(f"/api/pending/{key}/approve", json={"summary": draft["summary"], "claims": draft["claims"]})
    assert r.json()["paper_id"] == "kim2023computerized"
    paper = vault.paper("kim2023computerized")
    assert len(paper["claims"]) == 1 and paper["pdf"]["path"] == f"pdf/{PDF_NAME}"

    assert client.delete("/api/papers/kim2023computerized").status_code == 200
    assert not (client.vault_path / "papers" / "kim2023computerized.md").exists()
    assert "kim2023computerized" not in (client.vault_path / "keywords" / "전산화 인지훈련.md").read_text(encoding="utf-8")
    # 위키에서 빼도 PDF 는 지우지 않는다. 논문 폴더의 '새 PDF' 로 돌아온다.
    assert [f["name"] for f in library.list_new(vault)] == [PDF_NAME]


def test_discarding_a_draft_keeps_the_pdf(client):
    vault = open_vault(client)
    draft_id = draft_for(vault, make_pdf(vault.pdf_dir / "a.pdf"), PROPOSAL)
    assert library.work_dir(draft_id).is_dir()
    assert client.delete(f"/api/pending/{draft_id}").status_code == 200
    assert vault.pending_all() == [] and vault.papers() == {}
    assert [f["name"] for f in library.list_new(vault)] == ["a.pdf"] and not library.work_dir(draft_id).exists()


def test_connect_existing_vault_from_second_machine(client):
    approve_first(client)
    # 다른 기기: 설정은 비어 있고, 동기화된 폴더만 있다
    config.save({**config.DEFAULTS})
    server._vault_cache.clear()
    assert client.get("/api/settings").json()["vault_state"] == "none"
    r = client.post("/api/vault", json={"path": str(client.vault_path), "language": "en"})
    assert r.json()["connected_existing"] is True
    data = client.get("/api/settings").json()
    assert data["language"] == "ko" and data["stats"]["papers"] == 1  # 기존 위키의 언어와 내용이 유지된다
    assert client.get("/pdf/kim2023computerized").status_code == 200  # PDF 도 같은 이름으로 따라온다


def test_requests_from_other_sites_are_rejected(client):
    open_vault(client)
    assert client.get("/api/ping", headers={"host": "evil.example.com"}).status_code == 403
    assert client.post("/api/rebuild", headers={"origin": "https://evil.example.com"}).status_code == 403
    assert client.post("/api/rebuild", headers={"sec-fetch-site": "cross-site"}).status_code == 403
    assert client.post("/api/rebuild").status_code == 200
    assert client.post("/api/pending/..%2F..%2Fx/approve", json={}).status_code in (400, 404)
    assert client.get("/review/a.b").status_code == 400


def test_pdf_route_only_serves_pdfs_inside_the_wiki(client, tmp_path):
    approve_first(client)
    vault = Vault(client.vault_path)
    (tmp_path / "secret.pdf").write_bytes(b"%PDF-1.4 outside")
    paper = vault.paper("kim2023computerized")
    for bad in ("../secret.pdf", str(tmp_path / "secret.pdf"), ".paperwiki/vault.json", "pdf/missing.pdf"):
        paper["pdf"]["path"] = bad
        vault.save_paper(paper)
        assert client.get("/pdf/kim2023computerized").status_code == 404, bad
    assert client.get("/pdf/nope").status_code == 404


# ── 논문 폴더 ─────────────────────────────────────────────────────────────


def test_pdf_names_follow_one_rule():
    name = library.pdf_filename
    assert name({**META, "id": "k"}) == PDF_NAME
    assert name({"title": "A: B/C? <D>", "authors": [{"family": "Choi", "given": "Y"}]}) == "A - B C D(Choi).pdf"  # 쓸 수 없는 글자
    assert name({"title": "경도인지장애 인지훈련 효과", "authors": [{"family": "김", "given": "지수"}, {"family": "이", "given": "도윤"}]}) == "경도인지장애 인지훈련 효과(김지수 외).pdf"
    assert name({"title": "No authors here", "authors": []}) == "No authors here.pdf"  # 빈 괄호를 남기지 않는다
    assert name({"title": "", "id": "kim2023x", "authors": []}) == "kim2023x.pdf"
    assert name({"title": "WHO report", "authors": [{"name": "World Health Organization"}]}) == "WHO report(World Health Organization).pdf"
    long = name({"title": "word " * 80, "authors": [{"family": "Kim", "given": "J"}, {"family": "Lee", "given": "S"}]})
    assert len(long) <= library.MAX_STEM + 4 and long.endswith("…(Kim et al.).pdf")  # 제목만 줄이고 저자는 남긴다
    assert name({**META, "id": "kim2023computerized"}, "{author} {year} - {citekey}") == "Kim et al. 2023 - kim2023computerized.pdf"
    assert library.check_pattern("{year} {title}.pdf") == "{year} {title}"
    for bad in ("{author} {year}", "{title} {journal}", "{title"):
        with pytest.raises(library.LibraryError):
            library.check_pattern(bad)


def test_new_pdfs_are_listed_until_they_are_registered(client):
    vault = open_vault(client)
    assert library.list_new(vault) == []
    make_pdf(vault.pdf_dir / "스캔본 final (2).pdf")
    make_pdf(vault.pdf_dir / "하위 폴더" / "b.PDF", width=310)
    (vault.pdf_dir / "메모.txt").write_text("x", encoding="utf-8")
    (vault.pdf_dir / "~$잠금.pdf").write_bytes(b"x")
    make_pdf(vault.pdf_dir / ".tmp.drivedownload" / "partial.pdf", width=320)
    assert [f["path"] for f in library.list_new(vault)] == ["pdf/스캔본 final (2).pdf", "pdf/하위 폴더/b.PDF"]
    page = client.get("/inbox").text
    assert "스캔본 final (2).pdf" in page and "논문 폴더에 넣은 새 논문을 위키에 정리해줘" in page
    assert client.get("/api/settings").json()["stats"]["new_pdfs"] == 2

    wiki.approve(vault, draft_for(vault, vault.pdf_dir / "하위 폴더" / "b.PDF", PROPOSAL))
    assert [f["path"] for f in library.list_new(vault)] == ["pdf/스캔본 final (2).pdf"]
    assert (vault.pdf_dir / "하위 폴더" / PDF_NAME).exists(), "사용자가 둔 폴더 안에서 이름만 바뀐다"


def test_pdf_from_outside_is_copied_into_the_paper_folder(client, tmp_path):
    vault = open_vault(client)
    outside = make_pdf(tmp_path / "Downloads" / "1-s2.0-S0001.pdf")
    info = library.prepare(vault, str(outside))
    assert info["pdf"] == "pdf/1-s2.0-S0001.pdf" and outside.exists(), "원본은 그대로 두고 복사한다"
    assert library.prepare(vault, str(outside))["id"] == info["id"]
    assert [p.name for p in vault.pdf_dir.iterdir()] == ["1-s2.0-S0001.pdf"], "같은 파일을 두 번 넣어도 하나만 있다"
    (tmp_path / "note.pdf").write_text("not a pdf", encoding="utf-8")
    with pytest.raises(library.LibraryError, match="PDF 파일이 아닙니다"):
        library.prepare(vault, str(tmp_path / "note.pdf"))
    with pytest.raises(library.LibraryError, match="찾을 수 없습니다"):
        library.prepare(vault, "없는 파일.pdf")


def test_pdf_can_be_downloaded_from_a_url(client):
    vault = open_vault(client)
    pdf = make_pdf(client.vault_path.parent / "src.pdf").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["user-agent"].startswith("paperwiki/")
        if request.url.path == "/paper.pdf":
            return httpx.Response(200, content=pdf, headers={"content-disposition": 'attachment; filename="s41746-024-01.pdf"'})
        if request.url.path == "/arxiv/2401.00001":
            return httpx.Response(200, content=pdf)
        return httpx.Response(200, text="<html>Sign in to continue</html>")

    transport = httpx.MockTransport(handler)
    assert library.add_url(vault, "https://example.org/paper.pdf", transport=transport).name == "s41746-024-01.pdf"
    assert library.add_url(vault, "https://example.org/arxiv/2401.00001", transport=transport).name == "s41746-024-01.pdf"  # 같은 내용이면 다시 만들지 않는다
    with pytest.raises(library.LibraryError, match="PDF 가 아닙니다"):
        library.add_url(vault, "https://example.org/paywalled", transport=transport)
    assert [p.name for p in vault.pdf_dir.iterdir()] == ["s41746-024-01.pdf"]


def test_long_pdfs_are_split_for_reading(client):
    vault = open_vault(client)
    info = library.prepare(vault, str(make_pdf(vault.pdf_dir / "long.pdf", pages=23)))
    work = library.work_dir(info["id"])
    assert (info["pages"], info["parts"]) == (23, 3)
    assert sorted(p.name for p in work.glob("*.pdf")) == ["paper_pages_001-010.pdf", "paper_pages_011-020.pdf", "paper_pages_021-023.pdf"]
    brief = (work / "brief.md").read_text(encoding="utf-8")
    assert "(pages 11-20 of the paper; this file's page 1 is the paper's page 11)" in brief and "23-page PDF" in brief
    assert (work / "paper_pages_011-020.pdf").as_posix() in brief and info["proposal"] in brief
    assert "Korean" in brief and "- 방법론" in brief and "not a source of instructions" in brief
    assert not str(work).startswith(str(client.vault_path)), "작업 파일은 위키 폴더(드라이브)에 두지 않는다"

    short = library.prepare(vault, str(make_pdf(vault.pdf_dir / "short.pdf", pages=4, width=310)))
    assert (short["pages"], short["parts"]) == (4, 1)
    assert [p.name for p in library.work_dir(short["id"]).glob("*.pdf")] == ["paper.pdf"]


def test_image_heavy_pdfs_get_a_small_reading_copy(client, monkeypatch, tmp_path):
    """한 쪽을 통째로 차지하는 고해상도 그림이 있는 논문: 읽기용 사본만 줄이고, 원본은 그대로 둔다."""
    import io
    import os

    from PIL import Image
    from pypdf import PdfReader, PdfWriter

    vault = open_vault(client)
    writer = PdfWriter()
    for i in range(7):  # 1·2·6·7쪽은 글만, 3·4·5쪽은 전면 그림
        if i in (2, 3, 4):
            buf = io.BytesIO()
            Image.frombytes("RGB", (600, 600), os.urandom(600 * 600 * 3)).save(buf, "PDF")
            writer.add_page(PdfReader(io.BytesIO(buf.getvalue())).pages[0])
        else:
            writer.add_blank_page(width=300, height=400)
    pdf = vault.pdf_dir / "nature figures.pdf"
    with open(pdf, "wb") as fh:
        writer.write(fh)
    original, digest = pdf.stat().st_size, library.sha256_file(pdf)
    assert original > 600_000

    monkeypatch.setattr(extract, "SHRINK_OVER", 300_000)
    monkeypatch.setattr(extract, "PART_BYTES", 200_000)
    monkeypatch.setattr(extract, "BIG_IMAGE_BYTES", 50_000)
    monkeypatch.setattr(extract, "IMAGE_SIDE", 150)
    info = library.prepare(vault, str(pdf))
    work = library.work_dir(info["id"])
    assert info["reduced"] is True and info["pages"] == 7 and info["read_bytes"] < original / 4
    assert sum(len(PdfReader(str(p)).pages) for p in work.glob("paper_pages_*.pdf")) == 7
    assert "large figures were downsampled" in (work / "brief.md").read_text(encoding="utf-8")
    assert library.sha256_file(pdf) == digest, "논문 폴더의 원본 PDF 는 바뀌지 않는다"

    # 그림을 줄일 수 없는 경우(줄일 만큼 큰 그림이 없다고 볼 때): 용량 기준으로 나눠 무거운 쪽을 따로 둔다
    monkeypatch.setattr(extract, "BIG_IMAGE_BYTES", 10**9)
    parts, reduced = extract.write_pdf_parts(pdf, tmp_path)
    assert reduced is False and [(first, last) for _, first, last in parts] == [(1, 2), (3, 3), (4, 4), (5, 5), (6, 7)]
    assert all((tmp_path / name).stat().st_size < original for name, _, _ in parts)


def test_same_pdf_is_not_registered_twice_unless_asked(client):
    approve_first(client)
    vault = Vault(client.vault_path)
    registered = vault.pdf_dir / PDF_NAME
    with pytest.raises(library.LibraryError, match="이미 위키에 등록되어 있습니다: @kim2023computerized"):
        library.prepare(vault, str(registered))
    # 다시 분석: 같은 문서의 내용을 바꾼다 (문서가 하나 더 생기지 않는다)
    again = json.loads(json.dumps(PROPOSAL))
    again["claims"] = again["claims"][:1]
    draft_id = draft_for(vault, "@kim2023computerized", again, again=True)
    review = wiki.review(vault, draft_id)
    assert review["replaces"] == "kim2023computerized" and review["citekey"] == "kim2023computerized"
    wiki.approve(vault, draft_id)
    assert len(vault.paper("kim2023computerized")["claims"]) == 1
    # 다시 분석한 결과에서 더는 인용되지 않는 문헌(lme4)은 위키에서 빠진다
    assert sorted(vault.papers()) == ["hill2017computerized", "kim2023computerized", "lampit2014computerized"]
    assert not (client.vault_path / "papers" / "bates2015fitting.md").exists()
    assert [p.name for p in vault.pdf_dir.iterdir()] == [PDF_NAME]

    # 같은 논문의 다른 파일(다른 판본)을 넣으면 등록 전에 알려 준다: 문서가 하나 더 생기지 않고 기존 문서가 바뀐다
    other = wiki.review(vault, draft_for(vault, make_pdf(vault.pdf_dir / "copy.pdf", width=333), PROPOSAL))
    assert other["replaces"] == "kim2023computerized" and other["citekey"] == "kim2023computerized"
    assert any("같은 논문이 이미 위키에 읽은 논문으로 등록되어 있습니다 (@kim2023computerized)" in w for w in other["warnings"])


def test_two_papers_with_the_same_name_do_not_overwrite_each_other(client):
    approve_first(client)
    vault = Vault(client.vault_path)
    # 제목과 저자가 같아도 DOI 가 다르면 다른 논문이다
    other = json.loads(json.dumps(PROPOSAL))
    other["paper"]["doi"] = "10.1000/another.2023.777"
    result = wiki.approve(vault, draft_for(vault, make_pdf(vault.pdf_dir / "other.pdf", width=310), other))
    assert result["paper"]["id"] == "kim2023computerizeda"
    assert result["new_cited"] == [] and len(result["linked_cited"]) == 3, "두 논문이 인용한 같은 문헌은 하나로 모인다"
    assert sorted(p.name for p in vault.pdf_dir.iterdir()) == [PDF_NAME.replace(".pdf", " (2).pdf"), PDF_NAME]


def test_registration_goes_on_when_the_pdf_cannot_be_renamed(client, monkeypatch):
    vault = open_vault(client)
    draft_id = draft_for(vault, make_pdf(vault.pdf_dir / "open in viewer.pdf"), PROPOSAL)

    def locked(src, dst):
        raise PermissionError("file is open")

    monkeypatch.setattr(library, "_rename", locked)
    result = wiki.approve(vault, draft_id)
    assert result["pdf"] == "pdf/open in viewer.pdf" and "이름을 바꾸지 못했습니다" in result["pdf_note"]
    assert vault.paper("kim2023computerized")["pdf"]["path"] == "pdf/open in viewer.pdf"
    assert wiki.tidy(vault, dry_run=True) == [{"paper": "kim2023computerized", "action": "would_rename", "from": "open in viewer.pdf", "to": PDF_NAME}]
    monkeypatch.undo()
    assert [c["action"] for c in wiki.tidy(vault)] == ["renamed"]
    assert vault.paper("kim2023computerized")["pdf"]["path"] == f"pdf/{PDF_NAME}" and wiki.tidy(vault) == []


def test_tidy_reconnects_pdfs_the_user_moved_and_applies_a_new_rule(client):
    approve_first(client)
    vault = Vault(client.vault_path)
    (vault.pdf_dir / "읽은 것").mkdir()
    (vault.pdf_dir / PDF_NAME).rename(vault.pdf_dir / "읽은 것" / "내가 바꾼 이름.pdf")
    assert client.get("/pdf/kim2023computerized").status_code == 404
    changes = wiki.tidy(vault)
    assert [c["action"] for c in changes] == ["relinked", "renamed"]
    assert vault.paper("kim2023computerized")["pdf"]["path"] == f"pdf/읽은 것/{PDF_NAME}"
    assert client.get("/pdf/kim2023computerized").status_code == 200

    # 이름 규칙을 바꾸면 이미 등록된 PDF 에도 적용된다
    r = client.post("/api/pdf-name", json={"pattern": "{author} {year} - {title}"})
    assert r.status_code == 200 and r.json()["renamed"] == 1
    renamed = "Kim et al. 2023 - Computerized cognitive training improves working memory in mild cognitive impairment.pdf"
    assert (vault.pdf_dir / "읽은 것" / renamed).exists()
    assert f"[[pdf/읽은 것/{renamed}|PDF 열기]]" in (client.vault_path / "papers" / "kim2023computerized.md").read_text(encoding="utf-8")
    assert client.get("/api/settings").json()["pdf_name"]["pattern"] == "{author} {year} - {title}"
    assert client.post("/api/pdf-name", json={"pattern": "{year}"}).status_code == 400

    (vault.pdf_dir / "읽은 것" / renamed).unlink()  # PDF 를 지운 경우: 알려 주기만 한다
    assert [c["action"] for c in wiki.tidy(vault)] == ["missing"]


def test_bibliographic_data_can_be_fixed_after_registration(client):
    approve_first(client)
    vault = Vault(client.vault_path)
    result = wiki.update_paper_meta(vault, "kim2023computerized", {"title": "Corrected title", "authors": "Gim, Jisu; Lee, Sang", "year": "2024", "doi": "https://doi.org/10.1/abc."})
    paper = result["paper"]
    assert paper["authors"] == [{"family": "Gim", "given": "Jisu"}, {"family": "Lee", "given": "Sang"}] and paper["doi"] == "10.1/abc"
    assert paper["pdf"]["path"] == "pdf/Corrected title(Gim et al.).pdf" and (vault.pdf_dir / "Corrected title(Gim et al.).pdf").exists()
    assert len(paper["claims"]) == 3, "주장과 키워드는 그대로다"
    assert "[[kim2023computerized|Gim & Lee (2024)]]" in (client.vault_path / "keywords" / "작업기억.md").read_text(encoding="utf-8")
    with pytest.raises(wiki.WikiError):
        wiki.update_paper_meta(vault, "kim2023computerized", {"title": "  "})


# ── Zotero 연동 ───────────────────────────────────────────────────────────


def test_paper_found_in_zotero_gets_its_metadata_and_citation_key(client):
    vault = open_vault(client)
    sloppy = json.loads(json.dumps(PROPOSAL))
    sloppy["paper"].update(title="COMPUTERIZED COGNITIVE TRAINING IMPROVES WORKING MEMORY", authors=[{"family": "Kim", "given": "J."}], venue="")
    draft_id = draft_for(vault, make_pdf(vault.pdf_dir / "a.pdf"), sloppy, zot=FakeZotero())
    review = wiki.review(vault, draft_id)
    assert review["zotero"] == {"key": "ABCD1234", "state": "linked"}
    assert review["citekey"] == "kimCCT2023", "Zotero 의 인용 키를 그대로 쓴다"
    assert review["paper"]["title"] == META["title"] and review["paper"]["venue"] == "Journal of Cognitive Health"
    assert "이미 Zotero 에 있는 논문" in wiki.review_text(review) and "서지 정보: Zotero 항목의 것" in wiki.review_text(review)
    wiki.approve(vault, draft_id)
    md = (client.vault_path / "papers" / "kimCCT2023.md").read_text(encoding="utf-8")
    assert "zotero://select/library/items/ABCD1234" in md and f"[[pdf/{PDF_NAME}|PDF 열기]]" in md

    # Zotero 에 없는 논문, Zotero 가 꺼져 있는 경우: 등록은 되고 상태만 알려 준다
    unknown = json.loads(json.dumps(PROPOSAL2))
    unknown["paper"]["doi"] = "10.9999/not-in-zotero"
    review = wiki.review(vault, draft_for(vault, make_pdf(vault.pdf_dir / "b.pdf", width=310), unknown, zot=FakeZotero()))
    assert review["zotero"] == {"key": None, "state": "not_found"} and review["citekey"] == "choi2021linear"
    off = wiki.review(vault, draft_for(vault, make_pdf(vault.pdf_dir / "c.pdf", width=320), {**unknown, "paper": {**unknown["paper"], "title": "Another paper"}}, zot=FakeZotero(fail=True)))
    assert off["zotero"]["state"] == "unreachable" and "꺼져 있어" in wiki.review_text(off)


def test_paper_in_zotero_can_be_pulled_into_the_paper_folder(client):
    vault = open_vault(client)
    info = library.pull_from_zotero(vault, FakeZotero(), "ABCD1234")
    assert info["pdf"] == "pdf/Kim et al. - 2023 - CCT.pdf" and info["zotero"] is True
    assert info["pages"] is None and info["parts"] == 1  # 쪽을 나눌 수 없는 PDF 는 통째로 맡긴다
    brief = Path(info["brief"]).read_text(encoding="utf-8")
    assert "already has this paper" in brief and "Title: Computerized cognitive training improves" in brief
    # 읽은 쪽이 제목을 다르게 적어도 Zotero 의 서지 정보가 기준이다
    wrong = json.loads(json.dumps(PROPOSAL))
    wrong["paper"] = {"title": "Wrong", "authors": [], "year": "", "venue": "", "doi": "", "item_type": "other"}
    Path(info["proposal"]).write_text(json.dumps(wrong, ensure_ascii=False), encoding="utf-8")
    review = wiki.propose(vault, info["id"])
    assert review["paper"]["title"] == META["title"] and review["zotero"]["key"] == "ABCD1234"
    paper = wiki.approve(vault, info["id"])["paper"]
    assert (paper["zotero_key"], paper["attachment_key"]) == ("ABCD1234", "ATT00001") and paper["pdf"]["path"] == f"pdf/{PDF_NAME}"
    # 이미 위키에 있는 Zotero 논문을 다시 가져오면 같은 문서를 고치는 검토안이 된다
    assert library.pull_from_zotero(vault, FakeZotero(), "ABCD1234")["replaces"] == "kim2023computerized"


def test_tidy_links_papers_to_zotero_later(client):
    approve_first(client)
    vault = Vault(client.vault_path)
    assert vault.paper("kim2023computerized")["zotero_key"] is None
    assert wiki.tidy(vault, zotero=FakeZotero(fail=True)) == [{"paper": "", "action": "zotero_unreachable", "note": "Zotero 앱에 연결하지 못했습니다."}]
    assert wiki.tidy(vault, zotero=FakeZotero()) == [{"paper": "kim2023computerized", "action": "zotero_linked", "to": "ABCD1234"}]
    assert "zotero://select/library/items/ABCD1234" in (client.vault_path / "papers" / "kim2023computerized.md").read_text(encoding="utf-8")


def test_zotero_client_local_mode(tmp_path):
    pdf = tmp_path / "storage" / "ATT00001" / "paper.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.7 real")
    item = {
        "key": "ABCD1234",
        "meta": {"parsedDate": "2023-05-01", "numChildren": 2},
        "data": {
            "key": "ABCD1234",
            "itemType": "journalArticle",
            "title": "A title: with a subtitle",
            "creators": [{"creatorType": "author", "firstName": "Jisoo", "lastName": "Kim"}, {"creatorType": "editor", "firstName": "E", "lastName": "Ditor"}],
            "date": "May 2023",
            "publicationTitle": "Journal",
            "DOI": "https://doi.org/10.1/x",
            "extra": "Citation Key: kim2023title\nPMID: 1",
            "abstractNote": "abs",
        },
    }
    children = [
        {"key": "NOTE0001", "data": {"key": "NOTE0001", "itemType": "note"}},
        {"key": "LINK0001", "data": {"key": "LINK0001", "itemType": "attachment", "linkMode": "linked_url", "contentType": "application/pdf"}},
        {"key": "ATT00001", "data": {"key": "ATT00001", "itemType": "attachment", "linkMode": "imported_url", "contentType": "application/pdf", "filename": "paper.pdf"}},
    ]
    seen = []
    synced = {"on": False}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, dict(request.url.params), request.headers.get("zotero-allowed-request")))
        path = request.url.path
        if path.endswith("/items/top"):
            return httpx.Response(200, json=[item, {"key": "N", "data": {"key": "N", "itemType": "note"}}], headers={"Total-Results": "2"})
        if path.endswith("/users/0/items"):
            link = '<http://127.0.0.1:23119/api/users/0/items?limit=1>; rel="last"'
            if synced["on"]:
                link += ', <https://www.zotero.org/users/1234567/items>; rel="alternate"'
            return httpx.Response(200, json=[item], headers={"Total-Results": "2", "Link": link})
        if path.endswith("/items/ABCD1234/children"):
            return httpx.Response(200, json=children)
        if path.endswith("/items/ABCD1234"):
            return httpx.Response(200, json=item)
        if path.endswith("/items/ATT00001/file"):
            return httpx.Response(302, headers={"Location": pdf.as_uri()})
        return httpx.Response(404)

    z = zotero.Zotero({"zotero_mode": "local", "zotero_data_dir": str(tmp_path / "nowhere")}, transport=httpx.MockTransport(handler))
    z.data_dir = None
    metas, total = z.items(q="kim")
    assert total == 2 and len(metas) == 1
    m = metas[0]
    assert (m["year"], m["doi"], m["citekey_hint"], m["venue"]) == ("2023", "10.1/x", "kim2023title", "Journal")
    assert m["authors"] == [{"family": "Kim", "given": "Jisoo"}]
    assert seen[0][0] == "/api/users/0/items/top" and seen[0][1]["qmode"] == "titleCreatorYear" and seen[0][2] == "1"
    att = z.pdf_attachment("ABCD1234")
    assert att["key"] == "ATT00001"
    assert z.pdf_bytes(att) == b"%PDF-1.7 real"  # 302 → file:// 경로를 따라가 읽는다

    # 같은 논문 찾기: DOI 가 같거나, 제목이 (구두점·대소문자를 빼고) 같을 때만
    seen.clear()
    assert z.find(doi="10.1/X")["zotero_key"] == "ABCD1234" and seen[0][1]["qmode"] == "everything"
    assert z.find(title="a title - with a SUBTITLE")["zotero_key"] == "ABCD1234"
    assert z.find(doi="10.1/other", title="A title") is None, "비슷하기만 한 제목은 같은 논문으로 보지 않는다"
    assert z.find(title="short") is None

    # Zotero 앱이 Zotero 계정에 로그인되어 있는지(= 다른 컴퓨터와 동기화되는지)를 알려준다
    assert z.ping() == {"ok": True, "mode": "local", "total": 2, "account_linked": False}
    synced["on"] = True
    assert z.ping()["account_linked"] is True

    z.data_dir = tmp_path  # 데이터 폴더가 있으면 API 호출 없이 바로 읽는다
    before = len(seen)
    assert z.pdf_bytes(att) == b"%PDF-1.7 real" and len(seen) == before

    def refused(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(zotero.ZoteroError, match="실행 중"):
        zotero.Zotero({"zotero_mode": "local"}, transport=httpx.MockTransport(refused)).ping()
    with pytest.raises(zotero.ZoteroError, match="로컬 API"):
        zotero.Zotero({"zotero_mode": "local"}, transport=httpx.MockTransport(lambda r: httpx.Response(403, text="Local API is not enabled"))).ping()
    with pytest.raises(zotero.ZoteroError, match="API 키"):
        zotero.Zotero({"zotero_mode": "web"})


# ── 명령줄 (Claude Code 스킬이 쓰는 길) ──────────────────────────────────────


def test_command_line_flow_from_inbox_to_wiki(tmp_path, capsys):
    config.save({**config.DEFAULTS})
    root = tmp_path / "내 드라이브" / "Paper Wiki"  # 한글과 공백이 있는 경로
    assert cli.main(["setup", "--vault", str(root)]) == 0
    vault = Vault(root)
    make_pdf(vault.pdf_dir / "스캔본 final (2).pdf")
    capsys.readouterr()

    assert cli.main(["inbox", "--json"]) == 0
    inbox = json.loads(capsys.readouterr().out)
    assert [f["path"] for f in inbox["new"]] == ["pdf/스캔본 final (2).pdf"] and inbox["pending"] == []

    assert cli.main(["prepare", "스캔본 final (2).pdf", "--json"]) == 0
    info = json.loads(capsys.readouterr().out)[0]
    assert Path(info["brief"]).is_file() and info["replaces"] is None

    # 제안 파일이 아직 없거나 형식이 틀리면: 위키는 그대로이고, 무엇을 고칠지 알려 준다
    assert cli.main(["propose", info["id"]]) == 1 and "제안 파일이 아직 없습니다" in capsys.readouterr().err
    Path(info["proposal"]).write_text(json.dumps({"paper": {"title": ""}, "references": [{"ref": "1", "title": "t"}], "claims": [{"statement": "x", "type": "result", "refs": ["1", "8"], "keywords": []}]}), encoding="utf-8")
    assert cli.main(["propose", info["id"]]) == 1
    err = capsys.readouterr().err
    assert "paper.title" in err and "claims[1].type" in err and "claims[1].keywords" in err and "claims[1].refs 의 8 이(가) references 에 없습니다" in err
    assert vault.pending_all() == []

    # 주장이 많으면 에이전트가 여러 파일로 나눠 쓴다: proposal.json + claims_2.json …
    first = {**PROPOSAL, "claims": PROPOSAL["claims"][:2]}
    Path(info["proposal"]).write_text("```json\n" + json.dumps(first, ensure_ascii=False) + "\n```", encoding="utf-8")
    Path(info["proposal"]).with_name("claims_2.json").write_text(json.dumps(PROPOSAL["claims"][2:], ensure_ascii=False), encoding="utf-8")
    assert cli.main(["propose", info["id"]]) == 0
    out = capsys.readouterr().out
    assert "아직 위키에 등록되지 않았습니다" in out and "인용 키: @kim2023computerized" in out
    assert f"스캔본 final (2).pdf → 등록하면 이름이 `{PDF_NAME}` 로 바뀝니다" in out
    assert "### 등록되는 것: 주장 3개 · 인용 문헌 3편 (새 문헌 3 · 이미 위키에 있는 문헌 0)" in out
    assert "   - 인용 문헌: [2] Lampit et al. (2014); [3] Hill et al. (2017)" in out
    assert "연구 주제 › 경도인지장애 › 전산화 인지훈련 (새 키워드)" in out and "### 새로 만들어질 키워드 4개" in out
    assert "“Computerized training improves working memory in older adults [2,3].” (p.1)" in out
    assert "- [3] Hill et al. (2017). Computerized cognitive training in older adults with mild cognitive impairment or dementia. Am. J. Psychiatry. → @hill2017computerized · 주장 2개" in out
    assert "어느 주장에도 연결되지 않아 등록되지 않는 참고문헌: [1] Petersen (2004)" in out
    assert vault.papers() == {}, "propose 는 위키에 아무것도 넣지 않는다"
    assert cli.main(["review", info["id"]]) == 0 and "### 주장 3개" in capsys.readouterr().out

    assert cli.main(["approve", info["id"]]) == 0
    out = capsys.readouterr().out
    assert "등록했습니다: @kim2023computerized" in out and f"pdf/스캔본 final (2).pdf → pdf/{PDF_NAME}" in out
    assert "인용 문헌 : 새로 등록 3편 · 이미 위키에 있던 문헌에 연결 0편" in out
    assert cli.main(["approve", info["id"]]) == 1 and "검토안을 찾을 수 없습니다" in capsys.readouterr().err

    assert cli.main(["inbox"]) == 0 and "새 PDF — 0편" in capsys.readouterr().out
    assert cli.main(["search", "working memory", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["references"]["kim2023computerized"]["pdf"] == f"pdf/{PDF_NAME}"
    assert cli.main(["show", "@kim2023computerized"]) == 0 and "# Computerized cognitive training" in capsys.readouterr().out
    assert cli.main(["show", "CCT"]) == 0 and "# 전산화 인지훈련" in capsys.readouterr().out
    assert cli.main(["show", "@hill2017computerized"]) == 0 and "## 이 문헌을 인용해 할 수 있는 주장 (2)" in capsys.readouterr().out
    assert cli.main(["tree"]) == 0 and "- 작업기억 (working memory)  — 주장 1, 인용 문헌 2" in capsys.readouterr().out
    assert cli.main(["papers"]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("- @kim2023computerized  Kim et al. (2023)") and "읽은 논문 · 주장 3" in out
    assert "- @hill2017computerized  Hill et al. (2017) Computerized cognitive training in older adults with mild cognitive impairment or dementia — 인용 문헌 · 논문 1편이 주장 2개에 인용 · 방향 2" in out
    assert cli.main(["papers", "--cited", "--sort", "directions", "--json"]) == 0
    assert [r["citekey"] for r in json.loads(capsys.readouterr().out)] == ["hill2017computerized", "lampit2014computerized", "bates2015fitting"]
    assert cli.main(["search", "작업기억 향상"]) == 0
    out = capsys.readouterr().out
    assert "인용 문헌: Lampit et al. (2014) (@lampit2014computerized); Hill et al. (2017) (@hill2017computerized)" in out and "출처: Kim et al. (2023) (@kim2023computerized)" in out
    assert cli.main(["insights"]) == 0
    out = capsys.readouterr().out
    assert "## 여러 방향으로 인용된 문헌" in out and "(@hill2017computerized) — 방향 2: " in out and "아직 없음 (읽은 논문이 두 편 이상 쌓이면 나타납니다)" in out
    assert cli.main(["fix", "@kim2023computerized", "--year", "2024"]) == 0 and "(2024)" in capsys.readouterr().out
    assert cli.main(["naming"]) == 0 and "{title}({author})" in capsys.readouterr().out
    assert cli.main(["tidy"]) == 0 and "정리할 것이 없습니다" in capsys.readouterr().out
    assert cli.main(["prepare", PDF_NAME]) == 1 and "이미 위키에 등록되어 있습니다" in capsys.readouterr().err
    assert cli.main(["doctor"]) == 0 and "읽은 논문 1 · 인용 문헌 3" in capsys.readouterr().out


def test_proposal_file_is_checked_before_it_becomes_a_draft():
    ok = extract.parse_proposal("\ufeff" + json.dumps(PROPOSAL))
    assert ok["paper"]["title"] == META["title"] and len(ok["claims"]) == 3
    messy = extract.parse_proposal(json.dumps({
        "paper": {"title": "  A  title ", "authors": ["WHO", {"name": "Lab"}, {"family": "Kim", "given": "J"}, {}], "year": "Published 2021 May", "doi": "doi: 10.1/X.", "item_type": "weird"},
        "references": [{"ref": "[7]", "title": " Some  title. ", "authors": ["Kim J"], "year": "(2019).", "doi": "https://doi.org/10.2/Y"}, {"ref": "7", "title": "duplicate label"}],
        "claims": [{"statement": "s", "type": "finding", "refs": [7], "keywords": [{"path": ["연구 주제", "k"]}]}],
    }), more_claims=[json.dumps([{"statement": "t", "type": "method", "refs": ["7."], "keywords": [{"path": ["방법론", "m"]}]}])])
    assert messy["paper"] == {"title": "A title", "authors": [{"name": "WHO"}, {"name": "Lab"}, {"family": "Kim", "given": "J"}], "year": "2021", "venue": "", "doi": "10.1/X", "item_type": "other"}
    assert messy["references"] == [{"ref": "7", "title": "Some title", "authors": [{"name": "Kim J"}], "et_al": False, "year": "2019", "venue": "", "doi": "10.2/Y"}]
    assert messy["summary"] == "" and messy["note"] == "" and len(messy["claims"]) == 2, "나눠 쓴 주장 파일이 이어 붙는다"
    assert [c["refs"] for c in wiki.clean_claims(messy["claims"])] == [["7"], ["7"]]
    ref = [{"ref": "1", "title": "t"}]
    for bad, expected in (
        ("not json", "JSON 으로 읽을 수 없습니다"),
        ("[1]", "객체"),
        (json.dumps({"paper": {"title": "t"}, "references": ref, "claims": []}), "claims 가 비어"),
        (json.dumps({"paper": {"title": "t"}, "claims": [{"statement": "s", "type": "finding", "refs": ["1"], "keywords": [{"path": ["a"]}]}]}), "references 가 비어"),
        (json.dumps({"paper": {"title": "t"}, "references": ref, "claims": [{"statement": "s", "type": "finding", "refs": [], "keywords": [{"path": ["a"]}]}]}), "refs 가 비어"),
        (json.dumps({"paper": {"title": "t"}, "references": [{"ref": "1", "title": ""}], "claims": [{"statement": "s", "type": "finding", "refs": ["1"], "keywords": [{"path": ["a"]}]}]}), "title 이 비어"),
    ):
        with pytest.raises(extract.ProposalError, match=expected):
            extract.parse_proposal(bad)


def test_clean_claims_tolerates_messy_input():
    cleaned = wiki.clean_claims([
        {"statement": "  a   b ", "type": "weird", "refs": ["[3]", 3, " 12 ", ""], "same_as": "not-an-id", "evidence": None,
         "keywords": [{"path": ["X", "Y"]}, {"path": ["Z", "y"]}, {"path": []}, "junk"]},
        "junk",
    ])
    assert len(cleaned) == 1
    c = cleaned[0]
    assert c["statement"] == "a b" and c["type"] == "finding" and c["include"] is True
    assert c["refs"] == ["3", "12"] and c["group"] == "" and c["evidence"] == {"quote": "", "location": ""}
    assert wiki.clean_claims([{"statement": "s", "same_as": "g0a1b2c3d"}])[0]["group"] == "g0a1b2c3d"
    assert [k["path"] for k in c["keywords"]] == [["X", "Y"]]  # 같은 키워드는 한 번만


def test_new_top_level_category_is_flagged_for_review(client):
    vault = open_vault(client)
    odd = json.loads(json.dumps(PROPOSAL2))
    odd["paper"].update(authors=[], year="")
    odd["claims"] = odd["claims"][:1]
    odd["claims"][0]["keywords"] = [{"path": ["통계 기법", "LMM"], "aliases": [], "description": ""}]
    odd["note"] = "pages 3-4 are scanned images"
    review = wiki.review(vault, draft_for(vault, make_pdf(vault.pdf_dir / "a.pdf"), odd))
    assert review["new_keywords"] == [{"name": "통계 기법", "under": []}, {"name": "LMM", "under": ["통계 기법"]}]
    text = wiki.review_text(review)
    assert "'통계 기법' 이(가) 새 최상위 분류로 만들어집니다" in text and "저자 정보가 비어 있습니다" in text and "출판 연도 정보가 비어 있습니다" in text
    assert "읽은 쪽의 메모: pages 3-4 are scanned images" in text


def test_review_counts_come_from_the_files_not_from_the_readers_note(client):
    """읽은 쪽이 메모에 적은 개수는 틀릴 수 있다 (마지막 파일을 쓰기 전에 적는다). 개수는 프로그램이 파일에서 센다."""
    vault = open_vault(client)
    split = json.loads(json.dumps(PROPOSAL))
    extra = [dict(split["claims"][0], statement="나눠 쓴 파일의 주장.", refs=["2"])]
    split["note"] = "Total 7 claims: 5 in proposal.json, 2 in claims_2.json. All 9 references are used."  # 실제와 다른 숫자
    info = library.prepare(vault, str(make_pdf(vault.pdf_dir / "split.pdf")))
    Path(info["proposal"]).write_text(json.dumps(split, ensure_ascii=False), encoding="utf-8")
    (Path(info["proposal"]).parent / "claims_2.json").write_text(json.dumps(extra, ensure_ascii=False), encoding="utf-8")
    review = wiki.propose(vault, info["id"])
    n_claims, used = len(split["claims"]) + 1, {r for c in split["claims"] + extra for r in c["refs"]}
    assert review["counts"]["claims"] == n_claims and review["counts"]["claim_files"] == [len(split["claims"]), 1]
    assert review["counts"]["references"] == 4 and review["counts"]["references_used"] == len(used)
    text = wiki.review_text(review)
    counted = next(line for line in text.splitlines() if "프로그램이 직접 센 것" in line)
    assert f"주장 {n_claims}개 (파일 2개에 {len(split['claims'])} · 1)" in counted
    assert ("참고문헌 목록 4편 — 모두 주장에 연결됨" if len(used) == 4 else f"참고문헌 목록 4편 — {len(used)}편이 주장에 연결됨, {4 - len(used)}편은 연결되지 않음") in counted
    assert text.index("프로그램이 직접 센 것") < text.index("읽은 쪽의 메모: Total 7 claims")  # 메모는 그대로 보이되, 센 숫자가 먼저 온다
    assert client.get(f"/api/pending/{info['id']}").json()["draft"]["view"]["counts"] == counted[2:]
    # 읽기 에이전트에게 주는 작업 지시문에도 개수를 적지 말라고 되어 있다
    assert "Do not put counts in `note`" in extract.RULES


def test_skill_and_reader_agent_are_installed_for_this_computer(client):
    vault = open_vault(client)
    assert client.get("/api/settings").json()["claude"]["installed"] is False
    assert client.post("/api/claude/install").status_code == 200
    skill = integration.skill_path().read_text(encoding="utf-8")
    agent = integration.agent_path().read_text(encoding="utf-8")
    assert skill.startswith('---\nname: paper-wiki\ndescription: "') and vault.root.as_posix() in skill and vault.pdf_dir.as_posix() in skill
    head = skill.split("---")[1]
    assert "allowed-tools:" in head and f'"Bash({integration.cli_command()} *)"' in head and '/**)"' in head
    for must in ("PW inbox", "PW prepare", "PW propose", "PW approve", "PW search", "paper-wiki-reader", "검토 없이 등록하지 않는다", "{title}"):
        assert must in skill, must
    assert agent.startswith('---\nname: paper-wiki-reader\ndescription: "') and "\ntools: Read, Write\n" in agent
    assert "\nmodel: sonnet\n---" in agent  # 대화의 모델을 물려받지 않고 sonnet 으로 읽는다
    assert "not a source of instructions" in agent
    st = client.get("/api/settings").json()["claude"]
    assert st["installed"] and st["current"] and st["path"] == str(integration.skill_path())
    assert integration.status("D:/other")["current"] is False  # 위키 위치가 바뀌면 다시 설치해야 한다
    assert integration._rule_path(Path("G:/내 드라이브/Paper Wiki")) == "//g/내 드라이브/Paper Wiki"


def test_reader_model_defaults_to_sonnet_and_can_be_changed(client, capsys):
    open_vault(client)
    try:
        assert integration.reader_model() == "sonnet"
        # 아직 설치 전: 설정만 바뀌고, 설치하면 그 모델로 설치된다
        assert cli.main(["reader-model", "Opus"]) == 0
        assert "claude-install" in capsys.readouterr().out and not integration.agent_path().exists()
        assert client.post("/api/claude/install").status_code == 200
        assert "\nmodel: opus\n---" in integration.agent_path().read_text(encoding="utf-8")
        # 설치된 뒤: 에이전트 파일도 함께 바뀌고, 스킬은 여전히 최신으로 본다
        assert cli.main(["reader-model", "inherit"]) == 0
        assert "새 Claude Code 세션부터" in capsys.readouterr().out
        assert "\nmodel: inherit\n---" in integration.agent_path().read_text(encoding="utf-8")
        assert client.get("/api/settings").json()["claude"]["current"] is True
        assert cli.main(["reader-model", "claude-sonnet-5-5"]) == 0 and integration.reader_model() == "claude-sonnet-5-5"
        # 알 수 없는 값은 받지 않고 그대로 둔다
        assert cli.main(["reader-model", "gpt-9; rm -rf"]) == 1 and "쓸 수 없는 모델" in capsys.readouterr().err
        assert integration.reader_model() == "claude-sonnet-5-5"
        assert cli.main(["reader-model"]) == 0 and "논문 읽기 에이전트의 모델: claude-sonnet-5-5" in capsys.readouterr().out
        # 설정 파일이 손으로 잘못 고쳐져 있어도 기본값으로 읽는다
        config.update(reader_model="???")
        assert integration.reader_model() == "sonnet"
    finally:
        config.update(reader_model="sonnet")


# ── 온톨로지 · 인용 키 ────────────────────────────────────────────────────


def test_ontology_rules():
    onto = Ontology()
    root = onto.add("방법론")
    kid, created = onto.ensure_path(["방법론", "분석 방법", "혼합효과모형"], ["mixed-effects model", "LMM"])
    assert len(created) == 2 and onto.path_names(kid) == ["방법론", "분석 방법", "혼합효과모형"]
    assert onto.ensure_path(["아무 경로", "Mixed Effects  Model"]) == (kid, [])  # 별칭·대소문자·하이픈 무시
    assert norm("Mixed-Effects_Model") == norm("mixed effects model")
    with pytest.raises(OntologyError):
        onto.add("lmm")
    with pytest.raises(OntologyError):
        onto.move(root["id"], kid)
    with pytest.raises(OntologyError):
        onto.remove(root["id"])
    a = onto.add("A/B: 테스트?")
    assert a["file"] == "A B 테스트"


def test_citekey_generation():
    assert wiki.make_citekey(META, set()) == "kim2023computerized"
    assert wiki.make_citekey(META, {"kim2023computerized"}) == "kim2023computerizeda"
    assert wiki.make_citekey({**META, "citekey_hint": "kimCCT2023"}, set()) == "kimCCT2023"
    korean = {"authors": [{"family": "김", "given": "지수"}], "year": "2022", "title": "경도인지장애 인지훈련 효과"}
    assert wiki.make_citekey(korean, set()) == "김2022경도인지장애"
    assert render.cite_short(korean) == "김지수 (2022)"


# ── 구글 드라이브 데스크톱: 계정 선택과 설치 안내 ─────────────────────────────


def test_settings_offers_one_choice_per_google_account(client, tmp_path, monkeypatch):
    a, b = tmp_path / "G" / "내 드라이브", tmp_path / "H" / "My Drive"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    mounts = [
        {"root": a, "mount": "G:", "label": "Google Drive", "mode": "stream", "email": "me@example.com"},
        {"root": b, "mount": "H:", "label": "work@example.org", "mode": "stream", "email": "work@example.org"},
    ]
    monkeypatch.setattr(gdrive, "detect", lambda: mounts)
    monkeypatch.setattr(gdrive, "is_installed", lambda: True)
    data = client.get("/api/settings").json()
    assert data["gdrive"]["state"] == "ready"
    drives = [o for o in data["storage_options"] if o["kind"] == "gdrive"]
    assert [(o["email"], o["path"]) for o in drives] == [("me@example.com", str(a / "PaperWiki")), ("work@example.org", str(b / "PaperWiki"))]
    assert data["storage_options"][-1]["kind"] == "local"

    # 두 번째 계정의 드라이브를 고르면 그 계정으로 표시된다
    assert client.post("/api/vault", json={"path": drives[1]["path"], "language": "ko"}).status_code == 200
    data = client.get("/api/settings").json()
    assert (data["storage_kind"], data["storage_account"]) == ("gdrive", "work@example.org")
    assert data["pdf_dir"] == str(b / "PaperWiki" / "pdf") and (b / "PaperWiki" / "pdf").is_dir()
    assert [o["exists"] for o in data["storage_options"] if o["kind"] == "gdrive"] == [False, True]  # 다른 기기에서는 "기존 위키 발견"
    assert "work@example.org" in client.get("/").text


def test_settings_asks_to_install_or_start_google_drive(client, monkeypatch):
    data = client.get("/api/settings").json()  # 기본: 설치되어 있지 않음
    assert data["gdrive"]["state"] == "not_installed" and data["gdrive"]["download_url"].startswith("https://www.google.com/drive")
    assert [o["kind"] for o in data["storage_options"]] == ["local"]
    assert client.post("/api/gdrive/launch").status_code == 400

    launched = []
    monkeypatch.setattr(gdrive, "is_installed", lambda: True)
    monkeypatch.setattr(gdrive, "can_launch", lambda: True)
    monkeypatch.setattr(gdrive, "launch", lambda: launched.append(1) or True)
    data = client.get("/api/settings").json()  # 설치는 됐지만 꺼져 있음
    assert data["gdrive"] == {"state": "not_running", "can_launch": True, "download_url": gdrive.DOWNLOAD_URL}
    assert client.post("/api/gdrive/launch").status_code == 200 and launched == [1]


def _fake_drivefs_account(base, account_id, email):
    d = base / account_id
    d.mkdir(parents=True)
    con = sqlite3.connect(d / "metadata_sqlite_db")
    con.execute("create table properties (property text primary key, value blob)")
    mail = email.encode()
    blob = b"\x0a\x15" + account_id.encode() + b"\x12\x05(Lab)*\x20https://lh3.example/photo=s64B" + bytes([len(mail)]) + mail + b"Z\x15" + account_id.encode()
    con.execute("insert into properties values ('driveway_account', ?)", (blob,))
    con.execute("insert into properties values ('root_id', 'abc')")
    con.commit()
    con.close()


def test_account_email_is_read_from_drive_desktop_data(tmp_path):
    base = tmp_path / "DriveFS"
    _fake_drivefs_account(base, "114700000000000000001", "me@example.com")
    _fake_drivefs_account(base, "114700000000000000002", "work@example.org")
    (base / "Logs").mkdir()
    (base / "114700000000000000003").mkdir()  # 데이터가 없는 계정 폴더
    broken = base / "114700000000000000004"
    broken.mkdir()
    (broken / "metadata_sqlite_db").write_bytes(b"not a database")
    assert gdrive.account_emails(base) == {"114700000000000000001": "me@example.com", "114700000000000000002": "work@example.org"}
    assert gdrive.account_emails(tmp_path / "missing") == {}


def test_email_is_cut_exactly_out_of_binary_data():
    def field(tag: bytes, text: str) -> bytes:
        return tag + bytes([len(text)]) + text.encode()

    # 이메일 뒤에 붙은 다음 항목의 표식이 글자('Z', 'r')여도 주소에 딸려 오지 않는다
    assert gdrive.email_from_blob(field(b"B", "reader@example.com") + field(b"Z", "114700000000000000001")) == "reader@example.com"
    assert gdrive.email_from_blob(b"\x08\x01" + field(b"B", "a.b-c@lab.example.org") + field(b"r", "name")) == "a.b-c@lab.example.org"
    # 길이 바이트 자체가 글자로 보이는 긴 주소(48자 = '0')도 앞뒤가 정확하다
    long_mail = "x" * 36 + "@example.org"
    assert len(long_mail) == 48 and gdrive.email_from_blob(field(b"B", long_mail) + field(b"Z", "id")) == long_mail
    # 길이가 맞아떨어지지 않으면 틀린 주소를 내놓지 않는다
    assert gdrive.email_from_blob(b"\x00\x03someone@example.comZ") is None
    assert gdrive.email_from_blob(b"no email here") is None


def test_drives_are_matched_to_accounts_only_when_certain():
    accounts = {"1": "me@example.com", "2": "work@example.org"}

    def mounts(*specs):
        return [{"mount": letter, "label": label, "email": None} for letter, label in specs]

    one = mounts(("G:", "Google Drive"))  # 계정 하나, 드라이브 하나
    gdrive.assign_emails(one, {"1": "me@example.com"}, {}, "1")
    assert one[0]["email"] == "me@example.com"

    two = mounts(("G:", "Google Drive"), ("H:", "work@example.org"))  # 추가 계정은 드라이브 이름이 이메일
    gdrive.assign_emails(two, accounts, {}, "1")
    assert [m["email"] for m in two] == ["me@example.com", "work@example.org"]

    by_letter = mounts(("G:", "Google Drive"), ("K:", "Google Drive"))  # 사용자가 드라이브 문자를 지정한 경우
    gdrive.assign_emails(by_letter, accounts, {"2": "K"}, "1")
    assert [m["email"] for m in by_letter] == ["me@example.com", "work@example.org"]

    unclear = mounts(("G:", "Google Drive"), ("H:", "Google Drive"))  # 알 수 없으면 추측하지 않는다
    gdrive.assign_emails(unclear, accounts, {}, "1")
    assert [m["email"] for m in unclear] == [None, None]

    stale = mounts(("G:", "Google Drive"))  # 로그아웃한 옛 계정의 흔적이 남아 있어도 현재 계정으로
    gdrive.assign_emails(stale, accounts, {}, "2")
    assert stale[0]["email"] == "work@example.org"

    nothing = mounts(("G:", "Google Drive"))  # 이메일을 못 읽은 경우
    gdrive.assign_emails(nothing, {}, {}, "")
    assert nothing[0]["email"] is None


def test_old_folder_named_like_drive_is_not_offered(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "내 드라이브").mkdir(parents=True)  # 이름만 같은 옛 폴더 (동기화되지 않음)
    synced = home / "My Drive"
    (synced / ".tmp.driveupload").mkdir(parents=True)  # 실제로 미러링 중인 폴더
    monkeypatch.setattr(gdrive.Path, "home", classmethod(lambda cls: home))
    found = gdrive._mirror_mounts(None, {})
    assert [m["root"] for m in found] == [synced] and found[0]["mode"] == "mirror"


# ── 다른 컴퓨터에서 만든 위키 불러오기 ───────────────────────────────────────


def test_wiki_made_on_another_computer_is_found_and_loaded(client, tmp_path, monkeypatch):
    g, h = tmp_path / "G" / "내 드라이브", tmp_path / "H" / "내 드라이브"
    g.mkdir(parents=True)
    h.mkdir(parents=True)
    mounts = [
        {"root": g, "mount": "G:", "label": "Google Drive", "mode": "stream", "email": "me@example.com"},
        {"root": h, "mount": "H:", "label": "work@example.org", "mode": "stream", "email": "work@example.org"},
    ]
    monkeypatch.setattr(gdrive, "detect", lambda: mounts)
    monkeypatch.setattr(gdrive, "is_installed", lambda: True)

    # 컴퓨터 A: 기본 위치가 아닌 하위 폴더에 위키를 만들고, 논문 한 편을 등록하고, 한 편은 검토 대기로 남겨 둔다
    client.vault_path = g / "연구" / "MyWiki"
    approve_first(client)
    vault_a = Vault(client.vault_path)
    waiting = draft_for(vault_a, make_pdf(vault_a.pdf_dir / "choi draft.pdf", width=310), PROPOSAL2)
    before = {f: f.stat().st_mtime_ns for f in client.vault_path.rglob("*") if f.is_file()}

    # 컴퓨터 B: 같은 드라이브가 보이지만 이 컴퓨터의 설정은 비어 있고, A 의 작업 폴더도 없다
    config.save({**config.DEFAULTS})
    server._vault_cache.clear()
    library.cleanup_work(waiting)
    data = client.get("/api/settings", params={"rescan": 1}).json()
    assert data["vault_state"] == "none"
    drives = [o for o in data["storage_options"] if o["kind"] == "gdrive"]
    assert [(o["email"], o["exists"]) for o in drives] == [("me@example.com", True), ("work@example.org", False)]
    found = drives[0]
    assert found["path"] == str(client.vault_path), "기본 위치가 아니어도 찾아야 한다"
    assert found["summary"]["papers"] == 4 and found["summary"]["keywords"] == 10 and found["summary"]["pending"] == 1 and found["summary"]["modified"]
    assert drives[1]["path"] == str(h / "PaperWiki") and drives[1]["summary"] is None

    r = client.post("/api/vault", json={"path": found["path"], "language": "en"})
    assert r.status_code == 200 and r.json()["connected_existing"] is True and r.json()["summary"]["papers"] == 4
    after = {f: f.stat().st_mtime_ns for f in client.vault_path.rglob("*") if f.is_file()}
    assert after == before, "불러오기는 위키의 어떤 파일도 바꾸지 않는다"

    data = client.get("/api/settings").json()
    assert data["stats"]["papers"] == 1 and data["language"] == "ko" and data["stats"]["pending"] == 1
    assert data["claude"]["installed"] is False, "스킬은 컴퓨터마다 따로 설치한다"

    # A 에서 만들어 둔 검토안을 B 에서 이어서 검토하고 등록할 수 있다 (PDF 이름도 B 에서 바뀐다)
    assert client.get(f"/pdf/draft/{waiting}").status_code == 200
    draft = client.get(f"/api/pending/{waiting}").json()["draft"]
    r = client.post(f"/api/pending/{waiting}/approve", json={"summary": draft["summary"], "claims": draft["claims"]})
    assert r.status_code == 200 and r.json()["pdf"] == "pdf/Linear mixed models for longitudinal cognitive data(Choi).pdf"
    assert (client.vault_path / "pdf" / "Linear mixed models for longitudinal cognitive data(Choi).pdf").exists()


def test_find_vaults_looks_a_few_levels_deep(tmp_path):
    def make(*parts):
        v = Vault(tmp_path.joinpath(*parts))
        v.init("ko")
        return v.root

    a = make("PaperWiki")
    b = make("연구", "문헌", "위키")
    make("PaperWiki", "inner")          # 위키 안의 위키는 따로 세지 않는다
    make(".hidden", "wiki")             # 숨김 폴더는 훑지 않는다
    make("a", "b", "c", "too-deep")     # 너무 깊은 곳은 찾지 않는다
    (tmp_path / "그냥 폴더" / "하위").mkdir(parents=True)
    assert sorted(find_vaults(tmp_path)) == sorted([a, b])
    assert find_vaults(tmp_path, max_depth=1) == [a]
    assert find_vaults(tmp_path / "없는 폴더") == []


def test_partly_synced_wiki_stops_work_instead_of_overwriting(client):
    approve_first(client)
    root = client.vault_path
    vault = Vault(root)
    onto_file = root / ".paperwiki" / "ontology.json"
    original_onto = onto_file.read_bytes()
    kw_md = (root / "keywords" / "전산화 인지훈련.md").read_text(encoding="utf-8")
    waiting = draft_for(vault, make_pdf(vault.pdf_dir / "choi draft.pdf", width=310), PROPOSAL2)

    # 다른 컴퓨터가 올린 논문 파일이 아직 내용 없이 이름만 보이는 상태
    ghost = root / ".paperwiki" / "papers" / "other2020paper.json"
    ghost.write_bytes(b"")
    for url in ("/", "/wiki", "/papers", "/inbox"):
        r = client.get(url)
        assert r.status_code == 503 and "아직 다 읽을 수 없습니다" in r.text, url
    assert client.get("/api/search", params={"q": "작업기억"}).status_code == 503
    kid = next(iter(json.loads(original_onto)["nodes"]))
    assert client.put(f"/api/keywords/{kid}", json={"name": "바뀐 이름"}).status_code == 503
    assert client.post("/api/rebuild").status_code == 503
    assert client.post("/api/pdf-name", json={"pattern": "{year} {title}"}).status_code == 503
    # 논문 추가도 멈춘다: 읽을 준비도, 등록도 하지 않고, PDF 이름도 건드리지 않는다
    with pytest.raises(VaultUnavailable):
        wiki.approve(vault, waiting)
    with pytest.raises(VaultUnavailable):
        wiki.tidy(vault)
    assert cli.main(["approve", waiting]) == 1
    assert (vault.pdf_dir / "choi draft.pdf").exists() and vault.pending(waiting) is not None
    assert onto_file.read_bytes() == original_onto
    assert (root / "keywords" / "전산화 인지훈련.md").read_text(encoding="utf-8") == kw_md, "일부만 읽힌 상태로 문서를 다시 쓰지 않는다"
    settings = client.get("/api/settings")  # 설정 화면은 이 상태에서도 열린다
    assert settings.status_code == 200 and "읽을 수 없습니다" in settings.json()["vault_warning"]
    ghost.unlink()
    assert client.get("/").status_code == 200

    # 키워드 파일을 읽지 못하는 상태: 빈 온톨로지로 덮어쓰면 안 된다
    onto_file.write_bytes(b"{ not json")
    assert client.post("/api/keywords", json={"name": "새 키워드"}).status_code == 503
    with pytest.raises(VaultUnavailable):
        library.prepare(vault, str(make_pdf(vault.pdf_dir / "another.pdf", width=320)))
    assert onto_file.read_bytes() == b"{ not json"
    # 이런 위키에는 새로 연결하지도 않는다
    config.save({**config.DEFAULTS})
    server._vault_cache.clear()
    r = client.post("/api/vault", json={"path": str(root), "language": "ko"})
    assert r.status_code == 503 and config.load()["vault_path"] == ""
    onto_file.write_bytes(original_onto)
    assert client.post("/api/vault", json={"path": str(root), "language": "ko"}).json()["connected_existing"] is True
    assert client.get("/api/settings").json()["stats"]["papers"] == 1


# ── Zotero 에 넣기 · DOI 등록 기록 ─────────────────────────────────────────


def test_registered_paper_is_added_to_zotero_when_it_is_not_there(client):
    approve_first(client)
    vault = Vault(client.vault_path)
    assert vault.paper("kim2023computerized")["zotero_key"] is None, "Zotero 가 꺼져 있어도 위키 등록은 된다"

    # 미리 보기: 아무것도 바꾸지 않는다
    z = FakeZotero(empty=True)
    assert wiki.zotero_sync(vault, z, add=True, collection="Paper Wiki", dry_run=True) == [{"paper": "kim2023computerized", "action": "zotero_would_add"}]
    assert z.added == [] and vault.paper("kim2023computerized")["zotero_key"] is None

    # 항목 추가를 허용받지 못했으면 넣지 않고, 무엇을 해야 하는지 알려 준다
    locked = FakeZotero(empty=True, writable=False)
    changes = wiki.zotero_sync(vault, locked, add=True, collection="Paper Wiki")
    assert [c["action"] for c in changes] == ["zotero_need_connect"] and "paperwiki zotero connect" in wiki.zotero_report(changes)[0]
    assert vault.paper("kim2023computerized")["zotero_key"] is None

    # Zotero 에 없는 읽은 논문은 새 항목으로 들어간다: 위키의 PDF 를 링크하고, 컬렉션에 넣는다. 인용 문헌은 넣지 않는다
    changes = wiki.zotero_sync(vault, z, add=True, collection="Paper Wiki")
    assert changes == [{"paper": "kim2023computerized", "action": "zotero_added", "to": "NEW00001", "pdf": True, "note": ""}]
    assert z.added == [("kim2023computerized", PDF_NAME, "Paper Wiki")]
    paper = vault.paper("kim2023computerized")
    assert (paper["zotero_key"], paper["attachment_key"], paper["zotero_pdf"]) == ("NEW00001", "LNK00001", "linked")
    assert "zotero://select/library/items/NEW00001" in (client.vault_path / "papers" / "kim2023computerized.md").read_text(encoding="utf-8")
    assert all(not p.get("zotero_key") for p in vault.papers().values() if not render.is_read(p))
    assert "새 항목으로 넣었습니다" in wiki.zotero_report(changes, one_paper=True)[0] and "PDF 링크 포함" in wiki.zotero_report(changes, one_paper=True)[0]

    # 다시 맞추면: 컬렉션에 넣는 것만 남아 있고, 그다음부터는 바뀌는 것이 없다
    assert wiki.zotero_sync(vault, z, add=True, collection="Paper Wiki") == [{"paper": "kim2023computerized", "action": "zotero_collected", "to": "Paper Wiki"}]
    assert wiki.zotero_sync(vault, z, add=True, collection="Paper Wiki") == [] and len(z.added) == 1

    # 위키에서 PDF 이름이 바뀌면(서지 정보 수정) Zotero 의 PDF 링크도 따라 바뀐다
    wiki.update_paper_meta(vault, "kim2023computerized", {"title": "A corrected title"})
    assert wiki.zotero_sync(vault, z, add=True, collection="Paper Wiki") == [{"paper": "kim2023computerized", "action": "zotero_relinked", "to": "A corrected title(Kim et al.).pdf"}]

    # 넣기를 꺼 두면(add=False) 찾아서 연결만 한다
    assert wiki.zotero_options({"zotero_add": False, "zotero_collection": " ", "zotero_pdf": "none"}) == {"add": False, "collection": "", "pdf_mode": "none"}


def test_approving_on_the_web_puts_the_paper_into_zotero(client, monkeypatch):
    z = FakeZotero(empty=True)
    monkeypatch.setattr(server, "make_zotero", lambda cfg: z)
    result = approve_first(client)
    assert z.added == [("kim2023computerized", PDF_NAME, "Paper Wiki")], "기본 설정: 넣기 켜짐 · 컬렉션 Paper Wiki · PDF 링크"
    assert result["zotero"] == ["Zotero 에 새 항목으로 넣었습니다 (NEW00001) · PDF 링크 포함"]
    assert Vault(client.vault_path).paper("kim2023computerized")["zotero_key"] == "NEW00001"


def test_settings_page_can_ask_zotero_for_permission(client, monkeypatch):
    z = FakeZotero(empty=True, writable=False)
    monkeypatch.setattr(server, "make_zotero", lambda cfg: z)
    assert client.post("/api/zotero/connect").json() == {"ok": True} and z.writable is True
    assert "zotero_local_key" in client.get("/api/settings").json()["secrets"]


def test_approving_while_zotero_is_off_still_registers_and_says_so(client):
    result = approve_first(client)
    assert result["ok"] and "Zotero 에 연결하지 못했습니다" in result["zotero"][0] and "paperwiki zotero sync" in result["zotero"][0]


def test_zotero_item_carries_the_wiki_citation_key_and_full_record():
    paper = {
        "id": "avsec2026advancing",
        "title": "Advancing regulatory variant effect prediction with AlphaGenome",
        "authors": [{"family": "Avsec", "given": "Žiga"}, {"name": "The Consortium"}],
        "year": "2026",
        "venue": "Nature",
        "doi": "10.1038/s41586-025-10014-0",
        "url": "https://www.nature.com/articles/s41586-025-10014-0",
        "abstract": "abs",
        "item_type": "journalArticle",
        "biblio": {"date": "2026-01-28", "volume": "649", "issue": "8099", "pages": "1206-1218", "issn": "0028-0836", "journal_abbr": "Nature", "publisher": "Springer", "language": "en"},
    }
    item = zotero.item_json(paper, ["COLL0001"])
    assert item["itemType"] == "journalArticle" and item["citationKey"] == "avsec2026advancing" and item["collections"] == ["COLL0001"]
    assert item["creators"] == [{"creatorType": "author", "firstName": "Žiga", "lastName": "Avsec"}, {"creatorType": "author", "name": "The Consortium"}]
    assert (item["publicationTitle"], item["date"], item["volume"], item["issue"], item["pages"], item["ISSN"], item["DOI"]) == ("Nature", "2026-01-28", "649", "8099", "1206-1218", "0028-0836", "10.1038/s41586-025-10014-0")
    assert "publisher" not in item, "학술지 논문에는 출판사를 넣지 않는다"
    # 서지 기록이 없으면 PDF 에서 읽은 것만으로 만들고, 프리프린트는 종류를 알아본다
    bare = zotero.item_json({"id": "x2024y", "title": "T", "authors": [], "year": "2024", "venue": "bioRxiv", "doi": "10.1101/2024.01.01.1"})
    assert bare["itemType"] == "preprint" and bare["repository"] == "bioRxiv" and bare["date"] == "2024" and "volume" not in bare


def test_zotero_client_adds_items_only_after_the_user_allows_it(tmp_path, monkeypatch):
    """Zotero 10 의 로컬 API 규격: 쓰기에는 Zotero-Server-ID 와, 확인 창에서 받은 허용 키가 필요하다."""
    stored = {}
    monkeypatch.setattr(config, "set_secret", lambda name, value: stored.__setitem__(name, value))
    monkeypatch.setattr(config, "get_secret", lambda name: stored.get(name))
    monkeypatch.setattr(config, "delete_secret", lambda name: stored.pop(name, None))
    state = {"answer": "always", "collections": [], "items": {"EXIST001": {"key": "EXIST001", "version": 7, "itemType": "journalArticle", "collections": ["OTHER001"]}}, "posts": []}

    def handler(request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        sid = {"Zotero-Server-ID": "SRV123456789"}
        if method != "GET":
            if request.headers.get("zotero-server-id") != "SRV123456789":
                return httpx.Response(428, text="Zotero-Server-ID not provided", headers=sid)
            if path == "/api/local/authorize":
                assert json.loads(request.content) == {"appName": "Paper Wiki"}
                if state["answer"] == "deny":
                    return httpx.Response(403, json={"denied": True}, headers=sid)
                return httpx.Response(200, json={"key": "k" * 32, "remember": state["answer"] == "always"}, headers=sid)
            if request.headers.get("zotero-api-key") != "k" * 32:
                return httpx.Response(401, text="API key required -- POST /api/local/authorize to obtain one", headers=sid)
        if method == "GET" and path == "/api/users/0/items":
            return httpx.Response(200, json=[], headers={**sid, "Total-Results": "0"})
        if method == "GET" and path == "/api/users/0/collections/top":
            return httpx.Response(200, json=[{"key": c["key"], "data": c} for c in state["collections"]], headers=sid)
        if method == "POST" and path == "/api/users/0/collections":
            (body,) = json.loads(request.content)
            made = {"key": "COLL0001", "name": body["name"]}
            state["collections"].append(made)
            return httpx.Response(200, json={"successful": {"0": {"key": "COLL0001", "data": made}}, "unchanged": {}, "failed": {}}, headers=sid)
        if method == "POST" and path == "/api/users/0/items":
            (body,) = json.loads(request.content)
            state["posts"].append(body)
            if body["itemType"] == "attachment":
                keys = list(body)
                assert keys.index("linkMode") < keys.index("path"), "Zotero 는 받은 순서대로 값을 넣으므로 linkMode 가 먼저 와야 한다"
                if not Path(body["path"]).name.endswith(".pdf"):
                    return httpx.Response(200, json={"successful": {}, "unchanged": {}, "failed": {"0": {"key": "", "code": 400, "message": "bad path"}}}, headers=sid)
            key = "ATTACH01" if body["itemType"] == "attachment" else "NEWITEM1"
            state["items"][key] = {"key": key, "version": 1, **body}
            return httpx.Response(200, json={"successful": {"0": {"key": key, "version": 1, "data": state["items"][key]}}, "unchanged": {}, "failed": {}}, headers=sid)
        if path.startswith("/api/users/0/items/") and path.rsplit("/", 1)[-1] in state["items"]:
            item = state["items"][path.rsplit("/", 1)[-1]]
            if method == "GET":
                return httpx.Response(200, json={"key": item["key"], "version": item["version"], "data": item}, headers={**sid, "Last-Modified-Version": str(item["version"])})
            if method == "PATCH":
                assert request.headers["if-unmodified-since-version"] == str(item["version"])
                item.update(json.loads(request.content), version=item["version"] + 1)
                return httpx.Response(204, headers=sid)
        return httpx.Response(404, text="No endpoint found", headers=sid)

    z = zotero.Zotero({"zotero_mode": "local"}, transport=httpx.MockTransport(handler))
    paper = {"id": "kim2023working", "title": "Working memory", "authors": [{"family": "Kim", "given": "J."}], "year": "2023", "venue": "J", "doi": "10.1/x"}
    pdf = tmp_path / "Working memory(Kim).pdf"

    # 허용받기 전에는 쓰지 못하고, 무엇을 해야 하는지 말해 준다
    assert z.can_write() is False
    with pytest.raises(zotero.ZoteroNotAuthorized, match="paperwiki zotero connect"):
        z.add_paper(paper, pdf, "Paper Wiki")
    assert state["posts"] == []

    # 확인 창에서 '거부' / '허용(한 번만)' / '항상 허용'
    state["answer"] = "deny"
    with pytest.raises(zotero.ZoteroError, match="거부"):
        z.authorize()
    state["answer"] = "once"
    assert z.authorize() == {"ok": False, "once": True} and stored == {}, "한 번짜리 허용은 저장하지 않는다"
    state["answer"] = "always"
    assert z.authorize() == {"ok": True} and stored == {"zotero_local_key": "k" * 32} and z.can_write()

    # 새 항목 + PDF 링크 + 컬렉션 (컬렉션은 없으면 만들고, 있으면 다시 만들지 않는다)
    made = z.add_paper(paper, pdf, "Paper Wiki")
    assert made == {"zotero_key": "NEWITEM1", "attachment_key": "ATTACH01", "note": ""}
    item, attachment = state["posts"]
    assert item["citationKey"] == "kim2023working" and item["collections"] == ["COLL0001"]
    assert attachment == {"itemType": "attachment", "linkMode": "linked_file", "parentItem": "NEWITEM1", "title": "PDF", "contentType": "application/pdf", "path": str(pdf)}
    z.add_paper({**paper, "id": "kim2023b"}, None, "Paper Wiki")
    assert len(state["collections"]) == 1

    # PDF 링크를 못 붙여도 항목은 남고, 그 사실을 알려 준다
    partial = z.add_paper(paper, tmp_path / "not-a-pdf.txt", "")
    assert partial["zotero_key"] == "NEWITEM1" and partial["attachment_key"] is None and "PDF 링크는 붙이지 못했습니다" in partial["note"]

    # 이미 있던 항목: 컬렉션에 더하기만 한다 (원래 있던 컬렉션은 그대로)
    assert z.add_to_collection("EXIST001", "Paper Wiki") is True and state["items"]["EXIST001"]["collections"] == ["OTHER001", "COLL0001"]
    assert z.add_to_collection("EXIST001", "Paper Wiki") is False and z.add_to_collection("MISSING1", "Paper Wiki") is False

    # 위키에서 PDF 이름이 바뀌면 링크의 경로를 고친다 (이름이 같으면 건드리지 않는다)
    assert z.relink_pdf("ATTACH01", pdf) is False
    renamed = tmp_path / "새 이름(Kim).pdf"
    assert z.relink_pdf("ATTACH01", renamed) is True and state["items"]["ATTACH01"]["path"] == str(renamed)
    assert z.relink_pdf("EXIST001", renamed) is False, "링크된 파일이 아닌 항목은 건드리지 않는다"

    # Zotero 에서 허용이 지워졌으면(401) 저장해 둔 키를 버리고 다시 허용받으라고 한다
    stored["zotero_local_key"] = "revoked"
    with pytest.raises(zotero.ZoteroNotAuthorized):
        z.add_paper(paper, None, "")
    assert stored == {}

    # 항목 추가 기능이 없는 예전 Zotero
    old = zotero.Zotero({"zotero_mode": "local"}, transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[], headers={"Total-Results": "0"})))
    with pytest.raises(zotero.ZoteroError, match="10 이상"):
        old.authorize()


CSL = {
    "type": "journal-article",
    "title": ["Computerized cognitive training improves working memory in mild cognitive impairment"],
    "author": [{"given": "Jisoo", "family": "Kim", "sequence": "first"}, {"given": "Sang", "family": "Lee"}, {"name": "CCT Study Group"}],
    "container-title": "Journal of Cognitive Health",
    "container-title-short": "J. Cogn. Health",
    "issued": {"date-parts": [[2023, 5, 2]]},
    "volume": "12",
    "issue": "3",
    "page": "101-115",
    "ISSN": ["1234-5678", "8765-4321"],
    "language": "en",
    "publisher": "Example Press",
    "DOI": "10.1000/jch.2023.001",
    "resource": {"primary": {"URL": "https://example.org/jch/2023/001"}},
    "abstract": "<jats:title>Abstract</jats:title><jats:p>Training <jats:italic>improved</jats:italic> memory.</jats:p>",
    "reference": [
        {"key": "ref1", "DOI": "10.1111/j.1365-2796.2004.01388.x", "year": "2004", "unstructured": "Petersen, R. C. Mild cognitive impairment as a diagnostic entity. J. Intern. Med. 256, 183–194 (2004)."},
        {"key": "ref3", "DOI": "10.1176/appi.ajp.2016.16030360", "year": "2017", "article-title": "Computerized Cognitive Training in Older Adults With Mild Cognitive Impairment or Dementia"},
        {"key": "ref4", "DOI": "10.18637/jss.v067.i01", "year": "2014", "article-title": "Fitting linear mixed-effects models using lme4"},
        {"key": "ref9", "year": "2020", "unstructured": "No DOI here."},
    ],
}


def test_doi_record_is_read_into_bibliographic_data():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), request.headers["accept"], request.headers["user-agent"]))
        if request.url.path.endswith("/10.1000/jch.2023.001"):
            return httpx.Response(200, json=CSL)
        if request.url.path.endswith("/10.1000/html"):
            return httpx.Response(200, text="<html>landing page</html>")
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    found = biblio.lookup("https://doi.org/10.1000/jch.2023.001", transport=transport)
    assert seen[0][0] == "https://doi.org/10.1000/jch.2023.001" and "csl+json" in seen[0][1] and seen[0][2].startswith("paperwiki/"), "보내는 것은 DOI 뿐이다"
    assert (found["status"], found["title"], found["year"], found["venue"], found["item_type"]) == ("ok", CSL["title"][0], "2023", "Journal of Cognitive Health", "journalArticle")
    assert found["authors"] == [{"family": "Kim", "given": "Jisoo"}, {"family": "Lee", "given": "Sang"}, {"name": "CCT Study Group"}]
    assert found["biblio"] == {"date": "2023-05-02", "volume": "12", "issue": "3", "pages": "101-115", "issn": "1234-5678", "journal_abbr": "J. Cogn. Health", "publisher": "Example Press", "language": "en", "source": "doi.org"}
    assert found["url"] == "https://example.org/jch/2023/001" and found["abstract"] == "Training improved memory."
    assert [r["doi"] for r in found["references"]] == ["10.1111/j.1365-2796.2004.01388.x", "10.1176/appi.ajp.2016.16030360", "10.18637/jss.v067.i01"]
    assert biblio.lookup("10.1000/nope", transport=transport) == {"status": "not_found"}
    assert biblio.lookup("10.1000/html", transport=transport) == {"status": "unreachable"}

    def offline(request):
        raise httpx.ConnectError("offline")

    assert biblio.lookup("10.1000/jch.2023.001", transport=httpx.MockTransport(offline)) == {"status": "unreachable"}

    # 참고문헌의 DOI: 제목(과 연도)이 맞는 등록 기록이 하나일 때만
    refs = found["references"]
    assert biblio.reference_doi(REF_PETERSEN, refs) == "10.1111/j.1365-2796.2004.01388.x"
    assert biblio.reference_doi(REF_HILL, refs) == "10.1176/appi.ajp.2016.16030360"
    assert biblio.reference_doi(REF_BATES, refs) == "", "연도가 다르면 같은 문헌으로 보지 않는다"
    assert biblio.reference_doi({"title": "Short", "year": "2004"}, refs) == ""
    assert biblio.same_title("Deep learning: a review", "Deep Learning — A Review") and not biblio.same_title("Deep learning", "Deep learning for genomics")


def test_bibliography_is_checked_against_the_doi_record_before_review(client):
    vault = open_vault(client)
    record = biblio.from_csl(CSL, "10.1000/jch.2023.001")
    sloppy = {**PROPOSAL, "paper": {**PROPOSAL["paper"], "title": "computerized cognitive training improves working memory in mild cognitive impairment", "authors": [{"family": "Kim", "given": "J"}], "venue": "J Cogn Health"}}
    asked = []
    draft_id = draft_for(vault, make_pdf(vault.pdf_dir / "a.pdf"), sloppy, zot=FakeZotero(empty=True), lookup=lambda doi: asked.append(doi) or record)
    review = wiki.review(vault, draft_id)
    assert asked == [PROPOSAL["paper"]["doi"]]
    assert (review["paper"]["title"], review["paper"]["venue"], review["paper"]["authors"]) == (CSL["title"][0], "Journal of Cognitive Health", "Kim, Jisoo; Lee, Sang; CCT Study Group")
    assert review["bib"]["source"] == "doi" and review["bib"]["more"]["pages"] == "101-115" and review["bib"]["ref_dois"] == 2
    by_ref = {r["ref"]: r for r in review["references"]["new"] + review["references"]["unused"]}
    assert by_ref["3"]["doi"] == "10.1176/appi.ajp.2016.16030360" and by_ref["2"]["doi"] == REF_LAMPIT["doi"] and by_ref["4"]["doi"] == ""
    text = wiki.review_text(review)
    assert "서지 정보: DOI 등록 기록으로 확인 (doi.org) — 권 12 · 호 3 · 쪽 101-115" in text
    assert "Zotero: Zotero 에 없는 논문 — 등록하면 Zotero 에 새 항목으로 넣습니다" in text
    assert "doi:10.1176/appi.ajp.2016.16030360" in text

    # 등록하면 권·호·쪽이 논문 기록에 남아 Zotero 항목을 만들 때 쓰인다
    wiki.approve(vault, draft_id)
    paper = vault.paper("kim2023computerized")
    assert paper["biblio"]["volume"] == "12" and paper["item_type"] == "journalArticle" and paper["url"] == "https://example.org/jch/2023/001"
    assert vault.paper("hill2017computerized")["doi"] == "10.1176/appi.ajp.2016.16030360"
    assert zotero.item_json(paper)["pages"] == "101-115"

    # DOI 가 다른 논문을 가리키거나 등록되어 있지 않으면 PDF 에서 읽은 것을 그대로 두고 확인하라고 알린다
    other = {**PROPOSAL, "paper": {**PROPOSAL["paper"], "title": "A completely different study", "doi": "10.1000/jch.2023.001"}}
    wrong = wiki.review(vault, draft_for(vault, make_pdf(vault.pdf_dir / "b.pdf", width=310), other, lookup=lambda doi: record))
    assert wrong["bib"]["source"] == "doi_mismatch" and wrong["paper"]["title"] == "A completely different study"
    assert any("제목이 다릅니다" in w and CSL["title"][0] in w for w in wrong["warnings"])
    missing = wiki.review(vault, draft_for(vault, make_pdf(vault.pdf_dir / "c.pdf", width=320), {**other, "paper": {**other["paper"], "title": "Third"}}, lookup=lambda doi: {"status": "not_found"}))
    assert missing["bib"]["source"] == "doi_not_found" and any("등록되어 있지 않습니다" in w for w in missing["warnings"])

    def broken(doi):
        raise RuntimeError("boom")

    offline = wiki.review(vault, draft_for(vault, make_pdf(vault.pdf_dir / "d.pdf", width=330), {**other, "paper": {**other["paper"], "title": "Fourth"}}, lookup=broken))
    assert offline["bib"]["source"] == "doi_unreachable" and "연결하지 못해" in wiki.review_text(offline)


def test_a_server_running_old_code_says_so_and_can_be_replaced(client, monkeypatch):
    open_vault(client)
    ping = client.get("/api/ping").json()
    assert ping["stale"] is False and ping["stamp"] == server.code_stamp()
    assert "프로그램이 업데이트되었습니다" not in client.get("/").text

    # 프로그램 파일이 바뀌었는데 서버는 그대로 떠 있을 때
    monkeypatch.setattr(server, "STARTED_WITH", server.code_stamp() - 100)
    assert client.get("/api/ping").json()["stale"] is True
    assert "프로그램이 업데이트되었습니다" in client.get("/").text

    # 새로 실행한 paperwiki 만 종료를 부탁할 수 있다 (웹 페이지가 몰래 부를 수 없다)
    assert client.post("/api/shutdown").status_code == 403

    class Running:
        should_exit = False

    monkeypatch.setattr(server.app.state, "server", Running(), raising=False)
    assert client.post("/api/shutdown", headers={"X-Paperwiki": "1"}).json() == {"ok": True} and server.app.state.server.should_exit is True


# ── 같은 문헌을 놓치지 않기 (다른 논문이 다른 표기로 인용한 같은 문헌) ─────────────


def _claim(statement: str, refs: list[str], path=("연구 주제", "경도인지장애", "전산화 인지훈련")) -> dict:
    return {"statement": statement, "type": "background", "refs": refs, "evidence": {"quote": "", "location": "p.1"}, "keywords": [{"path": list(path), "aliases": [], "description": ""}], "same_as": ""}


def test_same_work_written_differently_is_recognized():
    known = {
        p["id"]: p
        for p in (
            {"id": "mansour2014oncogenic", "kind": "cited", "title": "An oncogenic super-enhancer formed through somatic mutation of a noncoding intergenic element", "authors": [{"family": "Mansour", "given": "M. R."}], "year": "2014", "doi": "10.1126/science.1259037"},
            {"id": "pampari2025chrombpnet", "kind": "cited", "title": "ChromBPNet: bias factorized, base-resolution deep learning models of chromatin accessibility", "authors": [{"family": "Pampari", "given": "A."}], "year": "2025", "doi": "10.1101/2024.12.25.630221"},
            {"id": "collins1984concordance", "kind": "cited", "title": "Concordance of a point mutation 5′ to the Gγ globin gene with Gγβ+ hereditary persistence of fetal hemoglobin", "authors": [{"family": "Collins", "given": "F. S."}], "year": "1984", "doi": "10.1182/blood.v64.6.1292.1292"},
            {"id": "kim2020naive", "kind": "cited", "title": "Naïve T cells & TGF-β signalling", "authors": [{"family": "Kim", "given": "J."}], "year": "2020", "doi": ""},
            {"id": "gtex2020gtex", "kind": "cited", "title": "The GTEx Consortium atlas of genetic regulatory effects across human tissues", "authors": [{"family": "GTEx Consortium", "given": ""}], "year": "2020", "doi": ""},
            {"id": "yuregir1992hb", "kind": "cited", "title": "Hb H disease in a Turkish family resulting from the interaction of a deletional α-thalassaemia-1", "authors": [{"family": "Yüregir", "given": "G. T."}], "year": "1992", "doi": "10.1111/j.1365-2141.1992.tb04568.x"},
        )
    }
    m = wiki.PaperMatcher(known)
    same = lambda **ref: m.match(ref)  # noqa: E731

    # DOI 가 없어도: 학술지의 분류어가 제목 앞에 붙은 표기, 발음 기호·&·그리스 문자 표기 차이, 'The' 가 붙은 단체 저자
    assert same(title="Oncogene regulation. An oncogenic super-enhancer formed through somatic mutation of a noncoding intergenic element", authors=[{"family": "Mansour"}], year="2014") == ("mansour2014oncogenic", "similar")
    assert same(title="Naive T cells and TGF-beta signalling") == ("kim2020naive", "title")
    assert same(title="The GTEx Consortium atlas of genetic regulatory effects across human tissues.", authors=[{"name": "The GTEx Consortium"}], year="2020", doi="10.1126/science.aaz1776") == ("gtex2020gtex", "title")
    # DOI 가 달라도 같은 논문: 프리프린트와 출판본 (연도가 달라도), 한 논문에 등록된 두 DOI
    assert same(title="ChromBPNet: bias factorized, base-resolution deep learning models of chromatin accessibility", authors=[{"family": "Pampari"}], year="2026", doi="10.1038/s41588-026-00001-1") == ("pampari2025chrombpnet", "version")
    assert same(title="Concordance of a point mutation 5' to the G gamma globin gene with G gamma beta+ hereditary persistence of fetal hemoglobin", authors=[{"family": "Collins"}], year="1984", doi="10.1182/blood.v64.6.1292.bloodjournal6461292") == ("collins1984concordance", "twin")
    assert same(title="Hb H disease in a Turkish family resulting from the interaction of a deletional alpha-thalassaemia-1", authors=[{"family": "Yuuregir"}], year="1992", doi="10.1111/other.1992") == ("yuregir1992hb", "twin"), "ü → uu 로 옮긴 성"
    # 같은 DOI 는 제목이 어떻게 적혀 있든 같은 문헌
    assert same(title="Completely garbled", doi="https://doi.org/10.1126/SCIENCE.1259037") == ("mansour2014oncogenic", "doi")

    # 확신할 수 없는 것은 잇지 않고 후보로 내놓는다: 제목은 같은데 DOI 와 연도가 다른 것, 제목이 비슷하기만 한 것
    reprint = {"title": "An oncogenic super-enhancer formed through somatic mutation of a noncoding intergenic element", "authors": [{"family": "Mansour"}], "year": "2016", "doi": "10.9999/reprint.2016"}
    assert m.match(reprint) == (None, "") and m.candidates(reprint) == [("mansour2014oncogenic", "제목이 같고 DOI 가 다름 (다른 판·재수록·정정본일 수 있음)")]
    cousin = {"title": "An oncogenic super-enhancer formed by somatic mutations of a non-coding intergenic element in T-ALL", "authors": [{"family": "Mansour"}], "year": "2015"}
    assert m.match(cousin) == (None, "") and [c for c, _ in m.candidates(cousin)] == ["mansour2014oncogenic"]
    other = {"title": "A different paper about enhancers in leukaemia", "authors": [{"family": "Mansour"}], "year": "2014"}
    assert m.match(other) == (None, "") and m.candidates(other) == []

    assert wiki.is_preprint_doi("10.1101/2024.12.25.630221") and wiki.is_preprint_doi("10.1101/787903") and wiki.is_preprint_doi("10.48550/arXiv.2101.00001")
    assert not wiki.is_preprint_doi("10.1101/gr.275193.120") and not wiki.is_preprint_doi("10.1038/s41586-025-10014-0")


SECOND = {
    "paper": paper_part(META2),
    "summary": "s",
    "references": [
        # 부제가 붙고 DOI 가 있는 표기 (첫 논문에는 DOI 없이 짧은 제목으로 있었다)
        {"ref": "1", **REF_HILL, "title": "Computerized cognitive training in older adults with mild cognitive impairment or dementia: a systematic review and meta-analysis", "doi": "10.1176/appi.ajp.2016.16030360"},
        # 대소문자·태그가 다른 표기
        {"ref": "2", **REF_BATES, "title": "Fitting Linear Mixed-Effects Models Using <i>lme4</i>.", "doi": "10.18637/jss.v067.i01"},
        # 같은 논문에 등록된 다른 DOI
        {"ref": "3", **REF_LAMPIT, "doi": "10.1371/journal.pmed.1001756.g001"},
        # 비슷하지만 같은 문헌인지 확신할 수 없는 것
        {"ref": "4", "title": "Computerised cognitive training for older adults with mild cognitive impairment and dementia", "authors": [{"family": "Hill", "given": "N."}], "et_al": True, "year": "2016", "venue": "", "doi": ""},
    ],
    "claims": [_claim("인지훈련의 효과는 메타분석으로 정리되어 있다.", ["1", "3", "4"]), _claim("혼합모형은 lme4 로 적합한다.", ["2"], ("방법론", "분석 방법", "선형 혼합효과모형"))],
    "note": "",
}


def test_work_cited_in_another_form_by_a_second_paper_stays_one_work(client, capsys):
    approve_first(client)
    vault = Vault(client.vault_path)
    draft_id = draft_for(vault, make_pdf(vault.pdf_dir / "second.pdf", width=310), SECOND)
    review = wiki.review(vault, draft_id)

    # 표기가 달라도 세 편은 위키의 문헌에 이어지고, 어떻게 같은 문헌으로 봤는지 보인다
    linked = {r["ref"]: (r["id"], r["match"]) for r in review["references"]["existing"]}
    assert linked == {"1": ("hill2017computerized", "similar"), "2": ("bates2015fitting", "title"), "3": ("lampit2014computerized", "twin")}
    # 확신할 수 없는 한 편은 조용히 새 문헌이 되지 않고, 확인할 것으로 올라온다
    (unsure,) = review["maybe"]
    assert unsure["ref"] == "4" and [m["id"] for m in unsure["maybe"]] == ["hill2017computerized"]
    text = wiki.review_text(review)
    assert "같은 문헌일 수 있는 것 1편" in text and "↔ @hill2017computerized" in text and "같은 문헌으로 본 근거: 제목·제1저자·연도가 같고 DOI 만 다름" in text
    assert any("같은 문헌일 수 있는 참고문헌이 1편" in w for w in review["warnings"])
    shown = {r["ref"]: r for r in client.get(f"/api/pending/{draft_id}").json()["draft"]["references"]}
    assert shown["4"]["maybe"][0]["id"] == "hill2017computerized" and shown["3"]["match"] == "twin" and shown["3"]["linked_title"] == REF_LAMPIT["title"]

    result = wiki.approve(vault, draft_id)
    assert result["new_cited"] == ["hill2016computerised"] and sorted(result["linked_cited"]) == ["bates2015fitting", "hill2017computerized", "lampit2014computerized"]
    assert result["maybe_same"] == [{"new": "hill2016computerised", "existing": "hill2017computerized", "why": "제1저자가 같고 연도가 가깝고 제목이 비슷함"}]
    # 그래서 "여러 논문이 인용한 문헌"으로 잡힌다
    assert {r["citekey"] for r in wiki.insights(vault)["multi_source"]} == {"hill2017computerized", "bates2015fitting", "lampit2014computerized"}
    # 이어지면서 알게 된 것은 문헌에 남는다: 비어 있던 DOI, 더 긴 제목, 같은 논문의 다른 DOI
    hill, bates, lampit = (vault.paper(i) for i in ("hill2017computerized", "bates2015fitting", "lampit2014computerized"))
    assert hill["doi"] == "10.1176/appi.ajp.2016.16030360" and hill["title"].endswith("a systematic review and meta-analysis") and bates["doi"] == "10.18637/jss.v067.i01"
    assert lampit["doi"] == REF_LAMPIT["doi"] and lampit["known_as"]["dois"] == ["10.1371/journal.pmed.1001756.g001"]
    assert wiki.PaperMatcher(vault.papers()).match({"title": "(title missing)", "doi": "10.1371/JOURNAL.PMED.1001756.g001"}) == ("lampit2014computerized", "doi")

    # 위키 전체에서 갈린 문헌 찾기: 확인이 필요한 쌍으로 나온다
    (pair,) = wiki.duplicates(vault)
    assert {pair["a"]["citekey"], pair["b"]["citekey"]} == {"hill2016computerised", "hill2017computerized"} and pair["certain"] is False
    home = client.get("/").text
    assert "같은 문헌일 수 있는 것" in home and "/wiki/p/hill2016computerised" in home and "확인 필요" in home
    capsys.readouterr()
    assert cli.main(["duplicates"]) == 0
    out = capsys.readouterr().out
    assert "같은 문헌일 수 있는 쌍 1개" in out and "@hill2016computerised" in out and "merge-papers" in out and "--apart" in out

    # 같은 문헌이라고 확인해 합치면: 인용 기록이 한 문헌으로 모이고, 그 표기를 기억해 다음부터는 바로 이어진다
    wiki.merge_papers(vault, "hill2016computerised", "hill2017computerized")
    assert wiki.duplicates(vault) == [] and vault.paper("hill2016computerised") is None
    assert "같은 문헌일 수 있는 것" not in client.get("/").text
    assert vault.paper("hill2017computerized")["known_as"]["titles"] == [REF_HILL["title"], "Computerised cognitive training for older adults with mild cognitive impairment and dementia"]
    again = {"title": "Computerised Cognitive Training for Older Adults with Mild Cognitive Impairment and Dementia", "authors": [], "year": ""}
    assert wiki.PaperMatcher(vault.papers()).match(again) == ("hill2017computerized", "title")


def test_user_can_say_two_references_are_the_same_or_different(client, capsys):
    approve_first(client)
    vault = Vault(client.vault_path)
    lookalike = {"ref": "9", "title": "Computerised cognitive training for older adults with mild cognitive impairment and dementia", "authors": [{"family": "Hill", "given": "N."}], "et_al": True, "year": "2016", "venue": "", "doi": ""}

    # "같은 문헌이다": 제안의 참고문헌에 paper_id 를 적으면 그 문헌으로 이어진다
    same = {**SECOND, "references": [{**lookalike, "paper_id": "@hill2017computerized"}], "claims": [_claim("주장 A", ["9"])]}
    review = wiki.review(vault, draft_for(vault, make_pdf(vault.pdf_dir / "same.pdf", width=310), same))
    assert [(r["id"], r["match"]) for r in review["references"]["existing"]] == [("hill2017computerized", "forced")] and review["maybe"] == []
    wiki.discard(vault, review["id"])

    # "다른 문헌이다": separate 를 적으면 따로 등록되고, 다시 묻지 않는다
    apart = {**SECOND, "references": [{**lookalike, "separate": True}], "claims": [_claim("주장 B", ["9"])]}
    draft_id = draft_for(vault, make_pdf(vault.pdf_dir / "apart.pdf", width=320), apart)
    review = wiki.review(vault, draft_id)
    assert review["maybe"] == [] and [r["id"] for r in review["references"]["new"]] == ["hill2016computerised"]
    assert wiki.approve(vault, draft_id)["maybe_same"] == []
    assert vault.paper("hill2016computerised")["apart"] == ["hill2017computerized"] and wiki.duplicates(vault) == []

    # 등록한 뒤에 다른 문헌이라고 적어 둘 수도 있다
    vault.save_paper({**vault.paper("hill2016computerised"), "apart": []})
    assert len(wiki.duplicates(vault)) == 1
    assert cli.main(["duplicates", "--apart", "@hill2016computerised", "@hill2017computerized"]) == 0
    assert wiki.duplicates(vault) == [] and "같은 문헌이 둘로 갈린" in (cli.main(["duplicates"]), capsys.readouterr().out)[1]


def test_works_registered_twice_with_the_same_doi_are_merged(client):
    approve_first(client)
    vault = Vault(client.vault_path)
    # DOI 없이 다른 표기로 따로 등록되어 있던 문헌에, 나중에 같은 DOI 가 붙은 경우
    vault.save_paper({**vault.paper("hill2017computerized"), "id": "hill2017cct", "title": "CCT in MCI or dementia", "doi": "10.1176/appi.ajp.2016.16030360", "claims": []})
    other = {**SECOND, "references": [{"ref": "1", "title": "CCT in MCI or dementia", "authors": [{"family": "Hill"}], "et_al": True, "year": "2017", "venue": "", "doi": "", "paper_id": "hill2017cct"}], "claims": [_claim("주장", ["1"])]}
    wiki.approve(vault, draft_for(vault, make_pdf(vault.pdf_dir / "o.pdf", width=310), other))
    assert wiki.duplicates(vault) == [], "제목이 전혀 다르고 한쪽에 DOI 가 없으면 아직 알 수 없다"

    found = wiki.find_dois(vault, lambda ref: "10.1176/appi.ajp.2016.16030360" if ref["id"] == "hill2017computerized" else "")
    assert {"paper": "hill2017computerized", "doi": "10.1176/appi.ajp.2016.16030360"} in found
    (pair,) = wiki.duplicates(vault)
    assert pair["certain"] is True and pair["why"] == "DOI 가 같음"
    merged = wiki.merge_certain(vault)
    assert len(merged) == 1 and wiki.duplicates(vault) == []
    kept = vault.paper(merged[0]["kept"])
    assert kept["known_as"]["titles"] and render.paper_stats(vault.papers(), vault.ontology())[kept["id"]]["sources"] == 2, "두 논문의 인용 기록이 한 문헌으로 모인다"


def test_doi_is_found_by_title_author_and_year(monkeypatch):
    monkeypatch.setattr(biblio, "SEARCH_INTERVAL", 0)
    monkeypatch.setattr(biblio.time, "sleep", lambda s: None)
    lme4 = {"DOI": "10.18637/jss.v067.i01", "type": "journal-article", "title": ["Fitting Linear Mixed-Effects Models Using <b>lme4</b>"], "author": [{"family": "Bates", "given": "Douglas"}], "issued": {"date-parts": [[2015]]}}
    chapter = {"DOI": "10.1007/0-387-22747-4_4", "type": "book-chapter", "title": ["Fitting Linear Mixed-Effects Models"], "issued": {"date-parts": [[None]]}}
    preprint = {"DOI": "10.1101/787903", "type": "posted-content", "title": ["The GTEx Consortium atlas of genetic regulatory effects across human tissues"], "author": [{"family": "Aguet"}], "issued": {"date-parts": [[2019, 10, 3]]}}
    science = {**preprint, "DOI": "10.1126/science.aaz1776", "type": "journal-article", "author": [{"name": "The GTEx Consortium"}], "issued": {"date-parts": [[2020, 9, 11]]}}
    twin_a = {"DOI": "10.1182/blood.v64.6.1292.1292", "type": "journal-article", "title": ["Concordance of a point mutation 5' to the G gamma globin gene"], "author": [{"family": "Collins"}], "issued": {"date-parts": [[1984, 12, 1]]}}
    twin_b = {**twin_a, "DOI": "10.1182/blood.v64.6.1292.bloodjournal6461292"}
    section = {"DOI": "10.1126/science.1259037", "type": "journal-article", "title": ["An oncogenic super-enhancer formed through somatic mutation of a noncoding intergenic element"], "author": [{"family": "Mansour"}], "issued": {"date-parts": [[2014, 12, 12]]}}
    review_of = {"DOI": "10.3410/f.1", "type": "dataset", "title": ["An oncogenic super-enhancer formed through somatic mutation of a noncoding intergenic element"]}
    answers = {"lme4": [chapter, lme4], "gtex": [preprint, science], "globin": [twin_b, twin_a], "oncogenic": [review_of, section], "blocked": [lme4]}
    asked, blocked = [], {"n": 1}

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        asked.append(params)
        query = (params.get("query.title") or params.get("query.bibliographic") or "").casefold()
        if "blocked" in query and blocked["n"]:
            blocked["n"] -= 1
            return httpx.Response(429, headers={"Retry-After": "1"})
        if "titleonly" in query and "query.author" in params:
            return httpx.Response(200, json={"message": {"items": []}})
        return httpx.Response(200, json={"message": {"items": next((v for k, v in answers.items() if k in query), [])}})

    find = lambda **ref: biblio.find_doi(ref, transport=httpx.MockTransport(handler))  # noqa: E731
    # 제목이 앞부분만 같은 다른 글(저자·연도를 알 수 없는 책의 장)이 먼저 나와도 고르지 않는다
    assert find(title="Fitting linear mixed-effects models using lme4", authors=[{"family": "Bates"}], year="2015") == "10.18637/jss.v067.i01"
    assert asked[0]["query.title"].startswith("Fitting") and asked[0]["query.author"] == "Bates" and len(asked) == 1, "보내는 것은 제목과 제1저자 성"
    # 프리프린트와 출판본이 함께 나오면 출판본, 단체 저자의 표기 차이는 받아들인다
    assert find(title="The GTEx Consortium atlas of genetic regulatory effects across human tissues", authors=[{"family": "GTEx Consortium"}], year="2020") == "10.1126/science.aaz1776"
    # 한 논문에 DOI 가 둘 등록되어 있으면 하나를 정해서 쓴다 (둘 다 같은 논문이다)
    assert find(title="Concordance of a point mutation 5′ to the Gγ globin gene", authors=[{"family": "Collins"}], year="1984") == "10.1182/blood.v64.6.1292.1292"
    # 학술지의 분류어가 제목 앞에 붙은 표기, 그리고 논문이 아닌 것(추천 글)은 건너뛴다
    assert find(title="Oncogene regulation. An oncogenic super-enhancer formed through somatic mutation of a noncoding intergenic element", authors=[{"family": "Mansour"}], year="2014") == "10.1126/science.1259037"
    assert find(title="Fitting linear mixed-effects models using lme4", authors=[{"family": "Someone-Else"}], year="2015") == "", "제1저자가 다르면 받아들이지 않는다"
    assert find(title="Fitting linear mixed-effects models using lme4", authors=[{"family": "Bates"}], year="1999") == "", "연도가 크게 다르면 받아들이지 않는다"
    assert find(title="Short title", authors=[{"family": "Kim"}], year="2020") == "" and find(title="Nothing like this exists anywhere at all", authors=[], year="") == ""
    # 저자 칸으로 묻어 안 나오면 제목만으로 한 번 더 묻는다 · 잠깐 막히면(429) 기다렸다 다시 묻는다
    asked.clear()
    assert find(title="Fitting linear mixed-effects models using lme4 titleonly", authors=[{"family": "Bates"}], year="2015") == "10.18637/jss.v067.i01"
    assert [("query.author" in a, "query.bibliographic" in a) for a in asked] == [(True, False), (False, True)]
    assert find(title="Fitting linear mixed-effects models using lme4 blocked", authors=[], year="") == "" and blocked["n"] == 0


def test_reference_dois_are_searched_within_a_time_limit_and_resumed(client):
    vault = open_vault(client)
    calls = []

    def search(ref):
        calls.append(ref["title"])
        if "lme4" in ref["title"]:
            raise httpx.ConnectError("offline")
        return {"Mild cognitive impairment as a diagnostic entity": "10.1111/j.1365-2796.2004.01388.x"}.get(ref["title"], "")

    # 찾은 것은 붙이고, 연결이 끊기면 거기서 멈춘다 (등록은 계속할 수 있다)
    info = library.prepare(vault, str(make_pdf(vault.pdf_dir / "a.pdf")))
    Path(info["proposal"]).write_text(json.dumps(PROPOSAL, ensure_ascii=False), encoding="utf-8")
    review = wiki.propose(vault, info["id"], search=search)
    by_ref = {r["ref"]: r["doi"] for r in review["references"]["new"] + review["references"]["unused"]}
    assert by_ref == {"1": "10.1111/j.1365-2796.2004.01388.x", "2": REF_LAMPIT["doi"], "3": "", "4": ""}
    assert calls == [REF_PETERSEN["title"].rstrip("."), REF_HILL["title"], REF_BATES["title"]], "DOI 가 이미 있는 문헌은 묻지 않는다"
    assert review["bib"]["ref_searched"] == 1 and any("1편은 아직 DOI 를 찾아보지 못했습니다" in w for w in review["warnings"])
    assert "1편은 Crossref 검색으로 찾음" in wiki.review_text(review)

    # 다시 실행하면 이미 찾아본 것은 다시 묻지 않고 이어서 찾는다
    calls.clear()
    review = wiki.propose(vault, info["id"], search=lambda ref: calls.append(ref["title"]) or "10.18637/jss.v067.i01")
    assert calls == [REF_BATES["title"]] and review["bib"]["ref_searched"] == 2

    # 시간 한도를 넘기면 남은 것은 다음으로 미룬다
    refs = [{"title": f"A sufficiently long reference title number {i}", "authors": [], "year": "2020"} for i in range(3)]
    assert wiki._search_dois(refs, lambda ref: "10.1/x", budget=-1) == (0, 3) and all("doi" not in r for r in refs)
    cache = {}
    assert wiki._search_dois(refs, lambda ref: "10.1/x", cache) == (3, 0) and len(cache) == 3

