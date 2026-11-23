"""로컬 웹 화면 (127.0.0.1 에서만 열린다).

웹이 하는 일은 위키를 '보는' 것이다: 키워드 → 주장 → 인용된 문헌 → 그 문헌이 인용된 다른 주장으로 타고 넘어가며 읽기,
검색, 그래프, 문헌 목록(많이 인용된 순 · 여러 방향으로 인용된 순).
그리고 설정(저장 위치·다른 컴퓨터에서 만든 위키 불러오기·Zotero·스킬 설치)과, Claude Code 가 만든
검토안을 화면에서 고치며 검토하는 일. 논문을 읽고 제안을 만드는 일은 Claude Code 의 스킬이 한다.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import __version__, config, gdrive, integration, library, render, wiki
from .library import LibraryError
from .store import CLAIM_TYPES, Vault, VaultUnavailable, now_iso, vault_summary
from .wiki import WikiError
from .zotero import LOCAL_HELP, Zotero, ZoteroError, lookup_user_id

HERE = Path(__file__).parent

app = FastAPI(title="Paper Wiki", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")

TYPE_LABELS = {"finding": "결과·발견", "method": "방법론", "background": "배경·개념", "limitation": "한계·논점"}
templates.env.globals.update(type_labels=TYPE_LABELS, version=__version__)


def code_stamp() -> int:
    """프로그램 파일이 마지막으로 바뀐 시각. 실행 중인 서버가 디스크의 코드보다 오래됐는지 가리는 데 쓴다."""
    here = Path(__file__).parent
    return int(max((f.stat().st_mtime for f in here.glob("*.py")), default=0))


STARTED_WITH = code_stamp()  # 이 프로세스가 읽어 들인 코드


def is_stale() -> bool:
    """프로그램이 업데이트됐는데 이 서버는 예전 코드로 돌고 있는가 (화면 파일은 새것이라 서로 어긋난다)."""
    return code_stamp() != STARTED_WITH


# ── 보안: 이 컴퓨터의 브라우저에서 온 요청만 받는다 ───────────────────────────

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]", "testserver"}


@app.middleware("http")
async def local_only(request: Request, call_next):
    host = request.headers.get("host", "")
    hostname = host.rsplit(":", 1)[0] if host.count(":") == 1 or host.startswith("[") else host
    if hostname not in _LOCAL_HOSTS:
        return JSONResponse({"error": "허용되지 않은 호스트입니다."}, status_code=403)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        # 다른 웹사이트가 사용자의 브라우저를 통해 이 앱에 요청을 보내는 것을 막는다
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc != host:
            return JSONResponse({"error": "허용되지 않은 출처입니다."}, status_code=403)
        if request.headers.get("sec-fetch-site", "same-origin") not in ("same-origin", "none"):
            return JSONResponse({"error": "허용되지 않은 출처입니다."}, status_code=403)
    return await call_next(request)


@app.exception_handler(WikiError)
async def _wiki_error(_request, exc):
    return JSONResponse({"error": str(exc)}, status_code=400)


@app.exception_handler(ZoteroError)
async def _zotero_error(_request, exc):
    return JSONResponse({"error": str(exc)}, status_code=502)


@app.exception_handler(LibraryError)
async def _library_error(_request, exc):
    return JSONResponse({"error": str(exc)}, status_code=400)


@app.exception_handler(VaultUnavailable)
async def _vault_unavailable(request: Request, exc):
    """위키 파일을 다 읽을 수 없을 때(동기화 중·오프라인)는 화면도 작업도 멈추고 이유를 알린다."""
    if request.url.path.startswith("/api/"):
        return JSONResponse({"error": str(exc)}, status_code=503)
    ctx = {"active": "", "vault_state": "ok", "pending_n": 0, "message": str(exc)}
    return templates.TemplateResponse(request, "unavailable.html", ctx, status_code=503)


@app.exception_handler(HTTPException)
async def _http_error(_request, exc):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


# ── 위키 폴더 ────────────────────────────────────────────────────────────

_vault_cache: dict[str, Vault] = {}


def vault_state() -> tuple[str, Vault | None]:
    """('ok' | 'missing' | 'none', Vault)"""
    path = config.load().get("vault_path") or ""
    if not path:
        return "none", None
    if not Vault.is_vault(path):
        return "missing", None
    if path not in _vault_cache:
        _vault_cache.clear()
        _vault_cache[path] = Vault(path)
    return "ok", _vault_cache[path]


def need_vault() -> Vault:
    state, vault = vault_state()
    if state == "none":
        raise HTTPException(409, "위키 폴더가 아직 설정되지 않았습니다. 설정 화면에서 저장 위치를 선택해 주세요.")
    if state == "missing":
        raise HTTPException(409, "위키 폴더를 찾을 수 없습니다. 구글 드라이브가 실행 중인지 확인해 주세요.")
    return vault


def make_zotero(cfg: dict) -> Zotero:
    return Zotero(cfg)


_ID_RE = re.compile(r"^[\w\-]{1,80}$")


def draft_key(key: str) -> str:
    """검토안 id (파일 이름으로 쓰이므로 글자·숫자·밑줄·하이픈만 받는다)."""
    if not _ID_RE.match(key):
        raise HTTPException(400, "잘못된 검토안 id 입니다.")
    return key


# ── 화면 ─────────────────────────────────────────────────────────────────


def page(request: Request, name: str, active: str, **ctx):
    state, vault = vault_state()
    pending_n = len(vault.pending_all()) if vault else 0
    return templates.TemplateResponse(
        request, name, {"active": active, "vault_state": state, "pending_n": pending_n, "stale": is_stale(), **ctx}
    )


def _pending_row(draft: dict) -> dict:
    meta = draft.get("paper") or {}
    return {
        "key": draft["id"],
        "title": meta.get("title", ""),
        "cite": render.cite_short(meta),
        "claims": len(draft.get("claims", [])),
        "editing": bool(draft.get("paper_id")),
        "created": (draft.get("created") or "")[:10],
    }


def _pdf_response(vault: Vault, relative: str) -> FileResponse:
    """논문 폴더의 PDF 를 브라우저에서 바로 볼 수 있게 내준다 (위키 폴더 밖의 경로는 거절)."""
    path = (vault.root / relative).resolve() if relative else None
    if not path or vault.root.resolve() not in path.parents or path.suffix.lower() != ".pdf" or not path.is_file():
        raise HTTPException(404, "PDF 파일을 찾을 수 없습니다. 다른 컴퓨터에서 넣은 논문이라면 구글 드라이브 동기화가 끝났는지 확인해 주세요.")
    return FileResponse(path, media_type="application/pdf", filename=path.name, content_disposition_type="inline")


def _chip(paper: dict, stats: dict) -> dict:
    """문헌 한 편을 가리키는 작은 표시 (어디서나 같은 모양으로 쓴다)."""
    s = stats.get(paper["id"], {})
    return {
        "id": paper["id"],
        "cite": render.cite_short(paper),
        "title": render.one_line(paper.get("title")),
        "read": render.is_read(paper),
        "sources": s.get("sources", 0),  # 위키 전체에서 이 문헌을 인용한 논문 수
    }


def _entry_view(entry: dict, onto, papers: dict, stats: dict, via: dict | None = None, focus: str | None = None) -> dict:
    """같은 주장 한 묶음을 화면용으로. focus 는 지금 보고 있는 문헌 (그 문헌은 인용 문헌 목록에서 뺀다)."""
    many = len(entry["members"]) > 1
    uses = []
    for src, claim in entry["members"]:
        if focus is not None and focus not in claim.get("cites", []):
            continue
        uses.append(
            {
                "paper_id": src["id"],
                "cite": render.cite_short(src),
                "paper_title": render.one_line(src.get("title")),
                "quote": render.one_line((claim.get("evidence") or {}).get("quote")),
                "location": render.one_line((claim.get("evidence") or {}).get("location")),
                "cites": [_chip(papers[pid], stats) for pid in claim.get("cites", []) if pid in papers] if many else [],
            }
        )
    return {
        "statement": entry["statement"],
        "type": entry["type"],
        "cites": [{**_chip(papers[pid], stats), "n": len(srcs)} for pid, srcs in entry["cites"].items() if pid in papers and pid != focus],
        "uses": uses,
        "shared": len(entry["sources"]),
        "keywords": [onto.nodes[k] for k in entry["keywords"] if k in onto.nodes],
        "via": via,
    }


def _own_claim_view(claim: dict, onto, papers: dict, stats: dict) -> dict:
    """읽은 논문이 한 주장 한 개 (그 논문 문서에서 차례대로 보여 준다)."""
    return {
        "statement": render.one_line(claim.get("statement")),
        "type": claim.get("type", "finding"),
        "cites": [{**_chip(papers[pid], stats), "n": 1} for pid in claim.get("cites", []) if pid in papers],
        "uses": [],
        "quote": render.one_line((claim.get("evidence") or {}).get("quote")),
        "location": render.one_line((claim.get("evidence") or {}).get("location")),
        "shared": 1,
        "keywords": [onto.nodes[k] for k in claim.get("keywords", []) if k in onto.nodes],
        "via": None,
    }


def _tree(onto, counts) -> list[dict]:
    def build(node):
        return {
            "id": node["id"],
            "name": node["name"],
            "aliases": node.get("aliases", []),
            "claims": counts[node["id"]]["claims"],
            "papers": counts[node["id"]]["papers"],
            "children": [build(c) for c in onto.children(node["id"])],
        }

    return [build(r) for r in onto.roots()]


@app.get("/")
def home(request: Request):
    state, vault = vault_state()
    if state != "ok":
        return RedirectResponse("/settings", status_code=302)
    onto, papers = vault.ontology(), vault.papers()
    usage = render.build_usage(papers, onto)
    counts = render.subtree_counts(onto, usage)
    recent = sorted((p for p in papers.values() if render.is_read(p)), key=lambda p: p.get("added", ""), reverse=True)[:6]
    top = sorted(
        (n for n in onto.nodes.values() if usage.get(n["id"])),
        key=lambda n: (-counts[n["id"]]["direct"], n["name"]),
    )[:14]
    found = wiki.insights(vault, limit=6)
    return page(
        request,
        "home.html",
        "home",
        stats=wiki.stats(vault),
        recent=[{"id": p["id"], "cite": render.cite_short(p), "title": render.one_line(p.get("title")), "claims": len(p.get("claims", []))} for p in recent],
        top=[{"id": n["id"], "name": n["name"], "n": counts[n["id"]]["direct"]} for n in top],
        roots=[{"id": r["id"], "name": r["name"], "claims": counts[r["id"]]["claims"], "children": len(onto.descendants(r["id"]))} for r in onto.roots()],
        multi_source=found["multi_source"],
        split=wiki.duplicates(vault),  # 같은 문헌이 둘로 갈렸을 수 있는 쌍 — 갈려 있으면 위의 집계에서 빠진다
        multi_direction=found["multi_direction"],
        queue=[_pending_row(d) for d in vault.pending_all()],
        storage=config.storage_info(str(vault.root)),
        vault_path=str(vault.root),
        pdf_dir=str(vault.pdf_dir),
        skill=integration.status(str(vault.root)),
    )


@app.get("/inbox")
def inbox_page(request: Request):
    """새 논문 · 검토: 논문 폴더에서 분석을 기다리는 PDF 와, 검토를 기다리는 검토안."""
    if vault_state()[0] != "ok":
        return RedirectResponse("/settings", status_code=302)
    vault = need_vault()

    def view(f: dict) -> dict:
        folder = f["path"][len("pdf/") : -len(f["name"])].strip("/")  # 논문 폴더 안의 하위 폴더 (없으면 빈 문자열)
        size = f"{f['size'] / 1e6:.1f} MB" if f["size"] >= 1e5 else f"{max(1, round(f['size'] / 1e3))} KB"
        return {**f, "detail": " · ".join(x for x in (folder, size, f["modified"]) if x)}

    return page(
        request,
        "inbox.html",
        "inbox",
        new=[view(f) for f in library.list_new(vault)],
        queue=[_pending_row(d) for d in vault.pending_all()],
        pdf_dir=str(vault.pdf_dir),
        skill=integration.status(str(vault.root)),
    )


@app.get("/review/{key}")
def review_page(request: Request, key: str):
    vault = need_vault()
    if not vault.pending(draft_key(key)):
        return RedirectResponse("/inbox", status_code=302)
    return page(request, "review.html", "inbox", key=key)


@app.get("/pdf/draft/{key}")
def draft_pdf(key: str):
    vault = need_vault()
    draft = vault.pending(draft_key(key))
    if not draft:
        raise HTTPException(404, "검토안을 찾을 수 없습니다.")
    return _pdf_response(vault, render.pdf_path(draft.get("paper") or {}))


@app.get("/pdf/{paper_id}")
def paper_pdf(paper_id: str):
    vault = need_vault()
    paper = vault.paper(draft_key(paper_id))
    if not paper:
        raise HTTPException(404, "논문을 찾을 수 없습니다.")
    return _pdf_response(vault, render.pdf_path(paper))


@app.get("/wiki")
def wiki_page(request: Request):
    if vault_state()[0] != "ok":
        return RedirectResponse("/settings", status_code=302)
    vault = need_vault()
    onto, papers = vault.ontology(), vault.papers()
    counts = render.subtree_counts(onto, render.build_usage(papers, onto))
    return page(request, "wiki.html", "wiki", tree=_tree(onto, counts), total=len(onto.nodes), flat=onto.flat())


PAPER_SORTS = {
    "recent": lambda r: (r["status"] != "read", [-ord(ch) for ch in r["added"]], r["cite"].casefold()),
    "cited": lambda r: (-r["cited_by"], -r["cited_claims"], r["cite"].casefold()),
    "directions": lambda r: (-r["directions"], -r["cited_claims"], r["cite"].casefold()),
    "claims": lambda r: (-r["cited_claims"], -r["cited_by"], r["cite"].casefold()),
}


@app.get("/papers")
def papers_page(request: Request, kind: str = "all", sort: str = ""):
    if vault_state()[0] != "ok":
        return RedirectResponse("/settings", status_code=302)
    vault = need_vault()
    onto = vault.ontology()
    rows = wiki.paper_rows(vault)
    totals = {"all": len(rows), "read": sum(1 for r in rows if r["status"] == "read")}
    totals["cited"] = totals["all"] - totals["read"]
    kind = kind if kind in ("all", "read", "cited") else "all"
    sort = sort if sort in PAPER_SORTS else ("recent" if kind == "read" else "cited")
    if kind != "all":
        rows = [r for r in rows if r["status"] == kind]
    rows.sort(key=PAPER_SORTS[sort])
    for r in rows:
        r["keywords"] = [onto.nodes[k] for k in r["keyword_ids"][:4]]
        r["more"] = max(0, len(r["keyword_ids"]) - 4)
    return page(request, "papers.html", "papers", rows=rows, kind=kind, sort=sort, totals=totals)


@app.get("/wiki/k/{node_id}")
def keyword_page(request: Request, node_id: str, sub: int = 0):
    vault = need_vault()
    onto, papers = vault.ontology(), vault.papers()
    node = onto.get(node_id)
    if not node:
        raise HTTPException(404, "키워드를 찾을 수 없습니다.")
    usage = render.build_usage(papers, onto)
    counts = render.subtree_counts(onto, usage)
    all_groups = render.claim_groups(papers)
    stats = render.paper_stats(papers, onto)
    ids = [node_id, *(onto.descendants(node_id) if sub else [])]
    groups: dict[str, list] = {t: [] for t in CLAIM_TYPES}
    seen = set()
    for kid in ids:
        for entry in render.grouped(usage.get(kid, []), all_groups):
            if entry["key"] in seen:
                continue
            seen.add(entry["key"])
            via = onto.nodes[kid] if kid != node_id else None
            groups.setdefault(entry["type"], []).append(_entry_view(entry, onto, papers, stats, via))
    top: dict[str, dict] = {}
    for kid in ids:  # 이 키워드(와 펼친 하위 키워드)에서 자주 인용되는 문헌
        for row in render.keyword_cited(kid, usage, papers):
            item = top.setdefault(row["paper"]["id"], {**_chip(row["paper"], stats), "claims": 0, "here": 0})
            item["claims"] += row["claims"]
            item["here"] = max(item["here"], row["sources"])
    ranked = sorted(top.values(), key=lambda r: (-r["here"], -r["claims"], r["cite"].casefold()))
    _, notes = render.split_notes(vault.keywords_md / f"{node['file']}.md")
    return page(
        request,
        "keyword.html",
        "wiki",
        node=node,
        crumbs=[onto.nodes[i] for i in onto.path_ids(node_id)[:-1]],
        groups={t: items for t, items in groups.items() if items},
        top_cited=ranked[:12],
        top_more=max(0, len(ranked) - 12),
        counts=counts[node_id],
        children=[{**c, **counts[c["id"]]} for c in onto.children(node_id)],
        related=[{"id": n["id"], "name": n["name"], "n": k} for n, k in render.related_keywords(node_id, papers, onto)],
        sub=bool(sub),
        notes=notes.strip(),
        flat=[f for f in onto.flat() if f["id"] != node_id and f["id"] not in onto.descendants(node_id)],
    )


@app.get("/wiki/p/{paper_id}")
def paper_page(request: Request, paper_id: str):
    vault = need_vault()
    paper = vault.paper(paper_id)
    if not paper:
        raise HTTPException(404, "논문을 찾을 수 없습니다.")
    onto, papers = vault.ontology(), vault.papers()
    cited = render.citations(papers)
    stats = render.paper_stats(papers, onto, cited)
    mine = stats.get(paper["id"], {"claims": 0, "sources": 0, "keywords": 0, "keyword_ids": []})
    uses = cited.get(paper["id"], [])
    per_kw: dict[str, int] = {}
    for _, claim in uses:
        for k in dict.fromkeys(claim.get("keywords", [])):
            if k in onto.nodes:
                per_kw[k] = per_kw.get(k, 0) + 1
    _, notes = render.split_notes(vault.papers_md / f"{paper['id']}.md")
    return page(
        request,
        "paper.html",
        "papers",
        paper=paper,
        read=render.is_read(paper),
        cite=render.cite_short(paper),
        authors="; ".join(render.author_name(a, full=True) for a in paper.get("authors", [])) + (" et al." if paper.get("et_al") else ""),
        mine=mine,
        directions=[{"id": k, "name": onto.nodes[k]["name"], "n": n} for k, n in sorted(per_kw.items(), key=lambda kv: (-kv[1], onto.nodes[kv[0]]["name"]))],
        cited_for=[_entry_view(e, onto, papers, stats, focus=paper["id"]) for e in render.grouped(uses, render.claim_groups(papers))],
        claims=[_own_claim_view(c, onto, papers, stats) for c in paper.get("claims", [])],
        zotero_uri=render.zotero_select_uri(paper),
        pdf_uri=f"/pdf/{paper['id']}" if render.pdf_path(paper) else render.zotero_pdf_uri(paper),
        pdf_name=render.pdf_path(paper).rsplit("/", 1)[-1],
        notes=notes.strip(),
    )


@app.get("/search")
def search_page(request: Request, q: str = ""):
    vault = need_vault()
    results = wiki.search(vault, q) if q.strip() else None
    claims = []
    for c in (results or {}).get("claims", []):  # 검색 결과(JSON)를 다른 화면과 같은 주장 모양으로
        refs = results["references"]
        claims.append(
            {
                "statement": c["statement"],
                "type": c["type"],
                "cites": [{"id": x["citekey"], "cite": x["cite"], "title": x["title"], "read": refs.get(x["citekey"], {}).get("status") == "read", "sources": 0, "n": x["cited_in"]} for x in c["cites"]],
                "uses": [{"paper_id": s["citekey"], "cite": s["cite"], "paper_title": refs.get(s["citekey"], {}).get("title", ""), "quote": s["quote"], "location": s["location"], "cites": []} for s in c["sources"]],
                "shared": len(c["sources"]),
                "keywords": [{"id": kid, "name": name} for kid, name in zip(c["keyword_ids"], c["keywords"])],
                "via": None,
            }
        )
    return page(request, "search.html", "wiki", q=q, results=results, claims=claims)


@app.get("/graph")
def graph_page(request: Request):
    if vault_state()[0] != "ok":
        return RedirectResponse("/settings", status_code=302)
    return page(request, "graph.html", "graph")


@app.get("/settings")
def settings_page(request: Request):
    return page(request, "settings.html", "settings")


# ── API: 설정 ────────────────────────────────────────────────────────────


@app.get("/api/ping")
def api_ping():
    return {"app": "paperwiki", "version": __version__, "stamp": STARTED_WITH, "stale": is_stale()}


@app.post("/api/shutdown")
def api_shutdown(request: Request):
    """새로 실행한 paperwiki 가 예전 코드로 떠 있는 서버를 끄고 자리를 넘겨받을 때 부른다."""
    if request.headers.get("x-paperwiki") != "1":  # 웹 페이지가 몰래 부르지 못하게
        raise HTTPException(403, "허용되지 않은 요청입니다.")
    server = getattr(app.state, "server", None)
    if server is None:
        raise HTTPException(409, "이 서버는 스스로 종료할 수 없습니다.")
    server.should_exit = True
    return {"ok": True}


@app.get("/api/settings")
def api_settings(rescan: int = 0):
    cfg = config.load()
    state, vault = vault_state()
    data_dir = config.detect_zotero_data_dir(cfg)
    mounts = gdrive.detect()
    storage = config.storage_info(cfg.get("vault_path", ""), mounts)
    stats, warning = None, ""
    if vault:
        try:
            stats = wiki.stats(vault)
        except VaultUnavailable as exc:  # 설정 화면은 이 상태에서도 열려야 한다
            warning = str(exc)
    return {
        "config": cfg,
        "vault_state": state,
        "vault_warning": warning,
        "storage_kind": storage["kind"],
        "storage_account": storage["email"],
        "language": vault.settings().get("language") if vault else None,
        "stats": stats,
        "storage_options": config.storage_options(mounts, rescan=bool(rescan)),
        "gdrive": {"state": gdrive.state(mounts), "can_launch": gdrive.can_launch(), "download_url": gdrive.DOWNLOAD_URL},
        "secrets": {name: config.secret_source(name) for name in config.SECRET_ENV},
        "zotero_data_dir": str(data_dir) if data_dir else "",
        "zotero_local_help": LOCAL_HELP,
        "claude": integration.status(cfg.get("vault_path", "")) if state == "ok" else None,
        "claude_code_installed": integration.claude_code_installed(),
        "pdf_dir": str(vault.pdf_dir) if vault else "",
        "pdf_name": {"pattern": library.name_pattern(vault), "example": library.pdf_filename(_NAME_SAMPLE, library.name_pattern(vault))} if vault else None,
    }


_NAME_SAMPLE = {
    "id": "kim2023computerized",
    "title": "Computerized cognitive training in mild cognitive impairment",
    "authors": [{"family": "Kim", "given": "Jisoo"}, {"family": "Lee", "given": "Sang"}],
    "year": "2023",
}


@app.post("/api/vault")
def api_set_vault(body: dict = Body(...)):
    raw = str(body.get("path") or "").strip().strip('"')
    if not raw:
        raise HTTPException(400, "폴더 경로를 입력해 주세요.")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise HTTPException(400, "전체 경로(절대 경로)를 입력해 주세요.")
    existing = Vault.is_vault(path)
    if not existing:
        if path.exists() and not path.is_dir():
            raise HTTPException(400, "폴더가 아닌 파일 경로입니다.")
        if path.is_dir() and any(path.iterdir()) and not body.get("confirm_nonempty"):
            raise HTTPException(409, "비어 있지 않은 폴더입니다. 이 폴더 안에 위키를 만들까요?")
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise HTTPException(400, f"폴더를 만들 수 없습니다: {exc}") from exc
    vault = Vault(path)
    try:
        if existing:
            # 불러오기: 아무것도 쓰지 않는다. 다 읽을 수 있는지만 확인한다 (동기화가 덜 끝났으면 여기서 멈춘다).
            vault.ontology()
            vault.papers()
        else:
            vault.init(language=body.get("language") or "ko")
            render.sync(vault)
    except OSError as exc:
        raise HTTPException(400, f"이 폴더에 쓸 수 없습니다: {exc}") from exc
    config.update(vault_path=str(path))
    _vault_cache.clear()
    config._scan_cache.clear()
    return {"ok": True, "connected_existing": existing, "path": str(path), "summary": vault_summary(path) if existing else None}


@app.post("/api/gdrive/launch")
def api_gdrive_launch():
    """설치되어 있지만 꺼져 있는 구글 드라이브 데스크톱을 켠다."""
    if not gdrive.launch():
        raise HTTPException(400, "구글 드라이브 데스크톱을 실행하지 못했습니다. 시작 메뉴에서 직접 실행해 주세요.")
    return {"ok": True}


@app.post("/api/settings")
def api_save_settings(body: dict = Body(...)):
    changes = {}
    if body.get("zotero_mode") in ("local", "web"):
        changes["zotero_mode"] = body["zotero_mode"]
    if "zotero_data_dir" in body:
        changes["zotero_data_dir"] = str(body["zotero_data_dir"] or "").strip()
    config.update(**changes)
    return {"ok": True}


@app.post("/api/secrets")
def api_set_secret(body: dict = Body(...)):
    name, value = body.get("name"), str(body.get("value") or "").strip()
    if name not in config.SECRET_ENV:
        raise HTTPException(400, "알 수 없는 키 이름입니다.")
    extra = {}
    try:
        if not value:
            config.delete_secret(name)
        else:
            if name == "zotero_api_key":
                who = lookup_user_id(value)  # 키가 유효한지 확인하면서 사용자 ID 도 알아낸다
                config.update(zotero_user_id=who["user_id"])
                extra = {"username": who["username"]}
            config.set_secret(name, value)
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc
    return {"ok": True, "source": config.secret_source(name), **extra}


@app.post("/api/test/zotero")
def api_test_zotero():
    with make_zotero(config.load()) as z:
        return z.ping()


@app.post("/api/zotero/connect")
def api_zotero_connect():
    """Zotero 앱에 항목 추가 허용을 요청한다. Zotero 가 띄운 확인 창에서 사용자가 고를 때까지 기다린다."""
    with make_zotero(config.load()) as z:
        z.ping()
        return z.authorize()


@app.post("/api/claude/install")
def api_claude_install():
    vault = need_vault()
    path = integration.install(str(vault.root))
    return {"ok": True, "path": str(path)}


@app.post("/api/rebuild")
def api_rebuild():
    return {"ok": True, **render.sync(need_vault())}


@app.post("/api/pdf-name")
def api_pdf_name(body: dict = Body(...)):
    """PDF 이름 규칙을 바꾸고, 이미 등록된 논문의 PDF 에도 적용한다."""
    vault = need_vault()
    vault.check_readable()
    pattern = library.set_name_pattern(vault, str(body.get("pattern") or ""))
    changes = wiki.tidy(vault)
    return {"ok": True, "pattern": pattern, "renamed": sum(1 for c in changes if c["action"] == "renamed"), "failed": sum(1 for c in changes if c["action"] == "rename_failed")}


# ── API: 검토 ────────────────────────────────────────────────────────────


@app.get("/api/inbox")
def api_inbox():
    vault = need_vault()
    return {"new": library.list_new(vault), "pending": [_pending_row(d) for d in vault.pending_all()]}


@app.get("/api/pending/{key}")
def api_pending_one(key: str):
    vault = need_vault()
    draft = vault.pending(draft_key(key))
    if not draft:
        raise HTTPException(404, "검토안을 찾을 수 없습니다.")
    info = wiki.review(vault, key)  # 등록되면 생길 것(인용 키, PDF 이름, 문헌 연결)과 확인할 점
    out = wiki.annotate_draft(vault, draft)
    meta = out["paper"]
    unused = info["references"]["unused"]
    if unused:
        info["warnings"].append("어느 주장에도 연결되지 않아 등록되지 않는 참고문헌: " + ", ".join(f"[{r['ref']}] {r['cite']}" for r in unused[:40]) + (" …" if len(unused) > 40 else ""))
    out["view"] = {
        "cite": render.cite_short(meta),
        "authors": "; ".join(render.author_name(a, full=True) for a in meta.get("authors") or []),
        "zotero_uri": render.zotero_select_uri(meta),
        "pdf_uri": f"/pdf/draft/{key}" if render.pdf_path(meta) else render.zotero_pdf_uri(meta),
        "citekey": info["citekey"],
        "pdf": info["pdf"],
        "status": wiki.review_status(info),
        "warnings": info["warnings"],
        "counts": wiki.counts_text(info),
        "note": info["note"],
    }
    return {"draft": out, "ontology": vault.ontology().flat()}


@app.put("/api/pending/{key}")
def api_pending_save(key: str, body: dict = Body(...)):
    vault = need_vault()
    with vault.lock:
        draft = vault.pending(draft_key(key))
        if not draft:
            raise HTTPException(404, "검토안을 찾을 수 없습니다.")
        draft["summary"] = str(body.get("summary", draft.get("summary", "")))[:3000]
        draft["claims"] = wiki.clean_claims(body.get("claims"))
        draft["updated"] = now_iso()
        vault.save_pending(key, draft)
    return {"ok": True}


@app.post("/api/pending/{key}/approve")
def api_pending_approve(key: str, body: dict = Body(...)):
    vault = need_vault()
    result = wiki.approve(vault, draft_key(key), body)
    # 위키 등록이 끝난 뒤에 Zotero 와 맞춘다. 이 단계가 안 되어도 등록은 그대로다.
    try:
        with make_zotero(config.load()) as z:
            changes = wiki.zotero_sync(vault, z, [result["paper"]["id"]], **wiki.zotero_options())
    except ZoteroError as exc:
        changes = [{"paper": "", "action": "zotero_unreachable", "note": str(exc)}]
    return {
        "ok": True,
        "zotero": wiki.zotero_report(changes, one_paper=True),
        "paper_id": result["paper"]["id"],
        "created_keywords": result["created_keywords"],
        "pdf": result["pdf"],
        "pdf_note": result["pdf_note"],
        "new_cited": len(result["new_cited"]),
        "linked_cited": len(result["linked_cited"]),
    }


@app.delete("/api/pending/{key}")
def api_pending_delete(key: str):
    wiki.discard(need_vault(), draft_key(key))
    return {"ok": True}


# ── API: 위키 ────────────────────────────────────────────────────────────


@app.get("/api/ontology")
def api_ontology():
    return {"nodes": need_vault().ontology().flat()}


def _aliases(value) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = re.split(r"[,\n]", value)
    return [str(v).strip() for v in value if str(v).strip()]


@app.post("/api/keywords")
def api_keyword_add(body: dict = Body(...)):
    node = wiki.add_keyword(
        need_vault(), str(body.get("name") or ""), body.get("parent") or None, _aliases(body.get("aliases")) or [], str(body.get("description") or "")
    )
    return {"ok": True, "id": node["id"]}


@app.put("/api/keywords/{node_id}")
def api_keyword_update(node_id: str, body: dict = Body(...)):
    kwargs = {}
    if "name" in body:
        kwargs["name"] = str(body["name"])
    if "aliases" in body:
        kwargs["aliases"] = _aliases(body["aliases"])
    if "description" in body:
        kwargs["description"] = str(body["description"] or "")
    if "parent" in body:
        kwargs["parent"] = body["parent"] or None
    wiki.update_keyword(need_vault(), node_id, **kwargs)
    return {"ok": True}


@app.post("/api/keywords/{node_id}/merge")
def api_keyword_merge(node_id: str, body: dict = Body(...)):
    target = wiki.merge_keywords(need_vault(), node_id, str(body.get("into") or ""))
    return {"ok": True, "id": target["id"]}


@app.delete("/api/keywords/{node_id}")
def api_keyword_delete(node_id: str):
    wiki.delete_keyword(need_vault(), node_id)
    return {"ok": True}


@app.post("/api/papers/{paper_id}/edit")
def api_paper_edit(paper_id: str):
    """승인된 논문을 검토 화면에서 다시 고칠 수 있게 검토안을 만든다."""
    vault = need_vault()
    with vault.lock:
        paper = vault.paper(draft_key(paper_id))
        if not paper:
            raise HTTPException(404, "논문을 찾을 수 없습니다.")
        if not render.is_read(paper):
            raise HTTPException(400, "인용 문헌에는 고칠 주장이 없습니다. 이 문헌을 인용한 논문의 문서에서 주장을 고쳐 주세요.")
        key = paper["id"]
        if not vault.pending(key):
            vault.save_pending(key, wiki.draft_from_paper(vault, paper))
    return {"ok": True, "key": key}


@app.delete("/api/papers/{paper_id}")
def api_paper_delete(paper_id: str):
    result = wiki.delete_paper(need_vault(), paper_id)
    return {"ok": True, **result}


@app.get("/api/graph")
def api_graph(papers: int = 2):
    return wiki.graph(need_vault(), papers_mode=max(0, min(3, papers)))


@app.get("/api/search")
def api_search(q: str = ""):
    return wiki.search(need_vault(), q)
