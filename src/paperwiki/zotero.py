"""Zotero 연동.

위키에 등록한 '읽은 논문'은 Zotero 에도 있는 논문이어야 한다. 논문을 등록할 때 같은 논문이 Zotero 에
있으면 그 항목과 연결해 서지 정보·인용 키를 그대로 쓰고, 없으면 Zotero 에 새 항목으로 넣는다
(위키의 인용 키를 Zotero 의 인용 키로, 위키 논문 폴더의 PDF 를 링크된 파일로). Zotero 에만 있는 논문은
PDF 를 논문 폴더로 가져올 수 있다. 인용 문헌(참고문헌으로만 아는 논문)은 Zotero 에 넣지 않는다.

두 가지 연결 방식을 지원한다.

- local: 이 컴퓨터에서 실행 중인 Zotero 앱의 로컬 API (http://127.0.0.1:23119/api).
  zotero.org 의 API 키가 필요 없고 PDF 도 로컬 파일을 그대로 읽는다. 가장 안전하고 관리할 것이 없다.
  Zotero 설정 → 고급 → "이 컴퓨터의 다른 애플리케이션이 Zotero와 통신하도록 허용" 을 켜야 한다.
  읽기는 바로 되고, 쓰기(항목 추가)는 Zotero 가 띄우는 확인 창에서 사용자가 '항상 허용'을 눌러야 한다
  (authorize). 그때 받은 허용 키는 OS 자격 증명 저장소에만 둔다. Zotero 10 이상에서만 쓸 수 있다.
- web: Zotero 웹 API (https://api.zotero.org). Zotero 앱이 꺼져 있어도 되지만 API 키가 필요하다
  (항목을 추가하려면 쓰기 권한이 있는 키).

여러 컴퓨터에서 같은 라이브러리를 보는 것은 어느 방식이든 Zotero 자체의 계정 동기화가 맡는다
(구글 드라이브 데스크톱이 위키를 동기화하는 것과 같은 구조). 로컬 방식에서는 Zotero 앱이
계정에 로그인되어 있는지를 확인해 알려준다.

Paper Wiki 가 Zotero 에서 하는 일은 셋뿐이다: 새 항목(과 그 PDF 링크) 만들기, 위키에 있는 논문을
모으는 컬렉션에 넣기, 자신이 만든 PDF 링크의 경로 고치기. 기존 항목의 내용을 바꾸거나 지우지 않는다.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

import httpx

from . import config

LOCAL_ROOT = "http://127.0.0.1:23119/api"
LOCAL_BASE = LOCAL_ROOT + "/users/0"
WEB_ROOT = "https://api.zotero.org"
APP_NAME = "Paper Wiki"
_SKIP_TYPES = {"attachment", "note", "annotation"}

LOCAL_HELP = (
    "Zotero 설정 → 고급(Advanced) → '이 컴퓨터의 다른 애플리케이션이 Zotero와 통신하도록 허용"
    "(Allow other applications on this computer to communicate with Zotero)' 을 켜 주세요."
)
CONNECT_HELP = (
    "Zotero 가 아직 Paper Wiki 의 항목 추가를 허용하지 않았습니다. Zotero 를 켠 채로 'paperwiki zotero connect' 를 "
    "실행하고, Zotero 에 뜨는 확인 창에서 '항상 허용(Always Allow)'을 눌러 주세요."
)
OLD_VERSION = "이 Zotero 는 다른 프로그램이 항목을 추가하는 기능이 없는 버전입니다. Zotero 를 10 이상으로 업데이트해 주세요."


class ZoteroError(Exception):
    """사용자에게 그대로 보여줄 수 있는 오류."""


class ZoteroNotAuthorized(ZoteroError):
    """Zotero 가 Paper Wiki 의 쓰기를 (아직) 허용하지 않았다."""


def lookup_user_id(api_key: str, transport=None) -> dict:
    """웹 API 키로 사용자 ID 를 알아낸다 (사용자가 ID 를 따로 찾아 입력할 필요가 없도록)."""
    try:
        with httpx.Client(timeout=20, transport=transport) as client:
            r = client.get(f"{WEB_ROOT}/keys/current", headers={"Zotero-API-Key": api_key})
    except httpx.HTTPError as exc:
        raise ZoteroError(f"Zotero 서버에 연결하지 못했습니다: {exc}") from exc
    if r.status_code in (403, 404):
        raise ZoteroError("Zotero API 키가 올바르지 않습니다.")
    if r.status_code != 200:
        raise ZoteroError(f"Zotero 서버 오류 (HTTP {r.status_code})")
    data = r.json()
    return {"user_id": str(data.get("userID", "")), "username": data.get("username", "")}


class Zotero:
    def __init__(self, cfg: dict, transport=None):
        self.mode = cfg.get("zotero_mode") or "local"
        self.data_dir = config.detect_zotero_data_dir(cfg)
        headers = {"Zotero-API-Version": "3"}
        if self.mode == "web":
            key = config.get_secret("zotero_api_key")
            user_id = str(cfg.get("zotero_user_id") or "").strip()
            if not key or not user_id:
                raise ZoteroError("Zotero 웹 API 키가 설정되지 않았습니다. 설정 화면에서 입력해 주세요.")
            self.base = f"{WEB_ROOT}/users/{user_id}"
            headers["Zotero-API-Key"] = key
        else:
            self.base = LOCAL_BASE
            headers["Zotero-Allowed-Request"] = "1"
        self._server_id = ""
        self._collections: dict[str, str] = {}
        self._client = httpx.Client(headers=headers, timeout=httpx.Timeout(30, read=120), transport=transport)

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ── HTTP ──
    def _get(self, path: str, params: dict | None = None, follow: bool = True) -> httpx.Response:
        try:
            r = self._client.get(self.base + path, params=params, follow_redirects=follow)
        except httpx.ConnectError as exc:
            if self.mode == "local":
                raise ZoteroError("Zotero 앱에 연결하지 못했습니다. Zotero 가 실행 중인지 확인해 주세요.") from exc
            raise ZoteroError("Zotero 서버에 연결하지 못했습니다. 인터넷 연결을 확인해 주세요.") from exc
        except httpx.HTTPError as exc:
            raise ZoteroError(f"Zotero 요청 실패: {exc}") from exc
        if r.status_code == 403:
            if self.mode == "local":
                raise ZoteroError("Zotero 의 로컬 API 가 꺼져 있습니다. " + LOCAL_HELP)
            raise ZoteroError("Zotero API 키에 이 라이브러리를 읽을 권한이 없습니다.")
        return r

    def ping(self) -> dict:
        r = self._get("/items", {"limit": 1})
        if r.status_code != 200:
            raise ZoteroError(f"Zotero 응답 오류 (HTTP {r.status_code})")
        total = r.headers.get("Total-Results", "")
        # 로컬 API 는 Zotero 앱이 Zotero 계정에 로그인(동기화 설정)된 경우에만 웹 주소(alternate) 링크를 함께 준다
        linked = True if self.mode == "web" else 'rel="alternate"' in r.headers.get("Link", "")
        return {"ok": True, "mode": self.mode, "total": int(total) if total.isdigit() else None, "account_linked": linked}

    # ── 항목 ──
    def items(self, q: str = "", start: int = 0, limit: int = 30) -> tuple[list[dict], int | None]:
        """최근 추가한 순서로 최상위 항목(논문)을 가져온다."""
        params = {"limit": limit, "start": start, "sort": "dateAdded", "direction": "desc"}
        if q.strip():
            params.update(q=q.strip(), qmode="titleCreatorYear")
        r = self._get("/items/top", params)
        if r.status_code != 200:
            raise ZoteroError(f"Zotero 항목을 가져오지 못했습니다 (HTTP {r.status_code})")
        total = r.headers.get("Total-Results", "")
        metas = [to_meta(it) for it in r.json() if _data(it).get("itemType") not in _SKIP_TYPES]
        return metas, (int(total) if total.isdigit() else None)

    def item(self, key: str) -> dict:
        r = self._get(f"/items/{key}")
        if r.status_code == 404:
            raise ZoteroError("Zotero 에서 이 항목을 찾을 수 없습니다.")
        if r.status_code != 200:
            raise ZoteroError(f"Zotero 항목을 가져오지 못했습니다 (HTTP {r.status_code})")
        return to_meta(r.json())

    def find(self, doi: str = "", title: str = "") -> dict | None:
        """DOI 나 제목으로 라이브러리에서 같은 논문을 찾는다. 확실히 같을 때만 돌려준다."""

        def search(q: str, qmode: str) -> list[dict]:
            r = self._get("/items/top", {"q": q, "qmode": qmode, "limit": 10})
            if r.status_code != 200:
                return []
            return [to_meta(it) for it in r.json() if _data(it).get("itemType") not in _SKIP_TYPES]

        doi = doi.strip().casefold()
        if doi:
            for meta in search(doi, "everything"):
                if meta["doi"].casefold() == doi:
                    return meta
        wanted = _title_key(title)
        if len(wanted) >= 12:
            words = re.findall(r"\w+", title)[:6]
            for meta in search(" ".join(words), "titleCreatorYear"):
                if _title_key(meta["title"]) == wanted:
                    return meta
        return None

    def pdf_attachment(self, key: str) -> dict | None:
        r = self._get(f"/items/{key}/children")
        if r.status_code != 200:
            return None
        pdfs = []
        for child in r.json():
            d = _data(child)
            if d.get("itemType") != "attachment" or d.get("linkMode") == "linked_url":
                continue
            name = (d.get("filename") or d.get("path") or d.get("title") or "").lower()
            if d.get("contentType") == "application/pdf" or name.endswith(".pdf"):
                pdfs.append(child)
        # 라이브러리에 저장된 파일을 링크된 파일보다 우선
        pdfs.sort(key=lambda c: 0 if str(_data(c).get("linkMode", "")).startswith("imported") else 1)
        return pdfs[0] if pdfs else None

    def pdf_bytes(self, attachment: dict) -> bytes:
        """첨부 PDF 를 읽는다. 로컬 파일을 먼저 찾고, 없으면 API 로 내려받는다."""
        d = _data(attachment)
        key = d.get("key") or attachment.get("key")
        for path in self._local_candidates(attachment, key):
            try:
                if path.is_file():
                    return path.read_bytes()
            except OSError:
                continue
        r = self._get(f"/items/{key}/file", follow=(self.mode == "web"))
        if r.status_code in (301, 302, 303, 307, 308):
            path = _file_url_to_path(r.headers.get("Location", ""))
            if path and path.is_file():
                return path.read_bytes()
        if r.status_code == 200 and r.content[:5] == b"%PDF-":
            return r.content
        if self.mode == "web":
            raise ZoteroError(
                "PDF 를 가져오지 못했습니다. Zotero 파일 동기화를 쓰지 않는다면, PDF 가 있는 컴퓨터에서 "
                "연결 방식을 '이 컴퓨터의 Zotero 앱'으로 바꿔 가져와 주세요."
            )
        raise ZoteroError("PDF 파일을 찾지 못했습니다. Zotero 에서 첨부 파일이 열리는지 확인해 주세요.")

    def _local_candidates(self, attachment: dict, key: str) -> list[Path]:
        d = _data(attachment)
        out: list[Path] = []
        href = ((attachment.get("links") or {}).get("enclosure") or {}).get("href", "")
        path = _file_url_to_path(href)
        if path:
            out.append(path)
        raw = d.get("path") or ""
        if d.get("linkMode") == "linked_file" and raw and not raw.startswith("attachments:"):
            out.append(Path(raw))
        if self.data_dir and key:
            filename = d.get("filename") or (raw[len("storage:"):] if raw.startswith("storage:") else "")
            if filename:
                out.append(self.data_dir / "storage" / key / filename)
        return out

    # ── 쓰기 (항목 추가) ──
    def can_write(self) -> bool:
        """쓰기 허용을 받아 둔 상태인가 (실제로 통하는지는 써 봐야 안다)."""
        return self.mode == "web" or bool(config.get_secret("zotero_local_key"))

    def authorize(self, timeout: float = 300) -> dict:
        """Zotero 앱에 항목 추가 허용을 요청한다. Zotero 에 확인 창이 뜨고, 사용자가 고를 때까지 기다린다.

        '항상 허용'을 고르면 허용 키를 자격 증명 저장소에 두고 {'ok': True} 를, '허용'(한 번만)을 고르면
        키를 두지 않고 {'ok': False, 'once': True} 를 돌려준다.
        """
        if self.mode == "web":
            return {"ok": True}
        try:
            r = self._client.post(LOCAL_ROOT + "/local/authorize", json={"appName": APP_NAME}, headers={"Zotero-Server-ID": self._server()}, timeout=timeout)
        except httpx.ConnectError as exc:
            raise ZoteroError("Zotero 앱에 연결하지 못했습니다. Zotero 가 실행 중인지 확인해 주세요.") from exc
        except httpx.TimeoutException as exc:
            raise ZoteroError("Zotero 의 확인 창에서 답이 없었습니다. Zotero 창을 앞으로 가져와 확인 창에서 '항상 허용'을 누른 뒤 다시 실행해 주세요.") from exc
        except httpx.HTTPError as exc:
            raise ZoteroError(f"Zotero 요청 실패: {exc}") from exc
        if r.status_code == 200:
            data = r.json()
            if not data.get("remember"):
                return {"ok": False, "once": True}
            try:
                config.set_secret("zotero_local_key", str(data.get("key") or ""))
            except RuntimeError as exc:
                raise ZoteroError(str(exc)) from exc
            return {"ok": True}
        if r.status_code == 403:
            if "denied" in r.text:
                raise ZoteroError("Zotero 의 확인 창에서 거부를 선택했습니다. 허용하려면 다시 실행해 '항상 허용'을 눌러 주세요.")
            raise ZoteroError("Zotero 의 로컬 API 가 꺼져 있습니다. " + LOCAL_HELP)
        if r.status_code == 429:
            raise ZoteroError("허용 요청이 너무 잦습니다. 1분쯤 뒤에 다시 시도해 주세요.")
        if r.status_code in (400, 404, 405, 501):
            raise ZoteroError(OLD_VERSION)
        raise ZoteroError(f"Zotero 응답 오류 (HTTP {r.status_code})")

    def _server(self) -> str:
        """쓰기 요청에 함께 보내야 하는, 이 Zotero 의 ID."""
        if not self._server_id:
            self._server_id = self._get("/items", {"limit": 1}).headers.get("Zotero-Server-ID", "")
            if not self._server_id:
                raise ZoteroError(OLD_VERSION)
        return self._server_id

    def _write(self, method: str, path: str, body, headers: dict | None = None) -> httpx.Response:
        headers = dict(headers or {})
        if self.mode == "local":
            key = config.get_secret("zotero_local_key")
            if not key:
                raise ZoteroNotAuthorized(CONNECT_HELP)
            headers.update({"Zotero-API-Key": key, "Zotero-Server-ID": self._server()})
        try:
            r = self._client.request(method, self.base + path, json=body, headers=headers)
        except httpx.ConnectError as exc:
            raise ZoteroError("Zotero 에 연결하지 못했습니다. Zotero 가 실행 중인지 확인해 주세요.") from exc
        except httpx.HTTPError as exc:
            raise ZoteroError(f"Zotero 요청 실패: {exc}") from exc
        if r.status_code == 401 and self.mode == "local":
            config.delete_secret("zotero_local_key")  # Zotero 쪽에서 허용이 지워졌다
            raise ZoteroNotAuthorized(CONNECT_HELP)
        if r.status_code in (401, 403):
            if self.mode == "web":
                raise ZoteroError("Zotero API 키에 이 라이브러리에 쓸 권한이 없습니다. zotero.org 의 키 설정에서 쓰기 권한을 켜 주세요.")
            if "not enabled" in r.text:
                raise ZoteroError("Zotero 의 로컬 API 가 꺼져 있습니다. " + LOCAL_HELP)
            raise ZoteroError("Zotero 라이브러리에 쓸 수 없습니다 (읽기 전용).")
        if r.status_code in (405, 501) or (r.status_code == 400 and "does not support method" in r.text):
            raise ZoteroError(OLD_VERSION)
        return r

    def _create(self, path: str, obj: dict) -> dict:
        """객체 하나를 만들고 Zotero 가 돌려준 기록을 돌려준다."""
        r = self._write("POST", path, [obj])
        if r.status_code != 200:
            raise ZoteroError(f"Zotero 에 저장하지 못했습니다 (HTTP {r.status_code}: {r.text.strip()[:200]})")
        data = r.json()
        made = (data.get("successful") or {}).get("0")
        if isinstance(made, dict) and (made.get("key") or _data(made).get("key")):
            return made
        failed = (data.get("failed") or {}).get("0") or {}
        raise ZoteroError(f"Zotero 가 받아들이지 않았습니다: {failed.get('message') or '이유를 알 수 없음'}")

    def collection_key(self, name: str) -> str:
        """이름이 같은 최상위 컬렉션의 키. 없으면 만든다."""
        if name not in self._collections:
            key = ""
            r = self._get("/collections/top", {"limit": 100} if self.mode == "web" else None)
            if r.status_code == 200:
                key = next((_data(c).get("key") or c.get("key") for c in r.json() if _data(c).get("name") == name and not _data(c).get("deleted")), "")
            if not key:
                made = self._create("/collections", {"name": name})
                key = made.get("key") or _data(made).get("key")
            self._collections[name] = key
        return self._collections[name]

    def add_paper(self, paper: dict, pdf: Path | None = None, collection: str = "") -> dict:
        """읽은 논문을 Zotero 에 새 항목으로 만든다. pdf 를 주면 그 파일을 링크된 첨부로 붙인다.

        돌려주는 값: zotero_key, attachment_key(PDF 링크를 만들었을 때), note(일부만 됐을 때의 설명).
        """
        coll = self.collection_key(collection) if collection else ""
        made = self._create("/items", item_json(paper, [coll] if coll else []))
        key = made.get("key") or _data(made).get("key")
        out = {"zotero_key": key, "attachment_key": None, "note": ""}
        if pdf is not None:
            # linkMode 가 path 보다 먼저 와야 한다 (Zotero 는 받은 순서대로 값을 넣는다)
            attachment = {"itemType": "attachment", "linkMode": "linked_file", "parentItem": key, "title": "PDF", "contentType": "application/pdf", "path": str(pdf)}
            try:
                att = self._create("/items", attachment)
                out["attachment_key"] = att.get("key") or _data(att).get("key")
            except ZoteroError as exc:
                out["note"] = f"Zotero 항목은 만들었지만 PDF 링크는 붙이지 못했습니다: {exc}"
        return out

    def _current(self, key: str) -> tuple[dict, str] | None:
        """항목의 현재 내용과 버전 (고치기 전에 읽는다)."""
        r = self._get(f"/items/{key}")
        if r.status_code != 200:
            return None
        raw = r.json()
        version = r.headers.get("Last-Modified-Version") or str(raw.get("version", _data(raw).get("version", "")))
        return _data(raw), version

    def _patch(self, key: str, changes: dict, version: str) -> None:
        r = self._write("PATCH", f"/items/{key}", changes, {"If-Unmodified-Since-Version": str(version)})
        if r.status_code not in (200, 204):
            raise ZoteroError(f"Zotero 항목을 고치지 못했습니다 (HTTP {r.status_code}: {r.text.strip()[:200]})")

    def add_to_collection(self, key: str, collection: str) -> bool:
        """이미 있던 항목을 컬렉션에 넣는다 (다른 내용은 건드리지 않는다). 새로 넣었으면 True."""
        current = self._current(key)
        if current is None:
            return False
        data, version = current
        coll = self.collection_key(collection)
        have = list(data.get("collections") or [])
        if coll in have:
            return False
        self._patch(key, {"collections": have + [coll]}, version)
        return True

    def relink_pdf(self, attachment_key: str, pdf: Path) -> bool:
        """Paper Wiki 가 만든 PDF 링크가 가리키는 파일 이름이 위키의 PDF 와 다르면 고친다. 고쳤으면 True."""
        current = self._current(attachment_key)
        if current is None:
            return False
        data, version = current
        if data.get("linkMode") != "linked_file":
            return False
        linked = re.split(r"[\\/]", str(data.get("path") or "").removeprefix("attachments:"))[-1]
        if unicodedata.normalize("NFC", linked) == unicodedata.normalize("NFC", pdf.name):
            return False
        self._patch(attachment_key, {"path": str(pdf)}, version)
        return True


# 항목 종류마다 게재지를 넣는 필드와, 그 종류에서 쓸 수 있는 나머지 필드 (Zotero 항목 스키마)
_VENUE_FIELD = {
    "journalArticle": "publicationTitle",
    "conferencePaper": "proceedingsTitle",
    "preprint": "repository",
    "bookSection": "bookTitle",
    "book": "",
    "report": "institution",
    "thesis": "university",
}
_MORE_FIELDS = {
    "journalArticle": ("volume", "issue", "pages", "ISSN", "journalAbbreviation"),
    "conferencePaper": ("volume", "issue", "pages", "ISSN", "publisher"),
    "bookSection": ("volume", "pages", "ISSN", "publisher"),
    "book": ("volume", "ISSN", "publisher"),
    "preprint": (),
    "report": ("pages",),
    "thesis": (),
}
_PREPRINT = re.compile(r"arxiv|biorxiv|medrxiv|psyarxiv|ssrn|preprint|research square", re.I)


def item_json(paper: dict, collections=()) -> dict:
    """위키의 읽은 논문 → Zotero 항목. 인용 키는 위키의 것을 그대로 넣는다."""
    more = paper.get("biblio") or {}
    kind = paper.get("item_type")
    if kind not in _VENUE_FIELD:
        kind = "preprint" if _PREPRINT.search(str(paper.get("venue") or "")) or re.match(r"10\.(48550|1101|31234|2139)/", str(paper.get("doi") or "")) else "journalArticle"
    creators = [
        {"creatorType": "author", "name": a["name"]} if a.get("name") else {"creatorType": "author", "firstName": a.get("given", ""), "lastName": a.get("family", "")}
        for a in paper.get("authors") or []
    ]
    item = {"itemType": kind, "title": paper.get("title") or "", "creators": creators, "date": more.get("date") or str(paper.get("year") or "")}
    if _VENUE_FIELD[kind] and paper.get("venue"):
        item[_VENUE_FIELD[kind]] = paper["venue"]
    values = {"volume": more.get("volume"), "issue": more.get("issue"), "pages": more.get("pages"), "ISSN": more.get("issn"), "journalAbbreviation": more.get("journal_abbr"), "publisher": more.get("publisher")}
    for field in _MORE_FIELDS[kind]:
        if values.get(field):
            item[field] = values[field]
    for field, value in (("DOI", paper.get("doi")), ("url", paper.get("url")), ("abstractNote", paper.get("abstract")), ("language", more.get("language")), ("citationKey", paper.get("id"))):
        if value:
            item[field] = value
    if collections:
        item["collections"] = list(collections)
    return item


def _data(item: dict) -> dict:
    return item.get("data") or item


def _file_url_to_path(url: str) -> Path | None:
    if not url or not url.lower().startswith("file:"):
        return None
    try:
        return Path(url2pathname(urlparse(url).path))
    except (ValueError, OSError):
        return None


def _title_key(title: str) -> str:
    """제목 비교용: 글자와 숫자만 남긴다 (구두점·대소문자·띄어쓰기 차이 무시)."""
    return "".join(re.findall(r"\w+", str(title or "").casefold()))


_YEAR = re.compile(r"(1[5-9]\d\d|20\d\d)")


def to_meta(item: dict) -> dict:
    """Zotero 항목 JSON → Paper Wiki 가 쓰는 서지 정보."""
    d = _data(item)
    creators = d.get("creators") or []
    authors_raw = [c for c in creators if c.get("creatorType") == "author"] or creators
    authors = [
        {"name": c["name"]} if c.get("name") else {"family": c.get("lastName", ""), "given": c.get("firstName", "")}
        for c in authors_raw
    ]
    year_match = _YEAR.search(str(d.get("date") or "")) or _YEAR.search(str((item.get("meta") or {}).get("parsedDate") or ""))
    extra = d.get("extra") or ""
    citekey = d.get("citationKey") or ""
    if not citekey:
        m = re.search(r"(?im)^citation key:\s*(\S+)", extra)
        citekey = m.group(1) if m else ""
    doi = d.get("DOI") or ""
    if not doi:
        m = re.search(r"(?im)^doi:\s*(\S+)", extra)
        doi = m.group(1) if m else ""
    venue = next(
        (d[k] for k in ("publicationTitle", "proceedingsTitle", "bookTitle", "conferenceName", "repository", "university", "publisher") if d.get(k)),
        "",
    )
    return {
        "zotero_key": d.get("key") or item.get("key"),
        "attachment_key": None,
        "item_type": d.get("itemType", ""),
        "title": d.get("title", ""),
        "authors": authors,
        "year": year_match.group(1) if year_match else "",
        "venue": venue,
        "doi": re.sub(r"^https?://(dx\.)?doi\.org/", "", doi.strip()),
        "url": d.get("url", ""),
        "abstract": d.get("abstractNote", ""),
        "citekey_hint": citekey,
        "date_added": d.get("dateAdded", ""),
        "num_children": (item.get("meta") or {}).get("numChildren"),
    }
