---
title: "Neural Machine Translation by Jointly Learning to Align and Translate"
authors: "Dzmitry Bahdanau, Kyunghyun Cho, Yoshua Bengio"
year: 2014
venue: "ICLR 2015"
tags: [nmt, attention, seq2seq]
status: studied
date_read: "2026-03-02"
related_papers: ["[[2017-attention-is-all-you-need]]"]
concepts: ["[[attention-mechanism]]"]
my_rating: 4
review_weak_spots: []
next_review: ""
supersedes: []
superseded_by: []
contradicts: []
---

# Neural Machine Translation by Jointly Learning to Align and Translate

## TL;DR
고정 길이 벡터 병목을 없애기 위해, 디코더가 매 시점 소스 문장의 어느 부분을 볼지 **가중치(soft alignment)로 스스로 선택**하게 한 최초의 attention NMT.

## 문제 / 동기
기존 seq2seq는 문장 전체를 하나의 고정 벡터로 압축해 긴 문장에서 성능이 급락했다.

## 핵심 아이디어 / 방법
디코더 상태와 인코더의 각 hidden state 사이의 정렬 점수를 작은 신경망으로 계산하고, softmax 가중합으로 context 벡터를 매 시점 새로 만든다. 정렬을 별도 감독 없이 번역 손실만으로 학습한다.

## 결과
긴 문장에서 BLEU 하락이 크게 완화. 정렬 시각화가 실제 언어학적 대응과 유사.

## 개념
- [[attention-mechanism]]

## 능동 회상 (복습용 — 답은 접힘)

**Q1.** 고정 벡터 병목이 긴 문장에서 특히 문제가 되는 이유는?
<details><summary>답</summary>
문장이 길수록 압축해야 할 정보량이 늘지만 벡터 차원은 고정이라, 초반 토큰 정보가 소실된다.
</details>

**Q2.** 이 논문의 attention이 "soft"인 이유는?
<details><summary>답</summary>
하나의 소스 위치를 선택(hard)하는 게 아니라 softmax 확률로 모든 위치를 가중합하므로 미분 가능하다.
</details>

---

## ✍️ 내 파인만 재설명
번역할 때 사람처럼 "지금 이 단어를 옮기려면 원문 어디를 봐야 하지?"를 매 단어마다 다시 묻는 구조. 그 '어디'를 점수로 매겨 섞어 쓴다.

## 💡 내 연구에의 적용
시계열 정렬이 필요한 내 데이터에서 soft alignment 가중치를 해석 도구로 쓸 수 있겠다.

## 🤔 내 의견 / 비판
RNN 순차 처리 병목은 그대로라 병렬화가 안 된다. 이 한계가 [[2017-attention-is-all-you-need]]의 출발점.

---

## ⚠️ 모순 / 재검토
- 없음

## 연결
- [[2017-attention-is-all-you-need]] — 이 논문의 attention만 남기고 RNN을 제거해 일반화.
- [[attention-mechanism]] — 개념의 원형을 제시한 논문.
