---
title: "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models"
authors: "Jason Wei et al."
year: 2022
venue: "NeurIPS 2022"
tags: [reasoning, prompting, cot]
status: studied
date_read: "2026-05-10"
related_papers: ["[[2020-gpt3-few-shot-learners]]", "[[2022-self-consistency]]", "[[2023-tree-of-thoughts]]", "[[2023-unfaithful-cot]]"]
concepts: ["[[chain-of-thought]]", "[[in-context-learning]]"]
my_rating: 5
review_weak_spots: []
next_review: "2026-09-01"
supersedes: []
superseded_by: []
contradicts: ["[[2023-unfaithful-cot]]"]
---

# Chain-of-Thought Prompting Elicits Reasoning in LLMs

## TL;DR
few-shot 예시에 **중간 추론 단계를 적어주기만 하면** 대형 모델의 수리·상식 추론이 급상승. 이 효과는 충분한 규모에서만 창발.

## 문제 / 동기
표준 프롬프트로는 LLM이 다단계 추론 문제(산수, 상식 추론)에서 실패한다.

## 핵심 아이디어 / 방법
"답: 11" 대신 "롤은 공 5개로 시작했다. … 그래서 11"처럼 풀이 과정을 포함한 예시 8개를 프롬프트에 넣는다. 모델 수정 없음.

## 결과
PaLM 540B + CoT가 GSM8K에서 파인튜닝 GPT-3를 능가. ~100B 미만 모델에선 효과 미미(창발성).

## 개념
- [[chain-of-thought]]
- [[in-context-learning]]

## 능동 회상 (복습용 — 답은 접힘)

**Q1.** CoT 효과가 작은 모델에서 안 나타나는 이유로 제시된 가설은?
<details><summary>답</summary>
작은 모델은 유창하지만 논리적으로 틀린 사슬을 만들어, 중간 단계가 오히려 오류 전파 경로가 된다.
</details>

---

## ✍️ 내 파인만 재설명
문제를 풀 때 "풀이 과정을 보여주는 예시"를 먼저 보여주면, 모델도 풀이를 흉내 내며 한 번에 못 풀던 문제를 단계별로 풀게 된다.

## 💡 내 연구에의 적용
내 도메인의 다단계 판단 태스크 프롬프트에 중간 근거 서술을 넣어 ablation 해볼 것.

## 🤔 내 의견 / 비판
생성된 사슬이 실제 계산 과정인지 사후 합리화인지 이 논문은 답하지 않는다 — [[2023-unfaithful-cot]]가 정면으로 반박.

---

## ⚠️ 모순 / 재검토
- ⚠️ [[2023-unfaithful-cot]]와 어긋남 — CoT가 모델의 실제 추론을 반영한다는 해석에 반증. 편향 주입 실험에서 사슬이 진짜 이유를 숨김. 성능 향상 자체는 양립 가능하므로 contradicts(병존)로 기록.

## 연결
- [[2020-gpt3-few-shot-learners]] — CoT는 ICL 위에서 작동하는 기법.
- [[2022-self-consistency]] — 사슬 여러 개를 표집해 다수결로 보강.
- [[2023-tree-of-thoughts]] — 선형 사슬을 탐색 트리로 일반화.
- [[2023-unfaithful-cot]] — 사슬의 신실성(faithfulness)에 대한 반박.
