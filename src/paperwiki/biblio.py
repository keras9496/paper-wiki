"""DOI 등록 정보 조회 (doi.org → Crossref·DataCite 가 주는 CSL JSON).

논문의 서지 정보를 PDF 에서 읽은 것만 믿지 않고, DOI 에 등록된 기록으로 확인한다. 등록 기록에는
권·호·쪽 같은 PDF 첫 쪽에 없는 정보와, 출판사가 등록한 참고문헌의 DOI 도 들어 있다.
그래도 DOI 가 없는 참고문헌은 Crossref 에서 제목·제1저자·연도로 찾는다 (find_doi). DOI 는 서로 다른 논문이
다른 표기로 인용한 같은 문헌을 하나로 잇는 기준이다.

밖으로 보내는 것은 논문의 DOI 와, 참고문헌의 제목·제1저자 성뿐이다 (연도는 받은 결과를 고르는 데만 쓴다).
사용자나 위키에 관한 정보는 보내지 않는다.
"""

from __future__ import annotations

import difflib
import html
import re
import threading
import time
import unicodedata
from urllib.parse import quote

import httpx

from . import __version__

RESOLVER = "https://doi.org/"
SEARCH = "https://api.crossref.org/works"
_NOT_PAPERS = {"dataset", "component", "peer-review", "grant", "journal", "journal-issue", "reference-entry"}

# 등록 기록의 문헌 종류 → Zotero 항목 종류
ITEM_TYPES = {
    "journal-article": "journalArticle",
    "article-journal": "journalArticle",
    "proceedings-article": "conferencePaper",
    "paper-conference": "conferencePaper",
    "posted-content": "preprint",
    "article": "preprint",
    "book-chapter": "bookSection",
    "chapter": "bookSection",
    "book": "book",
    "monograph": "book",
    "edited-book": "book",
    "report": "report",
    "dissertation": "thesis",
    "thesis": "thesis",
}


_GREEK = str.maketrans({"α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "epsilon", "κ": "kappa", "λ": "lambda", "μ": "mu", "σ": "sigma", "τ": "tau", "ω": "omega", "ß": "ss", "ł": "l", "ø": "o", "đ": "d"})


def fold(text) -> str:
    """Žiga → Ziga. 발음 구별 기호를 뗀다 (한글은 그대로)."""
    decomposed = unicodedata.normalize("NFKD", str(text or ""))
    return unicodedata.normalize("NFC", "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn"))


def title_key(title) -> str:
    """제목 비교용 열쇠: 글자와 숫자만 남기고, 같은 제목의 흔한 표기 차이를 지운다.

    구두점·대소문자·띄어쓰기, 발음 기호(naïve = naive), 태그(<i>…</i>), '&' 와 'and', 그리스 문자와 그 이름(β = beta).
    """
    text = re.sub(r"<[^>]+>", "", unicodedata.normalize("NFKC", str(title or ""))).replace("&", " and ").casefold().translate(_GREEK)
    return "".join(re.findall(r"\w+", fold(text)))


def title_overlap(x: str, y: str) -> bool:
    """제목 열쇠 둘이, 한쪽이 다른 쪽의 앞이나 뒤에 말이 더 붙은 꼴인가.

    뒤에 붙는 것은 부제("…: a randomized trial"), 앞에 붙는 것은 학술지의 분류어("Oncogene regulation. An oncogenic …")다.
    """
    short, long = sorted((x, y), key=len)
    return (len(short) >= 25 and long.startswith(short)) or (len(short) >= 40 and long.endswith(short))


def same_title(a, b) -> bool:
    """두 제목이 같은 논문의 것인가. 부제나 분류어가 한쪽에만 붙은 경우까지 같다고 본다."""
    x, y = title_key(a), title_key(b)
    return bool(x and y) and (x == y or title_overlap(x, y))


def same_family(a, b) -> bool:
    """제1저자의 성이 같은 사람의 것으로 볼 수 있는가 (어느 한쪽이 비어 있으면 어긋나지 않는 것으로 본다).

    표기 차이를 받아들인다: 'The GTEx Consortium' 과 'GTEx Consortium', 'de Almeida' 와 'Almeida', 'Yüregir' 와 'Yuuregir'.
    """
    x, y = title_key(a), title_key(b)
    if not x or not y or x == y:
        return True
    short, long = sorted((x, y), key=len)
    return (len(short) >= 4 and short in long) or difflib.SequenceMatcher(None, x, y).ratio() >= 0.8


def _first(value):
    if isinstance(value, list):
        return value[0] if value else ""
    return value or ""


def _clean(text) -> str:
    """등록 기록의 제목·초록에 섞인 태그(<i>, <jats:p> …)와 줄바꿈을 걷어 낸다."""
    text = re.sub(r"<[^>]+>", " ", str(text or ""))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _date(value) -> str:
    parts = (value or {}).get("date-parts") if isinstance(value, dict) else None
    first = parts[0] if parts and isinstance(parts[0], list) else []
    nums = [int(p) for p in first if str(p).isdigit()]
    if not nums:
        return ""
    return "-".join([f"{nums[0]:04d}"] + [f"{n:02d}" for n in nums[1:3]])


def from_csl(data: dict, doi: str) -> dict:
    """CSL JSON → Paper Wiki 가 쓰는 서지 정보."""
    title = _clean(_first(data.get("title")))
    subtitle = _clean(_first(data.get("subtitle")))
    if subtitle and title_key(subtitle) not in title_key(title):
        title = f"{title}: {subtitle}"
    authors = []
    for a in data.get("author") or []:
        if not isinstance(a, dict):
            continue
        if a.get("family"):
            authors.append({"family": _clean(a["family"]), "given": _clean(a.get("given"))})
        elif a.get("literal") or a.get("name"):
            authors.append({"name": _clean(a.get("literal") or a.get("name"))})
    date = next((d for d in (_date(data.get(k)) for k in ("issued", "published", "published-online", "published-print")) if d), "")
    item_type = ITEM_TYPES.get(str(data.get("type") or ""), "journalArticle")
    institution = _first(data.get("institution"))
    venue = _clean(_first(data.get("container-title"))) or (
        _clean(institution.get("name") if isinstance(institution, dict) else institution) or _clean(data.get("publisher")) if item_type == "preprint" else ""
    )
    registered = str(data.get("DOI") or doi).strip()
    landing = ((data.get("resource") or {}).get("primary") or {}).get("URL") if isinstance(data.get("resource"), dict) else ""
    issn = data.get("ISSN")
    abstract = re.sub(r"^abstract\s+", "", _clean(data.get("abstract")), flags=re.I)
    return {
        "status": "ok",
        "title": title,
        "authors": authors,
        "year": date[:4],
        "venue": venue,
        "doi": registered,
        "url": str(landing or RESOLVER + registered),
        "abstract": abstract[:6000],
        "item_type": item_type,
        "biblio": {
            "date": date,
            "volume": _clean(data.get("volume")),
            "issue": _clean(data.get("issue")),
            "pages": _clean(data.get("page") or data.get("article-number")),
            "issn": str(_first(issn) if isinstance(issn, list) else issn or ""),
            "journal_abbr": _clean(_first(data.get("container-title-short"))),
            "publisher": _clean(data.get("publisher")),
            "language": _clean(data.get("language")),
            "source": "doi.org",
        },
        "references": [
            {
                "doi": str(r["DOI"]).strip(),
                "year": str(r.get("year") or "")[:4],
                "title": title_key(r.get("article-title") or r.get("volume-title")),
                "text": title_key(r.get("unstructured")),
            }
            for r in data.get("reference") or []
            if isinstance(r, dict) and r.get("DOI")
        ],
    }


def lookup(doi: str, transport=None, timeout: float = 12) -> dict:
    """DOI 에 등록된 서지 정보를 가져온다.

    돌려주는 값의 status: ok(나머지 값이 채워진다) · not_found(그런 DOI 가 등록되어 있지 않다) · unreachable(확인하지 못했다).
    """
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", str(doi or "").strip(), flags=re.I)
    if not doi:
        return {"status": "not_found"}
    headers = {"Accept": "application/vnd.citationstyles.csl+json", "User-Agent": f"paperwiki/{__version__}"}
    try:
        with httpx.Client(timeout=timeout, transport=transport, follow_redirects=True, headers=headers) as client:
            r = client.get(RESOLVER + quote(doi, safe="/"))
    except httpx.HTTPError:
        return {"status": "unreachable"}
    if r.status_code == 404:
        return {"status": "not_found"}
    if r.status_code != 200:
        return {"status": "unreachable"}
    try:
        data = r.json()
    except ValueError:
        return {"status": "unreachable"}  # CSL JSON 을 주지 않는 등록 기관
    if not isinstance(data, dict) or not _first(data.get("title")):
        return {"status": "unreachable"}
    return from_csl(data, doi)


def reference_doi(ref: dict, registered: list[dict]) -> str:
    """참고문헌 한 편(제목·연도)에 해당하는 등록된 DOI. 하나로 정해질 때만 돌려준다."""
    wanted = title_key(ref.get("title"))
    if len(wanted) < 15:
        return ""
    year = str(ref.get("year") or "")[:4]
    hits: dict[str, str] = {}
    for r in registered:
        if year and r.get("year") and r["year"] != year:
            continue
        if (r.get("title") and (r["title"] == wanted or (len(wanted) >= 25 and r["title"].startswith(wanted)))) or (r.get("text") and wanted in r["text"]):
            hits[r["doi"].casefold()] = r["doi"]
    return next(iter(hits.values())) if len(hits) == 1 else ""


_search_lock = threading.Lock()
_search_last = [0.0]
SEARCH_INTERVAL = 1.05  # Crossref 공개 창구의 한도: 1초에 한 번, 동시에 한 건


def _ask(client: httpx.Client, params: dict) -> list[dict]:
    """Crossref 검색 한 번. 한도를 지키려고 앞 요청과 간격을 두고, 잠깐 막히면(429) 기다렸다 한 번 더 묻는다."""
    for attempt in range(3):
        with _search_lock:
            wait = SEARCH_INTERVAL - (time.monotonic() - _search_last[0])
            if wait > 0:
                time.sleep(wait)
            r = client.get(SEARCH, params={**params, "rows": 5, "select": "DOI,title,author,issued,type"})
            _search_last[0] = time.monotonic()
        if r.status_code != 429:
            break
        time.sleep(min(float(r.headers.get("Retry-After") or 2), 10) * (attempt + 1))
    r.raise_for_status()
    return (r.json().get("message") or {}).get("items") or []


def _pick(items: list[dict], title: str, family: str, year: str) -> str:
    """검색 결과에서 이 참고문헌이 확실한 것 하나를 고른다. 없거나 둘이 똑같이 그럴듯하면 빈 문자열."""
    wanted, good = title_key(title), []
    for item in items:
        found_title = _clean(_first(item.get("title")))
        if not item.get("DOI") or item.get("type") in _NOT_PAPERS or not same_title(found_title, title):
            continue
        exact = title_key(found_title) == wanted
        first = _first(item.get("author"))
        theirs = title_key(first.get("family") or first.get("name")) if isinstance(first, dict) else ""
        found_year = _date(item.get("issued"))[:4]
        if not same_family(family, theirs):
            continue
        if year.isdigit() and found_year.isdigit() and abs(int(year) - int(found_year)) > 1:
            continue
        # 제목이 앞부분만 같은 것(부제 유무)은 저자와 연도가 모두 확인될 때만 받아들인다 — 제목이 비슷한 다른 글일 수 있다
        if not exact and not (family and theirs and year.isdigit() and found_year.isdigit()):
            continue
        gap = abs(int(year) - int(found_year)) if year.isdigit() and found_year.isdigit() else 1
        good.append(((not exact, item.get("type") == "posted-content", gap), title_key(found_title), found_year, str(item["DOI"]).strip()))
    if not good:
        return ""
    good.sort(key=lambda g: (g[0], len(g[3]), g[3]))
    best = [g for g in good if g[0] == good[0][0]]
    # 똑같이 그럴듯한 것이 둘이면 고르지 않는다. 다만 제목과 연도까지 같으면 한 논문에 DOI 가 둘 등록된 것이므로 하나를 쓴다.
    if len({(g[1], g[2]) for g in best}) > 1:
        return ""
    return best[0][3]


def find_doi(ref: dict, transport=None, timeout: float = 20) -> str:
    """참고문헌 한 편의 DOI 를 Crossref 에서 제목·제1저자·연도로 찾는다.

    제목이 같고(부제 유무 차이는 저자·연도가 확인될 때만 허용), 제1저자와 연도(±1년)가 어긋나지 않는 것만 받아들인다.
    프리프린트와 출판본이 함께 나오면 출판본을 고른다. 못 찾으면 빈 문자열, 연결이 안 되면 httpx.HTTPError 를 낸다.
    한 편에 1~2초가 걸린다 (Crossref 가 1초에 한 번만 받는다).
    """
    title = _clean(ref.get("title"))
    if len(title_key(title)) < 20:
        return ""
    authors = ref.get("authors") or []
    family = (authors[0].get("family") or authors[0].get("name") or "") if authors else ""
    year = str(ref.get("year") or "")[:4]
    with httpx.Client(timeout=timeout, transport=transport, headers={"User-Agent": f"paperwiki/{__version__}"}) as client:
        # 제목 칸과 저자 칸으로 먼저 묻고, 없으면 제목만으로 한 번 더 묻는다 (어느 한쪽에서만 나오는 문헌이 있다)
        doi = _pick(_ask(client, {"query.title": title[:400], "query.author": family}), title, family, year) if family else ""
        return doi or _pick(_ask(client, {"query.bibliographic": title[:400]}), title, family, year)
