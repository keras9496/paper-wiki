window.WIKI_GRAPH = {
  "meta": {
    "wikiRoot": "C:\\Users\\emocog\\Desktop\\오픈소스 프로젝트\\paper-wiki\\visualization\\sample-wiki",
    "counts": {
      "papers": 13,
      "concepts": 7,
      "mocs": 2,
      "edges": 51
    }
  },
  "nodes": [
    {
      "id": "2014-neural-machine-translation-attention",
      "type": "paper",
      "title": "Neural Machine Translation by Jointly Learning to Align and Translate",
      "tags": [
        "nmt",
        "attention",
        "seq2seq"
      ],
      "year": 2014,
      "authors": "Dzmitry Bahdanau, Kyunghyun Cho, Yoshua Bengio",
      "venue": "ICLR 2015",
      "status": "studied",
      "rating": 4,
      "dateRead": "2026-03-02",
      "tldr": "고정 길이 벡터 병목을 없애기 위해, 디코더가 매 시점 소스 문장의 어느 부분을 볼지 가중치(soft alignment)로 스스로 선택하게 한 최초의 attention NMT.",
      "concepts": [
        "attention-mechanism"
      ],
      "degree": 2,
      "primaryConcept": "attention-mechanism"
    },
    {
      "id": "2017-attention-is-all-you-need",
      "type": "paper",
      "title": "Attention Is All You Need",
      "tags": [
        "transformer",
        "attention",
        "architecture"
      ],
      "year": 2017,
      "authors": "Ashish Vaswani et al.",
      "venue": "NeurIPS 2017",
      "status": "studied",
      "rating": 5,
      "dateRead": "2026-03-05",
      "tldr": "RNN/CNN 없이 self-attention만으로 시퀀스를 처리하는 Transformer를 제안. 완전 병렬 학습이 가능해져 이후 대규모 언어모델의 기반이 됨.",
      "concepts": [
        "attention-mechanism",
        "transformer"
      ],
      "degree": 5,
      "primaryConcept": "attention-mechanism"
    },
    {
      "id": "2018-bert-pretraining",
      "type": "paper",
      "title": "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding",
      "tags": [
        "pretraining",
        "transformer",
        "nlp"
      ],
      "year": 2018,
      "authors": "Jacob Devlin, Ming-Wei Chang, Kenton Lee, Kristina Toutanova",
      "venue": "NAACL 2019",
      "status": "studied",
      "rating": 4,
      "dateRead": "2026-03-12",
      "tldr": "마스킹된 단어 맞히기(MLM)라는 자기지도 과제로 Transformer 인코더를 사전학습하면, 소량의 라벨로도 다양한 NLP 태스크에서 SOTA가 됨을 보임.",
      "concepts": [
        "transformer",
        "self-supervised-learning"
      ],
      "degree": 5,
      "primaryConcept": "transformer"
    },
    {
      "id": "2020-dense-passage-retrieval",
      "type": "paper",
      "title": "Dense Passage Retrieval for Open-Domain Question Answering",
      "tags": [
        "retrieval",
        "dense",
        "qa"
      ],
      "year": 2020,
      "authors": "Vladimir Karpukhin et al.",
      "venue": "EMNLP 2020",
      "status": "studied",
      "rating": 3,
      "dateRead": "2026-04-12",
      "tldr": "BM25 같은 희소 검색 대신, 질문·문서를 각각 BERT로 임베딩해 내적으로 검색하는 DPR. 소량의 QA 쌍만으로 학습해도 BM25를 크게 앞섬.",
      "concepts": [
        "retrieval-augmented-generation"
      ],
      "degree": 4,
      "primaryConcept": "retrieval-augmented-generation"
    },
    {
      "id": "2020-gpt3-few-shot-learners",
      "type": "paper",
      "title": "Language Models are Few-Shot Learners",
      "tags": [
        "llm",
        "in-context-learning",
        "scaling"
      ],
      "year": 2020,
      "authors": "Tom B. Brown et al.",
      "venue": "NeurIPS 2020",
      "status": "studied",
      "rating": 5,
      "dateRead": "2026-03-20",
      "tldr": "175B 파라미터 언어모델은 가중치 업데이트 없이 프롬프트 속 예시만으로 새 태스크를 수행(in-context learning)하며, 이 능력은 규모와 함께 자란다.",
      "concepts": [
        "in-context-learning",
        "scaling-laws",
        "transformer"
      ],
      "degree": 11,
      "primaryConcept": "in-context-learning"
    },
    {
      "id": "2020-retrieval-augmented-generation",
      "type": "paper",
      "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
      "tags": [
        "rag",
        "retrieval",
        "knowledge"
      ],
      "year": 2020,
      "authors": "Patrick Lewis et al.",
      "venue": "NeurIPS 2020",
      "status": "studied",
      "rating": 4,
      "dateRead": "2026-04-15",
      "tldr": "생성 모델이 답을 파라미터에서 꺼내는 대신 외부 문서를 검색해 조건화하도록 결합(RAG). 지식집약 태스크에서 순수 생성 모델을 능가하고, 지식 갱신이 재학습 없이 가능.",
      "concepts": [
        "retrieval-augmented-generation"
      ],
      "degree": 5,
      "primaryConcept": "retrieval-augmented-generation"
    },
    {
      "id": "2020-scaling-laws-neural-lm",
      "type": "paper",
      "title": "Scaling Laws for Neural Language Models",
      "tags": [
        "scaling",
        "llm",
        "empirical"
      ],
      "year": 2020,
      "authors": "Jared Kaplan, Sam McCandlish et al.",
      "venue": "arXiv",
      "status": "studied",
      "rating": 4,
      "dateRead": "2026-04-01",
      "tldr": "LM 손실은 파라미터 수·데이터·연산량 각각에 대해 매끈한 멱법칙(power law)을 따르며, 고정 연산 예산에서는 모델을 키우는 쪽이 데이터를 늘리는 것보다 유리하다고 주장.",
      "concepts": [
        "scaling-laws"
      ],
      "degree": 4,
      "primaryConcept": "scaling-laws"
    },
    {
      "id": "2022-chain-of-thought-prompting",
      "type": "paper",
      "title": "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models",
      "tags": [
        "reasoning",
        "prompting",
        "cot"
      ],
      "year": 2022,
      "authors": "Jason Wei et al.",
      "venue": "NeurIPS 2022",
      "status": "studied",
      "rating": 5,
      "dateRead": "2026-05-10",
      "tldr": "few-shot 예시에 중간 추론 단계를 적어주기만 하면 대형 모델의 수리·상식 추론이 급상승. 이 효과는 충분한 규모에서만 창발.",
      "concepts": [
        "chain-of-thought",
        "in-context-learning"
      ],
      "degree": 7,
      "primaryConcept": "chain-of-thought"
    },
    {
      "id": "2022-chinchilla-compute-optimal",
      "type": "paper",
      "title": "Training Compute-Optimal Large Language Models",
      "tags": [
        "scaling",
        "llm",
        "empirical"
      ],
      "year": 2022,
      "authors": "Jordan Hoffmann et al. (DeepMind)",
      "venue": "NeurIPS 2022",
      "status": "studied",
      "rating": 5,
      "dateRead": "2026-04-03",
      "tldr": "학습률 스케줄을 통제해 다시 재보니, 최적점은 모델과 데이터를 같은 비율로 키우는 것(≈ 파라미터 1개당 토큰 20개). 4배 작은 Chinchilla(70B)가 Gopher(280B)를 이김.",
      "concepts": [
        "scaling-laws"
      ],
      "degree": 4,
      "primaryConcept": "scaling-laws"
    },
    {
      "id": "2022-self-consistency",
      "type": "paper",
      "title": "Self-Consistency Improves Chain of Thought Reasoning in Language Models",
      "tags": [
        "reasoning",
        "cot",
        "decoding"
      ],
      "year": 2022,
      "authors": "Xuezhi Wang et al.",
      "venue": "ICLR 2023",
      "status": "studied",
      "rating": 3,
      "dateRead": "2026-05-14",
      "tldr": "CoT 사슬을 greedy로 1개 뽑는 대신 temperature 표집으로 여러 개 뽑아 최종 답을 다수결 — 같은 답에 도달하는 경로가 많을수록 그 답이 맞을 확률이 높다는 직관.",
      "concepts": [
        "chain-of-thought"
      ],
      "degree": 3,
      "primaryConcept": "chain-of-thought"
    },
    {
      "id": "2023-self-rag",
      "type": "paper",
      "title": "Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection",
      "tags": [
        "rag",
        "retrieval",
        "self-reflection"
      ],
      "year": 2023,
      "authors": "Akari Asai et al.",
      "venue": "ICLR 2024",
      "status": "reading",
      "rating": null,
      "dateRead": "2026-05-02",
      "tldr": "검색을 항상 하는 대신, 모델이 reflection token으로 검색 필요 여부·문서 관련성·답변의 근거성을 스스로 판단하며 생성하는 RAG.",
      "concepts": [
        "retrieval-augmented-generation"
      ],
      "degree": 4,
      "primaryConcept": "retrieval-augmented-generation"
    },
    {
      "id": "2023-tree-of-thoughts",
      "type": "paper",
      "title": "Tree of Thoughts: Deliberate Problem Solving with Large Language Models",
      "tags": [
        "reasoning",
        "search",
        "cot"
      ],
      "year": 2023,
      "authors": "Shunyu Yao et al.",
      "venue": "NeurIPS 2023",
      "status": "studied",
      "rating": 4,
      "dateRead": "2026-05-20",
      "tldr": "선형 CoT를 트리 탐색으로 일반화: 중간 \"생각\"을 여러 개 생성하고, 모델 스스로 각 상태를 평가해 유망한 가지만 BFS/DFS로 확장. 되돌아가기(backtrack)가 가능해짐.",
      "concepts": [
        "chain-of-thought"
      ],
      "degree": 3,
      "primaryConcept": "chain-of-thought"
    },
    {
      "id": "2023-unfaithful-cot",
      "type": "paper",
      "title": "Language Models Don't Always Say What They Think: Unfaithful Explanations in Chain-of-Thought Prompting",
      "tags": [
        "reasoning",
        "cot",
        "interpretability",
        "safety"
      ],
      "year": 2023,
      "authors": "Miles Turpin, Julian Michael, Ethan Perez, Samuel R. Bowman",
      "venue": "NeurIPS 2023",
      "status": "studied",
      "rating": 5,
      "dateRead": "2026-06-01",
      "tldr": "프롬프트에 몰래 편향(예: 정답이 항상 A)을 심으면 모델 답이 그 편향을 따라가는데, CoT 설명은 편향을 한 번도 언급하지 않고 그럴듯한 다른 이유를 댄다 — 사슬은 실제 결정 과정의 신실한(faithful) 기록이 아니다.",
      "concepts": [
        "chain-of-thought"
      ],
      "degree": 2,
      "primaryConcept": "chain-of-thought"
    },
    {
      "id": "attention-mechanism",
      "type": "concept",
      "title": "Attention Mechanism",
      "tags": [
        "architecture",
        "core"
      ],
      "aliases": [
        "어텐션",
        "soft alignment"
      ],
      "tldr": "입력의 각 부분에 대한 관련도 가중치를 계산해, 매 시점 필요한 정보만 가중합으로 끌어오는 연산.",
      "degree": 3,
      "paperCount": 2
    },
    {
      "id": "chain-of-thought",
      "type": "concept",
      "title": "Chain-of-Thought",
      "tags": [
        "reasoning",
        "prompting"
      ],
      "aliases": [
        "CoT",
        "사고 사슬"
      ],
      "tldr": "최종 답 전에 중간 추론 단계를 생성하게 하여 다단계 문제 해결력을 끌어내는 프롬프트 기법.",
      "degree": 5,
      "paperCount": 4
    },
    {
      "id": "in-context-learning",
      "type": "concept",
      "title": "In-Context Learning",
      "tags": [
        "capability",
        "emergent"
      ],
      "aliases": [
        "ICL",
        "문맥 내 학습"
      ],
      "tldr": "가중치 갱신 없이, 프롬프트에 담긴 예시만으로 새 태스크에 적응하는 능력.",
      "degree": 5,
      "paperCount": 2
    },
    {
      "id": "retrieval-augmented-generation",
      "type": "concept",
      "title": "Retrieval-Augmented Generation",
      "tags": [
        "knowledge",
        "system"
      ],
      "aliases": [
        "RAG",
        "검색 증강 생성"
      ],
      "tldr": "생성 모델이 외부 지식원을 검색해 그 결과에 조건화하여 답을 만드는 구조.",
      "degree": 5,
      "paperCount": 3
    },
    {
      "id": "scaling-laws",
      "type": "concept",
      "title": "Scaling Laws",
      "tags": [
        "empirical",
        "core"
      ],
      "aliases": [
        "스케일링 법칙",
        "멱법칙 스케일링"
      ],
      "tldr": "모델 크기·데이터·연산량과 손실 사이에 나타나는 매끈한 멱법칙 관계.",
      "degree": 6,
      "paperCount": 3
    },
    {
      "id": "self-supervised-learning",
      "type": "concept",
      "title": "Self-Supervised Learning",
      "tags": [
        "training",
        "core"
      ],
      "aliases": [
        "자기지도학습",
        "SSL"
      ],
      "tldr": "데이터 자체에서 만든 과제(마스킹 복원, 다음 토큰 예측 등)로 라벨 없이 표현을 학습하는 방식.",
      "degree": 3,
      "paperCount": 1
    },
    {
      "id": "transformer",
      "type": "concept",
      "title": "Transformer",
      "tags": [
        "architecture",
        "core"
      ],
      "aliases": [
        "트랜스포머"
      ],
      "tldr": "self-attention을 주 연산으로 하는 완전 병렬 시퀀스 아키텍처.",
      "degree": 6,
      "paperCount": 3
    },
    {
      "id": "llm-scaling-debate",
      "type": "moc",
      "title": "MOC: LLM 스케일링 논쟁 — 모델 vs 데이터",
      "tags": [
        "scaling",
        "synthesis"
      ],
      "tldr": "고정 연산 예산에서 모델 크기와 데이터량을 어떻게 배분해야 하는가, 그리고 왜 두 대표 논문의 답이 달랐는가.",
      "degree": 4
    },
    {
      "id": "parametric-vs-retrieval-knowledge",
      "type": "moc",
      "title": "MOC: 지식은 어디에 두는가 — 파라미터 vs 검색",
      "tags": [
        "knowledge",
        "rag",
        "synthesis"
      ],
      "tldr": "LLM의 지식을 파라미터 내부에 저장하는 노선과 외부 검색으로 보강하는 노선의 트레이드오프.",
      "degree": 6
    }
  ],
  "edges": [
    {
      "source": "2022-chinchilla-compute-optimal",
      "target": "2020-scaling-laws-neural-lm",
      "type": "supersedes",
      "directed": true
    },
    {
      "source": "2022-chain-of-thought-prompting",
      "target": "2023-unfaithful-cot",
      "type": "contradicts",
      "directed": false
    },
    {
      "source": "2014-neural-machine-translation-attention",
      "target": "attention-mechanism",
      "type": "concept",
      "directed": false
    },
    {
      "source": "2017-attention-is-all-you-need",
      "target": "attention-mechanism",
      "type": "concept",
      "directed": false
    },
    {
      "source": "2017-attention-is-all-you-need",
      "target": "transformer",
      "type": "concept",
      "directed": false
    },
    {
      "source": "2018-bert-pretraining",
      "target": "transformer",
      "type": "concept",
      "directed": false
    },
    {
      "source": "2018-bert-pretraining",
      "target": "self-supervised-learning",
      "type": "concept",
      "directed": false
    },
    {
      "source": "2020-dense-passage-retrieval",
      "target": "retrieval-augmented-generation",
      "type": "concept",
      "directed": false
    },
    {
      "source": "2020-gpt3-few-shot-learners",
      "target": "in-context-learning",
      "type": "concept",
      "directed": false
    },
    {
      "source": "2020-gpt3-few-shot-learners",
      "target": "scaling-laws",
      "type": "concept",
      "directed": false
    },
    {
      "source": "2020-gpt3-few-shot-learners",
      "target": "transformer",
      "type": "concept",
      "directed": false
    },
    {
      "source": "2020-retrieval-augmented-generation",
      "target": "retrieval-augmented-generation",
      "type": "concept",
      "directed": false
    },
    {
      "source": "2020-scaling-laws-neural-lm",
      "target": "scaling-laws",
      "type": "concept",
      "directed": false
    },
    {
      "source": "2022-chain-of-thought-prompting",
      "target": "chain-of-thought",
      "type": "concept",
      "directed": false
    },
    {
      "source": "2022-chain-of-thought-prompting",
      "target": "in-context-learning",
      "type": "concept",
      "directed": false
    },
    {
      "source": "2022-chinchilla-compute-optimal",
      "target": "scaling-laws",
      "type": "concept",
      "directed": false
    },
    {
      "source": "2022-self-consistency",
      "target": "chain-of-thought",
      "type": "concept",
      "directed": false
    },
    {
      "source": "2023-self-rag",
      "target": "retrieval-augmented-generation",
      "type": "concept",
      "directed": false
    },
    {
      "source": "2023-tree-of-thoughts",
      "target": "chain-of-thought",
      "type": "concept",
      "directed": false
    },
    {
      "source": "2023-unfaithful-cot",
      "target": "chain-of-thought",
      "type": "concept",
      "directed": false
    },
    {
      "source": "attention-mechanism",
      "target": "transformer",
      "type": "concept-rel",
      "directed": false
    },
    {
      "source": "chain-of-thought",
      "target": "in-context-learning",
      "type": "concept-rel",
      "directed": false
    },
    {
      "source": "in-context-learning",
      "target": "scaling-laws",
      "type": "concept-rel",
      "directed": false
    },
    {
      "source": "retrieval-augmented-generation",
      "target": "transformer",
      "type": "concept-rel",
      "directed": false
    },
    {
      "source": "scaling-laws",
      "target": "self-supervised-learning",
      "type": "concept-rel",
      "directed": false
    },
    {
      "source": "self-supervised-learning",
      "target": "transformer",
      "type": "concept-rel",
      "directed": false
    },
    {
      "source": "llm-scaling-debate",
      "target": "2020-scaling-laws-neural-lm",
      "type": "moc",
      "directed": true
    },
    {
      "source": "llm-scaling-debate",
      "target": "2022-chinchilla-compute-optimal",
      "type": "moc",
      "directed": true
    },
    {
      "source": "llm-scaling-debate",
      "target": "2020-gpt3-few-shot-learners",
      "type": "moc",
      "directed": true
    },
    {
      "source": "llm-scaling-debate",
      "target": "scaling-laws",
      "type": "moc",
      "directed": true
    },
    {
      "source": "parametric-vs-retrieval-knowledge",
      "target": "2020-gpt3-few-shot-learners",
      "type": "moc",
      "directed": true
    },
    {
      "source": "parametric-vs-retrieval-knowledge",
      "target": "2020-retrieval-augmented-generation",
      "type": "moc",
      "directed": true
    },
    {
      "source": "parametric-vs-retrieval-knowledge",
      "target": "2020-dense-passage-retrieval",
      "type": "moc",
      "directed": true
    },
    {
      "source": "parametric-vs-retrieval-knowledge",
      "target": "2023-self-rag",
      "type": "moc",
      "directed": true
    },
    {
      "source": "parametric-vs-retrieval-knowledge",
      "target": "retrieval-augmented-generation",
      "type": "moc",
      "directed": true
    },
    {
      "source": "parametric-vs-retrieval-knowledge",
      "target": "in-context-learning",
      "type": "moc",
      "directed": true
    },
    {
      "source": "2014-neural-machine-translation-attention",
      "target": "2017-attention-is-all-you-need",
      "type": "related",
      "directed": false
    },
    {
      "source": "2017-attention-is-all-you-need",
      "target": "2018-bert-pretraining",
      "type": "related",
      "directed": false
    },
    {
      "source": "2017-attention-is-all-you-need",
      "target": "2020-gpt3-few-shot-learners",
      "type": "related",
      "directed": false
    },
    {
      "source": "2018-bert-pretraining",
      "target": "2020-gpt3-few-shot-learners",
      "type": "related",
      "directed": false
    },
    {
      "source": "2020-dense-passage-retrieval",
      "target": "2020-retrieval-augmented-generation",
      "type": "related",
      "directed": false
    },
    {
      "source": "2020-dense-passage-retrieval",
      "target": "2018-bert-pretraining",
      "type": "related",
      "directed": false
    },
    {
      "source": "2020-gpt3-few-shot-learners",
      "target": "2020-scaling-laws-neural-lm",
      "type": "related",
      "directed": false
    },
    {
      "source": "2020-gpt3-few-shot-learners",
      "target": "2022-chain-of-thought-prompting",
      "type": "related",
      "directed": false
    },
    {
      "source": "2020-gpt3-few-shot-learners",
      "target": "2020-retrieval-augmented-generation",
      "type": "related",
      "directed": false
    },
    {
      "source": "2020-retrieval-augmented-generation",
      "target": "2023-self-rag",
      "type": "related",
      "directed": false
    },
    {
      "source": "2022-chain-of-thought-prompting",
      "target": "2022-self-consistency",
      "type": "related",
      "directed": false
    },
    {
      "source": "2022-chain-of-thought-prompting",
      "target": "2023-tree-of-thoughts",
      "type": "related",
      "directed": false
    },
    {
      "source": "2022-chinchilla-compute-optimal",
      "target": "2020-gpt3-few-shot-learners",
      "type": "related",
      "directed": false
    },
    {
      "source": "2022-self-consistency",
      "target": "2023-tree-of-thoughts",
      "type": "related",
      "directed": false
    },
    {
      "source": "2023-self-rag",
      "target": "2022-chain-of-thought-prompting",
      "type": "related",
      "directed": false
    }
  ]
};
