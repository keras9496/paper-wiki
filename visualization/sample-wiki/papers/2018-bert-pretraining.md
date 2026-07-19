---
title: "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding"
authors: "Jacob Devlin, Ming-Wei Chang, Kenton Lee, Kristina Toutanova"
year: 2018
venue: "NAACL 2019"
tags: [pretraining, transformer, nlp]
status: studied
date_read: "2026-03-12"
related_papers: ["[[2017-attention-is-all-you-need]]", "[[2020-gpt3-few-shot-learners]]"]
concepts: ["[[transformer]]", "[[self-supervised-learning]]"]
my_rating: 4
review_weak_spots: []
next_review: ""
supersedes: []
superseded_by: []
contradicts: []
---

# BERT: Pre-training of Deep Bidirectional Transformers

## TL;DR
마스킹된 단어 맞히기(MLM)라는 **자기지도 과제**로 Transformer 인코더를 사전학습하면, 소량의 라벨로도 다양한 NLP 태스크에서 SOTA가 됨을 보임.

## 문제 / 동기
태스크마다 라벨 데이터를 새로 모아 처음부터 학습하는 방식은 비싸고 성능 상한이 낮다.

## 핵심 아이디어 / 방법
문장의 15%를 [MASK]로 가리고 양방향 문맥으로 복원하는 MLM + 다음 문장 예측(NSP)으로 사전학습 후, 태스크별 얇은 헤드만 붙여 파인튜닝.

## 결과
GLUE, SQuAD 등 11개 벤치마크 동시 경신. "사전학습 → 파인튜닝" 패러다임 확립.

## 개념
- [[transformer]]
- [[self-supervised-learning]]

## 능동 회상 (복습용 — 답은 접힘)

**Q1.** GPT류(단방향)와 달리 BERT가 양방향일 수 있는 이유는?
<details><summary>답</summary>
다음 토큰 예측이 아니라 가려진 토큰 복원이 목표라, 좌우 문맥을 모두 보아도 정답 누출이 없다.
</details>

---

## ✍️ 내 파인만 재설명
빈칸 뚫린 문장을 수없이 풀게 해서 언어의 통계적 구조를 먼저 익히게 한 뒤, 실제 시험(다운스트림 태스크)은 가볍게 적응만 시키는 방식.

## 💡 내 연구에의 적용
라벨이 부족한 내 도메인 데이터에 MLM식 사전학습을 먼저 돌리는 파이프라인 검토.

## 🤔 내 의견 / 비판
NSP의 기여는 이후 연구(RoBERTa)에서 의문시됨. [MASK] 토큰이 파인튜닝 시엔 없다는 train-test 불일치도 찜찜하다.

---

## ⚠️ 모순 / 재검토
- 없음

## 연결
- [[2017-attention-is-all-you-need]] — 인코더 아키텍처를 그대로 차용.
- [[2020-gpt3-few-shot-learners]] — 파인튜닝 없이 프롬프트만으로 적응하는 반대 노선.
- [[self-supervised-learning]] — MLM이 이 개념의 대표 사례.
