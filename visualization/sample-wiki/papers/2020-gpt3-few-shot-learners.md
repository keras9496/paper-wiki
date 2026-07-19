---
title: "Language Models are Few-Shot Learners"
authors: "Tom B. Brown et al."
year: 2020
venue: "NeurIPS 2020"
tags: [llm, in-context-learning, scaling]
status: studied
date_read: "2026-03-20"
related_papers: ["[[2018-bert-pretraining]]", "[[2020-scaling-laws-neural-lm]]", "[[2022-chain-of-thought-prompting]]", "[[2020-retrieval-augmented-generation]]"]
concepts: ["[[in-context-learning]]", "[[scaling-laws]]", "[[transformer]]"]
my_rating: 5
review_weak_spots: ["ICL의 메커니즘 가설"]
next_review: "2026-08-15"
supersedes: []
superseded_by: []
contradicts: []
---

# Language Models are Few-Shot Learners (GPT-3)

## TL;DR
175B 파라미터 언어모델은 **가중치 업데이트 없이 프롬프트 속 예시만으로** 새 태스크를 수행(in-context learning)하며, 이 능력은 규모와 함께 자란다.

## 문제 / 동기
BERT식 패러다임은 태스크마다 파인튜닝 데이터셋과 별도 모델이 필요하다. 사람은 예시 몇 개면 되는데.

## 핵심 아이디어 / 방법
Transformer 디코더를 175B까지 확장하고 대규모 웹 코퍼스로 다음 토큰 예측만 학습. 평가 시 zero/one/few-shot 프롬프트로 태스크를 "설명"만 한다.

## 결과
다수 태스크에서 few-shot으로 파인튜닝 모델에 근접. 모델이 클수록 ICL 이득이 커짐 — [[scaling-laws]]의 실증.

## 개념
- [[in-context-learning]]
- [[scaling-laws]]
- [[transformer]]

## 능동 회상 (복습용 — 답은 접힘)

**Q1.** few-shot 예시는 gradient를 바꾸지 않는데 왜 성능이 오르나?
<details><summary>답</summary>
확정된 답은 없음. 프롬프트가 사전학습에서 배운 태스크 분포를 조건화한다는 가설(암묵적 베이지안 추론/메타학습)이 유력.
</details>

---

## ✍️ 내 파인만 재설명
방대한 텍스트로 "다음 단어 맞히기"만 시켰더니, 예시 몇 개를 보여주면 그 패턴을 즉석에서 흉내 내는 능력이 규모와 함께 생겨났다.

## 💡 내 연구에의 적용
소규모 라벨 상황에서 파인튜닝 대신 few-shot 프롬프트 베이스라인을 먼저 깔 것.

## 🤔 내 의견 / 비판
암기 vs 일반화 구분이 불명확하고, 데이터 오염 통제가 약하다. 폐쇄형 지식은 환각 문제가 심각 — [[2020-retrieval-augmented-generation]]이 이 지점을 공략.

---

## ⚠️ 모순 / 재검토
- 없음

## 연결
- [[2018-bert-pretraining]] — 파인튜닝 패러다임과의 대조축.
- [[2020-scaling-laws-neural-lm]] — 이 모델의 규모 설계 근거.
- [[2022-chain-of-thought-prompting]] — ICL 위에서 추론 단계를 끌어내는 후속.
- [[2020-retrieval-augmented-generation]] — 파라미터 내부 지식의 한계를 외부 검색으로 보완하는 노선.
