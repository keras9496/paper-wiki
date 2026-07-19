# Changelog

Paper Study 스킬의 변경 이력. / Changelog for the Paper Study skill.

## [Unreleased] — 2026-07-20

### Added
- **🌌 은하 뷰 (Paper Galaxy, `visualization/`)** — 위키를 온톨로지 우주로 렌더링하는 단일 파일 뷰어.
  개념 = 항성(크기 = 논문 수), 논문 = 주 개념을 공전하는 행성(크기 = 평점, 안쪽 궤도 = 오래된 논문,
  `reading` = 점선 펄스), MOC = 성운 코어, `contradicts` = 붉은 점선, `supersedes` = 호박색 화살표.
  파이프라인: `build-graph.mjs`(md 프론트매터·`[[링크]]` → 그래프 데이터, 의존성 0) → `galaxy.html`(`file://` 동작).
  Galaxy view: renders the wiki as an ontology universe (concepts = stars, papers = orbiting planets,
  MOCs = nebula cores; contradiction/supersede edges visualized) from a zero-dependency parser + single HTML.
- **학습 런처** — 상세 패널의 STUDY 버튼이 paper-study 명령(논문 복습/이어하기, 항성계 전체 복습,
  주제 종합, MOC 갱신)을 클립보드로 복사 → Claude Code에 붙여넣으면 해당 모드로 즉시 진입.
  SKILL.md에 명령 패턴 → 모드 매핑 표 추가. Study launcher: panel buttons copy ready-made
  paper-study commands; SKILL.md now maps each pattern to its mode.
- **탐색 UX** — 의미적 줌(멀리서는 핵심 항성 이름만, 항성 클릭 시 항성계 줌인 + 행성 라벨 노출),
  호버 하이라이트, 검색, 해시 딥링크(`#/슬러그`), 시네마 모드(`C`), 엣지 토글, 툴팁 행동 안내.
- **스케일 대응** — 궤도 링 패킹(둘레 비례 수용), 라벨 최상단 패스(백킹 + 겹침 컬링 + 위쪽 플립),
  엣지 밀도 자동 감쇠, `?data=` 그래프 전환. `gen-sample.mjs` 생성기로 논문 300편/항성계 100편 검증.
- 샘플 위키(`visualization/sample-wiki/` — 논문 13·개념 7·MOC 2, 실제 템플릿 스키마 준수).

### Changed
- SKILL.md 6단계: `concepts` 첫 항목 = 주 개념 규칙, 저장 후 은하 갱신 단계, 은하 연동·런처 처리 섹션 추가.
- README에 은하 뷰 섹션 추가(한·영).

## [Unreleased] — 2026-07-06

### Added
- **지식 리컨실 패스 (SKILL.md 6.7단계)** — 새 논문 저장 직후(6.5 다음) 실행. 새 논문은 덧붙이지 않고
  기존 지식체계를 갱신한다: ① 이 논문이 링크한 기존 개념·논문 노트를 열어 `## 핵심`·`## 등장 논문`을
  **본문으로 갱신**(백링크만 X) ② 기존 주장·`🤔 내 의견`과 대조해 모순을 **양쪽 노트에 `⚠️ 모순: [[..]]`**로
  표시하고 즉시 보고 ③ 옛 주장이 뒤집히면 프론트매터 `superseded_by`/`supersedes`/`contradicts` 기록.
  Karpathy LLM-wiki 정신(update-in-place, not append)을 수집 워크플로우에 못박음.
  Knowledge-reconciliation pass: a new paper revises existing concept/paper notes in-place,
  flags contradictions with `⚠️` on both sides, and records supersede/contradict frontmatter.
- 템플릿에 `supersedes`/`superseded_by`/`contradicts` 프론트매터와 `## ⚠️ 모순` 섹션 추가(paper·concept).

### Changed
- README에 지식 리컨실 기능/스텝 반영(한·영).

## [Unreleased] — 2026-07-05

### Added
- **링크 무결성 패스 (SKILL.md 6.5단계)** — 노트를 저장할 때마다 기계적으로 실행:
  깨진 `[[링크]]` 탐지 → 없는 개념은 스텁 자동 생성 → 역링크 보강 → `index.md` 동기화 → 보고.
  원칙: *어떤 노트도 대상 없는 링크를 남긴 채 저장되지 않는다.*
  Link-integrity pass that runs on every save: detect dangling links, auto-create missing
  concept stubs, backfill backlinks, sync the index.
- **종합·인사이트 모드 (6번째 모드)** — 여러 논문을 가로질러 대조표·모순·문헌 공백을 생성하고,
  그 결과를 능동 회상으로 되던진 뒤 사용자 통찰과 함께 `moc/{주제}.md`에 축적.
  Synthesis / insight mode: cross-paper comparison matrix, contradictions, and literature-gap
  detection, thrown back as active recall and accumulated in `moc/`.
- 위키 구조에 `moc/` 폴더 추가. / Added the `moc/` folder to the wiki structure.

### Changed
- README를 위 기능(6모드·링크 무결성·종합)에 맞게 갱신(한/영).
  README updated (KR/EN) to reflect the 6 modes, link integrity, and synthesis.

## [1.0.0] — Initial release
- 능동 학습 스킬: Active Recall · Feynman · Elaboration.
- 4가지 모드, 통독/섹션별 정독, 중단·이어하기, 간격 반복, 양방향 위키링크.
