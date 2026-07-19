---
type: concept
aliases: ["트랜스포머"]
tags: [architecture, core]
papers: ["[[2017-attention-is-all-you-need]]", "[[2018-bert-pretraining]]", "[[2020-gpt3-few-shot-learners]]"]
related_concepts: ["[[attention-mechanism]]", "[[self-supervised-learning]]"]
---

# Transformer

## 한 줄 정의
self-attention을 주 연산으로 하는 완전 병렬 시퀀스 아키텍처.

## 핵심
순차 계산을 제거해 규모 확장의 문을 연 구조. [[2017-attention-is-all-you-need]]가 인코더-디코더로 제안했고, [[2018-bert-pretraining]]는 인코더만(양방향 이해), [[2020-gpt3-few-shot-learners]]는 디코더만(생성) 떼어 각자의 패러다임을 만들었다. 같은 부품이 어느 쪽을 쓰느냐에 따라 이해/생성 노선으로 갈라진 점이 흥미로운 지점.

## 등장 논문
- [[2017-attention-is-all-you-need]] — 아키텍처 원전.
- [[2018-bert-pretraining]] — 인코더 스택 + MLM 사전학습.
- [[2020-gpt3-few-shot-learners]] — 디코더 스택을 175B로 확장.

## ⚠️ 이견 / 모순
-

## 관련 개념
- [[attention-mechanism]] — 핵심 구성 연산.
- [[self-supervised-learning]] — 이 구조를 채우는 학습 신호.
