---
type: concept
aliases: ["스케일링 법칙", "멱법칙 스케일링"]
tags: [empirical, core]
papers: ["[[2020-scaling-laws-neural-lm]]", "[[2022-chinchilla-compute-optimal]]", "[[2020-gpt3-few-shot-learners]]"]
related_concepts: ["[[in-context-learning]]", "[[self-supervised-learning]]"]
---

# Scaling Laws

## 한 줄 정의
모델 크기·데이터·연산량과 손실 사이에 나타나는 매끈한 멱법칙 관계.

## 핵심
"더 크게 만들면 얼마나 좋아지나"를 외삽 가능한 공식으로 만든 것. 단, 법칙의 **형태**는 합의됐지만 **계수**는 실험 설계에 민감하다 — [[2020-scaling-laws-neural-lm]]의 "모델 우선" 권고가 [[2022-chinchilla-compute-optimal]]의 "동비율" 권고로 교체된 것이 그 증거. 측정 방법론이 결론을 바꾼 대표 사례로 기억할 것.

## 등장 논문
- [[2020-scaling-laws-neural-lm]] — 멱법칙의 최초 정식화. 배분 권고는 폐기됨.
- [[2022-chinchilla-compute-optimal]] — 통제된 재측정으로 배분 권고를 대체(현행 합의).
- [[2020-gpt3-few-shot-learners]] — 법칙을 믿고 규모를 지른 실증 사례.

## ⚠️ 이견 / 모순
- ⚠️ [[2020-scaling-laws-neural-lm]]는 모델 우선, [[2022-chinchilla-compute-optimal]]는 동비율 — 학습률 스케줄 통제 여부가 갈랐고 후자가 승계.

## 관련 개념
- [[in-context-learning]] — 규모가 만드는 창발 능력.
- [[self-supervised-learning]] — 스케일링의 연료.
