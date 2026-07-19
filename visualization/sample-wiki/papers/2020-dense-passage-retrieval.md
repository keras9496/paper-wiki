---
title: "Dense Passage Retrieval for Open-Domain Question Answering"
authors: "Vladimir Karpukhin et al."
year: 2020
venue: "EMNLP 2020"
tags: [retrieval, dense, qa]
status: studied
date_read: "2026-04-12"
related_papers: ["[[2020-retrieval-augmented-generation]]", "[[2018-bert-pretraining]]"]
concepts: ["[[retrieval-augmented-generation]]"]
my_rating: 3
review_weak_spots: []
next_review: ""
supersedes: []
superseded_by: []
contradicts: []
---

# Dense Passage Retrieval for Open-Domain QA

## TL;DR
BM25 같은 희소 검색 대신, **질문·문서를 각각 BERT로 임베딩해 내적으로 검색**하는 DPR. 소량의 QA 쌍만으로 학습해도 BM25를 크게 앞섬.

## 문제 / 동기
어휘가 겹치지 않으면 못 찾는 희소 검색의 한계(synonym, paraphrase).

## 핵심 아이디어 / 방법
질문 인코더와 문서 인코더(dual-encoder, 둘 다 [[2018-bert-pretraining]] 기반)를 in-batch negative로 대조학습. 문서 임베딩은 사전 계산해 FAISS로 검색.

## 결과
top-20 검색 정확도에서 BM25 대비 +9~19%p. 이후 RAG류 시스템의 표준 리트리버가 됨.

## 개념
- [[retrieval-augmented-generation]]

## 능동 회상 (복습용 — 답은 접힘)

**Q1.** in-batch negative가 효율적인 이유는?
<details><summary>답</summary>
배치 내 다른 질문의 정답 문서를 내 부정 예시로 재활용하므로, 추가 연산 없이 배치 크기만큼 부정 예시를 얻는다.
</details>

---

## ✍️ 내 파인만 재설명
질문과 문서를 같은 좌표계의 점으로 찍어, 가까운 점을 찾는 문제로 검색을 바꾼 것.

## 💡 내 연구에의 적용
내 코퍼스 검색도 키워드 매칭 대신 dual-encoder 임베딩 검색으로 교체 검토.

## 🤔 내 의견 / 비판
도메인이 바뀌면(제로샷) BM25보다 못한 경우도 보고됨. 하이브리드가 실무 정답인 듯.

---

## ⚠️ 모순 / 재검토
- 없음

## 연결
- [[2020-retrieval-augmented-generation]] — DPR을 리트리버로 사용.
- [[2018-bert-pretraining]] — 두 인코더의 백본.
