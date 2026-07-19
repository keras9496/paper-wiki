---
type: concept
aliases: ["RAG", "검색 증강 생성"]
tags: [knowledge, system]
papers: ["[[2020-retrieval-augmented-generation]]", "[[2020-dense-passage-retrieval]]", "[[2023-self-rag]]"]
related_concepts: ["[[transformer]]"]
---

# Retrieval-Augmented Generation

## 한 줄 정의
생성 모델이 외부 지식원을 검색해 그 결과에 조건화하여 답을 만드는 구조.

## 핵심
"지식을 파라미터에 넣을 것인가, 밖에 둘 것인가"라는 축의 '밖' 진영. [[2020-dense-passage-retrieval]]이 검색기를, [[2020-retrieval-augmented-generation]]이 결합 학습을 제공했고, [[2023-self-rag]]는 "항상 검색"의 비효율을 자기성찰 토큰으로 고쳤다 — 검색이 고정 파이프라인에서 모델의 판단 대상으로 내려온 흐름.

## 등장 논문
- [[2020-dense-passage-retrieval]] — dual-encoder 밀집 검색기.
- [[2020-retrieval-augmented-generation]] — 검색+생성 end-to-end 결합의 원전.
- [[2023-self-rag]] — 검색 시점·근거성 자기평가로 확장 (읽는 중).

## ⚠️ 이견 / 모순
-

## 관련 개념
- [[transformer]] — 검색기(인코더)와 생성기(디코더) 양쪽의 백본.
