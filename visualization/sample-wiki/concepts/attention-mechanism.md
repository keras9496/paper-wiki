---
type: concept
aliases: ["어텐션", "soft alignment"]
tags: [architecture, core]
papers: ["[[2014-neural-machine-translation-attention]]", "[[2017-attention-is-all-you-need]]"]
related_concepts: ["[[transformer]]"]
---

# Attention Mechanism

## 한 줄 정의
입력의 각 부분에 대한 관련도 가중치를 계산해, 매 시점 필요한 정보만 가중합으로 끌어오는 연산.

## 핵심
고정 벡터 병목을 없애는 동적 정보 라우팅. [[2014-neural-machine-translation-attention]]에서는 RNN의 보조 장치였지만, [[2017-attention-is-all-you-need]]가 Q·K·V로 일반화하면서 주 연산으로 승격됐다 — "어디를 볼까"라는 같은 질문이 정렬 도구에서 범용 시퀀스 연산으로 진화한 것.

## 등장 논문
- [[2014-neural-machine-translation-attention]] — soft alignment로 최초 도입. RNN 디코더의 보조 장치.
- [[2017-attention-is-all-you-need]] — scaled dot-product + multi-head로 일반화, RNN을 완전히 대체.

## ⚠️ 이견 / 모순
-

## 관련 개념
- [[transformer]] — attention만으로 구성된 아키텍처.
