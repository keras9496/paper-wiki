"""웹 화면이 작업 공간이 된 흐름: 끌어다 놓아 올리기 → 뒤에서 Claude Code 로 정리 → 검토 · 학습 → 등록.

진짜 Claude Code 는 실행하지 않는다. runner.run_claude 자리에 '에이전트가 할 일을 대신 하는' 가짜를 넣는다.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from paperwiki import cli, dream, extract, integration, library, runner, study, wiki
from test_flow import PROPOSAL, client, make_pdf, open_vault, two_papers  # noqa: F401 — client 는 fixture

REAL_RUN_CLAUDE = runner.run_claude  # conftest 가 막아 두기 전의 진짜 (명령 조립을 확인할 때만 쓴다)


def pdf_bytes(tmp_path: Path, width: int = 300, pages: int = 3) -> bytes:
    return make_pdf(tmp_path / f"upload-{width}-{pages}.pdf", pages=pages, width=width).read_bytes()


def upload(client, data: bytes, name: str = "논문 final (2).pdf"):
    return client.post(f"/api/upload?name={name}", content=data, headers={"Content-Type": "application/pdf"})


# 학습 에이전트가 쓰는 파트 파일 (논문 3쪽: 1쪽 Introduction, 2쪽 Methods, 3쪽 Discussion)
SECTIONS = [
    {"title": "1. Introduction", "title_ko": "1. 서론", "pages": [1, 1], "terms": [{"term": "MCI", "note": "경도인지장애"}],
     "quiz": [{"q": "이 연구가 다루는 집단은?", "kind": "recall", "answer": "경도인지장애(MCI) 환자", "explain": "첫 문단"},
              {"q": "왜 전산화 인지훈련을 보았나?", "kind": "why", "answer": "작업기억을 높일 수 있다는 선행 결과 때문", "explain": "둘째 문단"}],
     "paragraphs": [{"page": 1, "starts": "Mild cognitive impairment is", "ko": "경도인지장애는 …"}]},
    {"title": "2. Methods", "title_ko": "2. 방법", "pages": [2, 2], "terms": [],
     "quiz": [{"q": "반복 측정 자료를 어떻게 분석했나?", "kind": "recall", "answer": "lme4 의 선형 혼합효과모형", "explain": "분석 문단"}],
     "paragraphs": [{"page": 2, "starts": "We fitted linear", "ko": "우리는 선형 혼합효과모형을 …"}]},
    {"title": "3. Discussion", "title_ko": "3. 논의", "pages": [3, 3], "terms": [],
     "quiz": [{"q": "추적 기간이 짧으면 무엇이 불분명한가?", "kind": "apply", "answer": "장기 효과", "explain": "한계 문단"}],
     "paragraphs": [{"page": 3, "starts": "Follow-up was short", "ko": "추적 기간이 짧아 …"}]},
]


class FakeClaude:
    """에이전트 대역: 받은 작업 지시(시스템 규칙)로 어떤 에이전트인지 보고, 그 에이전트가 쓸 파일을 쓴다."""

    def __init__(self, proposal=PROPOSAL, sections=SECTIONS, fail=None, translate=True):
        self.proposal, self.sections, self.fail, self.translate = proposal, sections, fail, translate
        self.calls = []

    def __call__(self, prompt, cwd, system, model, timeout, job=None):
        self.calls.append({"prompt": prompt, "cwd": Path(cwd), "system": system, "model": model})
        if self.fail:
            error, self.fail = self.fail, None  # 한 번만 실패한다
            raise error
        cwd = Path(cwd)
        if system == study.TUTOR_SYSTEM and (cwd / study.TRANSLATE_BRIEF).exists() and "translation brief" in prompt + (cwd / study.TRANSLATE_BRIEF).read_text(encoding="utf-8"):
            for i, sec in enumerate(self.sections, 1):
                (cwd / f"ko_{i:02d}.json").write_text(json.dumps({"paragraphs": sec["paragraphs"]}, ensure_ascii=False), encoding="utf-8")
            return {"result": "written", "cost": 0}
        if system == study.TUTOR_SYSTEM:
            for i, sec in enumerate(self.sections, 1):
                body = sec if self.translate else {k: v for k, v in sec.items() if k != "paragraphs"}
                (cwd / f"section_{i:02d}.json").write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
            return {"result": f"written {len(self.sections)}", "cost": 0}
        if system == study.GRADER_SYSTEM:
            (cwd / study.GRADE_FILE).write_text(json.dumps({"results": [{"n": 1, "verdict": "correct", "feedback": "핵심을 짚었습니다."}, {"n": 2, "verdict": "partial", "feedback": "이유가 빠졌습니다."}]}, ensure_ascii=False), encoding="utf-8")
            return {"result": "written", "cost": 0}
        if system == integration.dreamer_rules():
            return {"result": json.dumps({"merges": [], "considered": [], "note": ""}), "cost": 0}  # 파일 대신 답으로 돌려준 경우
        (cwd / extract.PROPOSAL_FILE).write_text(json.dumps(self.proposal, ensure_ascii=False), encoding="utf-8")
        return {"result": "written 3 4", "cost": 0}


@pytest.fixture()
def fake(monkeypatch):
    claude = FakeClaude()
    monkeypatch.setattr(runner, "run_claude", claude)
    return claude


def start(client, pdf: str, mode: str = "read", lang: str = "ko") -> dict:
    r = client.post("/api/jobs", json={"kind": "paper", "pdf": pdf, "mode": mode, "lang": lang})
    assert r.status_code == 200, r.text
    return runner.wait(r.json()["id"], timeout=60)


# ── 올리기 ────────────────────────────────────────────────────────────────


def test_dropped_pdf_is_saved_into_the_paper_folder_once(client, tmp_path):
    vault = open_vault(client)
    data = pdf_bytes(tmp_path)
    r = upload(client, data)
    assert r.status_code == 200, r.text
    first = r.json()
    assert first["path"].startswith("pdf/") and first["existed"] is False and not first["registered"] and not first["pending"]
    assert (vault.root / first["path"]).read_bytes() == data
    assert [f["path"] for f in client.get("/api/inbox").json()["new"]] == [first["path"]]

    again = upload(client, data, "다른 이름.pdf").json()  # 같은 PDF 를 또 넣으면 한 개만 남는다
    assert again["existed"] is True and again["path"] == first["path"]
    assert len(list(vault.pdf_dir.glob("*.pdf"))) == 1

    assert upload(client, b"not a pdf at all").status_code == 400
    assert upload(client, data, "../../밖으로.pdf").json()["path"] == first["path"]  # 이름에 경로가 섞여도 논문 폴더 안에만
    bad = client.post("/api/upload?name=x.pdf", content=data, headers={"Content-Type": "application/pdf", "Origin": "http://evil.example"})
    assert bad.status_code == 403  # 다른 웹사이트가 브라우저를 통해 올리지 못한다


def test_dropping_a_registered_paper_says_so(client, tmp_path, fake):
    vault = open_vault(client)
    data = pdf_bytes(tmp_path)
    path = upload(client, data).json()["path"]
    job = start(client, path)
    wiki.approve(vault, job["draft"])
    again = upload(client, data, "또 넣음.pdf").json()
    assert again["registered"] and again["registered"]["id"] == "kim2023computerized"


# ── 뒤에서 Claude Code 로 정리 ────────────────────────────────────────────


def test_upload_then_claude_code_reads_it_and_a_review_draft_appears(client, tmp_path, fake):
    vault = open_vault(client)
    path = upload(client, pdf_bytes(tmp_path)).json()["path"]
    job = start(client, path)
    assert job["state"] == "done", job
    assert job["result"]["review"] == f"/review/{job['draft']}" and job["result"]["claims"] == 3
    assert vault.pending(job["draft"])["paper"]["title"] == PROPOSAL["paper"]["title"]
    assert not vault.papers()  # 검토 전에는 위키에 아무것도 들어가지 않는다
    call = fake.calls[0]
    assert call["cwd"] == library.work_dir(job["draft"]) and f"Read the brief at {(call['cwd'] / extract.BRIEF_FILE).as_posix()}" in call["prompt"]
    assert call["system"] == integration.reader_rules() and call["model"] == "sonnet"
    page = client.get("/inbox").text
    assert "검토하기" in page and "dropzone" in page
    assert client.get("/api/jobs").json()["jobs"][0]["state"] == "done"


def test_job_refuses_to_start_without_login_and_explains(client, tmp_path, monkeypatch):
    vault = open_vault(client)
    path = upload(client, pdf_bytes(tmp_path)).json()["path"]
    monkeypatch.setattr(runner, "auth_status", lambda refresh=False: {"installed": True, "logged_in": False, "email": "", "plan": ""})
    r = client.post("/api/jobs", json={"kind": "paper", "pdf": path, "mode": "read"})
    assert r.status_code == 409 and r.json()["code"] == "login" and "로그인" in r.json()["error"]
    assert [f["path"] for f in client.get("/api/inbox").json()["new"]] == [path]  # PDF 는 논문 폴더에 남아 나중에 시작할 수 있다
    assert client.get("/api/claude").json()["logged_in"] is False
    assert client.post("/api/claude/login").json()["ok"] is True

    monkeypatch.setattr(runner, "auth_status", lambda refresh=False: {"installed": False, "logged_in": False, "email": "", "plan": "", "install_url": runner.INSTALL_URL})
    r = client.post("/api/jobs", json={"kind": "paper", "pdf": path, "mode": "read"})
    assert r.status_code == 409 and r.json()["code"] == "not_installed"
    assert not vault.pending_all()


def test_only_pdfs_inside_the_paper_folder_can_be_started(client, tmp_path, fake):
    vault = open_vault(client)
    outside = make_pdf(tmp_path / "outside.pdf")
    for bad in (str(outside), "../outside.pdf", "pdf/없음.pdf", ".paperwiki/vault.json", "https://example.org/x.pdf"):
        assert client.post("/api/jobs", json={"kind": "paper", "pdf": bad}).status_code == 400, bad
    assert not fake.calls


def test_login_expiring_mid_run_stops_the_job_and_retry_carries_on(client, tmp_path, fake):
    open_vault(client)
    path = upload(client, pdf_bytes(tmp_path)).json()["path"]
    fake.fail = runner.JobError("로그인이 만료되었습니다.", "login", "[로그인 창 열기]로 로그인한 뒤 [다시 시도]")
    job = start(client, path)
    assert job["state"] == "login" and job["parts"]["reader"] == "failed" and "로그인" in job["hint"]
    r = client.post(f"/api/jobs/{job['id']}/retry")
    assert r.status_code == 200
    job = runner.wait(job["id"], timeout=60)
    assert job["state"] == "done" and job["result"]["review"]


def test_a_malformed_proposal_is_sent_back_once_to_be_fixed(client, tmp_path, monkeypatch):
    vault = open_vault(client)
    path = upload(client, pdf_bytes(tmp_path)).json()["path"]
    broken = {**PROPOSAL, "claims": [{**PROPOSAL["claims"][0], "refs": ["99"]}]}
    calls = []

    def claude(prompt, cwd, system, model, timeout, job=None):
        calls.append(prompt)
        body = broken if len(calls) == 1 else PROPOSAL  # 두 번째는 '형식을 고쳐 달라'는 부탁
        (Path(cwd) / extract.PROPOSAL_FILE).write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        return {"result": "written", "cost": 0}

    monkeypatch.setattr(runner, "run_claude", claude)
    job = start(client, path)
    assert job["state"] == "done" and len(calls) == 2 and "did not pass the format check" in calls[1] and "99" in calls[1]
    assert len(vault.pending(job["draft"])["claims"]) == 3


def test_reader_failure_reply_is_reported(client, tmp_path, monkeypatch):
    open_vault(client)
    path = upload(client, pdf_bytes(tmp_path)).json()["path"]
    monkeypatch.setattr(runner, "run_claude", lambda *a, **k: {"result": "failed: the PDF is a scanned image without text", "cost": 0})
    job = start(client, path)
    assert job["state"] == "failed" and "scanned image" in job["error"]


def test_jobs_left_running_when_the_program_stopped_can_be_retried(client, tmp_path, monkeypatch):
    path = runner._jobs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([{"id": "jabc1234567", "kind": "paper", "state": "running", "created": "2026-11-27T10:00:00+09:00", "parts": {"reader": "running"}, "title": "x.pdf"}]), encoding="utf-8")
    runner._jobs.clear()
    monkeypatch.setattr(runner, "_loaded", False)
    job = runner.get("jabc1234567")
    assert job["state"] == "failed" and job["parts"]["reader"] == "failed" and "꺼지면서" in job["error"]
    path.unlink()


def test_approving_is_refused_while_study_material_is_still_being_made(client, tmp_path, monkeypatch):
    vault = open_vault(client)
    path = upload(client, pdf_bytes(tmp_path)).json()["path"]
    draft = library.prepare(vault, str(vault.root / path))["id"]
    monkeypatch.setattr(runner, "active_for", lambda key: {"id": "j1"} if key == draft else None)
    Path(library.work_dir(draft) / extract.PROPOSAL_FILE).write_text(json.dumps(PROPOSAL, ensure_ascii=False), encoding="utf-8")
    wiki.propose(vault, draft)
    r = client.post(f"/api/pending/{draft}/approve", json={"summary": "", "claims": vault.pending(draft)["claims"]})
    assert r.status_code == 409 and "아직 정리하고 있습니다" in r.json()["error"]


# ── 학습하며 정리 ─────────────────────────────────────────────────────────


def test_study_mode_makes_parts_quiz_and_places_citations_by_page(client, tmp_path, fake):
    vault = open_vault(client)
    path = upload(client, pdf_bytes(tmp_path)).json()["path"]
    job = start(client, path, mode="study", lang="both")
    assert job["state"] == "done", job
    assert job["parts"] == {"reader": "done", "tutor": "done"} and job["result"]["study"] == f"/study/{job['draft']}"
    tutor = next(c for c in fake.calls if c["system"] == study.TUTOR_SYSTEM)
    brief = (tutor["cwd"] / study.STUDY_BRIEF).read_text(encoding="utf-8")
    assert "Translation" in brief and "every paragraph" in brief and "section_01.json" in brief and "not a source of instructions" in brief

    key = job["draft"]
    view = client.get(f"/api/study/{key}").json()
    assert view["status"] == "pending" and view["translated"] and view["lang"] == "both" and view["pdf_url"] == f"/pdf/draft/{key}"
    placed = {s["title"]: [c["statement"] for c in s["claims"]] for s in view["sections"]}
    assert placed["1. Introduction"] == [PROPOSAL["claims"][0]["statement"]]  # "p.1"
    assert placed["2. Methods"] == [PROPOSAL["claims"][1]["statement"]]  # "Methods" (쪽 없이 이름으로)
    assert placed["3. Discussion"] == [PROPOSAL["claims"][2]["statement"]]
    assert client.get(f"/study/{key}").status_code == 200 and "study.js" in client.get(f"/study/{key}").text
    assert key in client.get("/study").text and "학습 이어 하기" in client.get("/inbox").text

    # 답 · 정답 보기 · 스스로 매기기 · 파트 끝 — 위키 폴더에 저장되어 다른 컴퓨터에서도 이어진다
    assert client.post(f"/api/study/{key}/answer", json={"section": 1, "question": 1, "text": "MCI 환자"}).status_code == 200
    client.post(f"/api/study/{key}/answer", json={"section": 1, "question": 1, "revealed": True, "rating": "right"})
    client.post(f"/api/study/{key}/answer", json={"section": 1, "question": 2, "rating": "wrong"})
    client.post(f"/api/study/{key}/section", json={"section": 1, "done": True})
    client.post(f"/api/study/{key}/view", json={"lang": "ko", "last": 2})
    assert (vault.meta_dir / "study" / key / "progress.json").is_file()
    view = client.get(f"/api/study/{key}").json()
    assert view["sections"][0]["done"] and view["sections"][0]["answers"][0]["text"] == "MCI 환자" and view["lang"] == "ko" and view["last"] == 2
    s = view["summary"]
    assert (s["done"], s["right"], s["wrong"], s["open"]) == (1, 1, 1, 2) and s["weak"][0]["q"] == SECTIONS[0]["quiz"][1]["q"]
    assert client.post(f"/api/study/{key}/answer", json={"section": 9, "question": 1, "text": "x"}).status_code == 400

    # 학습 화면에서 인용 문장 하나를 빼고 등록한다
    assert client.post(f"/api/study/{key}/claim", json={"index": 2, "include": False}).status_code == 200
    r = client.post(f"/api/study/{key}/approve")
    assert r.status_code == 200, r.text
    paper = vault.paper(r.json()["paper_id"])
    assert len(paper["claims"]) == 2 and not vault.pending(key)
    view = client.get(f"/api/study/{key}").json()  # 등록한 뒤에도 복습할 수 있다
    assert view["status"] == "registered" and view["paper_id"] == paper["id"] and view["pdf_url"] == f"/pdf/{paper['id']}"
    assert view["sections"][0]["answers"][0]["text"] == "MCI 환자"
    assert f"/study/{key}" in client.get(f"/wiki/p/{paper['id']}").text


def test_claude_grades_answers_and_the_grade_counts_over_self_rating(client, tmp_path, fake):
    open_vault(client)
    path = upload(client, pdf_bytes(tmp_path)).json()["path"]
    key = start(client, path, mode="study", lang="en")["draft"]
    assert client.post(f"/api/study/{key}/grade", json={"section": 1}).status_code == 400  # 답이 없으면 채점할 것이 없다
    client.post(f"/api/study/{key}/answer", json={"section": 1, "question": 1, "text": "MCI", "rating": "wrong"})
    client.post(f"/api/study/{key}/answer", json={"section": 1, "question": 2, "text": "효과가 있어서"})
    r = client.post(f"/api/study/{key}/grade", json={"section": 1})
    assert r.status_code == 200, r.text
    job = runner.wait(r.json()["id"], timeout=30)
    assert job["state"] == "done" and job["result"]["graded"] == 2
    grader = next(c for c in fake.calls if c["system"] == study.GRADER_SYSTEM)
    data = json.loads((grader["cwd"] / study.GRADE_INPUT).read_text(encoding="utf-8"))
    assert [i["response"] for i in data["items"]] == ["MCI", "효과가 있어서"] and grader["model"] == "sonnet"
    view = client.get(f"/api/study/{key}").json()
    answers = view["sections"][0]["answers"]
    assert answers[0]["claude"]["verdict"] == "correct" and answers[1]["claude"]["feedback"] == "이유가 빠졌습니다."
    assert (view["summary"]["right"], view["summary"]["unsure"], view["summary"]["wrong"]) == (1, 1, 0)  # Claude 의 채점이 스스로 매긴 '틀림'보다 앞선다
    client.post(f"/api/study/{key}/answer", json={"section": 1, "question": 1, "text": "고친 답"})
    view = client.get(f"/api/study/{key}").json()
    assert view["sections"][0]["answers"][0]["claude"]["stale"] is True and view["summary"]["wrong"] == 1  # 답을 고치면 예전 채점은 쓰지 않는다


def test_english_only_study_can_get_a_translation_later(client, tmp_path, monkeypatch):
    vault = open_vault(client)
    claude = FakeClaude(translate=False)
    monkeypatch.setattr(runner, "run_claude", claude)
    path = upload(client, pdf_bytes(tmp_path)).json()["path"]
    key = start(client, path, mode="study", lang="en")["draft"]
    brief = (library.work_dir(key) / study.STUDY_BRIEF).read_text(encoding="utf-8")
    assert "Translation" not in brief and '"paragraphs"' not in brief  # 영어 원문만 고르면 번역을 만들지 않는다
    view = client.get(f"/api/study/{key}").json()
    assert not view["translated"] and view["lang"] == "en"
    wiki.approve(vault, key)  # 등록하면 작업 폴더가 지워진다 — 번역은 위키 폴더의 PDF 로 다시 읽기 파일을 만든다
    assert not library.work_dir(key).exists()
    r = client.post(f"/api/study/{key}/translate")
    assert r.status_code == 200, r.text
    job = runner.wait(r.json()["id"], timeout=30)
    assert job["state"] == "done" and job["result"]["sections"] == 3
    view = client.get(f"/api/study/{key}").json()
    assert view["translated"] and view["lang"] == "both" and view["sections"][1]["paragraphs"][0]["ko"].startswith("우리는")


def test_study_files_are_checked(tmp_path):
    work = tmp_path / "w"
    work.mkdir()
    assert study.read_sections(work, need_translation=False) == ([], ["파트 파일(section_01.json …)이 하나도 없습니다."])
    (work / "section_01.json").write_text(json.dumps(SECTIONS[0], ensure_ascii=False), encoding="utf-8")
    (work / "section_02.json").write_text(json.dumps({"title": "", "pages": "x", "quiz": []}), encoding="utf-8")
    (work / "section_03.json").write_text("{not json", encoding="utf-8")
    (work / "section_04.json").write_text(json.dumps({**SECTIONS[1], "paragraphs": []}, ensure_ascii=False), encoding="utf-8")
    sections, problems = study.read_sections(work, need_translation=True)
    assert [s["title"] for s in sections] == ["1. Introduction", "2. Methods"]
    text = " ".join(problems)
    assert "section_02.json: title" in text and "pages" in text and "quiz" in text and "section_03.json: JSON" in text and "section_04.json: paragraphs" in text


def test_citations_are_placed_by_page_then_by_section_name():
    secs = [{"title": "Abstract", "title_ko": "초록", "pages": [1, 1]}, {"title": "1. Introduction", "title_ko": "서론", "pages": [1, 3]},
            {"title": "2. Materials and Methods", "title_ko": "재료와 방법", "pages": [3, 5]}, {"title": "4. Discussion", "title_ko": "논의", "pages": [8, 9]}]
    assert study.section_for(secs, "p.2") == 1
    assert study.section_for(secs, "p.3 Methods") == 2 and study.section_for(secs, "p. 3, Introduction") == 1  # 두 파트가 나눠 쓰는 쪽은 이름으로
    assert study.section_for(secs, "Methods") == 2 and study.section_for(secs, "Discussion, Figure 4") == 3
    assert study.section_for(secs, "8쪽") == 3 and study.section_for(secs, "page 9") == 3
    assert study.section_for(secs, "Supplementary Table 2") is None and study.section_for(secs, "p.42") is None


# ── 위키 정리를 웹에서 ────────────────────────────────────────────────────


def test_dream_cycle_runs_from_the_web(client, fake):
    vault, _ = two_papers(client)
    r = client.post("/api/jobs", json={"kind": "dream"})
    assert r.status_code == 200, r.text
    job = runner.wait(r.json()["id"], timeout=30)
    assert job["state"] == "done" and job["result"]["dream"] == "/dream"
    call = next(c for c in fake.calls if c["system"] == integration.dreamer_rules())
    assert call["model"] == "opus" and "Read the brief at" in call["prompt"]
    assert dream.status(vault)["last_run"]  # 에이전트가 답으로 돌려준 JSON 을 제안 파일로 저장해 검토안까지 만들었다 (합칠 것이 없어 저절로 닫힘)


# ── Claude Code 실행 ──────────────────────────────────────────────────────


class FakeProc:
    def __init__(self, out: dict | str, code: int = 0):
        self.stdout_data = (json.dumps(out) if isinstance(out, dict) else out).encode("utf-8")
        self.returncode = code

    def communicate(self, timeout=None):
        return self.stdout_data, b""

    def kill(self):
        pass


def test_claude_code_runs_restricted_to_the_work_folder(tmp_path, monkeypatch):
    seen = {}

    def popen(args, **kwargs):
        seen.update(args=args, **kwargs)
        return FakeProc({"type": "result", "is_error": False, "result": "written 12 30", "total_cost_usd": 0.4})

    monkeypatch.setattr(runner, "claude_exe", lambda: "C:/fake/claude.exe")
    monkeypatch.setattr(runner.subprocess, "Popen", popen)
    out = REAL_RUN_CLAUDE("Read the brief at x and follow it exactly.", tmp_path, "rules here", "sonnet", 60)
    assert out["result"] == "written 12 30"
    args = seen["args"]
    assert args[:3] == ["C:/fake/claude.exe", "-p", "Read the brief at x and follow it exactly."]
    for flag in ("--restricted", "--no-session-persistence"):
        assert flag in args
    assert args[args.index("--tools") + 1] == "Read,Write" and args[args.index("--model") + 1] == "sonnet"
    assert args[args.index("--output-format") + 1] == "json" and args[args.index("--permission-mode") + 1] == "acceptEdits"
    assert Path(args[args.index("--append-system-prompt-file") + 1]).read_text(encoding="utf-8") == "rules here"
    assert seen["cwd"] == str(tmp_path) and seen["stdin"] == subprocess.DEVNULL
    assert "Bash" not in " ".join(args)

    monkeypatch.setattr(runner.subprocess, "Popen", lambda args, **k: FakeProc({"is_error": True, "result": "Not logged in · Please run /login"}, 1))
    with pytest.raises(runner.JobError) as err:
        REAL_RUN_CLAUDE("p", tmp_path, "r", "inherit", 60)
    assert err.value.code == "login"
    monkeypatch.setattr(runner.subprocess, "Popen", lambda args, **k: FakeProc({"is_error": True, "result": "Claude AI usage limit reached|1764212400"}, 1))
    with pytest.raises(runner.JobError) as err:
        REAL_RUN_CLAUDE("p", tmp_path, "r", "sonnet", 60)
    assert err.value.code == "limit"


def test_agent_replies_are_read_carefully(tmp_path):
    target = tmp_path / "proposal.json"
    assert runner.accept_json_reply('```json\n{"paper": {}}\n```', target) and json.loads(target.read_text(encoding="utf-8")) == {"paper": {}}
    assert not runner.accept_json_reply('{"other": 1}', target)  # 에이전트가 이미 쓴 파일은 덮어쓰지 않는다
    assert not runner.accept_json_reply("written 40 12", tmp_path / "x.json") and not (tmp_path / "x.json").exists()
    assert runner.failed_reason("failed: encrypted PDF") == "encrypted PDF" and runner.failed_reason("written 3") is None
    assert runner.classify("Invalid API key · Please run /login") == "login" and runner.classify("5-hour limit reached") == "limit"
    assert runner.classify("Connection reset") == "error"


# ── Claude Code 대화: 웹을 열고, 인용할 문헌을 찾는다 ──────────────────────


def test_skill_opens_the_web_and_keeps_citation_search_in_chat(client):
    open_vault(client)
    assert client.post("/api/claude/install").status_code == 200
    skill = integration.skill_path().read_text(encoding="utf-8")
    head = skill.split("\n---\n", 1)[0]
    assert "웹 화면을 열" in head and "paper wiki 열어줘" in head and "인용할 논문 찾아줘" in head
    for must in ("## 0. 웹 화면 열기", "PW open inbox", "PW open study", "PW open dream", "학습하며 정리", "로그인은 사용자가 직접 한다",
                 "## B. 선행연구 넣기 (글쓰기) — 이 대화에서 한다", "## 부록 A. 대화에서 논문 넣기", "## 부록 D. 대화에서 위키 정리", "PW search"):
        assert must in skill, must
    assert skill.index("## 0. 웹 화면 열기") < skill.index("## B. 선행연구") < skill.index("## 부록 A.")
    assert "PW serve" not in skill  # 웹을 여는 방법은 하나로 (떠 있으면 그대로 쓰고, 없으면 새 창에서 띄운다)


def test_open_command_starts_the_web_once_and_opens_the_page(monkeypatch, capsys):
    opened, spawned = [], []
    urls = iter(["", "", "http://127.0.0.1:8765"])
    monkeypatch.setattr(cli, "_live_url", lambda: next(urls))
    monkeypatch.setattr(cli, "_spawn_server", lambda: spawned.append(1))
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: opened.append(url))
    monkeypatch.setattr("time.sleep", lambda s: None)
    assert cli.main(["open", "inbox"]) == 0
    out = capsys.readouterr().out
    assert spawned == [1] and opened == ["http://127.0.0.1:8765/inbox"] and out.strip().endswith("http://127.0.0.1:8765/inbox") and "새 창" in out

    monkeypatch.setattr(cli, "_live_url", lambda: "http://127.0.0.1:8765")  # 이미 떠 있으면 새로 띄우지 않는다
    assert cli.main(["open", "study/d0123456789ab"]) == 0 and spawned == [1] and opened[-1] == "http://127.0.0.1:8765/study/d0123456789ab"
    assert cli.main(["open"]) == 0 and opened[-1] == "http://127.0.0.1:8765/"
    with pytest.raises(SystemExit):
        cli.main(["open", "../../etc"])
