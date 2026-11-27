"""웹 화면이 뒤에서 Claude Code 를 실행한다.

웹에서 논문을 올리거나 [정리 시작] · [학습하며 정리] · [위키 정리 시작]을 누르면, 이 컴퓨터에 설치되고
로그인된 Claude Code 를 화면 없이(`claude -p`) 실행해 읽기 · 학습 · 정리 에이전트의 일을 맡긴다.
사용량은 사용자의 Claude 요금제에서 쓰이고, 이 프로그램은 로그인 정보를 다루지 않는다 (로그인은 Claude Code 가 한다).

맡길 때의 안전장치:
- `--restricted`: 명령 실행 도구(Bash · PowerShell 등)와 웹 접근이 없고, 사용자의 Claude Code 설정 · 훅을 읽지 않는다.
- `--tools Read,Write`: 쓸 수 있는 도구는 파일 읽기 · 쓰기뿐이다.
- 작업 폴더(이 컴퓨터의 설정 폴더 안)에서 실행한다: 파일 도구는 그 폴더 안으로 묶인다.
  위키 폴더도, 사용자 폴더도 건드리지 못한다.
- 에이전트가 쓴 파일은 프로그램이 형식을 검사한 뒤에만 검토안 · 학습 자료가 된다.
  위키에 들어가는 것은 여전히 사람이 승인한 것뿐이다.

작업(job)은 이 컴퓨터에서만 돈다. 진행 상태는 설정 폴더의 jobs.json 에 남겨, 화면을 새로 고쳐도 보이게 한다.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import config, extract, integration, library
from .store import Vault, now_iso, write_json_atomic

READ_TIMEOUT = 50 * 60  # 논문 한 편 읽기 (길고 그림이 많은 논문도 넉넉히)
STUDY_TIMEOUT = 60 * 60  # 학습 자료 만들기 (번역은 논문 전체를 새로 써내는 일이라 더 걸린다)
DREAM_TIMEOUT = 40 * 60
GRADE_TIMEOUT = 6 * 60
FIX_TIMEOUT = 15 * 60
MAX_CLAUDE = 3  # 동시에 돌리는 Claude Code 수 (학습하며 정리는 한 편에 둘을 쓴다)
KEEP_JOBS = 40

INSTALL_URL = "https://claude.com/claude-code"
AGENT_FILE = "agent.md"  # 에이전트의 기본 규칙 (--append-system-prompt-file 로 넘긴다)

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class RunnerError(Exception):
    """작업을 시작할 수 없다. code: not_installed | login | busy | error"""

    def __init__(self, message: str, code: str = "error"):
        super().__init__(message)
        self.code = code


class JobError(Exception):
    """작업이 실패했다. code: login | limit | error. hint 는 사용자가 할 수 있는 일."""

    def __init__(self, message: str, code: str = "error", hint: str = ""):
        super().__init__(message)
        self.code, self.hint = code, hint


class Canceled(Exception):
    pass


# ── Claude Code 찾기 · 로그인 ─────────────────────────────────────────────


def claude_exe() -> str | None:
    """이 컴퓨터의 Claude Code 실행 파일. PATH 에 없으면 흔한 설치 위치를 본다."""
    found = shutil.which("claude")
    if found:
        return found
    home = Path.home()
    candidates = [home / ".local" / "bin" / "claude", home / ".claude" / "local" / "claude"]
    if sys.platform == "win32":
        local = Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local")
        candidates = [local / "Microsoft" / "WinGet" / "Links" / "claude.exe", home / ".local" / "bin" / "claude.exe", *candidates]
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


_auth_cache: tuple[float, dict] | None = None


def auth_status(refresh: bool = False) -> dict:
    """Claude Code 가 설치되어 있는지, 로그인되어 있는지.

    {"installed": bool, "logged_in": bool | None, "email": str, "plan": str}. logged_in 이 None 이면 확인하지 못한 것이다.
    로그인 정보 자체는 읽지 않는다 — `claude auth status` 가 알려 주는 상태만 본다.
    """
    global _auth_cache
    now = time.monotonic()
    if _auth_cache and not refresh:
        age, data = now - _auth_cache[0], _auth_cache[1]
        if age < (30 if data.get("logged_in") else 4):
            return data
    exe = claude_exe()
    if not exe:
        data = {"installed": False, "logged_in": False, "email": "", "plan": "", "install_url": INSTALL_URL}
    else:
        try:
            r = subprocess.run(
                [exe, "auth", "status", "--json"], capture_output=True, stdin=subprocess.DEVNULL, timeout=25, creationflags=_NO_WINDOW
            )
            info = _json_object(r.stdout.decode("utf-8", errors="replace"))
        except (OSError, subprocess.TimeoutExpired):
            info = None
        if info is None:
            data = {"installed": True, "logged_in": None, "email": "", "plan": ""}
        else:
            data = {"installed": True, "logged_in": bool(info.get("loggedIn")), "email": str(info.get("email") or ""), "plan": str(info.get("subscriptionType") or "")}
    _auth_cache = (now, data)
    return data


def forget_auth() -> None:
    global _auth_cache
    _auth_cache = None


def login_command() -> str:
    exe = claude_exe() or "claude"
    return f'"{exe}" auth login' if " " in exe else f"{exe} auth login"


def open_login() -> bool:
    """로그인 창(터미널)을 연다. 그 창에서 Claude Code 가 브라우저 로그인을 안내한다. 열었으면 True."""
    exe = claude_exe()
    if not exe:
        return False
    forget_auth()
    try:
        if sys.platform == "win32":
            # 새 콘솔 창에서 실행하고, 끝나도 창을 남겨 결과를 읽을 수 있게 한다 (cmd /k)
            subprocess.Popen(f'cmd.exe /k ""{exe}" auth login"', creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
            return True
        if sys.platform == "darwin":
            command = f"'{exe}' auth login".replace("\\", "\\\\").replace('"', '\\"')
            subprocess.Popen(["osascript", "-e", f'tell application "Terminal" to do script "{command}"', "-e", 'tell application "Terminal" to activate'])
            return True
        for term in ("x-terminal-emulator", "xterm", "konsole"):
            if shutil.which(term):
                subprocess.Popen([term, "-e", exe, "auth", "login"], start_new_session=True)
                return True
    except OSError:
        return False
    return False


def check_ready() -> dict:
    """작업을 맡기기 전에: Claude Code 가 설치 · 로그인되어 있는지. 아니면 RunnerError (code 로 무엇이 필요한지 알린다)."""
    status = auth_status()
    if not status["installed"]:
        raise RunnerError("이 컴퓨터에서 Claude Code 를 찾지 못했습니다. 논문을 읽는 일은 Claude Code 가 하므로, 설치하고 로그인한 뒤 다시 시도해 주세요.", "not_installed")
    if status["logged_in"] is False:
        status = auth_status(refresh=True)  # 방금 로그인했을 수 있다
        if status["logged_in"] is False:
            raise RunnerError("Claude Code 에 로그인되어 있지 않습니다. [로그인 창 열기]로 로그인한 뒤 다시 시도해 주세요.", "login")
    return status


# ── Claude Code 실행 ──────────────────────────────────────────────────────


def _json_object(text: str) -> dict | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except ValueError:
        pass
    for line in reversed(text.splitlines()):  # 경고 문구가 앞에 섞여 나온 경우
        line = line.strip()
        if line.startswith("{"):
            try:
                data = json.loads(line)
                return data if isinstance(data, dict) else None
            except ValueError:
                continue
    return None


_LOGIN_WORDS = ("not logged in", "/login", "invalid api key", "authentication", "unauthorized", "401", "oauth token", "log in")
_LIMIT_WORDS = ("usage limit", "rate limit", "limit reached", "limit will reset", "quota", "429", "credit balance")


def classify(text: str) -> str:
    """Claude Code 가 실패했을 때의 이유: login | limit | error"""
    low = (text or "").lower()
    if any(w in low for w in _LOGIN_WORDS):
        return "login"
    if any(w in low for w in _LIMIT_WORDS):
        return "limit"
    return "error"


def run_claude(prompt: str, cwd: Path, system: str, model: str | None, timeout: int, job: dict | None = None) -> dict:
    """Claude Code 를 화면 없이 한 번 실행한다. 반환: {"result": 마지막 답, "cost": 달러(참고용)}

    실패하면 JobError (로그인이 필요함 · 사용 한도 · 그 밖의 오류).
    """
    exe = claude_exe()
    if not exe:
        raise JobError("Claude Code 를 찾지 못했습니다.", "error", "Claude Code 를 설치한 뒤 다시 시도해 주세요.")
    cwd.mkdir(parents=True, exist_ok=True)
    agent = cwd / AGENT_FILE
    agent.write_text(system, encoding="utf-8", newline="\n")
    args = [
        exe, "-p", prompt,
        "--restricted", "--tools", "Read,Write", "--permission-mode", "acceptEdits",
        "--output-format", "json", "--no-session-persistence",
        "--append-system-prompt-file", str(agent),
    ]
    if model and model != "inherit":
        args += ["--model", model]
    with _slots:
        _check_cancel(job)
        try:
            proc = subprocess.Popen(args, cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=_NO_WINDOW)
        except OSError as exc:
            raise JobError(f"Claude Code 를 실행하지 못했습니다: {exc}") from exc
        if job is not None:
            with _lock:
                _procs.setdefault(job["id"], []).append(proc)
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise JobError(f"{timeout // 60}분 안에 끝나지 않아 멈췄습니다.", "error", "[다시 시도]를 누르면 처음부터 다시 읽습니다.") from None
        finally:
            if job is not None:
                with _lock:
                    if proc in _procs.get(job["id"], []):
                        _procs[job["id"]].remove(proc)
    _check_cancel(job)
    stdout, stderr = out.decode("utf-8", errors="replace"), err.decode("utf-8", errors="replace")
    data = _json_object(stdout)
    if data is None or proc.returncode != 0 and data.get("is_error") is not False:
        text = (data or {}).get("result") or stderr.strip() or stdout.strip() or f"종료 코드 {proc.returncode}"
        _raise_for(text)
    if data.get("is_error"):
        _raise_for(str(data.get("result") or data.get("subtype") or "알 수 없는 오류"))
    return {"result": str(data.get("result") or ""), "cost": data.get("total_cost_usd")}


def _raise_for(text: str) -> None:
    kind = classify(text)
    short = re.sub(r"\s+", " ", text).strip()[:300]
    if kind == "login":
        raise JobError("Claude Code 에 로그인되어 있지 않거나 로그인이 만료되었습니다.", "login", "[로그인 창 열기]로 로그인한 뒤 [다시 시도]를 눌러 주세요.")
    if kind == "limit":
        raise JobError(f"Claude 사용 한도에 걸렸습니다: {short}", "limit", "한도가 풀린 뒤 [다시 시도]를 눌러 주세요. 이미 끝난 부분은 다시 하지 않습니다.")
    raise JobError(f"Claude Code 가 오류로 끝났습니다: {short}")


def _check_cancel(job: dict | None) -> None:
    if job is not None and job.get("cancel"):
        raise Canceled()


def accept_json_reply(reply: str, path: Path) -> bool:
    """에이전트가 파일을 쓰지 못해 JSON 을 답으로 돌려준 경우, 그것을 그 파일로 저장한다."""
    if path.exists():
        return False
    text = (reply or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text).strip()
    if not text.startswith("{"):
        return False
    try:
        json.loads(text)
    except ValueError:
        return False
    path.write_text(text, encoding="utf-8", newline="\n")
    return True


def failed_reason(reply: str) -> str | None:
    """에이전트가 'failed: …' 로 답했으면 그 이유."""
    m = re.match(r"\s*failed:\s*(.*)", reply or "", re.IGNORECASE | re.DOTALL)
    return re.sub(r"\s+", " ", m.group(1)).strip()[:400] if m else None


# ── 작업 목록 ─────────────────────────────────────────────────────────────

_lock = threading.RLock()
_slots = threading.BoundedSemaphore(MAX_CLAUDE)
_jobs: dict[str, dict] = {}
_threads: dict[str, threading.Thread] = {}
_procs: dict[str, list] = {}
_vaults: dict[str, Vault] = {}
_loaded = False

ACTIVE = ("queued", "running")
KIND_LABELS = {"paper": "논문 정리", "dream": "위키 정리", "grade": "채점", "translate": "번역 추가"}


def _jobs_path() -> Path:
    return config.config_dir() / "jobs.json"


def _load() -> None:
    """지난번에 프로그램이 꺼질 때 돌고 있던 작업은 '멈춤'으로 바꿔 보여 준다 (다시 시도할 수 있다)."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        items = json.loads(_jobs_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        items = []
    for job in items if isinstance(items, list) else []:
        if not isinstance(job, dict) or not job.get("id"):
            continue
        if job.get("state") in ACTIVE:
            job.update(state="failed", error="Paper Wiki 가 꺼지면서 작업이 멈췄습니다.", hint="[다시 시도]를 누르면 끝난 부분은 건너뛰고 이어서 합니다.", finished=now_iso())
            for part, state in (job.get("parts") or {}).items():
                if state == "running":
                    job["parts"][part] = "failed"
        _jobs[job["id"]] = job


def _persist() -> None:
    with _lock:
        items = sorted(_jobs.values(), key=lambda j: j.get("created", ""), reverse=True)[:KEEP_JOBS]
        keep = {j["id"] for j in items}
        for job_id in [k for k in _jobs if k not in keep]:
            del _jobs[job_id]
        clean = [{k: v for k, v in j.items() if k != "cancel"} for j in items]
    try:
        write_json_atomic(_jobs_path(), clean)
    except OSError:
        pass


def _update(job: dict, **changes) -> None:
    with _lock:
        job.update(changes)
    _persist()


def _set_part(job: dict, part: str, state: str) -> None:
    with _lock:
        job.setdefault("parts", {})[part] = state
    _persist()


def all_jobs() -> list[dict]:
    _load()
    with _lock:
        jobs = sorted(_jobs.values(), key=lambda j: j.get("created", ""), reverse=True)
        return [snapshot(j) for j in jobs]


def get(job_id: str) -> dict | None:
    _load()
    with _lock:
        job = _jobs.get(job_id)
        return snapshot(job) if job else None


def snapshot(job: dict) -> dict:
    out = {k: v for k, v in job.items() if k != "cancel"}
    out["label"] = KIND_LABELS.get(job.get("kind"), "작업")
    if job.get("state") in ACTIVE and job.get("started"):
        try:
            from datetime import datetime

            out["elapsed"] = int((datetime.now().astimezone() - datetime.fromisoformat(job["started"])).total_seconds())
        except ValueError:
            out["elapsed"] = 0
    if job.get("kind") == "paper" and (job.get("parts") or {}).get("tutor") == "running" and job.get("draft"):
        from . import study

        out["sections_ready"] = study.sections_written(library.work_dir(job["draft"]))
    return out


def active_for(draft: str) -> dict | None:
    """그 논문(검토안 id)을 지금 정리하고 있는 작업."""
    _load()
    with _lock:
        for job in _jobs.values():
            if job.get("draft") == draft and job.get("state") in ACTIVE:
                return job
    return None


def _new(kind: str, **fields) -> dict:
    _load()
    job = {"id": "j" + secrets.token_hex(5), "kind": kind, "state": "queued", "step": "기다리는 중", "created": now_iso(), "parts": {}, "error": "", "hint": "", "result": {}, **fields}
    with _lock:
        _jobs[job["id"]] = job
    _persist()
    return job


def _launch(job: dict, vault: Vault) -> dict:
    with _lock:
        _vaults[job["id"]] = vault
        thread = threading.Thread(target=_run, args=(job,), name=f"paperwiki-{job['id']}", daemon=True)
        _threads[job["id"]] = thread
    thread.start()
    return snapshot(job)


def wait(job_id: str, timeout: float = 30) -> dict | None:
    """작업이 끝날 때까지 기다린다 (테스트와 명령줄에서 쓴다)."""
    thread = _threads.get(job_id)
    if thread:
        thread.join(timeout)
    return get(job_id)


def cancel(job_id: str) -> dict | None:
    _load()
    with _lock:
        job = _jobs.get(job_id)
        if not job or job.get("state") not in ACTIVE:
            return snapshot(job) if job else None
        job["cancel"] = True
        procs = list(_procs.get(job_id, []))
    for proc in procs:
        try:
            proc.kill()
        except OSError:
            pass
    return get(job_id)


def retry(job_id: str, vault: Vault) -> dict:
    """실패한 작업을 다시 돌린다. 끝난 부분(읽기 · 학습 자료)은 건너뛴다."""
    _load()
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            raise RunnerError("작업을 찾을 수 없습니다.")
        if job.get("state") in ACTIVE:
            return snapshot(job)
    check_ready()
    with _lock:
        job.update(state="queued", step="기다리는 중", error="", hint="", finished=None, created=now_iso())
        job.pop("cancel", None)
        for part, state in list((job.get("parts") or {}).items()):
            if state != "done":
                job["parts"][part] = "waiting"
    _persist()
    return _launch(job, vault)


def clear_finished() -> int:
    _load()
    with _lock:
        gone = [k for k, j in _jobs.items() if j.get("state") not in ACTIVE]
        for k in gone:
            del _jobs[k]
    _persist()
    return len(gone)


# ── 작업 시작 ─────────────────────────────────────────────────────────────


def start_paper(vault: Vault, source: str, mode: str = "read", lang: str = "ko", again: bool = False) -> dict:
    """논문 한 편을 정리한다: 읽을 준비 → (읽기 에이전트 [+ 학습 에이전트]) → 검토안 [+ 학습 자료].

    mode: read(바로 정리) | study(학습하며 정리). lang: en(영어 원문) | ko(한국어 번역) | both(나란히).
    """
    from . import study

    if mode not in ("read", "study"):
        raise RunnerError("정리 방식은 read 또는 study 입니다.")
    if lang not in study.LANGS:
        raise RunnerError("읽기 언어는 en · ko · both 가운데 하나입니다.")
    check_ready()
    info = library.prepare(vault, source, again=again)  # 이미 등록된 논문이면 여기서 알려 준다 (LibraryError)
    running = active_for(info["id"])
    if running:
        raise RunnerError("이 논문은 이미 정리하고 있습니다. 끝날 때까지 기다려 주세요.", "busy")
    parts = {"reader": "waiting"}
    if mode == "study":
        parts["tutor"] = "waiting"
    title = Path(info["pdf"]).name
    job = _new("paper", mode=mode, lang=lang, draft=info["id"], pdf=info["pdf"], title=title, pages=info.get("pages"), parts=parts)
    return _launch(job, vault)


def start_dream(vault: Vault) -> dict:
    from . import dream

    check_ready()
    with _lock:
        if any(j.get("kind") == "dream" and j.get("state") in ACTIVE for j in _jobs.values()):
            raise RunnerError("위키 정리가 이미 돌고 있습니다.", "busy")
    info = dream.prepare(vault)  # 주장이 부족하면 여기서 알려 준다 (WikiError)
    job = _new("dream", run=info["id"], title=f"주장 묶음 {info['groups']}개", parts={"dreamer": "waiting"})
    return _launch(job, vault)


def start_grade(vault: Vault, study_id: str, section: int) -> dict:
    from . import study

    check_ready()
    info = study.prepare_grading(vault, study_id, section)  # 답이 없으면 여기서 알려 준다
    job = _new("grade", study=study_id, section=section, work=info["work"], title=info["title"], parts={"grader": "waiting"})
    return _launch(job, vault)


def start_translate(vault: Vault, study_id: str) -> dict:
    from . import study

    check_ready()
    data = study.load(vault, study_id)
    if not data:
        raise RunnerError("학습 자료를 찾을 수 없습니다.")
    with _lock:
        if any(j.get("study") == study_id and j.get("kind") == "translate" and j.get("state") in ACTIVE for j in _jobs.values()):
            raise RunnerError("이 논문의 번역을 이미 만들고 있습니다.", "busy")
    job = _new("translate", study=study_id, draft=study_id, title=data.get("title") or study_id, parts={"translator": "waiting"})
    return _launch(job, vault)


# ── 작업 실행 ─────────────────────────────────────────────────────────────


def _run(job: dict) -> None:
    vault = _vaults.get(job["id"])
    _update(job, state="running", started=now_iso(), step="시작하는 중")
    try:
        if vault is None:
            raise JobError("위키 폴더를 찾을 수 없습니다.")
        {"paper": _run_paper, "dream": _run_dream, "grade": _run_grade, "translate": _run_translate}[job["kind"]](job, vault)
    except Canceled:
        _update(job, state="canceled", step="취소됨", finished=now_iso())
    except JobError as exc:
        state = {"login": "login", "limit": "limit"}.get(exc.code, "failed")
        _update(job, state=state, error=str(exc), hint=exc.hint, finished=now_iso())
    except Exception as exc:  # 사용자에게 보여 줄 수 있는 오류(위키를 읽을 수 없음 등)도 여기로 온다
        _update(job, state="failed", error=f"{exc.__class__.__name__}: {exc}" if not str(exc) else str(exc), hint="[다시 시도]를 눌러 주세요. 계속 실패하면 Claude Code 에 \"논문 폴더의 새 논문 정리해줘\" 라고 하면 대화에서 이어서 합니다.", finished=now_iso())
    else:
        _update(job, state="done", step="끝남", finished=now_iso())
    finally:
        for part, state in list((job.get("parts") or {}).items()):
            if state == "running":
                _set_part(job, part, "failed")


def _services():
    """검토안을 만들 때 쓰는 바깥 연결: (Zotero 또는 None, DOI 등록 기록 찾기, 참고문헌 DOI 찾기)"""
    from . import biblio
    from .zotero import Zotero, ZoteroError

    try:
        z = Zotero(config.load())
    except ZoteroError:
        z = None
    return z, biblio.lookup, biblio.find_doi


def _reader(job: dict, vault: Vault, work: Path) -> None:
    _set_part(job, "reader", "running")
    brief = work / extract.BRIEF_FILE
    if not brief.is_file():
        raise JobError("읽기 준비 파일이 없습니다.", hint="[다시 시도] 대신 논문 폴더에서 다시 정리를 시작해 주세요.")
    reply = run_claude(f"Read the brief at {brief.as_posix()} and follow it exactly.", work, integration.reader_rules(), integration.reader_model(), READ_TIMEOUT, job)["result"]
    accept_json_reply(reply, work / extract.PROPOSAL_FILE)
    reason = failed_reason(reply)
    if reason:
        raise JobError(f"읽기 에이전트가 논문을 읽지 못했습니다: {reason}", hint="PDF 가 암호화되었거나 스캔본일 수 있습니다. 다른 PDF 로 다시 시도해 주세요.")
    if not (work / extract.PROPOSAL_FILE).is_file():
        short = re.sub(r"\s+", " ", reply).strip()[:300]
        raise JobError("읽기 에이전트가 제안 파일을 쓰지 않고 끝났습니다." + (f" 에이전트의 답: {short}" if short else ""), hint="[다시 시도]를 눌러 주세요.")
    _set_part(job, "reader", "done")


def _propose(job: dict, vault: Vault, work: Path) -> dict:
    from . import wiki

    _update(job, step="서지 정보 · 참고문헌 DOI 확인")
    for attempt in (1, 2):
        z, lookup, search = _services()
        try:
            info = wiki.propose(vault, job["draft"], zotero=z, lookup=lookup, search=search)
            break
        except extract.ProposalError as exc:
            if attempt == 2:
                raise JobError("제안 파일의 형식이 맞지 않습니다: " + "; ".join(exc.problems[:6]), hint="Claude Code 에 \"논문 폴더의 새 논문 정리해줘\" 라고 하면 대화에서 고쳐 이어서 합니다.") from None
            _update(job, step="제안 파일의 형식을 고치는 중")
            problems = "\n".join(f"- {p}" for p in exc.problems[:40])
            run_claude(
                f"The proposal files you wrote in {work.as_posix()} did not pass the format check:\n{problems}\n\n"
                f"Read the brief at {(work / extract.BRIEF_FILE).as_posix()} again for the required shape, fix only these problems "
                "in the existing files (do not re-read the paper unless a fix needs it), and reply `written`.",
                work, integration.reader_rules(), integration.reader_model(), FIX_TIMEOUT, job,
            )
        finally:
            if z is not None:
                z.close()
    for _ in range(3):  # 참고문헌 DOI 찾기가 시간 한도에 걸렸으면 이어서 찾는다
        draft = vault.pending(job["draft"]) or {}
        if not (draft.get("extraction") or {}).get("ref_search_failed"):
            break
        z, lookup, search = _services()
        try:
            info = wiki.propose(vault, job["draft"], zotero=z, lookup=lookup, search=search)
        finally:
            if z is not None:
                z.close()
    return info


def _tutor(job: dict, vault: Vault, work: Path, lang: str) -> None:
    from . import study

    _set_part(job, "tutor", "running")
    brief = study.write_brief(vault, work, lang)
    reply = run_claude(f"Read the brief at {brief.as_posix()} and follow it exactly.", work, study.TUTOR_SYSTEM, integration.reader_model(), STUDY_TIMEOUT, job)["result"]
    reason = failed_reason(reply)
    if reason:
        raise JobError(f"학습 자료를 만들지 못했습니다: {reason}")
    sections, problems = study.read_sections(work, need_translation=lang != "en")
    if problems:
        listing = "\n".join(f"- {p}" for p in problems[:40])
        run_claude(
            f"The study files you wrote in {work.as_posix()} did not pass the format check:\n{listing}\n\n"
            f"Read the brief at {brief.as_posix()} again for the required shape, fix only these problems in the files, and reply `written`.",
            work, study.TUTOR_SYSTEM, integration.reader_model(), FIX_TIMEOUT, job,
        )
        sections, problems = study.read_sections(work, need_translation=lang != "en")
    if not sections:
        raise JobError("학습 자료가 만들어지지 않았습니다." + (f" ({problems[0]})" if problems else ""), hint="[다시 시도]를 눌러 주세요.")
    study.save(vault, job["draft"], sections, lang=lang, title=job.get("title", ""), pdf=job.get("pdf", ""), problems=problems)
    _set_part(job, "tutor", "done")


def _run_paper(job: dict, vault: Vault) -> None:
    work = library.work_dir(job["draft"])
    parts = job.get("parts") or {}
    todo = [p for p in ("reader", "tutor") if p in parts and parts[p] != "done"]
    if job.get("mode") == "study":
        _update(job, step="Claude Code 가 논문을 읽고 학습 자료를 만드는 중")
    else:
        _update(job, step="Claude Code 가 논문을 읽는 중")
    errors: list[JobError] = []

    def guarded(fn, *args):
        try:
            fn(*args)
        except JobError as exc:
            errors.append(exc)
        except Canceled:
            errors.append(JobError("취소했습니다.", "canceled"))
        except Exception as exc:  # noqa: BLE001 — 한쪽이 실패해도 다른 쪽은 끝까지 하게 한다
            errors.append(JobError(f"{exc.__class__.__name__}: {exc}"))

    threads = []
    if "reader" in todo:
        threads.append(threading.Thread(target=guarded, args=(_reader, job, vault, work), daemon=True))
    if "tutor" in todo:
        threads.append(threading.Thread(target=guarded, args=(_tutor, job, vault, work, job.get("lang", "ko")), daemon=True))
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    for part in todo:
        if (job.get("parts") or {}).get(part) == "running":
            _set_part(job, part, "failed")
    if any(e.code == "canceled" for e in errors):
        raise Canceled()
    result = dict(job.get("result") or {})
    if (job.get("parts") or {}).get("reader") == "done" and not result.get("review"):
        info = _propose(job, vault, work)
        result.update(review=f"/review/{job['draft']}", claims=info["counts"]["claims"], citekey=info["citekey"], title=info["paper"]["title"])
        _update(job, result=result, title=info["paper"]["title"] or job.get("title"))
    if (job.get("parts") or {}).get("tutor") == "done":
        result["study"] = f"/study/{job['draft']}"
        _update(job, result=result)
    if errors:
        first = next((e for e in errors if e.code in ("login", "limit")), errors[0])
        done = [p for p in todo if (job.get("parts") or {}).get(p) == "done"]
        note = " 끝난 부분은 남아 있습니다: " + ", ".join({"reader": "인용 정리", "tutor": "학습 자료"}[p] for p in done) + "." if done else ""
        raise JobError(str(first) + note, first.code, first.hint)


def _run_dream(job: dict, vault: Vault) -> None:
    from . import dream

    work = library.work_dir(job["run"])
    brief = work / dream.BRIEF_FILE
    _set_part(job, "dreamer", "running")
    _update(job, step="Claude Code 가 위키의 주장을 살펴보는 중")
    reply = run_claude(f"Read the brief at {brief.as_posix()} and follow it exactly.", work, integration.dreamer_rules(), dream.dream_model(), DREAM_TIMEOUT, job)["result"]
    accept_json_reply(reply, work / dream.PROPOSAL_FILE)
    reason = failed_reason(reply)
    if reason:
        raise JobError(f"정리 에이전트가 끝내지 못했습니다: {reason}")
    if not (work / dream.PROPOSAL_FILE).is_file():
        raise JobError("정리 에이전트가 제안 파일을 쓰지 않고 끝났습니다.", hint="[다시 시도]를 눌러 주세요.")
    _update(job, step="제안 확인")
    for attempt in (1, 2):
        try:
            dream.propose(vault, job["run"])
            break
        except extract.ProposalError as exc:
            if attempt == 2:
                raise JobError("제안 파일의 형식이 맞지 않습니다: " + "; ".join(exc.problems[:6])) from None
            problems = "\n".join(f"- {p}" for p in exc.problems[:40])
            run_claude(
                f"The file you wrote in {work.as_posix()} did not pass the format check:\n{problems}\n\nRead the brief at {brief.as_posix()} "
                "again for the required shape, fix only these problems, and reply `written`.",
                work, integration.dreamer_rules(), dream.dream_model(), FIX_TIMEOUT, job,
            )
    _set_part(job, "dreamer", "done")
    _update(job, result={"dream": "/dream"})


def _run_grade(job: dict, vault: Vault) -> None:
    from . import study

    work = Path(job["work"])
    _set_part(job, "grader", "running")
    _update(job, step="Claude 가 답을 읽고 있습니다")
    reply = run_claude(f"Read the brief at {(work / study.GRADE_BRIEF).as_posix()} and follow it exactly.", work, study.GRADER_SYSTEM, "sonnet", GRADE_TIMEOUT, job)["result"]
    accept_json_reply(reply, work / study.GRADE_FILE)
    saved = study.save_grading(vault, job["study"], job["section"], work)
    _set_part(job, "grader", "done")
    _update(job, result={"study": f"/study/{job['study']}", "graded": saved})


def _run_translate(job: dict, vault: Vault) -> None:
    from . import study

    work = library.work_dir(job["study"])
    _set_part(job, "translator", "running")
    _update(job, step="Claude Code 가 한국어 번역을 만드는 중")
    brief = study.write_translation_brief(vault, job["study"], work)
    reply = run_claude(f"Read the brief at {brief.as_posix()} and follow it exactly.", work, study.TUTOR_SYSTEM, integration.reader_model(), STUDY_TIMEOUT, job)["result"]
    reason = failed_reason(reply)
    if reason:
        raise JobError(f"번역을 만들지 못했습니다: {reason}")
    added = study.merge_translation(vault, job["study"], work)
    if not added:
        raise JobError("번역 파일이 만들어지지 않았습니다.", hint="[다시 시도]를 눌러 주세요.")
    _set_part(job, "translator", "done")
    _update(job, result={"study": f"/study/{job['study']}", "sections": added})
