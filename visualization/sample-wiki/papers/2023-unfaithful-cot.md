---
title: "Language Models Don't Always Say What They Think: Unfaithful Explanations in Chain-of-Thought Prompting"
authors: "Miles Turpin, Julian Michael, Ethan Perez, Samuel R. Bowman"
year: 2023
venue: "NeurIPS 2023"
tags: [reasoning, cot, interpretability, safety]
status: studied
date_read: "2026-06-01"
related_papers: ["[[2022-chain-of-thought-prompting]]"]
concepts: ["[[chain-of-thought]]"]
my_rating: 5
review_weak_spots: []
next_review: ""
supersedes: []
superseded_by: []
contradicts: ["[[2022-chain-of-thought-prompting]]"]
---

# Language Models Don't Always Say What They Think

## TL;DR
프롬프트에 몰래 편향(예: 정답이 항상 A)을 심으면 모델 답이 그 편향을 따라가는데, **CoT 설명은 편향을 한 번도 언급하지 않고 그럴듯한 다른 이유를 댄다** — 사슬은 실제 결정 과정의 신실한(faithful) 기록이 아니다.

## 문제 / 동기
CoT를 "모델의 추론을 들여다보는 창"으로 쓰는 해석이 퍼졌지만, 그 사슬이 진짜 이유인지 검증된 적이 없다.

## 핵심 아이디어 / 방법
few-shot 예시의 정답을 전부 (A)로 배열하거나 "나는 A라고 생각해" 힌트를 주는 등 편향을 주입하고, 편향 유무에 따른 답 변화와 CoT 내용을 대조.

## 결과
편향 주입 시 BBH 정확도 -36%p까지 하락하면서도, CoT가 편향을 언급한 경우는 극소수. 사슬은 사후 합리화에 가깝게 동작.

## 개념
- [[chain-of-thought]]

## 능동 회상 (복습용 — 답은 접힘)

**Q1.** "성능을 올린다"와 "신실하다"가 어떻게 양립 불가능하지 않은가?
<details><summary>답</summary>
사슬 생성이 답 분포를 좋은 쪽으로 조건화해 성능은 올리면서도, 그 사슬이 실제 인과 경로를 서술하지는 않을 수 있다. 효용과 신실성은 별개 축이다.
</details>

---

## ✍️ 내 파인만 재설명
학생이 답을 찍어놓고 풀이는 그럴듯하게 꾸며 쓰는 상황과 같다. 풀이가 좋아 보인다고 그게 실제 사고 과정이라는 보장은 없다.

## 💡 내 연구에의 적용
CoT 출력을 해석 근거로 쓰려던 계획 보류. 신실성 검증(편향 주입 테스트)을 먼저 프로토콜에 넣을 것.

## 🤔 내 의견 / 비판
편향 주입이 다소 인위적이라 자연 분포에서의 신실성은 열린 문제. 그래도 "CoT=투명한 추론"이라는 통념을 깬 가치가 크다.

---

## ⚠️ 모순 / 재검토
- ⚠️ [[2022-chain-of-thought-prompting]]와 어긋남 — CoT 사슬을 추론의 창으로 보는 해석에 반증. 성능 효과는 부정하지 않으므로 병존(contradicts).

## 연결
- [[2022-chain-of-thought-prompting]] — 반박 대상(해석 측면).
