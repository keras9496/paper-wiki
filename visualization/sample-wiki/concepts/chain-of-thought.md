---
type: concept
aliases: ["CoT", "사고 사슬"]
tags: [reasoning, prompting]
papers: ["[[2022-chain-of-thought-prompting]]", "[[2022-self-consistency]]", "[[2023-tree-of-thoughts]]", "[[2023-unfaithful-cot]]"]
related_concepts: ["[[in-context-learning]]"]
---

# Chain-of-Thought

## 한 줄 정의
최종 답 전에 중간 추론 단계를 생성하게 하여 다단계 문제 해결력을 끌어내는 프롬프트 기법.

## 핵심
이 개념의 이해는 두 번 갱신됐다. ① 구조의 일반화: 선형 사슬([[2022-chain-of-thought-prompting]]) → 병렬 표집·다수결([[2022-self-consistency]]) → 트리 탐색([[2023-tree-of-thoughts]]). ② 해석의 교정: 사슬을 "모델 추론의 투명한 기록"으로 읽던 통념을 [[2023-unfaithful-cot]]가 반증 — **성능 도구로서의 CoT와 해석 도구로서의 CoT를 분리해서 볼 것.**

## 등장 논문
- [[2022-chain-of-thought-prompting]] — 기법의 원전. 창발적 효과.
- [[2022-self-consistency]] — 사슬 다수결로 성능 보강.
- [[2023-tree-of-thoughts]] — 탐색·백트래킹으로 구조 일반화.
- [[2023-unfaithful-cot]] — 사슬의 신실성 반증(해석 측면).

## ⚠️ 이견 / 모순
- ⚠️ [[2022-chain-of-thought-prompting]]는 사슬이 추론을 "끌어낸다"고 보지만, [[2023-unfaithful-cot]]는 사슬이 실제 이유를 숨길 수 있음을 보임 — 성능(양립)과 신실성(충돌)을 구분해야 함.

## 관련 개념
- [[in-context-learning]] — CoT가 작동하는 기반 능력.
