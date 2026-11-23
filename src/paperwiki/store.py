"""위키 데이터 저장소.

위키 폴더(= Obsidian vault) 구조:

    <vault>/
      index.md, CLAUDE.md          ← 생성되는 마크다운 (사람·Obsidian·Claude Code 가 읽는 뷰)
      papers/<citekey>.md
      keywords/<키워드>.md
      pdf/                         ← 논문 저장소. 새 PDF 를 여기에 넣고, 위키에 등록되면 정해진 규칙의 이름으로 바뀐다
      .paperwiki/                  ← 원본 데이터 (프로그램이 읽고 쓰는 곳)
        vault.json                   위키 설정(언어, PDF 이름 규칙 등)
        ontology.json                키워드 온톨로지
        papers/<citekey>.json        승인된 논문 + 주장
        pending/<검토안 id>.json     검토 대기 중인 제안

원본은 JSON, 마크다운은 그로부터 만들어지는 뷰다. 폴더 전체가 구글 드라이브로
동기화되므로 다른 기기에서도 같은 상태(논문 PDF 포함)를 이어서 쓸 수 있다.
"""

from __future__ import annotations

import copy
import json
import os
from collections import deque
import re
import secrets
import threading
import time
import unicodedata
from datetime import date, datetime
from pathlib import Path

SCHEMA_VERSION = 1
CLAIM_TYPES = ("finding", "method", "background", "limitation")
PDF_DIR = "pdf"  # 위키 폴더 안의 논문 저장소

SEED_ONTOLOGY = {
    "ko": [
        {
            "name": "연구 주제",
            "aliases": ["Topics"],
            "description": "논문이 다루는 주제·개념·대상. 결과나 내용에 대한 주장은 이 아래의 세부 키워드로 정리합니다.",
            "children": [],
        },
        {
            "name": "방법론",
            "aliases": ["Methodology"],
            "description": "연구 방법에 대한 키워드. 어떤 종류의 설계·분석·도구인지에 따라 나눕니다.",
            "children": [
                {"name": "연구 설계", "aliases": ["Study design"], "description": "무작위 대조 시험, 코호트, 메타분석 등 연구의 틀."},
                {"name": "분석 방법", "aliases": ["Analysis methods"], "description": "통계 분석, 모델링, 기계학습 등 분석 기법."},
                {"name": "측정·평가 도구", "aliases": ["Measures and instruments"], "description": "검사, 척도, 장비, 평가 지표."},
                {"name": "데이터·대상", "aliases": ["Data and participants"], "description": "데이터셋, 코호트, 표본 구성."},
            ],
        },
    ],
    "en": [
        {
            "name": "Topics",
            "aliases": [],
            "description": "Subjects, concepts and populations the papers are about. Claims about results or content go under specific keywords here.",
            "children": [],
        },
        {
            "name": "Methodology",
            "aliases": [],
            "description": "Keywords about how research is done, organized by kind of design, analysis or instrument.",
            "children": [
                {"name": "Study design", "aliases": [], "description": "RCTs, cohorts, meta-analyses and other research designs."},
                {"name": "Analysis methods", "aliases": [], "description": "Statistical analysis, modeling and machine-learning techniques."},
                {"name": "Measures and instruments", "aliases": [], "description": "Tests, scales, devices and evaluation metrics."},
                {"name": "Data and participants", "aliases": [], "description": "Datasets, cohorts and sample composition."},
            ],
        },
    ],
}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def today() -> str:
    return date.today().isoformat()


def norm(text: str) -> str:
    """이름 비교용 정규화: 대소문자·공백·하이픈 차이를 무시한다."""
    text = unicodedata.normalize("NFKC", text or "").casefold()
    return re.sub(r"[\s\-_‐-―·/]+", " ", text).strip()


_ID_RE = re.compile(r"^[\w\-]{1,80}$", re.UNICODE)


def safe_id(value: str) -> str:
    """파일 이름으로 쓰이는 식별자 검증 (경로 조작 방지)."""
    if not isinstance(value, str) or not _ID_RE.match(value):
        raise ValueError(f"잘못된 식별자: {value!r}")
    return value


def file_stem(name: str) -> str:
    """키워드 이름 → 마크다운 파일 이름(확장자 제외). Windows·Obsidian 금지 문자를 뺀다."""
    stem = re.sub(r'[\\/:*?"<>|#^\[\]]+', " ", unicodedata.normalize("NFC", name))
    stem = re.sub(r"\s+", " ", stem).strip(" .")
    return stem[:100].strip(" .") or "keyword"


def write_text_atomic(path: Path, text: str) -> None:
    """임시 파일에 쓴 뒤 교체한다. 동기화 프로그램이 파일을 잠시 잡고 있으면 재시도한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    for attempt in range(5):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.15 * (attempt + 1))
    path.write_text(text, encoding="utf-8", newline="\n")
    try:
        tmp.unlink()
    except OSError:
        pass


def write_json_atomic(path: Path, data) -> None:
    write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=2))


class OntologyError(ValueError):
    pass


class VaultUnavailable(Exception):
    """위키 파일을 지금은 읽을 수 없다 (드라이브가 아직 동기화 중이거나 오프라인).

    일부만 읽힌 상태로 계속 진행하면 빠진 데이터를 '없는 것'으로 보고 덮어쓰게 되므로,
    읽기에 실패하면 조용히 넘어가지 않고 이 예외로 작업을 멈춘다.
    """


def find_vaults(root: str | Path, max_depth: int = 3, budget: float = 2.0, max_dirs: int = 4000) -> list[Path]:
    """root 아래에서 이미 만들어진 위키 폴더를 찾는다 (다른 컴퓨터에서 만든 위키 불러오기용).

    얕은 폴더부터 훑고, 정해진 시간·개수를 넘으면 그때까지 찾은 것만 돌려준다.
    """
    found: list[Path] = []
    deadline = time.monotonic() + budget
    visited = 0
    queue: deque[tuple[Path, int]] = deque([(Path(root), 0)])
    while queue:
        folder, depth = queue.popleft()
        if Vault.is_vault(folder):
            found.append(folder)
            continue
        if depth >= max_depth:
            continue
        if time.monotonic() > deadline or visited >= max_dirs:
            break
        visited += 1
        try:
            with os.scandir(folder) as it:
                children = sorted(
                    (e.path for e in it if e.is_dir(follow_symlinks=False) and not e.name.startswith((".", "$", "~"))),
                    key=str.casefold,
                )
        except OSError:
            continue
        queue.extend((Path(child), depth + 1) for child in children)
    return found


def vault_summary(path: str | Path) -> dict:
    """위키 폴더를 열지 않고도 보여줄 수 있는 요약 (논문 수, 키워드 수, 마지막 수정 시각)."""
    vault = Vault(path)
    newest = 0.0

    def count_json(directory: Path) -> int:
        nonlocal newest
        n = 0
        try:
            with os.scandir(directory) as it:
                for entry in it:
                    if entry.name.endswith(".json"):
                        n += 1
                        try:
                            newest = max(newest, entry.stat().st_mtime)
                        except OSError:
                            pass
        except OSError:
            pass
        return n

    papers = count_json(vault.papers_json)
    pending = count_json(vault.pending_json)
    keywords = None
    try:
        newest = max(newest, vault.ontology_path.stat().st_mtime)
        keywords = len(json.loads(vault.ontology_path.read_text(encoding="utf-8")).get("nodes", {}))
    except (OSError, ValueError):
        pass
    return {
        "papers": papers,
        "pending": pending,
        "keywords": keywords,
        "language": vault.settings().get("language", "ko"),
        "modified": datetime.fromtimestamp(newest).strftime("%Y-%m-%d %H:%M") if newest else "",
    }


class Ontology:
    """키워드 트리. 이름(과 별칭)은 위키 전체에서 유일하다 — 위키 문서 제목이 되기 때문."""

    def __init__(self, nodes: dict[str, dict] | None = None):
        self.nodes: dict[str, dict] = nodes or {}
        self._index()

    def _index(self) -> None:
        self._names: dict[str, str] = {}
        self._children: dict[str | None, list[str]] = {}
        for n in self.nodes.values():
            parent = n.get("parent") if n.get("parent") in self.nodes else None
            n["parent"] = parent
            self._children.setdefault(parent, []).append(n["id"])
        for n in self.nodes.values():  # 이름이 별칭보다 우선
            self._names.setdefault(norm(n["name"]), n["id"])
        for n in self.nodes.values():
            for alias in n.get("aliases", []):
                self._names.setdefault(norm(alias), n["id"])
        for parent, ids in self._children.items():
            if parent is not None:  # 최상위 분류는 만든 순서를 유지한다 (연구 주제 → 방법론)
                ids.sort(key=lambda i: norm(self.nodes[i]["name"]))

    # ── 조회 ──
    def get(self, node_id: str) -> dict | None:
        return self.nodes.get(node_id)

    def find(self, name: str) -> dict | None:
        node_id = self._names.get(norm(name))
        return self.nodes.get(node_id) if node_id else None

    def children(self, node_id: str | None) -> list[dict]:
        return [self.nodes[i] for i in self._children.get(node_id, [])]

    def roots(self) -> list[dict]:
        return self.children(None)

    def path_ids(self, node_id: str) -> list[str]:
        out, seen, cur = [], set(), node_id
        while cur and cur in self.nodes and cur not in seen:
            seen.add(cur)
            out.append(cur)
            cur = self.nodes[cur].get("parent")
        return out[::-1]

    def path_names(self, node_id: str) -> list[str]:
        return [self.nodes[i]["name"] for i in self.path_ids(node_id)]

    def descendants(self, node_id: str) -> list[str]:
        out, stack = [], list(self._children.get(node_id, []))
        while stack:
            cur = stack.pop()
            out.append(cur)
            stack.extend(self._children.get(cur, []))
        return out

    def walk(self):
        """(depth, node) 를 트리 순서로 낸다."""
        stack = [(0, n) for n in reversed(self.roots())]
        while stack:
            depth, node = stack.pop()
            yield depth, node
            stack.extend((depth + 1, c) for c in reversed(self.children(node["id"])))

    def flat(self) -> list[dict]:
        return [
            {
                "id": n["id"],
                "name": n["name"],
                "aliases": n.get("aliases", []),
                "description": n.get("description", ""),
                "parent": n.get("parent"),
                "path": self.path_names(n["id"]),
                "depth": depth,
            }
            for depth, n in self.walk()
        ]

    def outline(self) -> str:
        """AI 프롬프트에 넣는 들여쓰기 목록."""
        lines = []
        for depth, n in self.walk():
            alias = f"  (aliases: {', '.join(n['aliases'])})" if n.get("aliases") else ""
            lines.append(f"{'  ' * depth}- {n['name']}{alias}")
        return "\n".join(lines)

    # ── 변경 ──
    def _unique_file(self, name: str, exclude: str | None = None) -> str:
        taken = {n.get("file", "").casefold() for n in self.nodes.values() if n["id"] != exclude}
        stem, i = file_stem(name), 2
        candidate = stem
        while candidate.casefold() in taken:
            candidate = f"{stem} {i}"
            i += 1
        return candidate

    def _clean_aliases(self, aliases, name: str, own_id: str | None) -> list[str]:
        out, seen = [], {norm(name)}
        for alias in aliases or []:
            alias = re.sub(r"\s+", " ", str(alias)).strip()
            key = norm(alias)
            if not key or key in seen:
                continue
            owner = self._names.get(key)
            if owner and owner != own_id:
                continue  # 다른 키워드가 이미 쓰는 이름
            seen.add(key)
            out.append(alias)
        return out

    def add(self, name: str, parent: str | None = None, aliases=(), description: str = "") -> dict:
        name = re.sub(r"\s+", " ", name or "").strip()
        if not name:
            raise OntologyError("키워드 이름이 비어 있습니다.")
        if parent is not None and parent not in self.nodes:
            raise OntologyError("상위 키워드를 찾을 수 없습니다.")
        existing = self.find(name)
        if existing:
            raise OntologyError(f"'{existing['name']}' 키워드가 이미 있습니다.")
        node_id = "k" + secrets.token_hex(4)
        while node_id in self.nodes:
            node_id = "k" + secrets.token_hex(4)
        node = {
            "id": node_id,
            "name": name,
            "aliases": self._clean_aliases(aliases, name, None),
            "description": (description or "").strip(),
            "parent": parent,
            "file": self._unique_file(name),
            "created": today(),
        }
        self.nodes[node_id] = node
        self._index()
        return node

    def ensure_path(self, path, aliases=(), description: str = "") -> tuple[str, list[str]]:
        """경로의 마지막 키워드를 찾거나 만든다. 중간 키워드가 없으면 함께 만든다.

        이미 있는 이름이면 경로와 상관없이 기존 키워드를 쓴다 (이름이 유일하므로).
        반환: (키워드 id, 새로 만든 id 목록)
        """
        names = [re.sub(r"\s+", " ", str(p)).strip() for p in (path or [])]
        names = [n for n in names if n]
        if not names:
            raise OntologyError("키워드 경로가 비어 있습니다.")
        leaf = self.find(names[-1])
        if leaf:
            return leaf["id"], []
        created, parent = [], None
        for name in names[:-1]:
            node = self.find(name)
            if node is None:
                node = self.add(name, parent)
                created.append(node["id"])
            parent = node["id"]
        node = self.add(names[-1], parent, aliases, description)
        created.append(node["id"])
        return node["id"], created

    def update(self, node_id: str, *, name=None, aliases=None, description=None) -> dict:
        node = self.nodes.get(node_id)
        if node is None:
            raise OntologyError("키워드를 찾을 수 없습니다.")
        if name is not None:
            name = re.sub(r"\s+", " ", name).strip()
            if not name:
                raise OntologyError("키워드 이름이 비어 있습니다.")
            other = self.find(name)
            if other and other["id"] != node_id:
                raise OntologyError(f"'{other['name']}' 키워드가 이미 있습니다.")
            if name != node["name"]:
                node["name"] = name
                node["file"] = self._unique_file(name, exclude=node_id)
                self._index()
        if aliases is not None:
            node["aliases"] = self._clean_aliases(aliases, node["name"], node_id)
        elif name is not None:
            node["aliases"] = self._clean_aliases(node.get("aliases", []), node["name"], node_id)
        if description is not None:
            node["description"] = description.strip()
        self._index()
        return node

    def move(self, node_id: str, parent: str | None) -> None:
        if node_id not in self.nodes:
            raise OntologyError("키워드를 찾을 수 없습니다.")
        if parent is not None:
            if parent not in self.nodes:
                raise OntologyError("상위 키워드를 찾을 수 없습니다.")
            if parent == node_id or parent in self.descendants(node_id):
                raise OntologyError("자기 자신이나 하위 키워드 아래로는 옮길 수 없습니다.")
        self.nodes[node_id]["parent"] = parent
        self._index()

    def remove(self, node_id: str) -> None:
        if node_id not in self.nodes:
            return
        if self._children.get(node_id):
            raise OntologyError("하위 키워드가 있어 삭제할 수 없습니다. 먼저 하위 키워드를 옮기거나 병합하세요.")
        del self.nodes[node_id]
        self._index()


class _DirCache:
    """폴더의 JSON 파일들을 읽되, 바뀐 파일만 다시 읽는다.

    다른 기기에서 동기화되어 들어온 변경도 다음 조회 때 반영된다.
    """

    def __init__(self, directory: Path):
        self.directory = directory
        self._items: dict[str, tuple[tuple[int, int], dict]] = {}
        self.unreadable: list[str] = []  # 목록에는 있지만 내용을 읽지 못한 파일

    def load(self) -> dict[str, dict]:
        fresh: dict[str, tuple[tuple[int, int], dict]] = {}
        unreadable: list[str] = []
        try:
            entries = list(os.scandir(self.directory))
        except FileNotFoundError:
            entries = []
        except OSError as exc:
            raise VaultUnavailable("위키 폴더를 읽을 수 없습니다. 구글 드라이브가 연결되어 있는지 확인해 주세요.") from exc
        for entry in entries:
            if not entry.name.endswith(".json"):
                continue
            stem = entry.name[:-5]
            try:
                st = entry.stat()
            except OSError:
                unreadable.append(stem)
                continue
            sig = (st.st_mtime_ns, st.st_size)
            cached = self._items.get(stem)
            if cached and cached[0] == sig:
                fresh[stem] = cached
                continue
            try:
                data = json.loads(Path(entry.path).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                unreadable.append(stem)
                continue
            if isinstance(data, dict):
                fresh[stem] = (sig, data)
        self._items = fresh
        self.unreadable = unreadable
        return {stem: data for stem, (_, data) in fresh.items()}


class Vault:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.meta_dir = self.root / ".paperwiki"
        self.papers_json = self.meta_dir / "papers"
        self.pending_json = self.meta_dir / "pending"
        self.ontology_path = self.meta_dir / "ontology.json"
        self.settings_path = self.meta_dir / "vault.json"
        self.papers_md = self.root / "papers"
        self.keywords_md = self.root / "keywords"
        self.pdf_dir = self.root / PDF_DIR
        self.lock = threading.RLock()
        self._papers = _DirCache(self.papers_json)
        self._pending = _DirCache(self.pending_json)
        self._onto: tuple[tuple[int, int], Ontology] | None = None

    # ── 초기화 ──
    @staticmethod
    def is_vault(path: str | Path) -> bool:
        return (Path(path) / ".paperwiki" / "vault.json").is_file()

    @property
    def exists(self) -> bool:
        return self.settings_path.is_file()

    def init(self, language: str = "ko") -> None:
        """새 위키를 만든다. 이미 있으면 아무것도 덮어쓰지 않는다."""
        brand_new = not self.settings_path.exists()
        for d in (self.papers_json, self.pending_json, self.papers_md, self.keywords_md, self.pdf_dir):
            d.mkdir(parents=True, exist_ok=True)
        if brand_new:
            language = language if language in SEED_ONTOLOGY else "ko"
            write_json_atomic(
                self.settings_path,
                {"schema": SCHEMA_VERSION, "language": language, "created": now_iso()},
            )
        # 기존 위키인데 온톨로지 파일이 아직 안 보이는 것은 '동기화 중'이다. 그때 새로 만들면 원본과 충돌한다.
        if brand_new and not self.ontology_path.exists():
            onto = Ontology()

            def seed(items, parent=None):
                for item in items:
                    node = onto.add(item["name"], parent, item.get("aliases", []), item.get("description", ""))
                    seed(item.get("children", []), node["id"])

            seed(SEED_ONTOLOGY[self.settings().get("language", "ko")])
            self.save_ontology(onto)

    def settings(self) -> dict:
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data.setdefault("language", "ko")
        return data

    def save_settings(self, **changes) -> dict:
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise VaultUnavailable("위키 설정 파일을 읽을 수 없습니다. 드라이브 동기화가 끝난 뒤 다시 시도해 주세요.") from exc
        data.update(changes)
        write_json_atomic(self.settings_path, data)
        return data

    # ── 온톨로지 ──
    def ontology(self) -> Ontology:
        unavailable = "키워드 데이터를 아직 읽을 수 없습니다. 구글 드라이브 동기화가 끝난 뒤 다시 시도해 주세요."
        try:
            st = self.ontology_path.stat()
            sig = (st.st_mtime_ns, st.st_size)
        except OSError as exc:
            raise VaultUnavailable(unavailable) from exc
        if self._onto and self._onto[0] == sig:
            return Ontology(copy.deepcopy(self._onto[1].nodes))
        try:
            nodes = json.loads(self.ontology_path.read_text(encoding="utf-8"))["nodes"]
            if not isinstance(nodes, dict):
                raise ValueError("nodes")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            # 빈 온톨로지로 계속하면 다음 저장 때 원본을 덮어쓰게 된다
            raise VaultUnavailable(unavailable) from exc
        onto = Ontology(nodes)
        for node in onto.nodes.values():  # 손으로 고친 파일에도 file 값이 있도록
            if not node.get("file"):
                node["file"] = onto._unique_file(node["name"], exclude=node["id"])
        self._onto = (sig, onto)
        return Ontology(copy.deepcopy(onto.nodes))

    def check_readable(self) -> None:
        """무언가를 쓰기 전에: 위키 데이터를 빠짐없이 읽을 수 있는지 확인한다.

        읽을 수 없으면 VaultUnavailable. 일부만 고쳐진 채로 작업이 중단되는 일을 막는다.
        """
        self.ontology()
        self.papers()

    def save_ontology(self, onto: Ontology) -> None:
        write_json_atomic(self.ontology_path, {"schema": SCHEMA_VERSION, "nodes": onto.nodes})
        self._onto = None

    # ── 논문 ──
    def papers(self) -> dict[str, dict]:
        """승인된 논문 전체. 돌려준 dict 는 읽기 전용으로 다룬다."""
        loaded = self._papers.load()
        if self._papers.unreadable:
            raise VaultUnavailable(
                f"논문 데이터 {len(self._papers.unreadable)}개를 아직 읽을 수 없습니다. "
                "구글 드라이브 동기화가 끝난 뒤(또는 인터넷에 연결한 뒤) 다시 시도해 주세요."
            )
        return {stem: p for stem, p in loaded.items() if p.get("id") == stem}

    def paper(self, paper_id: str) -> dict | None:
        found = self.papers().get(paper_id)
        return copy.deepcopy(found) if found else None

    def paper_by_zotero(self, zotero_key: str) -> dict | None:
        if not zotero_key:
            return None
        for p in self.papers().values():
            if p.get("zotero_key") == zotero_key:
                return copy.deepcopy(p)
        return None

    def paper_by_sha(self, sha256: str) -> dict | None:
        """같은 PDF 파일(내용 기준)로 이미 등록된 논문."""
        if not sha256:
            return None
        for p in self.papers().values():
            if (p.get("pdf") or {}).get("sha256") == sha256:
                return copy.deepcopy(p)
        return None

    def save_paper(self, paper: dict) -> None:
        write_json_atomic(self.papers_json / f"{safe_id(paper['id'])}.json", paper)

    def delete_paper(self, paper_id: str) -> None:
        try:
            (self.papers_json / f"{safe_id(paper_id)}.json").unlink()
        except FileNotFoundError:
            pass

    # ── 검토 대기 ──
    def pending_all(self) -> list[dict]:
        loaded = self._pending.load()
        items = [p for stem, p in loaded.items() if p.get("id") == stem]
        return sorted(items, key=lambda p: p.get("created", ""), reverse=True)

    def pending(self, draft_id: str) -> dict | None:
        path = self.pending_json / f"{safe_id(draft_id)}.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def save_pending(self, draft_id: str, data: dict) -> None:
        write_json_atomic(self.pending_json / f"{safe_id(draft_id)}.json", data)

    def delete_pending(self, draft_id: str) -> None:
        try:
            (self.pending_json / f"{safe_id(draft_id)}.json").unlink()
        except FileNotFoundError:
            pass
