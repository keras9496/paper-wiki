---
type: concept
aliases: ["자기지도학습", "SSL"]
tags: [training, core]
papers: ["[[2018-bert-pretraining]]"]
related_concepts: ["[[transformer]]", "[[scaling-laws]]"]
---

# Self-Supervised Learning

## 한 줄 정의
데이터 자체에서 만든 과제(마스킹 복원, 다음 토큰 예측 등)로 라벨 없이 표현을 학습하는 방식.

## 핵심
라벨 비용 없이 웹 규모 데이터를 전부 학습 신호로 바꾼다는 점이 LLM 시대를 연 열쇠. [[2018-bert-pretraining]]의 MLM이 대표 사례. 다음 토큰 예측(GPT류)도 같은 범주다.

## 등장 논문
- [[2018-bert-pretraining]] — MLM + NSP로 "사전학습→파인튜닝" 패러다임 확립.

## ⚠️ 이견 / 모순
-

## 관련 개념
- [[transformer]] — 이 신호로 채워지는 그릇.
- [[scaling-laws]] — 자기지도 신호가 규모와 만나면 나타나는 규칙성.
