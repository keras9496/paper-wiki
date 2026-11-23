"""명령줄 진입점. Claude Code 의 paper-wiki 스킬이 이 명령들로 위키를 다룬다.

    위키가 모으는 것: 읽은 논문이 다른 문헌을 인용하며 한 주장 → 그 주장에 인용된 문헌.

    논문 추가 (읽기는 Claude Code 가 하고, 사용자가 검토한 것만 등록된다)
      paperwiki inbox                       논문 폴더의 새 PDF 와 검토 대기 목록
      paperwiki prepare "<PDF | URL>"       읽을 준비 (작업 지시 파일을 만든다)
      paperwiki propose <id>                Claude 가 쓴 제안을 검토안으로 저장하고 요약을 보여 준다
      paperwiki approve <id>                검토안을 위키에 등록 (인용 문헌이 함께 등록되고, PDF 이름이 규칙대로 바뀐다)
      paperwiki discard <id>                검토안 폐기
      paperwiki zotero list|pull            Zotero 에 있는 논문 찾기 · 논문 폴더로 가져오기
      paperwiki zotero connect|sync|config  Zotero 에 넣기 허용받기 · 위키의 읽은 논문을 Zotero 와 맞추기 · 설정

    위키 읽기
      paperwiki search "작업기억" --json     키워드·주장(인용 문헌 포함)·문헌 검색
      paperwiki show "<키워드 | @citekey>"   문서 한 개
      paperwiki tree / papers / insights    키워드 온톨로지 / 문헌 목록 / 여러 번·여러 방향으로 인용된 문헌

    관리
      paperwiki                             웹 화면 (탐색·시각화·설정)
      paperwiki same / merge-papers         같은 주장 묶기 / 둘로 나뉜 같은 문헌 합치기
      paperwiki duplicates                  같은 문헌이 두 문서로 갈렸을 수 있는 쌍 찾기 (--merge, --find-dois, --apart)
      paperwiki tidy / fix / naming         논문 폴더 정리 / 서지 정보 고치기 / PDF 이름 규칙
      paperwiki reader-model [모델]         논문 읽기 에이전트의 모델 보기 · 바꾸기 (기본 sonnet)
      paperwiki setup / claude-install / doctor
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
import webbrowser
from pathlib import Path

from . import __version__, config


def _utf8_stdout() -> None:
    # Windows 에서 출력이 파이프로 넘어갈 때(예: Claude Code) 한글이 깨지지 않도록
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _vault():
    from .store import Vault

    path = config.load().get("vault_path") or ""
    if not path:
        sys.exit("위키 폴더가 아직 설정되지 않았습니다. 'paperwiki' 를 실행해 설정 화면에서 저장 위치를 정해 주세요.")
    if not Vault.is_vault(path):
        sys.exit(f"위키 폴더를 찾을 수 없습니다: {path}\n구글 드라이브가 실행 중인지 확인해 주세요.")
    return Vault(path)


def _zotero():
    """Zotero 연결 객체. 설정이 안 되어 있으면 None (연결이 안 되는 것은 쓸 때 드러난다)."""
    from .zotero import Zotero, ZoteroError

    try:
        return Zotero(config.load())
    except ZoteroError:
        return None


def _lookup():
    """DOI 등록 기록을 찾는 함수 (서지 정보 확인용)."""
    from . import biblio

    return biblio.lookup


def _search():
    """참고문헌의 DOI 를 제목·저자·연도로 찾는 함수 (같은 문헌을 잇는 기준을 채우는 용도)."""
    from . import biblio

    return biblio.find_doi


def _dump(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


# ── serve ────────────────────────────────────────────────────────────────


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _ping(port: int) -> dict | None:
    """그 포트에 Paper Wiki 가 떠 있으면 그 서버가 알려 주는 정보."""
    import httpx

    try:
        r = httpx.get(f"http://127.0.0.1:{port}/api/ping", timeout=2)
        return r.json() if r.status_code == 200 and r.json().get("app") == "paperwiki" else None
    except Exception:
        return None


def _is_paperwiki(port: int) -> bool:
    return _ping(port) is not None


def _take_over(port: int) -> bool:
    """예전 코드로 떠 있는 서버에 종료를 부탁하고, 포트가 빌 때까지 잠깐 기다린다."""
    import time

    import httpx

    try:
        httpx.post(f"http://127.0.0.1:{port}/api/shutdown", headers={"X-Paperwiki": "1"}, timeout=3)
    except Exception:
        pass
    for _ in range(40):
        if _port_free(port):
            return True
        time.sleep(0.25)
    return False


def _running_url() -> str:
    """웹 화면이 떠 있으면 그 주소."""
    port = int(config.load().get("port") or config.DEFAULT_PORT)
    return f"http://127.0.0.1:{port}" if not _port_free(port) and _is_paperwiki(port) else ""


def cmd_serve(args) -> int:
    import uvicorn

    from .server import app

    port = args.port or int(config.load().get("port") or config.DEFAULT_PORT)
    from .server import code_stamp

    if not _port_free(port):
        running = _ping(port)
        if running and running.get("stamp") == code_stamp() and not running.get("stale"):
            print(f"Paper Wiki 가 이미 실행 중입니다: http://127.0.0.1:{port}")
            if not args.no_browser:
                webbrowser.open(f"http://127.0.0.1:{port}")
            return 0
        if running:  # 프로그램이 바뀌기 전의 코드로 떠 있는 서버: 끄고 넘겨받는다
            print("예전 코드로 실행 중인 Paper Wiki 를 종료하고 다시 시작합니다…")
            if not _take_over(port):
                sys.exit(
                    f"http://127.0.0.1:{port} 에서 예전 버전의 Paper Wiki 가 실행 중인데 끄지 못했습니다.\n"
                    "그 창을 닫거나(작업 관리자에서 paperwiki·python 프로세스를 끝내도 됩니다) 다시 실행해 주세요."
                )
        else:
            port = next((p for p in range(port + 1, port + 20) if _port_free(p)), 0)
            if not port:
                sys.exit("사용할 수 있는 포트를 찾지 못했습니다. --port 로 지정해 주세요.")
    url = f"http://127.0.0.1:{port}"
    print(f"\n  Paper Wiki {__version__}\n  {url}\n\n  이 창을 닫거나 Ctrl+C 를 누르면 종료됩니다.\n")
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    app.state.server = server  # /api/shutdown 이 이 서버를 끌 수 있게
    server.run()
    return 0


# ── 논문 추가 ────────────────────────────────────────────────────────────


def _size(n: int) -> str:
    return f"{n / 1e6:.1f} MB" if n >= 1e5 else f"{max(1, round(n / 1e3))} KB"


def cmd_inbox(args) -> int:
    from . import library, render

    vault = _vault()
    new = library.list_new(vault)
    pending = [
        {"id": d["id"], "cite": render.cite_short(d.get("paper") or {}), "title": (d.get("paper") or {}).get("title", ""),
         "claims": len(d.get("claims", [])), "replaces": d.get("paper_id"), "pdf": ((d.get("paper") or {}).get("pdf") or {}).get("path")}
        for d in vault.pending_all()
    ]
    if args.json:
        _dump({"pdf_dir": vault.pdf_dir.as_posix(), "new": new, "pending": pending})
        return 0
    print(f"논문 폴더: {vault.pdf_dir.as_posix()}\n")
    print(f"## 새 PDF — {len(new)}편 (아직 위키에 등록되지 않음)")
    for item in new:
        print(f"- {item['path']}  ({_size(item['size'])}, {item['modified']})")
    if not new:
        print("- 없음. 읽을 논문 PDF 를 논문 폴더에 넣으면 여기에 나타납니다.")
    print(f"\n## 검토 대기 — {len(pending)}건 (읽기는 끝났고, 사용자 검토를 기다림)")
    for item in pending:
        print(f"- {item['id']}  {item['cite']} {item['title']} — 주장 {item['claims']}" + ("  (기존 문서를 바꾸는 검토안)" if item["replaces"] else ""))
    if not pending:
        print("- 없음")
    elif not args.json:
        print("\n검토 요약 보기: paperwiki review <id> · 등록: paperwiki approve <id> · 폐기: paperwiki discard <id>")
    return 0


def _print_prepared(info: dict) -> None:
    pages = f"{info['pages']}쪽" if info["pages"] else "쪽수 확인 불가"
    split = f", {info['parts']}개 파일로 나눔" if info["parts"] > 1 else ""
    reduced = f", 읽기용 사본은 큰 그림을 줄여 {_size(info['read_bytes'])}" if info.get("reduced") else ""
    print(f"검토안 id : {info['id']}")
    print(f"PDF       : {info['pdf']} ({pages}{split}{reduced})")
    if info["replaces"]:
        print(f"기존 문서 : @{info['replaces']} (등록하면 이 문서의 내용이 바뀝니다)")
    if info["zotero"]:
        print("Zotero    : 이 항목의 서지 정보를 사용합니다")
    if info.get("wiki_claims"):
        print(f"기존 주장 : 위키의 주장 {info['wiki_claims']}개를 함께 넘깁니다 (같은 주장이면 묶도록)")
    print(f"brief     : {info['brief']}")
    print(f"proposal  : {info['proposal']}")
    print(f"다음      : {info['brief']} 를 읽기 에이전트에게 맡기고, 끝나면 paperwiki propose {info['id']}\n")


def cmd_prepare(args) -> int:
    from . import library

    vault = _vault()
    results, failed = [], 0
    for source in args.source:
        try:
            info = library.prepare(vault, source, again=args.again)
        except library.LibraryError as exc:
            failed += 1
            results.append({"source": source, "error": str(exc)})
            if not args.json:
                print(f"[실패] {source}\n  {exc}\n", file=sys.stderr)
            continue
        results.append(info)
        if not args.json:
            _print_prepared(info)
    if args.json:
        _dump(results)
    return 1 if failed else 0


def cmd_propose(args) -> int:
    from . import wiki

    vault = _vault()
    text = Path(args.file).read_text(encoding="utf-8-sig") if args.file else None
    z = None if args.no_zotero else _zotero()
    try:
        info = wiki.propose(vault, args.id, text, zotero=z, lookup=None if args.no_lookup else _lookup(), search=None if args.no_lookup else _search())
    finally:
        if z:
            z.close()
    if args.json:
        _dump(info)
    else:
        url = _running_url()
        print(wiki.review_text(info, f"{url}/review/{info['id']}" if url else "", compact=args.compact))
        print(f"\n등록: paperwiki approve {info['id']} · 폐기: paperwiki discard {info['id']}  (등록은 사용자가 이 검토안을 확인한 뒤에만)")
    return 0


def cmd_review(args) -> int:
    from . import wiki

    info = wiki.review(_vault(), args.id)
    if args.json:
        _dump(info)
    else:
        url = _running_url()
        print(wiki.review_text(info, f"{url}/review/{info['id']}" if url else "", compact=args.compact))
    return 0


def cmd_approve(args) -> int:
    from . import wiki

    vault = _vault()
    cfg = config.load()
    z = None if args.no_zotero else _zotero()
    failed = 0
    for draft_id in args.id:
        try:
            result = wiki.approve(vault, draft_id)
        except wiki.WikiError as exc:
            failed += 1
            print(f"[실패] {draft_id}: {exc}", file=sys.stderr)
            continue
        paper = result["paper"]
        # 위키 등록이 끝난 뒤에 Zotero 와 맞춘다. 이 단계가 실패해도 위키 등록은 그대로다.
        zotero_notes = wiki.zotero_report(wiki.zotero_sync(vault, z, [paper["id"]], **wiki.zotero_options(cfg)), one_paper=True) if z else []
        paper = vault.paper(paper["id"]) or paper
        print(f"등록했습니다: @{paper['id']} — {paper.get('title', '')}")
        print(f"  위키 문서 : papers/{paper['id']}.md")
        print(f"  주장      : {len(paper['claims'])}개")
        print(f"  인용 문헌 : 새로 등록 {len(result['new_cited'])}편 · 이미 위키에 있던 문헌에 연결 {len(result['linked_cited'])}편")
        if result["linked_cited"]:
            print("              연결된 문헌: " + ", ".join("@" + pid for pid in result["linked_cited"][:20]) + (" …" if len(result["linked_cited"]) > 20 else ""))
        if result["maybe_same"]:
            print(f"  확인 필요 : 위키의 기존 문헌과 같은 문헌일 수 있는 것 {len(result['maybe_same'])}쌍이 따로 등록되었습니다 → paperwiki duplicates")
            for m in result["maybe_same"][:10]:
                print(f"              @{m['new']} ↔ @{m['existing']} — {m['why']}")
        if result["pdf"]:
            before = result["pdf_renamed_from"]
            print("  PDF       : " + (f"{before} → {result['pdf']}" if before else result["pdf"]))
        if result["pdf_note"]:
            print(f"  주의      : {result['pdf_note']}")
        if result["created_keywords"]:
            print(f"  새 키워드 : {', '.join(result['created_keywords'])}")
        if paper.get("zotero_key") and not zotero_notes:
            zotero_notes = ["Zotero 항목과 연결되어 있습니다"]
        for i, note in enumerate(zotero_notes or ["확인하지 않았습니다 (나중에 'paperwiki zotero sync')"]):
            print(("  Zotero    : " if i == 0 else "              ") + note)
    if z:
        z.close()
    return 1 if failed else 0


def cmd_discard(args) -> int:
    from . import wiki

    vault = _vault()
    for draft_id in args.id:
        wiki.discard(vault, draft_id)
        print(f"검토안을 폐기했습니다: {draft_id} (PDF 는 논문 폴더에 그대로 있습니다)")
    return 0


def cmd_zotero(args) -> int:
    from . import library, render, wiki
    from .zotero import Zotero

    cfg = config.load()
    if args.zcmd == "config":
        changes = {}
        if args.add:
            changes["zotero_add"] = args.add == "on"
        if args.collection is not None:
            changes["zotero_collection"] = args.collection.strip()
        if args.pdf:
            changes["zotero_pdf"] = args.pdf
        cfg = config.update(**changes) if changes else cfg
        print(f"읽은 논문을 Zotero 에 넣기 : {'켜짐' if cfg.get('zotero_add') else '꺼짐'}  (--add on|off)")
        print(f"모아 둘 Zotero 컬렉션      : {cfg.get('zotero_collection') or '(쓰지 않음)'}  (--collection \"이름\", 쓰지 않으려면 \"\")")
        print(f"Zotero 항목의 PDF          : {'위키 논문 폴더의 PDF 를 링크' if cfg.get('zotero_pdf') == 'link' else '붙이지 않음'}  (--pdf link|none)")
        return 0
    vault = _vault()
    with Zotero(cfg) as z:
        if args.zcmd == "connect":
            info = z.ping()
            if z.can_write() and not args.again:
                print(f"Zotero 에 연결되어 있고(항목 {info.get('total')}), 항목 추가도 이미 허용받았습니다. 다시 허용받으려면 --again.")
                return 0
            print("Zotero 창에 확인 창이 떴습니다. '항상 허용(Always Allow)'을 눌러 주세요…", flush=True)
            result = z.authorize()
            if result.get("once"):
                print("'허용'(이번 한 번만)을 고르셨습니다. Paper Wiki 는 논문을 등록할 때마다 Zotero 에 항목을 넣으므로 '항상 허용'이 필요합니다.\n다시 실행해 '항상 허용(Always Allow)'을 눌러 주세요.")
                return 1
            print("허용받았습니다. 이제 위키에 등록하는 읽은 논문이 Zotero 에도 들어갑니다. (허용 키는 이 컴퓨터의 자격 증명 저장소에만 있습니다)")
            return 0
        if args.zcmd == "sync":
            changes = wiki.zotero_sync(vault, z, dry_run=args.dry_run, include_cited=args.cited, **wiki.zotero_options(cfg))
            for line in wiki.zotero_report(changes):
                print(line)
            read = [p for p in vault.papers().values() if render.is_read(p)]
            print(("바뀐 것이 없습니다. " if not changes else "") + f"읽은 논문 {len(read)}편 중 {sum(1 for p in read if p.get('zotero_key'))}편이 Zotero 항목과 연결되어 있습니다.")
            return 0
        if args.zcmd == "pull":
            failed = 0
            for key in args.key:
                try:
                    _print_prepared(library.pull_from_zotero(vault, z, key))
                except library.LibraryError as exc:
                    failed += 1
                    print(f"[실패] {key}: {exc}\n", file=sys.stderr)
            return 1 if failed else 0
        metas, total = z.items(q=" ".join(args.query), limit=args.limit)
    in_wiki = {p.get("zotero_key"): p["id"] for p in vault.papers().values() if p.get("zotero_key")}
    rows = [
        {"key": m["zotero_key"], "cite": render.cite_short(m), "title": m["title"], "venue": m["venue"], "added": (m.get("date_added") or "")[:10], "in_wiki": in_wiki.get(m["zotero_key"])}
        for m in metas
    ]
    if args.json:
        _dump({"total": total, "items": rows})
        return 0
    for row in rows:
        state = f"위키에 있음 (@{row['in_wiki']})" if row["in_wiki"] else "위키에 없음"
        print(f"- {row['key']}  {row['cite']} {row['title']}  [{state}]")
    if not rows:
        print("결과가 없습니다.")
    else:
        print(f"\n({len(rows)}/{total if total is not None else '?'}) 논문 폴더로 가져오기: paperwiki zotero pull <항목 키>")
    return 0


# ── 조회 명령 ────────────────────────────────────────────────────────────


def cmd_search(args) -> int:
    from . import wiki

    result = wiki.search(_vault(), " ".join(args.query), limit=args.limit)
    if args.json:
        _dump(result)
        return 0
    if not (result["keywords"] or result["claims"] or result["papers"]):
        print("결과가 없습니다.")
        return 0
    if result["keywords"]:
        print("## 키워드")
        for k in result["keywords"]:
            alias = f"  (별칭: {', '.join(k['aliases'])})" if k["aliases"] else ""
            print(f"- {' › '.join(k['path'])}{alias} — 주장 {k['claims']}, 인용 문헌 {k['papers']}  [{k['file']}]")
        print()
    if result["claims"]:
        print("## 주장 (인용할 문헌 ← 그렇게 인용한 논문)")
        for c in result["claims"]:
            _print_claim(c)
        print()
    if result["papers"]:
        print("## 문헌")
        for p in result["papers"]:
            state = "읽은 논문" if p["status"] == "read" else "인용 문헌"
            print(f"- {p['cite']} {p['title']} (@{p['id']}) — {state} · 인용한 논문 {p['cited_by']} · 주장 {p['cited_claims']} · 방향 {p['directions']}  [{p['file']}]")
    return 0


def _print_claim(c: dict) -> None:
    same = f"  ← 논문 {len(c['sources'])}편이 같은 주장" if len(c["sources"]) > 1 else ""
    print(f"- [{c['type']}] {c['statement']}{same}" + (f"  ({c['group']})" if c["group"] else ""))
    print("    인용 문헌: " + "; ".join(f"{x['cite']} (@{x['citekey']})" + (f" ×{x['cited_in']}" if x["cited_in"] > 1 else "") for x in c["cites"]))
    for s in c["sources"]:
        quote = f" “{s['quote']}”" if s["quote"] else ""
        print(f"    출처: {s['cite']} (@{s['citekey']}){quote}" + (f" ({s['location']})" if s["location"] else ""))
    print(f"    키워드: {', '.join(c['keywords'])}")


def cmd_show(args) -> int:
    from . import render

    vault = _vault()
    name = " ".join(args.name)
    paper = vault.paper(name.lstrip("@")) if all(ch.isalnum() or ch in "-_@" for ch in name) else None
    if paper:
        path = vault.papers_md / f"{paper['id']}.md"
    else:
        node = vault.ontology().find(name)
        if not node:
            sys.exit(f"'{name}' 에 해당하는 키워드나 논문이 없습니다. 'paperwiki search' 로 찾아 보세요.")
        path = vault.keywords_md / f"{node['file']}.md"
    if not path.exists():
        render.sync(vault)
    print(path.read_text(encoding="utf-8"))
    return 0


def cmd_tree(_args) -> int:
    from . import render

    vault = _vault()
    onto, papers = vault.ontology(), vault.papers()
    counts = render.subtree_counts(onto, render.build_usage(papers, onto))
    for depth, node in onto.walk():
        c = counts[node["id"]]
        alias = f" ({', '.join(node['aliases'])})" if node.get("aliases") else ""
        tail = f"  — 주장 {c['claims']}, 인용 문헌 {c['papers']}" if c["claims"] else ""
        print(f"{'  ' * depth}- {node['name']}{alias}{tail}")
    return 0


def cmd_papers(args) -> int:
    from . import wiki

    rows = wiki.paper_rows(_vault())
    if args.read:
        rows = [r for r in rows if r["status"] == "read"]
    elif args.cited:
        rows = [r for r in rows if r["status"] == "cited"]
    order = {
        "recent": lambda r: (r["status"] != "read", [-ord(ch) for ch in r["added"]], r["cite"].casefold()),
        "cited": lambda r: (-r["cited_by"], -r["cited_claims"], r["cite"].casefold()),
        "directions": lambda r: (-r["directions"], -r["cited_claims"], r["cite"].casefold()),
    }
    rows.sort(key=order[args.sort])
    if args.json:
        _dump(rows)
        return 0
    for row in rows:
        if row["status"] == "read":
            tail = f"읽은 논문 · 주장 {row['own_claims']}" + (f" · 다른 논문 {row['cited_by']}편이 인용" if row["cited_by"] else "")
        else:
            tail = f"인용 문헌 · 논문 {row['cited_by']}편이 주장 {row['cited_claims']}개에 인용 · 방향 {row['directions']}"
        print(f"- @{row['citekey']}  {row['cite']} {row['title']} — {tail}")
    if not rows:
        print("아직 등록된 논문이 없습니다.")
    return 0


def cmd_insights(args) -> int:
    from . import wiki

    result = wiki.insights(_vault(), limit=args.limit)
    if args.json:
        _dump(result)
        return 0
    print("## 여러 논문이 인용한 문헌")
    for r in result["multi_source"]:
        print(f"- {r['cite']} {r['title']} (@{r['citekey']}) — 논문 {r['cited_by']}편 · 주장 {r['cited_claims']} · 방향 {r['directions']}")
    if not result["multi_source"]:
        print("- 아직 없음 (읽은 논문이 두 편 이상 쌓이면 나타납니다)")
    print("\n## 여러 방향으로 인용된 문헌 (한 문헌이 서로 다른 키워드의 주장에 인용됨)")
    for r in result["multi_direction"]:
        print(f"- {r['cite']} {r['title']} (@{r['citekey']}) — 방향 {r['directions']}: {', '.join(r['keywords'])}")
    if not result["multi_direction"]:
        print("- 아직 없음")
    print("\n## 여러 논문이 같은 주장에 인용한 문헌")
    for c in result["shared_claims"]:
        _print_claim(c)
    if not result["shared_claims"]:
        print("- 아직 없음 (서로 다른 논문의 주장이 '같은 주장'으로 묶이면 나타납니다)")
    return 0


# ── 관리 명령 ────────────────────────────────────────────────────────────


def cmd_same(args) -> int:
    from . import wiki

    vault = _vault()
    if args.undo:
        if len(args.id) != 2 or not args.id[1].startswith("@"):
            sys.exit("떼어 낼 때는: paperwiki same --undo <주장 묶음 id> @<논문 citekey>")
        wiki.split_claim(vault, args.id[0], args.id[1].lstrip("@"))
        print(f"@{args.id[1].lstrip('@')} 의 주장을 묶음 {args.id[0]} 에서 떼어 냈습니다.")
        return 0
    result = wiki.same_claims(vault, args.id)
    print(f"같은 주장으로 묶었습니다: {result['group']} (옮긴 주장 {result['moved']}개)")
    return 0


def cmd_duplicates(args) -> int:
    from . import wiki

    vault = _vault()
    if args.apart:
        a, b = (x.lstrip("@") for x in args.apart)
        wiki.keep_apart(vault, a, b)
        print(f"@{a} 와 @{b} 는 다른 문헌으로 적어 두었습니다. 다시 묻지 않습니다.")
        return 0
    if args.find_dois:
        search = _search()
        found = wiki.find_dois(vault, search) if search else []
        for item in found:
            print(f"- @{item['paper']}  DOI 를 찾았습니다: {item['doi']}" if item.get("paper") else f"({item['failed']}편은 아직 찾아보지 못했습니다 — 한 편에 1~2초가 걸립니다. 다시 실행하면 이어서 찾습니다)")
        if not found:
            print("새로 찾은 DOI 가 없습니다.")
    if args.merge:
        for m in wiki.merge_certain(vault):
            print(f"- 합쳤습니다: @{m['removed']} → @{m['kept']} ({m['why']})")
    pairs = wiki.duplicates(vault)
    if args.json:
        _dump(pairs)
        return 0
    certain = [d for d in pairs if d["certain"]]
    unsure = [d for d in pairs if not d["certain"]]

    def show(d: dict) -> None:
        for side in (d["a"], d["b"]):
            kind = "읽은 논문" if side["status"] == "read" else f"논문 {side['cited_by']}편이 인용"
            print(f"  @{side['citekey']}  {side['cite']} {side['title']}" + (f" doi:{side['doi']}" if side["doi"] else "") + f"  [{kind}]")
        print(f"  → {d['why']}\n")

    if certain:
        print(f"## 같은 문헌으로 보이는 쌍 {len(certain)}개 (합치려면 paperwiki duplicates --merge)\n")
        for d in certain:
            show(d)
    if unsure:
        print(f"## 같은 문헌일 수 있는 쌍 {len(unsure)}개 (확인이 필요합니다)\n")
        for d in unsure:
            show(d)
        print("같은 문헌이면: paperwiki merge-papers @<없앨 쪽> @<남길 쪽> · 다른 문헌이면: paperwiki duplicates --apart @a @b")
    if not pairs:
        print("같은 문헌이 둘로 갈린 것으로 보이는 쌍이 없습니다.")
    return 0


def cmd_merge_papers(args) -> int:
    from . import wiki

    result = wiki.merge_papers(_vault(), args.duplicate.lstrip("@"), args.keep.lstrip("@"))
    print(f"@{result['removed']} 을(를) @{result['kept']} 로 합쳤습니다. @{result['removed']} 을(를) 인용하던 주장은 이제 @{result['kept']} 을(를) 인용합니다.")
    return 0


def cmd_tidy(args) -> int:
    from . import wiki

    vault = _vault()
    z = None if args.no_zotero else _zotero()
    try:
        changes = wiki.tidy(vault, zotero=z, dry_run=args.dry_run, include_cited=args.cited, **wiki.zotero_options())
    finally:
        if z:
            z.close()
    text = {
        "renamed": "이름 변경: {from} → {to}",
        "would_rename": "이름을 바꿀 예정: {from} → {to}",
        "rename_failed": "이름을 바꾸지 못함: {from} ({note})",
        "relinked": "다시 연결: {from} → {to}",
        "missing": "PDF 를 찾지 못함: {from}",
    }
    for change in changes:
        if change["action"].startswith("zotero_"):
            print("\n".join(wiki.zotero_report([change])))
        else:
            print(f"- @{change['paper']}  " + text[change["action"]].format(**{"from": "", "to": "", "note": "", **change}))
    if not changes:
        print("정리할 것이 없습니다. 논문 폴더가 위키 기록과 맞습니다.")
    return 0


def cmd_fix(args) -> int:
    from . import wiki

    changes = {k: getattr(args, k) for k in ("title", "authors", "year", "venue", "doi")}
    if all(v is None for v in changes.values()):
        sys.exit("고칠 항목을 하나 이상 주세요: --title, --authors, --year, --venue, --doi")
    vault = _vault()
    result = wiki.update_paper_meta(vault, args.citekey.lstrip("@"), changes)
    paper = result["paper"]
    z = _zotero() if paper.get("zotero_pdf") == "linked" else None
    if z:  # PDF 이름이 바뀌었으면 Zotero 의 PDF 링크도 따라 고친다
        with z:
            for line in wiki.zotero_report(wiki.zotero_sync(vault, z, [paper["id"]]), one_paper=True):
                print(f"  Zotero: {line}")
    ref = wiki.reference(paper)
    print(f"고쳤습니다: @{paper['id']}\n  {'; '.join(ref['authors'])} ({ref['year']}). {ref['title']}. {ref['venue']}" + (f"  doi:{ref['doi']}" if ref["doi"] else ""))
    if ref["pdf"]:
        print(f"  PDF: {ref['pdf']}")
    if result["pdf_note"]:
        print(f"  주의: {result['pdf_note']}")
    return 0


def cmd_naming(args) -> int:
    from . import library

    vault = _vault()
    if args.pattern:
        pattern = library.set_name_pattern(vault, args.pattern)
        print(f"PDF 이름 규칙을 바꿨습니다: {pattern}\n이미 등록된 PDF 에 적용하려면: paperwiki tidy")
    else:
        pattern = library.name_pattern(vault)
        print(f"PDF 이름 규칙: {pattern}")
        print("쓸 수 있는 항목: {title} 제목 · {author} 제1저자(둘 이상이면 et al.) · {year} 연도 · {citekey} 인용 키")
    sample = {"id": "kim2023computerized", "title": "Computerized cognitive training in mild cognitive impairment: a randomized trial",
              "authors": [{"family": "Kim", "given": "Jisoo"}, {"family": "Lee", "given": "Sang"}], "year": "2023"}
    print(f"예: {library.pdf_filename(sample, pattern)}")
    return 0


def cmd_rebuild(_args) -> int:
    from . import render

    result = render.sync(_vault())
    print(f"마크다운을 갱신했습니다: 갱신 {result['written']}, 정리 {result['removed']}")
    return 0


def cmd_setup(args) -> int:
    from . import render
    from .store import Vault

    path = args.vault
    if not path:
        from . import gdrive

        options = config.storage_options()
        if not any(o["kind"] == "gdrive" for o in options):
            if gdrive.is_installed():
                print("구글 드라이브 데스크톱이 꺼져 있거나 로그인되어 있지 않습니다.\n실행해서 쓰려는 계정으로 로그인한 뒤 다시 실행하면 그 계정의 드라이브를 고를 수 있습니다.\n")
            else:
                print(f"이 컴퓨터에 구글 드라이브 데스크톱이 없습니다.\n위키를 구글 드라이브에 두려면 먼저 설치해 주세요: {gdrive.DOWNLOAD_URL}\n")
        print("위키를 어디에 저장할까요?\n")
        for i, o in enumerate(options, 1):
            if o["kind"] == "gdrive":
                kind = f"구글 드라이브 · {o['email'] or o['mount'] or '로그인된 계정'} (다른 컴퓨터와 동기화)"
            else:
                kind = "이 컴퓨터에만 저장"
            s = o.get("summary") or {}
            found = f"  ← 기존 위키 (문헌 {s.get('papers', '?')}편, 마지막 수정 {s.get('modified') or '?'}) 불러오기" if o["exists"] else ""
            print(f"  {i}. {kind}\n     {o['path']}{found}")
        print(f"  {len(options) + 1}. 폴더 직접 지정\n")
        choice = input(f"번호를 입력하세요 [1-{len(options) + 1}]: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            path = options[int(choice) - 1]["path"]
        else:
            path = input("폴더의 전체 경로: ").strip().strip('"')
    target = Path(path).expanduser()
    if not target.is_absolute():
        sys.exit("전체 경로(절대 경로)를 입력해 주세요.")
    existing = Vault.is_vault(target)
    vault = Vault(target)
    if existing:  # 불러오기: 아무것도 쓰지 않고, 다 읽을 수 있는지만 확인한다
        vault.check_readable()
    else:
        vault.init(language=args.lang)
        render.sync(vault)
    config.update(vault_path=str(target))
    print(("기존 위키를 불러왔습니다: " if existing else "새 위키를 만들었습니다: ") + str(target))
    print(f"논문 폴더: {vault.pdf_dir}\nClaude Code 스킬은 컴퓨터마다 한 번 설치합니다: paperwiki claude-install")
    return 0


def cmd_claude_install(_args) -> int:
    from . import integration

    path = integration.install(str(_vault().root))
    print(f"Claude Code 스킬을 설치했습니다: {path}\n논문 읽기 에이전트: {integration.agent_path()}")
    print("Claude Code 에서 \"논문 폴더에 넣은 새 논문 위키에 정리해줘\" 처럼 요청하거나 /paper-wiki 로 부르면 됩니다.")
    return 0


def cmd_reader_model(args) -> int:
    from . import integration

    if args.model:
        try:
            result = integration.set_reader_model(args.model)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"논문 읽기 에이전트의 모델을 바꿨습니다: {result['model']}")
        if result["agent_updated"]:
            print(f"에이전트 파일을 고쳤습니다: {integration.agent_path()}\n새 Claude Code 세션부터 적용됩니다.")
        else:
            print("에이전트가 아직 설치되어 있지 않습니다. 설치하면 이 모델로 설치됩니다: paperwiki claude-install")
        return 0
    current = integration.reader_model()
    print(f"논문 읽기 에이전트의 모델: {current}")
    print("바꾸려면: paperwiki reader-model <모델>")
    for name, label in integration.READER_MODELS.items():
        print(f"  {name:<8} {label}")
    print("  claude-… 로 시작하는 모델 ID 를 직접 적어도 됩니다.")
    return 0


def cmd_doctor(_args) -> int:
    from . import integration, library
    from .store import Vault, VaultUnavailable

    cfg = config.load()
    path = cfg.get("vault_path") or ""
    print(f"Paper Wiki {__version__}")
    print(f"설정 파일      : {config.config_path()}")
    ready = bool(path) and Vault.is_vault(path)
    if not path:
        print("위키 폴더      : (미설정)")
    else:
        info = config.storage_info(path)
        where = f"구글 드라이브 ({info['email'] or '계정 확인 불가'})" if info["kind"] == "gdrive" else "이 컴퓨터"
        print(f"위키 폴더      : {path}  [{'정상' if ready else '찾을 수 없음'} · {where}]")
    linked_note = ""
    if ready:
        vault = Vault(path)
        try:
            papers = vault.papers()
            read = sum(1 for p in papers.values() if p.get("kind", "read") != "cited")
            linked = sum(1 for p in papers.values() if p.get("kind", "read") != "cited" and p.get("zotero_key"))
            linked_note = f" · 읽은 논문 {read}편 중 {linked}편이 Zotero 항목과 연결됨"
            print(f"논문 폴더      : {vault.pdf_dir}  [새 PDF {len(library.list_new(vault))} · 검토 대기 {len(vault.pending_all())} · 읽은 논문 {read} · 인용 문헌 {len(papers) - read}]")
        except VaultUnavailable as exc:
            print(f"논문 폴더      : {vault.pdf_dir}  [{exc}]")
        print(f"PDF 이름 규칙  : {library.name_pattern(vault)}")
    print(f"Claude Code    : {'설치되어 있음' if integration.claude_code_installed() else '이 컴퓨터에서 찾지 못함 (논문 추가·선행연구 작성에 필요)'}")
    if ready:
        st = integration.status(path)
        print(f"Claude 스킬    : {'설치됨' if st['installed'] and st['current'] else '다시 설치 필요 (paperwiki claude-install)' if st['installed'] else '미설치 (paperwiki claude-install)'}  ({st['path']})")
    print(f"읽기 에이전트  : 모델 {integration.reader_model()}  (바꾸려면 paperwiki reader-model <sonnet|opus|haiku|inherit>)")
    print(f"Zotero 연결    : {cfg.get('zotero_mode')}", end="")
    try:
        from .zotero import Zotero

        with Zotero(cfg) as z:
            info = z.ping()
            writable = z.can_write()
        sync = "계정 동기화 사용 중" if info.get("account_linked") else "Zotero 계정에 로그인되어 있지 않음 → 다른 컴퓨터와 동기화되지 않음"
        print(f"  [연결됨 · 항목 {info.get('total')} · {sync}]")
    except Exception as exc:
        writable = bool(config.get_secret("zotero_local_key")) or cfg.get("zotero_mode") == "web"
        print(f"  [연결 안 됨: {exc}]  (꺼져 있으면 논문은 위키에만 등록되고, 나중에 'paperwiki zotero sync' 로 Zotero 에 넣습니다)")
    if cfg.get("zotero_add"):
        where = f"컬렉션 '{cfg.get('zotero_collection')}'" if cfg.get("zotero_collection") else "내 라이브러리"
        print(f"Zotero 에 넣기 : 켜짐 — 등록한 읽은 논문을 {where} 에 넣음 · " + ("항목 추가 허용받음" if writable else "아직 허용받지 않음 → paperwiki zotero connect") + linked_note)
    else:
        print("Zotero 에 넣기 : 꺼짐 (paperwiki zotero config --add on)" + linked_note)
    return 0


def main(argv: list[str] | None = None) -> int:
    _utf8_stdout()
    parser = argparse.ArgumentParser(prog="paperwiki", description="논문 PDF → (Claude Code 가 읽고 제안) → 사람 검토 → 개인 문헌 위키")
    parser.add_argument("--version", action="version", version=f"paperwiki {__version__}")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("serve", help="웹 화면 실행 (명령을 생략하면 이것이 실행됩니다)")
    p.add_argument("--port", type=int)
    p.add_argument("--no-browser", action="store_true")
    p.set_defaults(fn=cmd_serve)

    p = sub.add_parser("inbox", help="논문 폴더의 새 PDF 와 검토 대기 목록")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_inbox)

    p = sub.add_parser("prepare", help="논문을 읽을 준비 (PDF 경로·파일 이름·URL·@citekey)")
    p.add_argument("source", nargs="+")
    p.add_argument("--again", action="store_true", help="이미 등록된 논문을 다시 분석")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_prepare)

    p = sub.add_parser("propose", help="Claude 가 쓴 제안을 검토안으로 저장하고 검토 요약을 출력")
    p.add_argument("id")
    p.add_argument("--file", help="제안 JSON 파일 (생략하면 prepare 가 알려 준 proposal 경로)")
    p.add_argument("--no-zotero", action="store_true", help="Zotero 에서 같은 논문을 찾지 않음")
    p.add_argument("--no-lookup", action="store_true", help="DOI 등록 기록(doi.org·Crossref)으로 서지 정보를 확인하거나 참고문헌의 DOI 를 찾지 않음")
    p.add_argument("--compact", action="store_true", help="주장마다 한 줄로 (인용문과 참고문헌 제목 목록은 생략)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_propose)

    p = sub.add_parser("review", help="검토안의 검토 요약을 다시 출력")
    p.add_argument("id")
    p.add_argument("--compact", action="store_true", help="주장마다 한 줄로 (인용문과 참고문헌 제목 목록은 생략)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_review)

    p = sub.add_parser("approve", help="검토안을 위키에 등록 (사용자가 확인한 뒤에만). Zotero 에 없는 논문이면 Zotero 에도 넣는다")
    p.add_argument("id", nargs="+")
    p.add_argument("--no-zotero", action="store_true", help="이번에는 Zotero 와 맞추지 않음")
    p.set_defaults(fn=cmd_approve)

    p = sub.add_parser("discard", help="검토안 폐기")
    p.add_argument("id", nargs="+")
    p.set_defaults(fn=cmd_discard)

    p = sub.add_parser("zotero", help="Zotero 연동: 찾기 · 가져오기 · 위키의 읽은 논문을 Zotero 에 넣기")
    zsub = p.add_subparsers(dest="zcmd", required=True)
    z = zsub.add_parser("connect", help="Zotero 앱에 항목 추가를 허용받는다 (Zotero 의 확인 창에서 '항상 허용')")
    z.add_argument("--again", action="store_true", help="이미 허용받았어도 다시 요청")
    z = zsub.add_parser("sync", help="위키의 읽은 논문을 Zotero 와 맞춘다 (있으면 연결, 없으면 새 항목으로 넣기)")
    z.add_argument("--dry-run", action="store_true", help="바꾸지 않고 무엇이 바뀔지만 보기")
    z.add_argument("--cited", action="store_true", help="인용 문헌도 Zotero 에 이미 있으면 연결 (넣지는 않는다)")
    z = zsub.add_parser("config", help="Zotero 에 넣기 설정 보기·바꾸기")
    z.add_argument("--add", choices=["on", "off"], help="등록한 읽은 논문을 Zotero 에 넣을지")
    z.add_argument("--collection", help="위키에 있는 논문을 모아 둘 Zotero 컬렉션 이름 (빈 문자열이면 쓰지 않음)")
    z.add_argument("--pdf", choices=["link", "none"], help="Zotero 항목에 논문 폴더의 PDF 를 링크할지")
    z = zsub.add_parser("list", help="Zotero 라이브러리 검색 (최근 추가한 순)")
    z.add_argument("query", nargs="*")
    z.add_argument("--limit", type=int, default=20)
    z.add_argument("--json", action="store_true")
    z = zsub.add_parser("pull", help="Zotero 항목의 PDF 를 논문 폴더로 가져와 읽을 준비")
    z.add_argument("key", nargs="+")
    p.set_defaults(fn=cmd_zotero)

    p = sub.add_parser("search", help="위키 검색")
    p.add_argument("query", nargs="+")
    p.add_argument("--json", action="store_true", help="JSON 으로 출력")
    p.add_argument("--limit", type=int, default=15)
    p.set_defaults(fn=cmd_search)

    p = sub.add_parser("show", help="키워드 또는 논문(@citekey) 문서 출력")
    p.add_argument("name", nargs="+")
    p.set_defaults(fn=cmd_show)

    sub.add_parser("tree", help="키워드 온톨로지 출력").set_defaults(fn=cmd_tree)

    p = sub.add_parser("papers", help="위키의 문헌 목록 (읽은 논문 + 인용 문헌)")
    p.add_argument("--read", action="store_true", help="읽은 논문만")
    p.add_argument("--cited", action="store_true", help="인용 문헌만")
    p.add_argument("--sort", choices=["recent", "cited", "directions"], default="recent", help="recent 최근 읽은 순 · cited 많이 인용된 순 · directions 여러 방향으로 인용된 순")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_papers)

    p = sub.add_parser("insights", help="여러 논문이 인용한 문헌 · 여러 방향으로 인용된 문헌 · 같은 주장에 함께 인용된 문헌")
    p.add_argument("--limit", type=int, default=30)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_insights)

    p = sub.add_parser("same", help="서로 다른 논문의 주장을 '같은 주장'으로 묶기 (주장 묶음 id 는 search --json 의 group)")
    p.add_argument("id", nargs="+", help="묶을 주장 묶음 id 들 (첫 번째로 합쳐진다). --undo 일 때는 <묶음 id> @<논문>")
    p.add_argument("--undo", action="store_true", help="잘못 묶인 논문의 주장을 묶음에서 떼어 내기")
    p.set_defaults(fn=cmd_same)

    p = sub.add_parser("duplicates", help="같은 문헌이 표기 차이로 두 문서로 갈렸을 수 있는 쌍 찾기")
    p.add_argument("--merge", action="store_true", help="같은 문헌이라는 근거가 분명한 쌍(같은 DOI 등)을 합친다")
    p.add_argument("--find-dois", action="store_true", help="DOI 없이 등록된 문헌의 DOI 를 Crossref 에서 다시 찾는다")
    p.add_argument("--apart", nargs=2, metavar="@citekey", help="비슷해 보이지만 다른 문헌인 쌍을 적어 둔다 (다시 묻지 않음)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_duplicates)

    p = sub.add_parser("merge-papers", help="같은 문헌이 두 문서로 나뉘었을 때 하나로 합치기")
    p.add_argument("duplicate", help="없앨 쪽 @citekey")
    p.add_argument("keep", help="남길 쪽 @citekey")
    p.set_defaults(fn=cmd_merge_papers)

    p = sub.add_parser("tidy", help="논문 폴더 정리 (PDF 이름 맞추기, 옮겨진 PDF 다시 연결, Zotero 연결 보충)")
    p.add_argument("--dry-run", action="store_true", help="바꾸지 않고 무엇이 바뀔지만 출력")
    p.add_argument("--no-zotero", action="store_true")
    p.add_argument("--cited", action="store_true", help="인용 문헌도 Zotero 에서 찾아 연결 (문헌이 많으면 오래 걸린다)")
    p.set_defaults(fn=cmd_tidy)

    p = sub.add_parser("fix", help="등록된 논문의 서지 정보 고치기")
    p.add_argument("citekey")
    p.add_argument("--title")
    p.add_argument("--authors", help='"Kim, Jisoo; Lee, Sang" 형식')
    p.add_argument("--year")
    p.add_argument("--venue")
    p.add_argument("--doi")
    p.set_defaults(fn=cmd_fix)

    p = sub.add_parser("naming", help="PDF 이름 규칙 보기·바꾸기")
    p.add_argument("pattern", nargs="?")
    p.set_defaults(fn=cmd_naming)

    sub.add_parser("rebuild", help="마크다운 다시 생성").set_defaults(fn=cmd_rebuild)

    p = sub.add_parser("setup", help="위키 저장 위치 설정")
    p.add_argument("--vault", help="위키 폴더 경로 (생략하면 선택지를 보여줍니다)")
    p.add_argument("--lang", default="ko", choices=["ko", "en"])
    p.set_defaults(fn=cmd_setup)

    sub.add_parser("claude-install", help="Claude Code 스킬과 논문 읽기 에이전트 설치").set_defaults(fn=cmd_claude_install)

    p = sub.add_parser("reader-model", help="논문 읽기 에이전트가 쓰는 Claude 모델 보기·바꾸기 (기본 sonnet)")
    p.add_argument("model", nargs="?", help="sonnet | opus | haiku | inherit(대화의 모델) | claude- 로 시작하는 모델 ID")
    p.set_defaults(fn=cmd_reader_model)
    sub.add_parser("doctor", help="설정과 연결 상태 점검").set_defaults(fn=cmd_doctor)

    args = parser.parse_args(argv)
    if not args.cmd:
        args = parser.parse_args(["serve", *(argv or [])])
    return _run(args)


def _run(args) -> int:
    """명령을 실행한다. 사용자에게 설명할 수 있는 오류는 한 줄로 알리고 끝낸다."""
    from .extract import ProposalError
    from .library import LibraryError
    from .store import VaultUnavailable
    from .wiki import WikiError
    from .zotero import ZoteroError

    try:
        return args.fn(args) or 0
    except ProposalError as exc:
        print("제안 파일을 검토안으로 만들 수 없습니다. 아래를 고친 뒤 다시 실행해 주세요.", file=sys.stderr)
        for problem in exc.problems:
            print(f"- {problem}", file=sys.stderr)
        return 1
    except (WikiError, LibraryError, ZoteroError, VaultUnavailable) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
