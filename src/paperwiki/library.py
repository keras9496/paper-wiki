"""논문 저장소: 위키 폴더 안의 pdf/ 폴더.

사용자는 읽을 논문 PDF 를 이 폴더에 넣는다 (파일 이름은 무엇이든 괜찮다). 논문이 위키에 등록되면
그 PDF 는 정해진 규칙의 이름으로 바뀐다. 위키를 구글 드라이브에 두었다면 PDF 도 함께 동기화되므로
다른 컴퓨터에서도 같은 이름으로 정리된 원문을 볼 수 있다.

여기서는 파일만 다룬다: 새 PDF 찾기, 밖에서 받은 PDF 들여오기, 읽기 준비(작업 폴더), 이름 바꾸기.
무엇이 위키에 들어가는지는 wiki.py 가 정한다.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import __version__, config, extract, render
from .store import Vault, now_iso, safe_id, write_json_atomic

DEFAULT_PATTERN = "{title}({author})"  # 예: Computerized cognitive training in MCI(Kim et al.).pdf
PATTERN_TOKENS = ("title", "author", "year", "citekey")
MAX_STEM = 150  # 경로 길이 제한(Windows 260자)에 걸리지 않도록 파일 이름을 줄인다
MAX_DOWNLOAD = 150 * 1024 * 1024
WORK_KEEP_DAYS = 30


class LibraryError(Exception):
    """사용자에게 그대로 보여줄 수 있는 오류."""


# ── 이름 규칙 ─────────────────────────────────────────────────────────────

_HANGUL = re.compile(r"[가-힣]")
_FORBIDDEN = re.compile(r'[\\/*?"<>|#^\[\]\x00-\x1f]+')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def name_pattern(vault: Vault) -> str:
    return vault.settings().get("pdf_name") or DEFAULT_PATTERN


def check_pattern(pattern: str) -> str:
    pattern = re.sub(r"\s+", " ", pattern or "").strip()
    if pattern.lower().endswith(".pdf"):
        pattern = pattern[:-4].rstrip()
    used = re.findall(r"\{(\w*)\}", pattern)
    unknown = [t for t in used if t not in PATTERN_TOKENS]
    if unknown or "{" in re.sub(r"\{\w*\}", "", pattern) or "}" in re.sub(r"\{\w*\}", "", pattern):
        raise LibraryError("이름 규칙에는 {title}, {author}, {year}, {citekey} 만 쓸 수 있습니다.")
    if "title" not in used and "citekey" not in used:
        raise LibraryError("이름 규칙에는 {title} 이나 {citekey} 가 들어가야 논문마다 이름이 달라집니다.")
    return pattern


def set_name_pattern(vault: Vault, pattern: str) -> str:
    pattern = check_pattern(pattern)
    vault.save_settings(pdf_name=pattern)
    return pattern


def _clean_part(text: str) -> str:
    text = unicodedata.normalize("NFC", str(text or ""))
    text = re.sub(r"\s*:\s*", " - ", text)  # 부제의 쌍점은 파일 이름에 쓸 수 없다
    text = _FORBIDDEN.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def author_label(paper: dict) -> str:
    """파일 이름에 쓰는 저자 표기: 제1저자, 둘 이상이면 'et al.' (한글 이름은 '외')."""
    authors = paper.get("authors") or []
    if not authors:
        return ""
    first = authors[0]
    family, given = first.get("family", ""), first.get("given", "")
    name = first.get("name") or (f"{family}{given}" if _HANGUL.search(family) else (family or given))
    name = _clean_part(name)
    if len(authors) > 1 and name:
        name += " 외" if _HANGUL.search(name) else " et al."
    return name


def pdf_filename(paper: dict, pattern: str = DEFAULT_PATTERN) -> str:
    """등록된 논문의 PDF 이름. 같은 논문이면 어느 컴퓨터에서나 같은 이름이 나온다."""
    values = {
        "title": _clean_part(paper.get("title")),
        "author": author_label(paper),
        "year": re.sub(r"\D", "", str(paper.get("year") or ""))[:4],
        "citekey": _clean_part(paper.get("id")),
    }
    if not values["title"]:
        values["title"] = values["citekey"] or "paper"

    def fill(title: str) -> str:
        stem = pattern
        for token in PATTERN_TOKENS:
            stem = stem.replace("{" + token + "}", title if token == "title" else values[token])
        stem = re.sub(r"\(\s*\)|\[\s*\]", "", stem)  # 값이 없어 비어 버린 괄호
        stem = re.sub(r"\s+", " ", stem)
        stem = re.sub(r"^[\s_\-,.]+|[\s_\-,.]+$", "", stem)
        return stem

    stem = fill(values["title"])
    if len(stem) > MAX_STEM:  # 제목만 줄인다 (저자·연도는 남긴다)
        keep = max(20, len(values["title"]) - (len(stem) - MAX_STEM) - 1)
        stem = fill(values["title"][:keep].rstrip(" -,.") + "…")
    if not stem or stem.upper() in _RESERVED:
        stem = f"paper {stem}".strip()
    return stem + ".pdf"


# ── 저장소 훑기 ───────────────────────────────────────────────────────────


def _key(rel_path: str) -> str:
    return unicodedata.normalize("NFC", rel_path.replace("\\", "/")).casefold()


def _relative(path: Path, folder: Path) -> str | None:
    for a, b in ((path, folder), (path.resolve(), folder.resolve())):
        try:
            return a.relative_to(b).as_posix()
        except (ValueError, OSError):
            continue
    return None


def rel(vault: Vault, path: Path) -> str:
    """위키 폴더 기준 경로 (컴퓨터마다 드라이브 문자가 달라도 같은 값)."""
    relative = _relative(path, vault.root)
    if relative is None:
        raise LibraryError(f"위키 폴더 밖의 파일입니다: {path}")
    return relative


def is_pdf(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            return b"%PDF-" in fh.read(1024)
    except OSError:
        return False


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def claimed_paths(vault: Vault) -> dict[str, dict]:
    """저장소의 PDF 중 이미 주인이 있는 것: 경로 → {"kind": "paper" | "pending", "id": ...}"""
    out: dict[str, dict] = {}
    for draft in vault.pending_all():
        path = ((draft.get("paper") or {}).get("pdf") or {}).get("path")
        if path:
            out[_key(path)] = {"kind": "pending", "id": draft["id"]}
    for paper in vault.papers().values():
        path = (paper.get("pdf") or {}).get("path")
        if path:
            out[_key(path)] = {"kind": "paper", "id": paper["id"]}
    return out


def _pdf_files(vault: Vault) -> list[Path]:
    found = []
    try:
        walker = os.walk(vault.pdf_dir)
        for folder, dirs, files in walker:
            dirs[:] = sorted(d for d in dirs if not d.startswith((".", "~", "$")))
            for name in sorted(files, key=str.casefold):
                if name.lower().endswith(".pdf") and not name.startswith((".", "~$")):
                    found.append(Path(folder) / name)
    except OSError:
        pass
    return found


def list_new(vault: Vault) -> list[dict]:
    """저장소에 있지만 아직 위키에 등록되지도, 검토 대기에 올라가지도 않은 PDF."""
    claimed = claimed_paths(vault)
    out = []
    for path in _pdf_files(vault):
        relative = path.relative_to(vault.root).as_posix()
        if _key(relative) in claimed:
            continue
        try:
            st = path.stat()
        except OSError:
            continue
        out.append({"path": relative, "name": path.name, "size": st.st_size, "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))})
    return out


# ── 들여오기 ──────────────────────────────────────────────────────────────


def _free_name(folder: Path, name: str) -> Path:
    name = _clean_part(Path(name).stem)[:MAX_STEM] or "paper"
    candidate, n = folder / f"{name}.pdf", 2
    while candidate.exists():
        candidate = folder / f"{name} ({n}).pdf"
        n += 1
    return candidate


def _same_content(vault: Vault, size: int, sha: str) -> Path | None:
    """저장소에 이미 같은 내용의 PDF 가 있으면 그 파일."""
    for path in _pdf_files(vault):
        try:
            if path.stat().st_size == size and sha256_file(path) == sha:
                return path
        except OSError:
            continue
    return None


def add_bytes(vault: Vault, data: bytes, name: str) -> Path:
    if b"%PDF-" not in data[:1024]:
        raise LibraryError("PDF 파일이 아닙니다.")
    vault.pdf_dir.mkdir(parents=True, exist_ok=True)
    existing = _same_content(vault, len(data), hashlib.sha256(data).hexdigest())
    if existing:
        return existing
    target = _free_name(vault.pdf_dir, name)
    tmp = target.with_name(target.name + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, target)
    return target


def add_file(vault: Vault, src: Path) -> Path:
    """위키 밖에 있는 PDF 를 저장소로 복사한다 (원본은 그대로 둔다). 이미 저장소 안이면 그대로 돌려준다."""
    src = src.expanduser()
    if not src.is_file():
        raise LibraryError(f"파일을 찾을 수 없습니다: {src}")
    if not is_pdf(src):
        raise LibraryError(f"PDF 파일이 아닙니다: {src.name}")
    if _relative(src, vault.pdf_dir) is not None:
        return src
    vault.pdf_dir.mkdir(parents=True, exist_ok=True)
    existing = _same_content(vault, src.stat().st_size, sha256_file(src))
    if existing:
        return existing
    target = _free_name(vault.pdf_dir, src.name)
    shutil.copyfile(src, target)
    return target


def add_url(vault: Vault, url: str, transport=None) -> Path:
    """주소에서 PDF 를 내려받아 저장소에 둔다."""
    import httpx

    try:
        with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(30, read=120), transport=transport, headers={"User-Agent": f"paperwiki/{__version__}"}) as client:
            with client.stream("GET", url) as r:
                if r.status_code != 200:
                    raise LibraryError(f"내려받지 못했습니다 (HTTP {r.status_code}): {url}")
                chunks, size = [], 0
                for chunk in r.iter_bytes():
                    size += len(chunk)
                    if size > MAX_DOWNLOAD:
                        raise LibraryError("파일이 너무 큽니다 (150MB 초과).")
                    chunks.append(chunk)
                disposition = r.headers.get("content-disposition", "")
                final_url = str(r.url)
    except httpx.HTTPError as exc:
        raise LibraryError(f"내려받지 못했습니다: {exc}") from exc
    data = b"".join(chunks)
    if b"%PDF-" not in data[:1024]:
        raise LibraryError("받은 파일이 PDF 가 아닙니다 (로그인이나 구독이 필요한 페이지일 수 있습니다). 브라우저로 PDF 를 받아 논문 폴더에 넣어 주세요.")
    m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", disposition, re.IGNORECASE)
    name = unquote(m.group(1)) if m else unquote(Path(urlparse(final_url).path).name) or "download"
    return add_bytes(vault, data, name)


def resolve_source(vault: Vault, source: str) -> Path:
    """명령에 넘어온 '논문'을 저장소 안의 PDF 파일로 바꾼다.

    받는 것: 저장소 안의 경로·파일 이름, 위키 밖의 PDF 경로(저장소로 복사), http(s) 주소(내려받기),
    @citekey (이미 등록된 논문의 PDF).
    """
    source = str(source).strip().strip('"')
    if re.match(r"^https?://", source, re.IGNORECASE):
        return add_url(vault, source)
    if source.startswith("@"):
        paper = vault.paper(source[1:]) if re.fullmatch(r"@[\w\-]{1,80}", source) else None
        path = (paper or {}).get("pdf", {}).get("path") if paper and paper.get("pdf") else None
        if not path or not (vault.root / path).is_file():
            raise LibraryError(f"{source} 의 PDF 를 저장소에서 찾을 수 없습니다.")
        return vault.root / path
    given = Path(source).expanduser()
    candidates = [given] if given.is_absolute() else [Path.cwd() / given, vault.root / given, vault.pdf_dir / given]
    for candidate in candidates:
        if candidate.is_file():
            return add_file(vault, candidate)
    raise LibraryError(f"PDF 를 찾을 수 없습니다: {source}")


# ── 읽기 준비 (작업 폴더) ─────────────────────────────────────────────────


def work_root() -> Path:
    # 작업 파일은 이 컴퓨터에만 둔다 (위키 폴더에 두면 드라이브로 동기화된다)
    return config.config_dir() / "work"


def work_dir(draft_id: str) -> Path:
    return work_root() / safe_id(draft_id)


def cleanup_work(draft_id: str | None = None) -> None:
    """끝난 작업 폴더를 지운다. id 가 없으면 오래된 것들을 지운다."""
    if draft_id:
        shutil.rmtree(work_dir(draft_id), ignore_errors=True)
        return
    limit = time.time() - WORK_KEEP_DAYS * 86400
    try:
        for folder in work_root().iterdir():
            if folder.is_dir() and folder.stat().st_mtime < limit:
                shutil.rmtree(folder, ignore_errors=True)
    except OSError:
        pass


def load_job(draft_id: str) -> dict:
    try:
        return json.loads((work_dir(draft_id) / "job.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise LibraryError(f"'{draft_id}' 의 읽기 준비 기록이 이 컴퓨터에 없습니다. 먼저 prepare 를 실행해 주세요.") from None


def proposal_text(draft_id: str) -> str:
    path = work_dir(draft_id) / extract.PROPOSAL_FILE
    try:
        return path.read_text(encoding="utf-8-sig")
    except OSError:
        raise LibraryError(f"제안 파일이 아직 없습니다: {path}") from None


def proposal_more(draft_id: str) -> list[str]:
    """주장이 많아 나눠 쓴 파일들(claims_2.json, claims_3.json …)의 내용을 번호순으로."""

    def number(path: Path) -> int:
        digits = re.sub(r"\D", "", path.stem)
        return int(digits) if digits else 0

    out = []
    for path in sorted(work_dir(draft_id).glob("claims_*.json"), key=number):
        try:
            out.append(path.read_text(encoding="utf-8-sig"))
        except OSError:
            continue
    return out


def prepare(vault: Vault, source: str, again: bool = False, known_meta: dict | None = None) -> dict:
    """논문 한 편을 읽을 준비를 한다: PDF 를 저장소에 두고, 작업 폴더에 읽을 파일과 작업 지시문을 만든다.

    위키에는 아무것도 추가하지 않는다 (밖에서 온 PDF 가 저장소에 복사될 뿐이다).
    """
    onto = vault.ontology()  # 위키를 읽을 수 없는 상태면 여기서 멈춘다
    outline = onto.outline()
    path = resolve_source(vault, source)
    sha = sha256_file(path)
    registered = vault.paper_by_sha(sha)
    if registered and not again:
        raise LibraryError(
            f"이 PDF 는 이미 위키에 등록되어 있습니다: @{registered['id']} ({registered.get('title', '')}). "
            "다시 분석해 기존 내용을 바꾸려면 --again 을 붙여 주세요."
        )
    draft_id = "d" + sha[:12]
    cleanup_work()
    work = work_dir(draft_id)
    work.mkdir(parents=True, exist_ok=True)
    for stale in [work / extract.PROPOSAL_FILE, work / extract.CLAIMS_FILE, *work.glob("claims_*.json")]:
        stale.unlink(missing_ok=True)
    parts, reduced = extract.write_pdf_parts(path, work)
    pages = parts[-1][2] or None
    job = {
        "id": draft_id,
        "pdf": rel(vault, path),
        "sha256": sha,
        "size": path.stat().st_size,
        "pages": pages,
        "original_name": path.name,
        "paper_id": registered["id"] if registered else None,
        "zotero": known_meta,
        "prepared": now_iso(),
    }
    write_json_atomic(work / "job.json", job)
    language = vault.settings().get("language", "ko")
    # 위키에 이미 있는 주장 목록: 읽는 쪽이 '같은 주장'을 찾아 묶을 수 있게 작업 폴더에 둔다 (다시 분석하는 논문 자신의 주장은 뺀다)
    listing, known_claims = render.claims_listing(vault.papers(), onto, exclude=job["paper_id"])
    if known_claims:
        (work / extract.CLAIMS_FILE).write_text(listing, encoding="utf-8", newline="\n")
    brief = extract.build_brief(work, parts, outline, language, known_meta, reduced, wiki_claims=known_claims)
    (work / extract.BRIEF_FILE).write_text(brief, encoding="utf-8", newline="\n")
    return {
        "id": draft_id,
        "pdf": job["pdf"],
        "pages": pages,
        "parts": len(parts),
        "reduced": reduced,
        "read_bytes": sum((work / name).stat().st_size for name, _, _ in parts),
        "brief": (work / extract.BRIEF_FILE).as_posix(),
        "proposal": (work / extract.PROPOSAL_FILE).as_posix(),
        "replaces": job["paper_id"],
        "zotero": bool(known_meta),
        "wiki_claims": known_claims,
    }


def pull_from_zotero(vault: Vault, z, key: str) -> dict:
    """Zotero 에 있는 논문의 PDF 를 저장소로 가져와 읽을 준비를 한다. Zotero 쪽은 바꾸지 않는다."""
    meta = z.item(key)
    attachment = z.pdf_attachment(key)
    if not attachment:
        raise LibraryError(f"Zotero 의 이 항목에는 PDF 첨부가 없습니다: {meta.get('title') or key}")
    data = z.pdf_bytes(attachment)
    att = attachment.get("data") or attachment
    meta["attachment_key"] = att.get("key") or attachment.get("key")
    known = vault.paper_by_zotero(key)
    path = add_bytes(vault, data, att.get("filename") or meta.get("title") or key)
    return prepare(vault, str(path), again=bool(known), known_meta=meta)


# ── 이름 바꾸기 ───────────────────────────────────────────────────────────


def _rename(src: Path, dst: Path) -> None:
    for attempt in range(4):
        try:
            src.rename(dst)
            return
        except PermissionError:  # 동기화 프로그램이나 PDF 보기 프로그램이 잠시 잡고 있을 수 있다
            if attempt == 3:
                raise
            time.sleep(0.2 * (attempt + 1))


def place_pdf(vault: Vault, paper: dict) -> tuple[str | None, str]:
    """등록된 논문의 PDF 를 이름 규칙에 맞게 바꾼다 (같은 폴더 안에서). 반환: (위키 기준 경로, 알릴 말)

    바꾸지 못해도 등록은 계속된다: 지금 경로를 그대로 돌려주고 이유를 알린다.
    """
    info = paper.get("pdf") or {}
    current_rel = info.get("path")
    if not current_rel:
        return None, ""
    current = vault.root / current_rel
    wanted = pdf_filename(paper, name_pattern(vault))
    target = current.with_name(wanted)
    if not current.is_file():
        if target.is_file():  # 이전 시도에서 이름만 바뀌고 기록이 남지 않은 경우
            return target.relative_to(vault.root).as_posix(), ""
        return current_rel, "PDF 파일을 저장소에서 찾지 못했습니다. 파일을 옮겼다면 'paperwiki tidy' 로 다시 연결할 수 있습니다."
    if unicodedata.normalize("NFC", current.name) == wanted:
        return current_rel, ""
    same_file = target.exists() and os.path.samefile(current, target)  # 대소문자만 다른 경우
    if target.exists() and not same_file:
        stem, n = target.stem, 2
        while target.exists():
            target = current.with_name(f"{stem} ({n}).pdf")
            n += 1
    try:
        _rename(current, target)
    except OSError as exc:
        return current_rel, f"PDF 이름을 바꾸지 못했습니다 ({exc.__class__.__name__}). 파일이 다른 프로그램에서 열려 있으면 닫고 'paperwiki tidy' 를 실행해 주세요."
    return target.relative_to(vault.root).as_posix(), ""


def find_moved(vault: Vault, paper: dict) -> str | None:
    """기록된 경로에 PDF 가 없을 때: 저장소 안에서 같은 내용의 파일을 찾는다."""
    info = paper.get("pdf") or {}
    if not info.get("sha256"):
        return None
    claimed = claimed_paths(vault)
    for path in _pdf_files(vault):
        relative = path.relative_to(vault.root).as_posix()
        if _key(relative) in claimed and _key(relative) != _key(info.get("path", "")):
            continue
        try:
            if info.get("size") and path.stat().st_size != info["size"]:
                continue
            if sha256_file(path) == info["sha256"]:
                return relative
        except OSError:
            continue
    return None
