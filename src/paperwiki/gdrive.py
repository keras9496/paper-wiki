"""구글 드라이브 데스크톱 탐지: 설치 여부, 로그인된 계정, 계정별 '내 드라이브' 폴더.

Paper Wiki 는 구글에 직접 로그인하지 않는다. 동기화는 구글 드라이브 데스크톱이 하고,
앱은 그 프로그램이 이 컴퓨터에 연결해 둔 폴더 가운데 어느 계정의 것을 쓸지 고르게 할 뿐이다.

계정 이메일은 화면에 "어느 계정의 드라이브인지" 보여주기 위해서만 읽는다 (저장·전송하지 않음).
이메일을 알아내는 부분은 드라이브 데스크톱의 내부 파일에 기대므로, 실패하면 조용히
이메일 없이(드라이브 문자만) 보여준다.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import string
import subprocess
import sys
from pathlib import Path

MY_DRIVE_NAMES = ("내 드라이브", "My Drive")
DOWNLOAD_URL = "https://www.google.com/drive/download/"
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_EMAIL_B = re.compile(_EMAIL.pattern.encode())


def _exists(p: Path) -> bool:
    try:
        return p.exists()
    except OSError:
        return False


def _is_dir(p: Path) -> bool:
    try:
        return p.is_dir()
    except OSError:
        return False


# ── 설치·실행 ─────────────────────────────────────────────────────────────


def install_dir() -> Path | None:
    if sys.platform == "win32":
        for var in ("ProgramW6432", "ProgramFiles"):
            base = os.environ.get(var)
            if base and _is_dir(Path(base) / "Google" / "Drive File Stream"):
                return Path(base) / "Google" / "Drive File Stream"
        return None
    if sys.platform == "darwin":
        app = Path("/Applications/Google Drive.app")
        return app if _exists(app) else None
    return None


def is_installed() -> bool:
    return install_dir() is not None


def _launch_command() -> list[str] | None:
    root = install_dir()
    if root is None:
        return None
    if sys.platform == "darwin":
        return ["open", "-a", "Google Drive"]
    launcher = root / "launch.bat"  # 구글이 제공하는 실행 스크립트 (최신 버전을 찾아 실행)
    if _exists(launcher):
        return ["cmd", "/c", str(launcher)]
    versions = sorted(
        (d for d in root.iterdir() if d.is_dir() and _exists(d / "GoogleDriveFS.exe")),
        key=lambda d: [int(x) if x.isdigit() else 0 for x in d.name.split(".")],
    )
    return [str(versions[-1] / "GoogleDriveFS.exe")] if versions else None


def can_launch() -> bool:
    return _launch_command() is not None


def launch() -> bool:
    """구글 드라이브 데스크톱을 실행한다 (이미 실행 중이면 아무 일도 일어나지 않는다)."""
    cmd = _launch_command()
    if not cmd:
        return False
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    try:
        subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags, close_fds=True)
        return True
    except OSError:
        return False


# ── 계정 정보 (최선을 다해 읽되, 실패해도 괜찮다) ────────────────────────────


def app_data_dir() -> Path | None:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        return Path(base) / "Google" / "DriveFS" if base else None
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Google" / "DriveFS"
    return None


def read_account_email(account_dir: Path) -> str | None:
    """드라이브 데스크톱의 계정 폴더에서 그 계정의 이메일을 읽는다."""
    db = account_dir / "metadata_sqlite_db"
    if not _exists(db):
        return None
    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=0.5)
        try:
            rows = dict(con.execute("select property, value from properties where property in ('driveway_account', 'account')"))
        finally:
            con.close()
    except (sqlite3.Error, ValueError):
        return None
    for key in ("driveway_account", "account"):
        value = rows.get(key)
        if value is None:
            continue
        email = email_from_blob(value if isinstance(value, bytes) else str(value).encode("utf-8", "replace"))
        if email:
            return email
    return None


def email_from_blob(raw: bytes) -> str | None:
    """이진 데이터(protobuf) 안에 들어 있는 이메일 문자열을 정확한 범위로 꺼낸다.

    이메일 바로 뒤에는 다음 항목의 표식 바이트가 붙어 있는데, 그 값이 우연히 글자('Z' 등)이면
    이메일처럼 보이는 글자열에 딸려 들어온다. 그래서 글자열을 눈대중으로 자르지 않고,
    문자열 바로 앞에 기록된 길이 바이트와 맞아떨어지는 범위만 이메일로 인정한다.
    맞는 범위가 없으면 틀린 주소를 보여주느니 None 을 돌려준다.
    """
    for run in _EMAIL_B.finditer(raw):
        start, end = run.span()
        for s in range(max(start, 1), end):
            length = raw[s - 1]
            if 6 <= length <= end - s and _EMAIL_B.fullmatch(raw, s, s + length):
                return raw[s : s + length].decode("ascii")
    return None


def account_emails(base: Path | None = None) -> dict[str, str]:
    """{계정 ID: 이메일} — 지금 드라이브 데스크톱에 연결된 계정들."""
    base = base if base is not None else app_data_dir()
    out: dict[str, str] = {}
    if base is None or not _is_dir(base):
        return out
    try:
        dirs = [d for d in base.iterdir() if d.is_dir() and d.name.isdigit()]
    except OSError:
        return out
    for d in dirs:
        email = read_account_email(d)
        if email:
            out[d.name] = email
    return out


def _registry_prefs() -> tuple[dict[str, str], str]:
    """({계정 ID: 사용자가 지정한 드라이브 문자}, 현재 기본 계정 ID). Windows 전용."""
    letters: dict[str, str] = {}
    current = ""
    if sys.platform != "win32":
        return letters, current
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\DriveFS") as key:
            try:
                current = str(winreg.QueryValueEx(key, "CurrentAccountToken")[0])
            except OSError:
                pass
            try:
                prefs = json.loads(winreg.QueryValueEx(key, "PerAccountPreferences")[0])
                for entry in prefs.get("per_account_preferences", []):
                    mount = str((entry.get("value") or {}).get("mount_point_path") or "")
                    if mount[:1].isalpha():
                        letters[str(entry.get("key"))] = mount[:1].upper()
            except (OSError, ValueError, AttributeError):
                pass
    except OSError:
        pass
    return letters, current


def _volume_label(root: str) -> str:
    try:
        import ctypes

        buf = ctypes.create_unicode_buffer(261)
        ok = ctypes.windll.kernel32.GetVolumeInformationW(root, buf, len(buf), None, None, None, None, 0)
        return buf.value if ok else ""
    except Exception:
        return ""


def assign_emails(mounts: list[dict], accounts: dict[str, str], letters: dict[str, str], current: str) -> None:
    """각 드라이브(mount)가 어느 계정의 것인지 정한다. 확실할 때만 email 을 채운다.

    1) 드라이브 이름에 이메일이 들어 있으면 그것 (추가 계정의 드라이브는 이메일로 이름이 붙는다)
    2) 사용자가 계정별 드라이브 문자를 지정해 두었으면 그것
    3) 남은 드라이브와 남은 계정이 하나씩이면 서로 짝
    """
    used: set[str] = set()
    by_email = {email.lower(): acc for acc, email in accounts.items()}
    for m in mounts:
        found = _EMAIL.search(m.get("label") or "")
        if found:
            m["email"] = found.group()
            used.add(by_email.get(found.group().lower(), ""))
    for acc, letter in letters.items():
        for m in mounts:
            if not m.get("email") and m.get("mount", "")[:1].upper() == letter and acc in accounts:
                m["email"] = accounts[acc]
                used.add(acc)
    open_mounts = [m for m in mounts if not m.get("email")]
    open_accounts = [acc for acc in accounts if acc not in used]
    if len(open_mounts) == 1:
        if len(open_accounts) == 1:
            open_mounts[0]["email"] = accounts[open_accounts[0]]
        elif len(mounts) == 1 and current in open_accounts:
            open_mounts[0]["email"] = accounts[current]  # 예전 계정의 흔적이 남아 있어도 현재 계정은 하나


# ── '내 드라이브' 폴더 찾기 ───────────────────────────────────────────────


def _my_drive(root: Path) -> Path | None:
    for name in MY_DRIVE_NAMES:
        if _is_dir(root / name):
            return root / name
    return None


def _windows_mounts() -> list[dict]:
    """스트리밍 모드: 계정마다 가상 드라이브(G:, H: …)가 하나씩 생긴다."""
    mounts = []
    for letter in string.ascii_uppercase[3:]:
        root = Path(f"{letter}:/")
        if not _exists(root):
            continue
        label = _volume_label(f"{letter}:\\")
        if not (_exists(root / ".shortcut-targets-by-id") or "google drive" in label.lower()):
            continue
        my_drive = _my_drive(root)
        if my_drive:
            mounts.append({"root": my_drive, "mount": f"{letter}:", "label": label, "mode": "stream", "email": None})
    return mounts


def _mac_mounts() -> list[dict]:
    mounts = []
    cloud = Path.home() / "Library" / "CloudStorage"
    if _is_dir(cloud):
        for acct in sorted(cloud.glob("GoogleDrive-*")):
            my_drive = _my_drive(acct)
            if my_drive:
                email = acct.name[len("GoogleDrive-"):]
                mounts.append({"root": my_drive, "mount": "", "label": acct.name, "mode": "stream", "email": email if _EMAIL.fullmatch(email) else None})
    return mounts


def _mirror_mounts(base: Path | None, accounts: dict[str, str]) -> list[dict]:
    """미러링 모드: '내 드라이브'가 실제 폴더로 존재한다. 동기화 작업 폴더가 있는 것만 인정한다."""
    candidates: list[tuple[Path, str]] = []
    if base is not None and _exists(base / "root_preference_sqlite.db"):
        try:
            con = sqlite3.connect(f"file:{(base / 'root_preference_sqlite.db').as_posix()}?mode=ro", uri=True, timeout=0.5)
            try:
                for path, token in con.execute("select last_seen_absolute_path, account_token from roots where is_my_drive = 1"):
                    if path:
                        candidates.append((Path(str(path)), str(token or "")))
            finally:
                con.close()
        except (sqlite3.Error, ValueError):
            pass
    for name in (*MY_DRIVE_NAMES, "Google Drive", "GoogleDrive"):
        candidates.append((Path.home() / name, ""))
    mounts, seen = [], set()
    for path, token in candidates:
        key = str(path).casefold()
        if key in seen:
            continue
        seen.add(key)
        # 이름만 비슷한 옛 폴더를 구글 드라이브로 안내하면 동기화되지 않는 곳에 위키가 만들어진다
        if _exists(path / ".tmp.driveupload") or _exists(path / ".tmp.drivedownload"):
            mounts.append({"root": path, "mount": "", "label": "", "mode": "mirror", "email": accounts.get(token)})
    return mounts


def detect() -> list[dict]:
    """지금 이 컴퓨터에서 동기화 중인 '내 드라이브' 폴더들.

    [{"root": Path, "email": str | None, "mount": "G:" | "", "mode": "stream" | "mirror"}]
    """
    base = app_data_dir()
    accounts = account_emails(base)
    if sys.platform == "win32":
        mounts = _windows_mounts()
        letters, current = _registry_prefs()
        assign_emails(mounts, accounts, letters, current)
    elif sys.platform == "darwin":
        mounts = _mac_mounts()
    else:
        mounts = []
    known = {str(m["root"]).casefold() for m in mounts}
    mounts += [m for m in _mirror_mounts(base, accounts) if str(m["root"]).casefold() not in known]
    return mounts


def state(mounts: list[dict] | None = None) -> str:
    """'ready' (쓸 수 있는 계정이 있음) | 'not_running' (설치됐지만 연결된 드라이브 없음) | 'not_installed'"""
    mounts = detect() if mounts is None else mounts
    if mounts:
        return "ready"
    return "not_running" if is_installed() else "not_installed"


def account_for(path: str | Path) -> dict | None:
    """이 경로가 어느 계정의 드라이브 안에 있는지. 드라이브 밖이면 None."""
    if not path:
        return None
    try:
        target = Path(path).resolve()
    except OSError:
        target = Path(path)
    for m in detect():
        try:
            target.relative_to(Path(m["root"]).resolve())
            return m
        except (ValueError, OSError):
            continue
    return None
