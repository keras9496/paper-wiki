---
title: "Training Compute-Optimal Large Language Models"
authors: "Jordan Hoffmann et al. (DeepMind)"
year: 2022
venue: "NeurIPS 2022"
tags: [scaling, llm, empirical]
status: studied
date_read: "2026-04-03"
related_papers: ["[[2020-scaling-laws-neural-lm]]", "[[2020-gpt3-few-shot-learners]]"]
concepts: ["[[scaling-laws]]"]
my_rating: 5
review_weak_spots: []
next_review: ""
supersedes: ["[[2020-scaling-laws-neural-lm]]"]
superseded_by: []
contradicts: []
---

# Training Compute-Optimal Large Language Models (Chinchilla)

## TL;DR
학습률 스케줄을 통제해 다시 재보니, 최적점은 **모델과 데이터를 같은 비율로** 키우는 것(≈ 파라미터 1개당 토큰 20개). 4배 작은 Chinchilla(70B)가 Gopher(280B)를 이김.

## 문제 / 동기
[[2020-scaling-laws-neural-lm]]의 권고대로면 대형 모델들이 데이터 부족(undertrained) 상태라는 의심.

## 핵심 아이디어 / 방법
세 가지 독립적 방법(고정 모델 크기 스윕, IsoFLOP 곡선, 파라메트릭 손실 적합)으로 compute-optimal 배분을 재추정. 각 학습마다 학습률 스케줄을 총 스텝 수에 맞춤.

## 결과
세 방법 모두 N과 D를 동비율로 키우라고 수렴. 동일 연산으로 학습한 Chinchilla 70B가 Gopher 280B를 광범위하게 능가.

## 개념
- [[scaling-laws]]

## 능동 회상 (복습용 — 답은 접힘)

**Q1.** Kaplan et al.과 결론이 달라진 방법론적 핵심 차이는?
<details><summary>답</summary>
학습률 스케줄을 각 실험의 실제 학습 길이에 맞춰 통제한 것. Kaplan은 고정 스케줄로 중간 손실을 재서 작은 데이터 쪽 손실을 과대평가했다.
</details>

---

## ✍️ 내 파인만 재설명
앞선 실험이 "큰 모델이 이득"이라 했던 건 자로 잰 방식이 틀렸기 때문. 자를 고쳐 재니 "모델과 데이터를 반반씩 키워라"가 정답이었다.

## 💡 내 연구에의 적용
하이퍼파라미터(특히 스케줄)를 실험 조건에 맞춰 통제하지 않으면 스케일링 결론 자체가 뒤집힐 수 있다 — 내 ablation 설계에 반영.

## 🤔 내 의견 / 비판
추론 비용까지 넣으면 최적점은 더 데이터 쪽으로 이동한다(이후 Llama 계열이 실증). "compute-optimal"은 학습 관점의 최적일 뿐.

---

## ⚠️ 모순 / 재검토
- ⚠️ [[2020-scaling-laws-neural-lm]]와 어긋남 — 최적 배분 결론이 정반대. 원인은 학습률 스케줄 통제. 본 논문이 승계(supersedes).

## 연결
- [[2020-scaling-laws-neural-lm]] — 반박 대상. 방법론 결함을 지목하고 대체.
- [[2020-gpt3-few-shot-learners]] — GPT-3도 이 기준으론 undertrained.
