<div align="center">

<img src="assets/promo.png" alt="논문 Wiki — Paper Study Skill" width="420">

# 📚 Paper Study — 논문 능동학습 위키 스킬

**읽고 끝나는 논문 정리가 아니라, 학습하고 정리하고 연결해 연구 자산으로 남기는 논문 위키**

A [Claude Code](https://claude.com/claude-code) skill that turns passive paper-reading into **active learning**.
Instead of handing you a summary, it forces *active recall*, *Feynman re-explanation*, and *connection to what you already know* — then saves it all as a linked Markdown wiki.

[설치](#-설치) · [사용법](#-사용법) · [작동 원리](#-왜-요약이-아니라-능동학습인가) · [English](#-english)

</div>

---

## 🤔 왜 "요약"이 아니라 "능동학습"인가

LLM으로 논문을 읽으면 글은 많이 읽는데 **머릿속에 남는 게 없는** 경험, 다들 있을 거예요.
원인은 **수동적 읽기(요약 받기)** 예요. 기억에 남으려면 인지과학이 말하는 세 가지가 필요합니다:

| 장치 | 무엇 | 이 스킬에서 |
|------|------|------------|
| **Active Recall** | 답을 보기 전에 스스로 인출하기 | 답을 가린 채 회상 질문을 하나씩 출제 → 먼저 답하면 채점·교정 |
| **Feynman Technique** | 쉬운 말로 직접 설명하기 | 본인 말로 재설명 → AI가 칭찬 대신 *빈틈·오개념*을 지적 |
| **Elaboration** | 기존 지식과 연결하기 | 위키를 검색해 "예전에 읽은 [[X]]와 이렇게 다르다" 연결 질문 |

그리고 핵심: **저장 전에 본인이 직접** "내 연구에 어떻게 적용할까 / 내 의견은" 을 써야 합니다.
AI가 대신 채우지 않습니다 — 그게 진짜로 기억에 남는 부분이니까요.

## ✨ 기능

- 🧩 **4가지 모드** — 학습 / 이어하기 / 복습 / 위키 질문
- 📖 **통독 vs 섹션별 정독** 선택 — 정독 모드는 섹션마다 번역본 → 읽기 → 섹션 퀴즈
- 🔗 **마크다운 위키** — 논문·개념 노트를 `[[위키링크]]`로 양방향 연결 (Obsidian 호환)
- ⏸️ **중단 & 이어하기** — 여러 날에 걸친 학습을 체크포인트로 재개
- 🔁 **간격 반복** — 약했던 문제를 다음 복습 때 우선 재출제
- 🌐 **새 논문이 들어오면** 위키를 먼저 검색해 관련 연구를 제시

## 📦 설치

> 필요: [Claude Code](https://docs.claude.com/en/docs/claude-code)

### 방법 1 — 개인 스킬 (어디서나 사용)
```bash
git clone https://github.com/<your-id>/paper-study-skill.git
# paper-study 폴더를 개인 스킬 경로로 복사
cp -r paper-study-skill/paper-study ~/.claude/skills/paper-study
```

### 방법 2 — 프로젝트 스킬 (위키 폴더 안에 함께 보관, 추천)
논문 위키로 쓸 폴더를 하나 만들고, 그 안 `.claude/skills/`에 넣으세요. 스킬과 위키가 한 폴더에 묶여 이동·백업이 쉽습니다.
```bash
mkdir my-paper-wiki && cd my-paper-wiki
mkdir -p .claude/skills papers concepts inbox
git clone https://github.com/<your-id>/paper-study-skill.git /tmp/ps
cp -r /tmp/ps/paper-study .claude/skills/paper-study
```

설치 후 위키 루트에 다음 폴더를 둡니다(없으면 스킬이 안내):
```
my-paper-wiki/
├── index.md      # 위키 홈 (논문 목록·개념 인덱스)
├── papers/       # 논문당 .md 노트
├── concepts/     # 개념 원자 노트
├── inbox/        # 아직 안 읽은 PDF
└── .claude/skills/paper-study/
```

## 🚀 사용법

위키 폴더에서 Claude Code를 열고:

```text
# 새 논문 학습 — PDF를 inbox/에 넣고
"이 논문 공부하자"

# 이어하기 — 며칠에 걸친 정독
"그 논문 Results부터 이어서 공부하자"

# 복습 — 인출 다시
"[[2025-어쩌고]] 복습하자"

# 위키 질문
"내가 역인과(reverse causality)에 대해 뭘 읽었더라?"
```

스킬은 이렇게 진행합니다:
1. PDF를 읽고, 위키에서 **관련된 기존 노트를 먼저** 찾아 연결
2. **통독 / 섹션별 정독** 중 선택 (정독은 섹션마다 번역 → 퀴즈)
3. **회상 질문**을 답 가린 채 하나씩 → 직접 답하면 채점·교정
4. **파인만 재설명** → 빈틈 지적
5. 끝에 **본인이 직접** 파인만 정리 + 연구 적용 + 의견 작성
6. `papers/`에 노트 저장 + 개념 노트 + **양방향 [[링크]]** + 인덱스 갱신

## 📂 무엇이 들어있나

```
paper-study/
├── SKILL.md                 # 스킬 본체 (워크플로우 전체)
└── templates/
    ├── paper.md             # 논문 노트 템플릿
    └── concept.md           # 개념 노트 템플릿
```

## 🛠 커스터마이즈

- **언어**: 번역·질문이 한국어로 설정돼 있어요. `SKILL.md`에서 다른 언어로 바꿀 수 있습니다.
- **노트 형식**: `templates/`의 프론트매터·섹션을 본인 워크플로우에 맞게 수정하세요.
- **간격 반복**: 노트의 `next_review`·`review_weak_spots` 필드를 활용해 due-card 기능으로 확장 가능.

## 🤝 기여 · 라이선스

PR·이슈 환영합니다. MIT License — 자유롭게 쓰고 고치세요.

---

## 🌐 English

**Paper Study** is a Claude Code skill for *active* paper learning. It refuses to just summarize —
instead it runs **active recall** (hidden-answer quizzing), **Feynman re-explanation** (you explain, it finds your gaps),
and **elaboration** (it links each paper to what's already in your wiki). You must write your own
*"how does this apply to my research"* and *opinion* before it saves — because that's what actually sticks.

Everything is stored as a linked Markdown wiki (`[[wikilinks]]`, Obsidian-compatible): one note per paper,
atomic concept notes, bidirectional links. Supports **whole-read vs section-by-section** study (with per-section
translation + quiz), **pause & resume** across days, and **spaced repetition** of your weak spots.

**Install:** copy the `paper-study/` folder into `~/.claude/skills/` (personal) or your wiki's `.claude/skills/`
(project). Then, from your wiki folder in Claude Code: *"study this paper"* (drop a PDF in `inbox/`),
*"resume from Results"*, *"quiz me on [[note]]"*, or *"what have I read about X?"*.

MIT Licensed.
