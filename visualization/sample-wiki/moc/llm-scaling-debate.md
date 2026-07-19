---
type: moc
tags: [scaling, synthesis]
papers: ["[[2020-scaling-laws-neural-lm]]", "[[2022-chinchilla-compute-optimal]]", "[[2020-gpt3-few-shot-learners]]"]
concepts: ["[[scaling-laws]]"]
date_created: "2026-04-05"
---

# MOC: LLM 스케일링 논쟁 — 모델 vs 데이터

## 이 종합이 답하는 질문
고정 연산 예산에서 모델 크기와 데이터량을 어떻게 배분해야 하는가, 그리고 왜 두 대표 논문의 답이 달랐는가.

## 대조표

| | [[2020-scaling-laws-neural-lm]] | [[2022-chinchilla-compute-optimal]] |
|---|---|---|
| 권고 배분 | 모델 크기 우선 | 모델:데이터 동비율 (≈20 tok/param) |
| 학습률 스케줄 | 고정 (미통제) | 실험별 학습 길이에 맞춤 |
| 검증 방식 | 멱법칙 외삽 | 3개 독립 방법 + 70B 실모델 검증 |
| 현재 지위 | 배분 권고 폐기 | 현행 합의 (단, 추론 비용 미반영) |

## 모순·긴장
- 최적 배분 결론이 정반대 — 원인은 데이터가 아니라 **측정 방법론**(학습률 스케줄). [[scaling-laws]] 노트에 기록됨.
- [[2020-gpt3-few-shot-learners]]는 Kaplan 권고로 설계되어 Chinchilla 기준 undertrained.

## 공백 (연구 기회)
- 추론 비용까지 포함한 total-cost-optimal 배분의 정식화.
- 데이터 고갈 시나리오(고품질 토큰 유한)에서의 법칙 수정.

## 내 통찰 (사용자 작성)
스케일링 "법칙"도 결국 실험 프로토콜의 함수다. 내 분야의 경험 법칙들도 측정 방법을 바꿔 재검증할 가치가 있다.

## 근거 논문
- [[2020-scaling-laws-neural-lm]]
- [[2022-chinchilla-compute-optimal]]
- [[2020-gpt3-few-shot-learners]]
