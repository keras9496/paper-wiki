---
type: moc
tags: [knowledge, rag, synthesis]
papers: ["[[2020-gpt3-few-shot-learners]]", "[[2020-retrieval-augmented-generation]]", "[[2020-dense-passage-retrieval]]", "[[2023-self-rag]]"]
concepts: ["[[retrieval-augmented-generation]]", "[[in-context-learning]]"]
date_created: "2026-05-04"
---

# MOC: 지식은 어디에 두는가 — 파라미터 vs 검색

## 이 종합이 답하는 질문
LLM의 지식을 파라미터 내부에 저장하는 노선과 외부 검색으로 보강하는 노선의 트레이드오프.

## 대조표

| | 파라미터 내부 ([[2020-gpt3-few-shot-learners]]) | 외부 검색 ([[2020-retrieval-augmented-generation]] 계열) |
|---|---|---|
| 지식 갱신 | 재학습 필요 | 인덱스 교체로 즉시 |
| 환각 | 잦음 | 감소 (단, 검색 오류 전파) |
| 근거 제시 | 불가 | 출처 문서 제시 가능 |
| 병목 | 규모·데이터 | 리트리버 품질 ([[2020-dense-passage-retrieval]]) |

## 모순·긴장
- "항상 검색"은 만능이 아님 — 불필요한 검색이 답을 오염시킬 수 있고, [[2023-self-rag]]는 검색 여부 자체를 모델 판단으로 내림. 두 노선은 대립이 아니라 **판단 문제로 수렴 중**.

## 공백 (연구 기회)
- 파라미터 지식과 검색 지식이 충돌할 때 모델이 어느 쪽을 신뢰하는지의 체계적 연구.
- 검색 품질 저하가 생성 신뢰도에 전파되는 정도의 정량화.

## 내 통찰 (사용자 작성)
내 문헌 QA 시스템은 "무조건 RAG"로 설계했는데, Self-RAG처럼 검색 필요성 판단 단계를 넣는 것이 다음 개선 지점.

## 근거 논문
- [[2020-gpt3-few-shot-learners]]
- [[2020-retrieval-augmented-generation]]
- [[2020-dense-passage-retrieval]]
- [[2023-self-rag]]
