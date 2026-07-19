---
title: "Tree of Thoughts: Deliberate Problem Solving with Large Language Models"
authors: "Shunyu Yao et al."
year: 2023
venue: "NeurIPS 2023"
tags: [reasoning, search, cot]
status: studied
date_read: "2026-05-20"
related_papers: ["[[2022-chain-of-thought-prompting]]", "[[2022-self-consistency]]"]
concepts: ["[[chain-of-thought]]"]
my_rating: 4
review_weak_spots: ["BFS/DFS 선택 기준"]
next_review: ""
supersedes: []
superseded_by: []
contradicts: []
---

# Tree of Thoughts: Deliberate Problem Solving with LLMs

## TL;DR
선형 CoT를 **트리 탐색으로 일반화**: 중간 "생각"을 여러 개 생성하고, 모델 스스로 각 상태를 평가해 유망한 가지만 BFS/DFS로 확장. 되돌아가기(backtrack)가 가능해짐.

## 문제 / 동기
CoT는 왼쪽→오른쪽 한 방향 생성이라 탐색·계획·백트래킹이 필요한 문제(Game of 24 등)에서 실패.

## 핵심 아이디어 / 방법
문제를 "생각 단위"로 분해 → 각 상태에서 후보 생각 k개 생성 → LM 자체 평가(sure/maybe/impossible)로 가지치기 → BFS/DFS 탐색.

## 결과
Game of 24 성공률: CoT 4% → ToT 74%. 창의적 글쓰기·크로스워드에서도 향상.

## 개념
- [[chain-of-thought]]

## 능동 회상 (복습용 — 답은 접힘)

**Q1.** ToT가 self-consistency와 본질적으로 다른 점은?
<details><summary>답</summary>
self-consistency는 완성된 사슬들을 사후 집계하지만, ToT는 생성 도중 중간 상태를 평가·가지치기하며 탐색을 제어한다.
</details>

---

## ✍️ 내 파인만 재설명
문제 풀이를 외길 산책이 아니라 갈림길 지도로 바꾸고, 갈림길마다 "이 길이 유망한가"를 자문하며 막히면 되돌아온다.

## 💡 내 연구에의 적용
탐색 공간이 명확한 내 최적화 문제에 LM 평가자를 가지치기 휴리스틱으로 쓰는 아이디어.

## 🤔 내 의견 / 비판
호출 수가 폭증해 비용이 크고, "생각 단위" 설계가 태스크마다 수작업이다. 범용성은 과장된 감이 있다.

---

## ⚠️ 모순 / 재검토
- 없음

## 연결
- [[2022-chain-of-thought-prompting]] — 선형 사슬의 일반화.
- [[2022-self-consistency]] — 병렬 표집 노선과의 대조.
