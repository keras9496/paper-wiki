"""테스트는 실제 설정·자격 증명 저장소·Zotero·구글 드라이브·Claude Code 설정을 건드리지 않는다."""

import atexit
import os
import shutil
import tempfile

# paperwiki 를 import 하기 전에 격리된 설정 폴더를 지정한다 (작업 폴더도 이 안에 만들어진다)
_config_dir = tempfile.mkdtemp(prefix="paperwiki-test-config-")
atexit.register(shutil.rmtree, _config_dir, ignore_errors=True)
os.environ["PAPERWIKI_CONFIG_DIR"] = _config_dir
os.environ["PAPERWIKI_NO_KEYRING"] = "1"
os.environ.pop("ZOTERO_API_KEY", None)
os.environ.pop("ZOTERO_LOCAL_KEY", None)

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def no_real_google_drive(monkeypatch):
    """기본값: 구글 드라이브 데스크톱이 없는 컴퓨터. 필요한 테스트만 상태를 바꾼다."""
    from paperwiki import gdrive

    monkeypatch.setattr(gdrive, "detect", lambda: [])
    monkeypatch.setattr(gdrive, "is_installed", lambda: False)
    monkeypatch.setattr(gdrive, "can_launch", lambda: False)
    monkeypatch.setattr(gdrive, "launch", lambda: False)


@pytest.fixture(autouse=True)
def no_real_zotero_or_claude(monkeypatch, tmp_path):
    """기본값: Zotero 가 꺼져 있고, 스킬은 사용자의 ~/.claude 가 아니라 임시 폴더에 설치된다."""
    from paperwiki import cli, integration

    monkeypatch.setattr(cli, "_zotero", lambda: None)
    monkeypatch.setattr(cli, "_lookup", lambda: None)  # doi.org 에 묻지 않는다
    monkeypatch.setattr(cli, "_search", lambda: None)  # Crossref 에도 묻지 않는다
    monkeypatch.setattr(cli, "_running_url", lambda: "")
    monkeypatch.setattr(integration, "skill_path", lambda: tmp_path / "claude-home" / "skills" / "paper-wiki" / "SKILL.md")
    monkeypatch.setattr(integration, "agent_path", lambda: tmp_path / "claude-home" / "agents" / "paper-wiki-reader.md")
    monkeypatch.setattr(integration, "claude_code_installed", lambda: True)


@pytest.fixture(autouse=True)
def no_real_claude_runs(monkeypatch):
    """기본값: Claude Code 는 설치 · 로그인되어 있지만, 진짜로 실행하지는 않는다 (실행이 필요한 테스트는 가짜를 넣는다)."""
    from paperwiki import runner

    def refuse(*_args, **_kwargs):
        raise AssertionError("테스트에서 진짜 Claude Code 를 실행하려 했습니다")

    monkeypatch.setattr(runner, "auth_status", lambda refresh=False: {"installed": True, "logged_in": True, "email": "", "plan": ""})
    monkeypatch.setattr(runner, "run_claude", refuse)
    monkeypatch.setattr(runner, "open_login", lambda: True)
    monkeypatch.setattr(runner, "_services", lambda: (None, None, None))  # Zotero · doi.org · Crossref 에 묻지 않는다
    runner._jobs.clear()
    runner._loaded = True  # 이 컴퓨터의 jobs.json 을 읽지 않는다
