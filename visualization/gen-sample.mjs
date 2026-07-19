#!/usr/bin/env node
/**
 * gen-sample.mjs — 스케일 테스트용 대량 가상 위키 생성기
 *
 * 사용법:  node gen-sample.mjs [논문수] [개념수] [출력폴더]
 * 기본값:  node gen-sample.mjs 90 18 stress-wiki
 * 이후:    node build-graph.mjs stress-wiki stress-graph.js
 *          galaxy.html?data=stress-graph.js 로 열기
 *
 * paper-study 템플릿 스키마와 동일한 md를 합성한다(시드 고정 — 재현 가능).
 * 개념별 논문 수는 지프 분포 — 실제 위키처럼 큰 항성계와 작은 항성계가 섞이게.
 */
import { writeFileSync, mkdirSync, rmSync, existsSync } from 'node:fs';
import { join, resolve } from 'node:path';

const N_PAPERS = Number(process.argv[2] ?? 90);
const N_CONCEPTS = Number(process.argv[3] ?? 18);
const OUT = resolve(process.argv[4] ?? join(import.meta.dirname, 'stress-wiki'));

let _s = 20260719 >>> 0;
const rng = () => {
  _s = (_s + 0x6D2B79F5) | 0;
  let t = Math.imul(_s ^ (_s >>> 15), 1 | _s);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};
const pick = (arr) => arr[Math.floor(rng() * arr.length)];
const irand = (a, b) => a + Math.floor(rng() * (b - a + 1));

// ── 이름 소재 ─────────────────────────────────────────────
const ADJ = ['sparse', 'causal', 'latent', 'robust', 'neural', 'contrastive', 'federated',
  'hierarchical', 'multimodal', 'recurrent', 'implicit', 'adaptive', 'equivariant',
  'bayesian', 'compositional', 'continual', 'diffusive'];
const NOUN = ['attention', 'memory', 'alignment', 'distillation', 'retrieval', 'planning',
  'calibration', 'compression', 'grounding', 'reasoning', 'abstraction', 'curriculum',
  'representation', 'generalization', 'exploration', 'supervision', 'adaptation', 'routing'];
const VENUES = ['NeurIPS', 'ICML', 'ICLR', 'ACL', 'EMNLP', 'CVPR', 'AAAI', 'arXiv'];
const SURNAMES = ['Kim', 'Chen', 'Park', 'Wang', 'Smith', 'Tanaka', 'Muller', 'Garcia', 'Lee', 'Novak'];
const cap = (s) => s[0].toUpperCase() + s.slice(1);

// ── 개념 생성 ─────────────────────────────────────────────
const usedSlugs = new Set();
function conceptName(i) {
  for (let tries = 0; tries < 50; tries++) {
    const slug = `${pick(ADJ)}-${pick(NOUN)}`;
    if (!usedSlugs.has(slug)) { usedSlugs.add(slug); return slug; }
  }
  const slug = `concept-${i}`; usedSlugs.add(slug); return slug;
}
const concepts = Array.from({ length: N_CONCEPTS }, (_, i) => ({
  slug: conceptName(i),
  related: [],
}));
// 개념 간 관계 1~2개
for (const c of concepts) {
  const k = irand(0, 2);
  for (let j = 0; j < k; j++) {
    const o = pick(concepts);
    if (o !== c && !c.related.includes(o.slug)) c.related.push(o.slug);
  }
}
// 지프 가중치 — 앞쪽 개념일수록 논문이 몰림
const zipfW = concepts.map((_, i) => 1 / (i + 1));
const zipfSum = zipfW.reduce((a, b) => a + b, 0);
function zipfPick() {
  let r = rng() * zipfSum;
  for (let i = 0; i < zipfW.length; i++) { r -= zipfW[i]; if (r <= 0) return i; }
  return 0;
}

// ── 논문 생성 ─────────────────────────────────────────────
const papers = [];
for (let i = 0; i < N_PAPERS; i++) {
  const year = irand(2014, 2026);
  const primary = concepts[zipfPick()];
  const extra = [];
  const nExtra = rng() < 0.45 ? irand(1, 2) : 0;
  for (let j = 0; j < nExtra; j++) {
    const o = pick(concepts);
    if (o !== primary && !extra.includes(o)) extra.push(o);
  }
  const a = pick(ADJ), n1 = pick(NOUN), n2 = pick(NOUN);
  const title = pick([
    `${cap(a)} ${cap(n1)} for ${cap(n2)}`,
    `Learning ${cap(n1)} via ${cap(a)} ${cap(n2)}`,
    `Rethinking ${cap(n1)}: A ${cap(a)} Approach`,
    `${cap(n1)} Is Not Enough: Toward ${cap(a)} ${cap(n2)}`,
    `Scaling ${cap(a)} ${cap(n1)}`,
  ]);
  let slug = `${year}-${title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40)}`;
  while (usedSlugs.has(slug)) slug += '-' + irand(2, 9);
  usedSlugs.add(slug);
  const reading = rng() < 0.1;
  papers.push({
    slug, title, year,
    venue: `${pick(VENUES)} ${year}`,
    authors: `${pick(SURNAMES)} et al.`,
    concepts: [primary, ...extra],
    related: [], contradicts: [], supersedes: [],
    status: reading ? 'reading' : 'studied',
    rating: reading ? null : irand(2, 5),
    tags: [primary.slug.split('-')[1] || primary.slug, pick(NOUN)],
  });
}
papers.sort((a, b) => a.year - b.year);

// 관계 부여 (연도 역행 방지 — 관련/모순/승계는 과거 논문을 향함)
for (let i = 0; i < papers.length; i++) {
  const p = papers[i];
  const past = papers.slice(0, i);
  if (!past.length) continue;
  const sameCluster = past.filter((q) => q.concepts[0] === p.concepts[0]);
  const nRel = irand(0, 3);
  for (let j = 0; j < nRel; j++) {
    const pool = rng() < 0.6 && sameCluster.length ? sameCluster : past;
    const q = pick(pool);
    if (q !== p && !p.related.includes(q.slug)) p.related.push(q.slug);
  }
  if (rng() < 0.08 && sameCluster.length) {
    const q = pick(sameCluster);
    if (!p.contradicts.includes(q.slug)) { p.contradicts.push(q.slug); q.contradicts.push(p.slug); }
  }
  if (rng() < 0.06 && sameCluster.length) {
    const q = pick(sameCluster);
    if (!q.supersededBy) { p.supersedes.push(q.slug); q.supersededBy = p.slug; }
  }
}

// ── MOC 생성 (개념 상위 3개마다 1개 + 전체 조망 1개) ──────────
const mocs = [];
const bigConcepts = concepts.slice(0, Math.min(3, concepts.length));
for (const c of bigConcepts) {
  const members = papers.filter((p) => p.concepts.includes(c)).slice(0, 8);
  if (members.length < 2) continue;
  mocs.push({
    slug: `synthesis-${c.slug}`,
    title: `MOC: ${c.slug} 연구 지형`,
    papers: members.map((p) => p.slug),
    concepts: [c.slug],
  });
}

// ── 파일 쓰기 ─────────────────────────────────────────────
const wl = (s) => `"[[${s}]]"`;
if (existsSync(OUT)) rmSync(OUT, { recursive: true });
for (const d of ['papers', 'concepts', 'moc']) mkdirSync(join(OUT, d), { recursive: true });

for (const p of papers) {
  const fm = [
    '---',
    `title: "${p.title}"`,
    `authors: "${p.authors}"`,
    `year: ${p.year}`,
    `venue: "${p.venue}"`,
    `tags: [${p.tags.join(', ')}]`,
    `status: ${p.status}`,
    `date_read: "2026-${String(irand(1, 7)).padStart(2, '0')}-${String(irand(1, 28)).padStart(2, '0')}"`,
    `related_papers: [${p.related.map(wl).join(', ')}]`,
    `concepts: [${p.concepts.map((c) => wl(c.slug)).join(', ')}]`,
    `my_rating: ${p.rating ?? ''}`,
    `supersedes: [${p.supersedes.map(wl).join(', ')}]`,
    `superseded_by: [${p.supersededBy ? wl(p.supersededBy) : ''}]`,
    `contradicts: [${p.contradicts.map(wl).join(', ')}]`,
    '---',
  ].join('\n');
  const body = `
# ${p.title}

## TL;DR
${p.concepts[0].slug} 관점에서 ${p.tags[1]} 문제를 다룬 가상 논문 (스케일 테스트 데이터).

## 개념
${p.concepts.map((c) => `- [[${c.slug}]]`).join('\n')}

## 연결
${p.related.map((s) => `- [[${s}]] — 관련 연구.`).join('\n') || '-'}
`;
  writeFileSync(join(OUT, 'papers', p.slug + '.md'), fm + body, 'utf8');
}

for (const c of concepts) {
  const members = papers.filter((p) => p.concepts.includes(c));
  const body = `---
type: concept
aliases: []
tags: [${c.slug.split('-')[0]}]
papers: [${members.slice(0, 6).map((p) => wl(p.slug)).join(', ')}]
related_concepts: [${c.related.map(wl).join(', ')}]
---

# ${c.slug.split('-').map(cap).join(' ')}

## 한 줄 정의
${c.slug} 개념 (스케일 테스트 데이터).

## 등장 논문
${members.slice(0, 6).map((p) => `- [[${p.slug}]] —`).join('\n') || '-'}
`;
  writeFileSync(join(OUT, 'concepts', c.slug + '.md'), body, 'utf8');
}

for (const m of mocs) {
  const body = `---
type: moc
tags: [synthesis]
papers: [${m.papers.map(wl).join(', ')}]
concepts: [${m.concepts.map(wl).join(', ')}]
---

# ${m.title}

## 이 종합이 답하는 질문
${m.concepts[0]} 계열 연구들이 함께 말하는 것 (스케일 테스트 데이터).

## 근거 논문
${m.papers.map((s) => `- [[${s}]]`).join('\n')}
`;
  writeFileSync(join(OUT, 'moc', m.slug + '.md'), body, 'utf8');
}

writeFileSync(join(OUT, 'index.md'),
  `# 스트레스 테스트 위키\n\n논문 ${papers.length} · 개념 ${concepts.length} · MOC ${mocs.length} (합성 데이터)\n`, 'utf8');

console.log(`생성 완료 → ${OUT}`);
console.log(`  논문 ${papers.length} · 개념 ${concepts.length} · MOC ${mocs.length}`);
console.log(`다음: node build-graph.mjs "${OUT}" stress-graph.js`);
