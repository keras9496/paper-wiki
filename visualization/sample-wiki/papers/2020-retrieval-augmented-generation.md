---
title: "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks"
authors: "Patrick Lewis et al."
year: 2020
venue: "NeurIPS 2020"
tags: [rag, retrieval, knowledge]
status: studied
date_read: "2026-04-15"
related_papers: ["[[2020-dense-passage-retrieval]]", "[[2020-gpt3-few-shot-learners]]", "[[2023-self-rag]]"]
concepts: ["[[retrieval-augmented-generation]]"]
my_rating: 4
review_weak_spots: []
next_review: ""
supersedes: []
superseded_by: []
contradicts: []
---

# Retrieval-Augmented Generation for Knowledge-Intensive NLP

## TL;DR
생성 모델이 답을 **파라미터에서 꺼내는 대신 외부 문서를 검색해 조건화**하도록 결합(RAG). 지식집약 태스크에서 순수 생성 모델을 능가하고, 지식 갱신이 재학습 없이 가능.

## 문제 / 동기
파라미터에 지식을 욱여넣는 방식은 환각이 잦고, 지식을 갱신하려면 재학습이 필요하다.

## 핵심 아이디어 / 방법
[[2020-dense-passage-retrieval]] 리트리버로 위키 문서를 찾아 BART 생성기에 붙인다. 검색된 문서를 잠재변수로 보고 리트리버·생성기를 end-to-end로 함께 학습.

## 결과
open-domain QA 3종 SOTA. 생성 답변의 사실성·구체성이 향상.

## 개념
- [[retrieval-augmented-generation]]

## 능동 회상 (복습용 — 답은 접힘)

**Q1.** RAG-Sequence와 RAG-Token의 차이는?
<details><summary>답</summary>
Sequence는 문서 하나로 전체 답을 생성해 주변화, Token은 토큰마다 다른 문서를 참조할 수 있게 주변화한다.
</details>

---

## ✍️ 내 파인만 재설명
시험 볼 때 다 외워서 쓰는 대신 오픈북으로 만들어준 것. 게다가 어떤 페이지를 펴는 게 좋은지도 시험 점수로부터 같이 배운다.

## 💡 내 연구에의 적용
내 도메인 문헌 QA에 파인튜닝 대신 RAG 파이프라인을 먼저 시도할 것.

## 🤔 내 의견 / 비판
리트리버가 틀리면 생성기가 그대로 틀린 근거를 신뢰하는 문제. 검색 여부/시점을 스스로 판단 못 함 — [[2023-self-rag]]가 이 지점을 공략.

---

## ⚠️ 모순 / 재검토
- 없음

## 연결
- [[2020-dense-passage-retrieval]] — 리트리버 구성요소.
- [[2020-gpt3-few-shot-learners]] — 파라미터 내부 지식 노선과의 대조축.
- [[2023-self-rag]] — 검색 시점·인용 자기평가로 확장한 후속.
