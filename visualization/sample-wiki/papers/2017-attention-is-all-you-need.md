---
title: "Attention Is All You Need"
authors: "Ashish Vaswani et al."
year: 2017
venue: "NeurIPS 2017"
tags: [transformer, attention, architecture]
status: studied
date_read: "2026-03-05"
related_papers: ["[[2014-neural-machine-translation-attention]]", "[[2018-bert-pretraining]]", "[[2020-gpt3-few-shot-learners]]"]
concepts: ["[[attention-mechanism]]", "[[transformer]]"]
my_rating: 5
review_weak_spots: ["multi-head 이유"]
next_review: "2026-08-01"
supersedes: []
superseded_by: []
contradicts: []
---

# Attention Is All You Need

## TL;DR
RNN/CNN 없이 **self-attention만으로** 시퀀스를 처리하는 Transformer를 제안. 완전 병렬 학습이 가능해져 이후 대규모 언어모델의 기반이 됨.

## 문제 / 동기
RNN 기반 NMT는 순차 계산 탓에 학습이 느리고 장거리 의존성 학습이 어려웠다.

## 핵심 아이디어 / 방법
Q·K·V로 일반화한 scaled dot-product attention을 multi-head로 병렬 수행. 위치 정보는 positional encoding으로 주입. 인코더-디코더 각 6층, residual + layer norm.

## 결과
WMT14 En-De 28.4 BLEU(당시 SOTA), 학습 비용은 기존 대비 수 분의 일.

## 개념
- [[attention-mechanism]]
- [[transformer]]

## 능동 회상 (복습용 — 답은 접힘)

**Q1.** dot-product를 √d_k로 나누는 이유는?
<details><summary>답</summary>
차원이 커지면 내적 분산이 커져 softmax가 포화되고 gradient가 소실되므로 스케일을 정규화한다.
</details>

**Q2.** multi-head가 single-head보다 나은 이유는?
<details><summary>답</summary>
서로 다른 표현 부분공간에서 서로 다른 관계(구문·위치·의미 등)를 동시에 주목할 수 있다.
</details>

---

## ✍️ 내 파인만 재설명
문장의 모든 단어가 회의 테이블에 앉아, 각자 "누구 말을 얼마나 들을지"를 점수로 정해 정보를 섞는 구조. 순서 정보는 자리표(positional encoding)로 준다.

## 💡 내 연구에의 적용
attention map을 변수 간 상호작용 해석에 쓸 수 있을지 실험해 볼 것.

## 🤔 내 의견 / 비판
O(n²) 메모리는 긴 시퀀스에서 여전히 병목. positional encoding 선택이 다소 임의적이라는 인상.

---

## ⚠️ 모순 / 재검토
- 없음

## 연결
- [[2014-neural-machine-translation-attention]] — attention 아이디어의 출처. 본 논문은 RNN을 제거하고 attention을 주 연산으로 승격.
- [[2018-bert-pretraining]] — 이 인코더 스택을 사전학습에 활용.
- [[2020-gpt3-few-shot-learners]] — 이 디코더 스택을 초대형으로 확장.
- [[transformer]] — 개념을 정의한 논문.
