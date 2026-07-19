---
type: concept
aliases: ["ICL", "문맥 내 학습"]
tags: [capability, emergent]
papers: ["[[2020-gpt3-few-shot-learners]]", "[[2022-chain-of-thought-prompting]]"]
related_concepts: ["[[chain-of-thought]]", "[[scaling-laws]]"]
---

# In-Context Learning

## 한 줄 정의
가중치 갱신 없이, 프롬프트에 담긴 예시만으로 새 태스크에 적응하는 능력.

## 핵심
[[2020-gpt3-few-shot-learners]]가 규모의 부산물로 발견했고, [[2022-chain-of-thought-prompting]]는 예시의 "형식"(풀이 과정 포함 여부)이 능력 발현을 좌우함을 보여 ICL이 단순 패턴 매칭 이상임을 시사했다. 메커니즘(암묵적 메타학습? 베이지안 조건화?)은 아직 열린 문제.

## 등장 논문
- [[2020-gpt3-few-shot-learners]] — 현상의 발견과 명명.
- [[2022-chain-of-thought-prompting]] — 예시 형식을 바꿔 추론 능력을 끌어냄.

## ⚠️ 이견 / 모순
-

## 관련 개념
- [[chain-of-thought]] — ICL 위에서 작동하는 프롬프트 기법.
- [[scaling-laws]] — ICL이 창발하는 규모 조건.
