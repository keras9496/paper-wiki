# Changelog

Paper Study 스킬의 변경 이력. / Changelog for the Paper Study skill.

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
