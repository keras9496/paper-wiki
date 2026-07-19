---
title: "Scaling Laws for Neural Language Models"
authors: "Jared Kaplan, Sam McCandlish et al."
year: 2020
venue: "arXiv"
tags: [scaling, llm, empirical]
status: studied
date_read: "2026-04-01"
related_papers: ["[[2020-gpt3-few-shot-learners]]", "[[2022-chinchilla-compute-optimal]]"]
concepts: ["[[scaling-laws]]"]
my_rating: 4
review_weak_spots: []
next_review: ""
supersedes: []
superseded_by: ["[[2022-chinchilla-compute-optimal]]"]
contradicts: []
---

# Scaling Laws for Neural Language Models

## TL;DR
LM 손실은 파라미터 수·데이터·연산량 각각에 대해 **매끈한 멱법칙(power law)**을 따르며, 고정 연산 예산에서는 **모델을 키우는 쪽**이 데이터를 늘리는 것보다 유리하다고 주장.

## 문제 / 동기
"얼마나 큰 모델을 얼마나 많은 데이터로 학습해야 하나"에 대한 정량적 지침이 없었다.

## 핵심 아이디어 / 방법
크기·데이터·연산을 체계적으로 바꿔가며 수백 개 모델을 학습, 손실 곡선을 멱법칙으로 적합. compute-optimal frontier를 도출.

## 결과
L(N), L(D), L(C)가 수십 배 범위에서 멱법칙과 일치. "큰 모델 + 이른 조기종료"를 권고 — 이 권고는 이후 [[2022-chinchilla-compute-optimal]]에 의해 뒤집힘.

## 개념
- [[scaling-laws]]

## 능동 회상 (복습용 — 답은 접힘)

**Q1.** 이 논문이 "모델을 키워라"라고 결론 낸 근거는?
<details><summary>답</summary>
적합된 멱법칙 지수상 손실 감소가 데이터 증가보다 파라미터 증가에 더 민감하게 나타났기 때문. (후에 학습률 스케줄 미통제가 원인으로 지목됨)
</details>

---

## ✍️ 내 파인만 재설명
모델 크기·데이터·계산량을 각각 다이얼처럼 돌려보며 손실이 얼마나 내려가는지 잰 뒤, "예산이 정해져 있으면 어느 다이얼을 돌려야 이득인가"를 공식으로 만든 논문.

## 💡 내 연구에의 적용
내 모델 실험에도 작은 규모에서 스케일링 곡선을 먼저 그려 외삽하는 습관을 들일 것.

## 🤔 내 의견 / 비판
학습률 스케줄을 통제하지 않은 채 외삽한 것이 결정적 약점이었다. 멱법칙 자체는 살아남았지만 계수는 틀렸다.

---

## ⚠️ 모순 / 재검토
- ⚠️ [[2022-chinchilla-compute-optimal]]와 어긋남 — 최적 모델:데이터 배분이 상반됨. 학습률 스케줄 통제 여부가 원인. 본 노트의 권고는 폐기(superseded).

## 연결
- [[2022-chinchilla-compute-optimal]] — 본 논문의 compute-optimal 권고를 반박·대체.
- [[2020-gpt3-few-shot-learners]] — 이 법칙을 근거로 규모를 설계한 사례.
