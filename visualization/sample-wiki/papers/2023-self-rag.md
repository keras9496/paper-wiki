---
title: "Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection"
authors: "Akari Asai et al."
year: 2023
venue: "ICLR 2024"
tags: [rag, retrieval, self-reflection]
status: reading
date_read: "2026-05-02"
related_papers: ["[[2020-retrieval-augmented-generation]]", "[[2022-chain-of-thought-prompting]]"]
concepts: ["[[retrieval-augmented-generation]]"]
my_rating:
review_weak_spots: ["reflection token 종류"]
next_review: ""
supersedes: []
superseded_by: []
contradicts: []
---

# Self-RAG: Retrieve, Generate, and Critique through Self-Reflection

## ⏸️ 이어하기 체크포인트
- 완료: Abstract, Intro, Method 절반 (reflection token 정의까지)
- 다음 시작점: Method 3.2 (critic 모델 학습)부터
- 연구 맥락: 내 문헌 QA 파이프라인에서 "검색을 언제 할지" 판단 로직으로 검토 중

## TL;DR
검색을 **항상** 하는 대신, 모델이 reflection token으로 **검색 필요 여부·문서 관련성·답변의 근거성**을 스스로 판단하며 생성하는 RAG.

## 문제 / 동기
[[2020-retrieval-augmented-generation]]는 무조건 검색하므로, 불필요한 검색이 오히려 답을 오염시키거나 근거 없는 생성을 못 거른다.

## 핵심 아이디어 / 방법
[Retrieve], [IsRel], [IsSup], [IsUse] 등 reflection token을 어휘에 추가하고, critic 모델이 만든 라벨로 생성기를 학습. 디코딩 시 이 토큰들로 후보를 재랭킹.

## 결과
(읽는 중 — Results 미도달)

## 개념
- [[retrieval-augmented-generation]]

## 능동 회상 (복습용 — 답은 접힘)

**Q1.** Self-RAG가 기존 RAG와 달리 "검색하지 않기"를 선택할 수 있는 이유는?
<details><summary>답</summary>
[Retrieve] reflection token을 생성 과정에서 예측하도록 학습되어, 질의마다 검색 필요성을 스스로 판단한다.
</details>

**보류 중인 문제:** critic 모델의 학습 데이터는 어떻게 만드나? (다음 세션 첫 출제)

---

## ✍️ 내 파인만 재설명
[읽기 완료 후 작성]

## 💡 내 연구에의 적용
[읽기 완료 후 작성]

## 🤔 내 의견 / 비판
[읽기 완료 후 작성]

---

## ⚠️ 모순 / 재검토
- 없음

## 연결
- [[2020-retrieval-augmented-generation]] — 무조건 검색의 한계를 자기성찰로 보완.
- [[2022-chain-of-thought-prompting]] — "생성 과정에 메타 판단을 삽입"한다는 점에서 유사한 정신.
