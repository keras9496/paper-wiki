"""기기별 설정, 비밀키 보관, 저장 위치 탐지.

- 기기별 설정(위키 폴더 경로, Zotero 연결 방식 등)은 OS 설정 폴더의 config.json 에 둔다.
  경로가 기기마다 다르기 때문에 위키 폴더(구글 드라이브) 안에 두지 않는다.
- 논문 분석은 Claude Code 가 하므로 AI 용 API 키는 다루지 않는다. 비밀값은 Zotero 에 관한 둘뿐이고
  (Zotero 앱이 내준 쓰기 허용 키, 선택 사항인 웹 API 키) OS 자격 증명 저장소(Windows 자격 증명 관리자 /
  macOS 키체인)에만 저장한다.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

APP = "paperwiki"
DEFAULT_PORT = 8765

DEFAULTS = {
    "vault_path": "",
    "zotero_mode": "local",  # local: 이 컴퓨터의 Zotero 앱 / web: Zotero 웹 API
    "zotero_user_id": "",
    "zotero_data_dir": "",
    "zotero_add": True,  # 위키에 등록한 읽은 논문이 Zotero 에 없으면 새 항목으로 넣는다
    "zotero_collection": "Paper Wiki",  # 위키에 있는 논문을 모아 두는 Zotero 컬렉션 (빈 값이면 쓰지 않는다)
    "zotero_pdf": "link",  # link: 위키 논문 폴더의 PDF 를 Zotero 항목에 링크된 파일로 붙인다 / none: 붙이지 않는다
    "reader_model": "sonnet",  # 논문 읽기 에이전트가 쓰는 Claude 모델: sonnet | opus | haiku | inherit(대화의 모델) | 모델 ID
    "port": DEFAULT_PORT,
}

SECRET_ENV = {
    "zotero_api_key": "ZOTERO_API_KEY",  # zotero.org 웹 API 키 (웹 방식을 쓸 때만)
    "zotero_local_key": "ZOTERO_LOCAL_KEY",  # 이 컴퓨터의 Zotero 앱이 '항상 허용'으로 내준 쓰기 허용 키
}


def config_dir() -> Path:
    override = os.environ.get("PAPERWIKI_CONFIG_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP
    return Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")) / APP


def config_path() -> Path:
    return config_dir() / "config.json"


def load() -> dict:
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(config_path().read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return cfg


def save(cfg: dict) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = {k: cfg.get(k, v) for k, v in DEFAULTS.items()}
    path.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")


def update(**changes) -> dict:
    cfg = load()
    cfg.update({k: v for k, v in changes.items() if k in DEFAULTS and v is not None})
    save(cfg)
    return cfg


# ── 비밀키 ────────────────────────────────────────────────────────────────


def _keyring():
    if os.environ.get("PAPERWIKI_NO_KEYRING"):
        return None
    try:
        import keyring

        return keyring
    except Exception:
        return None


def get_secret(name: str) -> str | None:
    """자격 증명 저장소 → 환경 변수 순으로 찾는다."""
    kr = _keyring()
    if kr is not None:
        try:
            value = kr.get_password(APP, name)
            if value:
                return value
        except Exception:
            pass
    return os.environ.get(SECRET_ENV[name]) or None


def secret_source(name: str) -> str | None:
    """키가 어디에 있는지('keyring' | 'env')만 알려준다. 값은 돌려주지 않는다."""
    kr = _keyring()
    if kr is not None:
        try:
            if kr.get_password(APP, name):
                return "keyring"
        except Exception:
            pass
    return "env" if os.environ.get(SECRET_ENV[name]) else None


def set_secret(name: str, value: str) -> None:
    if name not in SECRET_ENV:
        raise KeyError(name)
    kr = _keyring()
    if kr is None:
        raise RuntimeError(
            "이 컴퓨터에서 자격 증명 저장소를 사용할 수 없습니다. "
            f"대신 환경 변수 {SECRET_ENV[name]} 에 키를 설정해 주세요."
        )
    kr.set_password(APP, name, value)


def delete_secret(name: str) -> None:
    kr = _keyring()
    if kr is None:
        return
    try:
        kr.delete_password(APP, name)
    except Exception:
        pass


# ── 저장 위치 탐지 ─────────────────────────────────────────────────────────

def default_local_vault() -> Path:
    docs = Path.home() / "Documents"
    return (docs if docs.is_dir() else Path.home()) / "PaperWiki"


def _has_wiki(folder: Path) -> bool:
    try:
        return (folder / ".paperwiki").is_dir()
    except OSError:
        return False


_scan_cache: dict[str, tuple[float, list[Path]]] = {}


def existing_wikis(root: Path, rescan: bool = False) -> list[Path]:
    """이 폴더(계정의 내 드라이브) 안에 이미 있는 위키들. 잠깐 기억해 두어 화면을 다시 그릴 때마다 훑지 않는다."""
    from .store import find_vaults

    key = str(root)
    cached = _scan_cache.get(key)
    if cached and not rescan and time.monotonic() - cached[0] < 30:
        return cached[1]
    default = root / "PaperWiki"
    found = [default] if _has_wiki(default) else []  # 기본 위치는 훑기 제한과 상관없이 항상 확인
    found += [p for p in find_vaults(root) if p != default]
    _scan_cache[key] = (time.monotonic(), found)
    return found


def storage_options(mounts: list[dict] | None = None, rescan: bool = False) -> list[dict]:
    """설치 화면에 보여줄 저장 위치 후보.

    구글 드라이브 계정마다: 그 드라이브에 이미 위키가 있으면 그 위키(들)를 "불러오기" 후보로,
    없으면 기본 위치에 "새로 만들기" 후보를 낸다. 마지막은 이 컴퓨터의 문서 폴더.
    """
    from . import gdrive
    from .store import vault_summary

    mounts = gdrive.detect() if mounts is None else mounts

    def option(kind: str, target: Path, base: Path, exists: bool, m: dict | None = None) -> dict:
        return {
            "kind": kind,
            "path": str(target),
            "base": str(base),
            "exists": exists,
            "summary": vault_summary(target) if exists else None,
            "email": (m or {}).get("email"),
            "mount": (m or {}).get("mount", ""),
            "mode": (m or {}).get("mode", ""),
        }

    options = []
    for m in mounts:
        root = Path(m["root"])
        wikis = existing_wikis(root, rescan)
        if wikis:
            options += [option("gdrive", w, root, True, m) for w in wikis]
        else:
            options.append(option("gdrive", root / "PaperWiki", root, False, m))
    local = default_local_vault()
    options.append(option("local", local, local.parent, _has_wiki(local)))
    return options


def storage_info(vault_path: str, mounts: list[dict] | None = None) -> dict:
    """위키 폴더가 어디에 있는지: {"kind": "gdrive" | "local" | "none", "email": 계정 이메일 또는 None}"""
    from . import gdrive

    if not vault_path:
        return {"kind": "none", "email": None}
    mounts = gdrive.detect() if mounts is None else mounts
    try:
        target = Path(vault_path).resolve()
    except OSError:
        target = Path(vault_path)
    for m in mounts:
        try:
            target.relative_to(Path(m["root"]).resolve())
            return {"kind": "gdrive", "email": m.get("email")}
        except (ValueError, OSError):
            continue
    return {"kind": "local", "email": None}


def storage_kind(vault_path: str) -> str:
    return storage_info(vault_path)["kind"]


def detect_zotero_data_dir(cfg: dict | None = None) -> Path | None:
    """Zotero 데이터 폴더(storage/ 가 들어 있는 곳)."""
    candidates = []
    if cfg and cfg.get("zotero_data_dir"):
        candidates.append(Path(cfg["zotero_data_dir"]))
    candidates.append(Path.home() / "Zotero")
    for c in candidates:
        try:
            if (c / "storage").is_dir():
                return c
        except OSError:
            continue
    return None
