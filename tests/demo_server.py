"""데모 서버: 실제 Zotero·Claude Code·설정 없이 화면을 둘러본다.

    .venv\\Scripts\\python tests\\demo_server.py [포트] [--empty] [--drive=two|off|none] [--existing] [--no-claude] [--no-skill] [--zotero-unlinked] [--no-dream]

임시 폴더에 예시 위키를 만든다: 읽은 논문 3편(이름이 규칙대로 바뀐 PDF 포함)과 그 논문들이 인용한 문헌, 검토 대기 1건, 논문 폴더의 새 PDF 2편,
위키 정리(dream cycle)에서 검토를 기다리는 합치기 제안 2건 (--no-dream 이면 없이).
실제 설정·자격 증명·위키·~/.claude 에는 손대지 않는다.  --empty 를 주면 첫 실행(설정 전) 상태로 뜬다.
--drive 로 구글 드라이브 데스크톱의 상태를 흉내 낸다: two(계정 2개, 기본값) / off(꺼져 있음) / none(미설치).
--existing 은 '다른 컴퓨터에서 이미 만든 위키가 두 번째 계정의 드라이브에 있는' 첫 실행 상황을 만든다.
--no-claude 는 Claude Code 가 없는 컴퓨터, --no-skill 은 스킬을 아직 설치하지 않은 상태를 보여 준다.
"""

from __future__ import annotations

import atexit
import copy
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(tempfile.mkdtemp(prefix="paperwiki-demo-"))
atexit.register(shutil.rmtree, ROOT, ignore_errors=True)  # 데모가 끝나면 임시 데이터도 지운다
os.environ["PAPERWIKI_CONFIG_DIR"] = str(ROOT / "config")
os.environ["PAPERWIKI_NO_KEYRING"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import uvicorn  # noqa: E402
from pypdf import PdfWriter  # noqa: E402

from paperwiki import config, gdrive, integration, library, render, server, wiki  # noqa: E402
from paperwiki.store import Vault  # noqa: E402


def paper(key, title, authors, year, venue, doi=""):
    return {
        "zotero_key": key, "attachment_key": "ATT" + key[:5], "item_type": "journalArticle", "title": title,
        "authors": [{"family": f, "given": g} for f, g in authors], "year": year, "venue": venue, "doi": doi, "url": "",
        "abstract": "", "citekey_hint": "", "date_added": f"2026-11-{10 + len(key) % 9}T09:00:00Z", "num_children": 1,
    }


LIBRARY = [
    paper("DEMO0001", "Computerized cognitive training improves working memory in mild cognitive impairment: a randomized controlled trial", [("Kim", "Jisoo"), ("Lee", "Sangmin"), ("Park", "Minji")], "2023", "Journal of Cognitive Health", "10.1000/jch.2023.001"),
    paper("DEMO0002", "Linear mixed-effects models for longitudinal cognitive data with dropout", [("Choi", "Yuna")], "2021", "Statistical Methods in Aging Research"),
    paper("DEMO0003", "Digital biomarkers from speech for early detection of cognitive decline", [("Nguyen", "Thi"), ("Schmidt", "Lena")], "2024", "npj Digital Medicine"),
    paper("DEMO0004", "Adherence to app-based cognitive interventions in older adults: a systematic review", [("Garcia", "Maria"), ("Oh", "Hyun")], "2022", "JMIR Aging"),
    paper("DEMO0005", "경도인지장애 노인의 디지털 인지중재 순응도에 영향을 미치는 요인", [("박", "서연"), ("이", "도윤")], "2024", "한국노년학"),
]


def kw(*path, aliases=(), description=""):
    return {"path": list(path), "aliases": list(aliases), "description": description}


T, M = "연구 주제", "방법론"


def ref(label, family, year, title, venue, et_al=True, doi=""):
    return {"ref": label, "authors": [{"family": family, "given": ""}], "et_al": et_al, "year": year, "title": title, "venue": venue, "doi": doi}


def claim(statement, ctype, refs, quote, location, *keywords):
    return {"statement": statement, "type": ctype, "refs": list(refs), "evidence": {"quote": quote, "location": location}, "keywords": list(keywords), "same_as": ""}


# 여러 논문의 참고문헌 목록에 되풀이해 나오는 문헌 (번호와 표기는 논문마다 조금씩 다르다)
PETERSEN = ("Petersen", "2004", "Mild cognitive impairment as a diagnostic entity", "J. Intern. Med.", False)
HILL = ("Hill", "2017", "Computerized cognitive training in older adults with mild cognitive impairment or dementia: a systematic review and meta-analysis", "Am. J. Psychiatry")
LAMPIT = ("Lampit", "2014", "Computerized cognitive training in cognitively healthy older adults: a systematic review and meta-analysis of effect modifiers", "PLoS Med.")
BATES = ("Bates", "2015", "Fitting linear mixed-effects models using lme4", "J. Stat. Softw.")
SIMONS = ("Simons", "2016", "Do brain-training programs work?", "Psychol. Sci. Public Interest")

CCT = kw(T, "경도인지장애", "전산화 인지훈련", aliases=["computerized cognitive training", "CCT"], description="컴퓨터·앱 기반으로 인지 과제를 반복 수행하는 중재.")
MCI = kw(T, "경도인지장애", aliases=["mild cognitive impairment", "MCI"], description="정상 노화와 치매 사이의 인지 저하 상태.")
TRANSFER = kw(T, "인지훈련의 전이 효과", aliases=["transfer effect"], description="훈련한 과제 밖의 능력으로 효과가 넓어지는 현상.")
LMM = kw(M, "분석 방법", "선형 혼합효과모형", aliases=["linear mixed-effects model", "LMM"], description="개인 내 반복 측정의 상관을 무선 효과로 다루는 회귀 모형.")
ADHERENCE = kw(T, "디지털 중재 순응도", aliases=["adherence", "engagement"], description="처방된 디지털 중재를 계획대로 수행하는 정도.")

PROPOSALS = {
    "DEMO0001": {
        "summary": "MCI 환자 120명을 대상으로 한 12주 무작위 대조 시험에서 전산화 인지훈련이 능동 대조군에 비해 작업기억을 유의하게 향상시켰으나 일화기억으로의 전이는 관찰되지 않았다.",
        "references": [
            ref("1", *PETERSEN), ref("2", *HILL), ref("3", *LAMPIT), ref("4", *SIMONS), ref("5", *BATES),
            ref("6", "Moher", "2010", "CONSORT 2010 explanation and elaboration: updated guidelines for reporting parallel group randomised trials", "BMJ"),
        ],
        "claims": [
            claim("경도인지장애는 정상 노화와 치매 사이의 진단 단위이며, 매년 10–15%가 치매로 진행한다.", "background", ["1"],
                  "Mild cognitive impairment (MCI) is a transitional state between normal ageing and dementia, with 10–15% converting each year [1].", "p.1, Introduction", MCI),
            claim("전산화 인지훈련은 MCI 노인의 전반적 인지와 작업기억에 작지만 유의한 효과가 있다.", "finding", ["2", "3"],
                  "Meta-analyses report small-to-moderate benefits of computerized cognitive training on global cognition and working memory [2,3].", "p.2, Introduction",
                  CCT, kw(T, "작업기억", aliases=["working memory", "WM"], description="정보를 잠시 유지하고 조작하는 능력.")),
            claim("인지훈련의 효과가 훈련하지 않은 과제로 전이된다는 근거는 제한적이다.", "limitation", ["4", "3"],
                  "Evidence that training gains transfer to untrained tasks remains limited [3,4].", "p.2, Introduction", TRANSFER, CCT),
            claim("반복 측정 자료는 R 의 lme4 로 무선 절편 선형 혼합효과모형을 적합해 분석한다.", "method", ["5"],
                  "We fitted linear mixed-effects models with random intercepts using lme4 [5].", "p.4, Statistical analysis", LMM),
            claim("무작위 대조 시험은 CONSORT 2010 지침에 따라 보고한다.", "method", ["6"],
                  "The trial is reported according to CONSORT 2010 [6].", "p.3, Methods", kw(M, "연구 설계", "무작위 대조 시험", aliases=["RCT", "randomized controlled trial"])),
        ],
    },
    "DEMO0002": {
        "summary": "탈락이 있는 종단 인지 자료에서 선형 혼합효과모형과 반복측정 분산분석을 모의실험으로 비교하여, 무작위 결측 가정 하에서 혼합모형이 편향이 작음을 보였다.",
        "references": [
            ref("12", "Bates", "2015", "Fitting Linear Mixed-Effects Models Using lme4.", "Journal of Statistical Software", doi="10.18637/jss.v067.i01"),
            ref("13", "Rubin", "1976", "Inference and missing data", "Biometrika", et_al=False),
            ref("14", *HILL),
        ],
        "claims": [
            claim("선형 혼합효과모형은 lme4 로 적합하는 것이 표준적이다.", "method", ["12"],
                  "Mixed models were fitted with the lme4 package [12].", "p.6", LMM),
            claim("무작위 결측(MAR) 가정에서는 관측된 자료만으로 편향 없는 추정이 가능하다.", "background", ["13"],
                  "Under the missing-at-random assumption, likelihood-based inference ignoring the missingness mechanism is valid [13].", "p.3",
                  kw(M, "분석 방법", "결측 자료 처리", aliases=["missing data", "dropout"])),
            claim("인지훈련 시험은 탈락률이 높아 결측을 다루는 분석이 필요하다.", "limitation", ["14"],
                  "Trials of cognitive training typically lose 10–30% of participants [14].", "p.2", CCT, kw(M, "분석 방법", "결측 자료 처리")),
        ],
    },
    "DEMO0004": {
        "summary": "고령자 대상 앱 기반 인지 중재 38편을 체계적으로 고찰한 결과, 평균 순응도는 68%였으며 원격 코칭과 알림이 순응도를 높이는 요인이었다.",
        "references": [
            ref("7", *LAMPIT), ref("8", *HILL),
            ref("9", "Kim", "2023", "Computerized cognitive training improves working memory in mild cognitive impairment: a randomized controlled trial", "J. Cogn. Health"),
            ref("10", "Page", "2021", "The PRISMA 2020 statement: an updated guideline for reporting systematic reviews", "BMJ"),
        ],
        "claims": [
            claim("전산화 인지훈련의 효과는 감독하에 집단으로 수행할 때 더 크고, 집에서 혼자 할 때는 작다.", "finding", ["7"],
                  "Unsupervised at-home training was less effective than group-based supervised training [7].", "p.2", CCT, ADHERENCE),
            claim("전산화 인지훈련은 MCI 노인의 전반적 인지와 작업기억에 작지만 유의한 효과가 있다.", "finding", ["8", "9"],
                  "Computerized training yields small but reliable cognitive gains in MCI [8,9].", "p.1", CCT),
            claim("체계적 문헌고찰은 PRISMA 2020 지침에 따라 수행·보고한다.", "method", ["10"],
                  "This review followed the PRISMA 2020 statement [10].", "Methods", kw(M, "연구 설계", "체계적 문헌고찰", aliases=["systematic review"])),
        ],
    },
}
PROPOSALS["DEMO0003"] = {
    "summary": "자발화 음성에서 추출한 음향·언어 특징으로 초기 인지 저하를 선별하는 모델을 제안하고 외부 코호트에서 검증하였다.",
    "references": [
        ref("1", *PETERSEN),
        ref("2", "König", "2015", "Automatic speech analysis for the assessment of patients with predementia and Alzheimer's disease", "Alzheimers Dement. (Amst.)"),
        ref("3", "Chen", "2016", "XGBoost: a scalable tree boosting system", "Proc. KDD", et_al=False),
    ],
    "claims": [
        claim("경도인지장애는 정상 노화와 치매 사이의 진단 단위이다.", "background", ["1"],
              "MCI denotes the stage between normal ageing and dementia [1].", "p.1", MCI),
        claim("자발화 음성의 쉼과 발화 속도 특징은 초기 알츠하이머병과 MCI 를 정상 노인과 구분한다.", "finding", ["2"],
              "Pause and tempo features of spontaneous speech separate early AD and MCI from healthy controls [2].", "p.2",
              kw(T, "디지털 바이오마커", "음성 바이오마커", aliases=["speech biomarker", "voice biomarker"], description="음성·발화에서 얻는 인지 상태 지표."), kw(T, "경도인지장애", "조기 선별", aliases=["early detection", "screening"])),
        claim("표 형태의 특징에는 그래디언트 부스팅(XGBoost)이 널리 쓰인다.", "method", ["3"],
              "We trained gradient-boosted trees (XGBoost [3]) on acoustic and linguistic features.", "Methods", kw(M, "분석 방법", "기계학습 분류", aliases=["machine learning classification"])),
    ],
}


class DemoZotero:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def close(self):
        pass

    def find(self, doi="", title=""):
        return next((copy.deepcopy(p) for p in LIBRARY if p["title"] == title), None)

    def ping(self):
        return {"ok": True, "mode": "local", "total": len(LIBRARY), "account_linked": "--zotero-unlinked" not in sys.argv}

    def items(self, q="", start=0, limit=30):
        found = [p for p in LIBRARY if q.lower() in (p["title"] + str(p["authors"]) + p["year"]).lower()]
        return found[start : start + limit], len(found)

    def item(self, key):
        return copy.deepcopy(next(p for p in LIBRARY if p["zotero_key"] == key))

    def pdf_attachment(self, key):
        return {"key": "ATT" + key[:5], "data": {"key": "ATT" + key[:5]}}

    def pdf_bytes(self, attachment):
        return b"%PDF-1.4 demo"


# 논문 폴더에 처음 넣었을 때의 (제각각인) 파일 이름
DROPPED = {"DEMO0001": "1-s2.0-S0001234523000-main.pdf", "DEMO0002": "choi2021 최종본(수정).pdf", "DEMO0003": "s41746-024-01012-3.pdf", "DEMO0004": "document (4).pdf"}


def drop_pdf(vault: Vault, name: str, pages: int) -> Path:
    """논문 폴더에 PDF 하나를 넣는다 (쪽수가 다르면 내용이 다른 파일이 된다)."""
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=420, height=595)
    vault.pdf_dir.mkdir(parents=True, exist_ok=True)
    with open(vault.pdf_dir / name, "wb") as fh:
        writer.write(fh)
    return vault.pdf_dir / name


def draft(vault: Vault, key: str, linked: bool = True) -> str:
    """Claude Code 가 한 것처럼: 읽을 준비 → 제안 파일 → 검토안. linked 면 Zotero 에서 같은 논문을 찾은 것으로 한다."""
    meta = DemoZotero().item(key)
    info = library.prepare(vault, str(drop_pdf(vault, DROPPED[key], pages=8 + int(key[-1]))))
    proposal = {"paper": {k: meta[k] for k in ("title", "authors", "year", "venue", "doi", "item_type")}, **copy.deepcopy(PROPOSALS[key]), "note": ""}
    Path(info["proposal"]).write_text(json.dumps(proposal, ensure_ascii=False), encoding="utf-8")
    wiki.propose(vault, info["id"], zotero=DemoZotero() if linked else None)
    return info["id"]


def seed(vault: Vault, keys) -> None:
    for key in keys:
        wiki.approve(vault, draft(vault, key, linked=key != "DEMO0004"))


def dream_review(vault: Vault) -> None:
    """정리 에이전트가 위키를 읽고 제안을 쓴 것처럼: '위키 정리' 화면에 검토를 기다리는 제안이 생긴다."""
    from paperwiki import dream

    groups = {c["statement"]: c["group"] for paper in vault.papers().values() for c in paper.get("claims", [])}
    g = lambda start: next(group for text, group in groups.items() if text.startswith(start))  # noqa: E731
    info = dream.prepare(vault)
    proposal = {
        "merges": [
            {"groups": [g("반복 측정 자료는 R 의 lme4"), g("선형 혼합효과모형은 lme4")], "confidence": "high",
             "reason": "둘 다 선형 혼합효과모형을 lme4 로 적합한다는 같은 말이고, 같은 문헌(Bates et al.)을 인용한다. 한쪽이 무선 절편이라는 설정을 덧붙였을 뿐이다."},
            {"groups": [g("인지훈련 시험은 탈락률이 높아"), g("전산화 인지훈련의 효과는 감독하에")], "confidence": "medium",
             "reason": "둘 다 집에서 하는 인지훈련은 끝까지 수행하기 어렵다는 점을 말한다. 다만 첫째 주장은 탈락률과 결측 분석의 필요를, 둘째 주장은 감독 여부에 따른 효과 차이를 말하고 있어 따로 두는 편이 나을 수도 있다."},
        ],
        "considered": [
            {"groups": [g("인지훈련의 효과가 훈련하지 않은 과제로"), g("전산화 인지훈련은 MCI 노인의")],
             "reason": "같은 메타분석(Lampit et al.)을 인용하지만 하나는 훈련한 영역에서의 효과, 다른 하나는 훈련하지 않은 과제로의 전이가 제한적이라는 한계다."},
            {"groups": [g("무작위 대조 시험은 CONSORT"), g("체계적 문헌고찰은 PRISMA")],
             "reason": "둘 다 보고 지침을 따른다는 말이지만 연구 설계(무작위 대조 시험과 체계적 문헌고찰)와 지침이 서로 다르다."},
        ],
        "note": "",
    }
    Path(info["proposal"]).write_text(json.dumps(proposal, ensure_ascii=False), encoding="utf-8")
    dream.propose(vault)


def fake_drive(mode: str) -> None:
    """구글 드라이브 데스크톱이 있는 것처럼(또는 없는 것처럼) 꾸민다."""
    roots = [ROOT / "Drive-G" / "내 드라이브", ROOT / "Drive-H" / "내 드라이브"]
    accounts = [
        {"root": roots[0], "mount": "G:", "label": "Google Drive", "mode": "stream", "email": "me@example.com"},
        {"root": roots[1], "mount": "H:", "label": "lab@example.org", "mode": "stream", "email": "lab@example.org"},
    ]
    live = {"on": mode == "two"}

    def detect():
        if not live["on"]:
            return []
        for r in roots:
            r.mkdir(parents=True, exist_ok=True)
        return accounts

    def launch():
        live["on"] = True  # 실행 버튼을 누르면 잠시 뒤 연결된 것처럼
        return True

    gdrive.detect = detect
    gdrive.is_installed = lambda: mode != "none"
    gdrive.can_launch = lambda: mode != "none"
    gdrive.launch = launch if mode != "none" else (lambda: False)


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    port = int(args[0]) if args else 8799
    fake_drive(next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--drive=")), "two"))
    server.make_zotero = lambda cfg: DemoZotero()
    # 스킬은 사용자의 ~/.claude 가 아니라 임시 폴더에 설치된다
    integration.skill_path = lambda: ROOT / "claude-home" / "skills" / "paper-wiki" / "SKILL.md"
    integration.agent_path = lambda: ROOT / "claude-home" / "agents" / "paper-wiki-reader.md"
    integration.claude_code_installed = lambda: "--no-claude" not in sys.argv
    if "--existing" in sys.argv:
        # 다른 컴퓨터에서 lab@example.org 계정의 드라이브(하위 폴더)에 만들어 둔 위키. 이 컴퓨터의 설정은 비어 있다.
        other = Vault(ROOT / "Drive-H" / "내 드라이브" / "연구" / "문헌위키")
        other.init("ko")
        seed(other, ["DEMO0001", "DEMO0002", "DEMO0004"])
        draft(other, "DEMO0003")  # 그 컴퓨터에서 검토하다 만 것
    elif "--empty" not in sys.argv:
        vault = Vault(ROOT / "PaperWiki")
        vault.init("ko")
        seed(vault, ["DEMO0001", "DEMO0002", "DEMO0004"])
        draft(vault, "DEMO0003")  # 검토 대기 1건
        drop_pdf(vault, "nihms-1823341.pdf", pages=21)  # 아직 읽지 않은 새 PDF 2편
        drop_pdf(vault, "스캔_20261120_논문.pdf", pages=34)
        render.sync(vault)
        config.update(vault_path=str(vault.root))
        if "--no-dream" not in sys.argv:
            dream_review(vault)  # '위키 정리'에 검토를 기다리는 합치기 제안 2건
        if "--no-skill" not in sys.argv and "--no-claude" not in sys.argv:
            integration.install(str(vault.root))
    print(f"데모 서버: http://127.0.0.1:{port}   (데이터: {ROOT})")
    uvicorn.run(server.app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
