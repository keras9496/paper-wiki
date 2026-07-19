---
title: "Self-Consistency Improves Chain of Thought Reasoning in Language Models"
authors: "Xuezhi Wang et al."
year: 2022
venue: "ICLR 2023"
tags: [reasoning, cot, decoding]
status: studied
date_read: "2026-05-14"
related_papers: ["[[2022-chain-of-thought-prompting]]", "[[2023-tree-of-thoughts]]"]
concepts: ["[[chain-of-thought]]"]
my_rating: 3
review_weak_spots: []
next_review: ""
supersedes: []
superseded_by: []
contradicts: []
---

# Self-Consistency Improves Chain of Thought Reasoning

## TL;DR
CoT 사슬을 greedy로 1개 뽑는 대신 **temperature 표집으로 여러 개 뽑아 최종 답을 다수결** — 같은 답에 도달하는 경로가 많을수록 그 답이 맞을 확률이 높다는 직관.

## 문제 / 동기
단일 사슬은 한 번의 실수로 전체가 틀어진다(greedy decoding의 취약성).

## 핵심 아이디어 / 방법
동일 CoT 프롬프트에서 사슬 40개를 표집하고, 사슬은 버리고 최종 답만 모아 최빈값을 채택. 학습·파인튜닝 불필요.

## 결과
GSM8K +17.9%p 등 산술·상식 추론 전반에서 CoT 단독 대비 큰 폭 향상.

## 개념
- [[chain-of-thought]]

## 능동 회상 (복습용 — 답은 접힘)

**Q1.** 다수결이 통하려면 오류에 어떤 가정이 필요한가?
<details><summary>답</summary>
틀린 경로들의 답은 서로 흩어지고(비상관 오류), 맞는 경로들은 같은 답에 수렴한다는 가정.
</details>

---

## ✍️ 내 파인만 재설명
한 명이 푼 풀이를 믿지 말고, 같은 학생에게 40번 다르게 풀게 해서 가장 많이 나온 답을 채택하는 것.

## 💡 내 연구에의 적용
LLM 평가 파이프라인에서 단일 응답 대신 k-표집 다수결을 기본값으로.

## 🤔 내 의견 / 비판
비용이 표집 수에 비례해 커진다. 답이 자유서술형이면 "같은 답" 판정 자체가 어렵다.

---

## ⚠️ 모순 / 재검토
- 없음

## 연결
- [[2022-chain-of-thought-prompting]] — 이 기법의 토대. 디코딩 측에서 보강.
- [[2023-tree-of-thoughts]] — 표집·다수결을 넘어 명시적 탐색으로.
