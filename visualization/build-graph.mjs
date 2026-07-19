#!/usr/bin/env node
/**
 * build-graph.mjs — paper-study 위키(md)를 은하 뷰용 그래프 데이터로 변환
 *
 * 사용법:
 *   node build-graph.mjs [위키루트] [출력파일]
 *   기본값: 위키루트 = ./sample-wiki, 출력파일 = ./graph-data.js
 *
 * 출력: window.WIKI_GRAPH = { nodes, edges, meta } 를 담은 JS 파일
 *       (galaxy.html이 <script src>로 로드 — file:// 에서도 동작)
 */
import { readFileSync, writeFileSync, readdirSync, existsSync } from 'node:fs';
import { join, basename, resolve } from 'node:path';

const wikiRoot = resolve(process.argv[2] ?? join(import.meta.dirname, 'sample-wiki'));
const outFile = resolve(process.argv[3] ?? join(import.meta.dirname, 'graph-data.js'));

const WIKILINK = /\[\[([^\]|#]+?)(?:[|#][^\]]*)?\]\]/g;

function extractLinks(text) {
  const out = [];
  for (const m of text.matchAll(WIKILINK)) out.push(m[1].trim());
  return out;
}

/** 템플릿이 쓰는 YAML 부분집합 파서: 스칼라, 인라인 배열, "- 항목" 블록 리스트 */
function parseFrontmatter(src) {
  const m = src.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  if (!m) return { fm: {}, body: src };
  const fm = {};
  let lastKey = null;
  for (const line of m[1].split(/\r?\n/)) {
    const kv = line.match(/^([A-Za-z_][\w-]*):\s*(.*)$/);
    if (kv) {
      lastKey = kv[1];
      fm[lastKey] = parseValue(kv[2].trim());
    } else {
      const item = line.match(/^\s+-\s+(.*)$/);
      if (item && lastKey) {
        if (!Array.isArray(fm[lastKey])) fm[lastKey] = fm[lastKey] ? [fm[lastKey]] : [];
        fm[lastKey].push(stripQuotes(item[1].trim()));
      }
    }
  }
  return { fm, body: src.slice(m[0].length) };
}

function stripQuotes(s) {
  return s.replace(/^["']|["']$/g, '');
}

function parseValue(v) {
  v = v.replace(/\s+#(?![^\[]*\]\]).*$/, '').trim(); // 뒤쪽 주석 제거([[..]] 안의 #은 보존)
  if (v === '' || v === '[]') return v === '[]' ? [] : '';
  if (v.startsWith('[') && v.endsWith(']')) {
    return v.slice(1, -1).split(',').map((s) => stripQuotes(s.trim())).filter(Boolean);
  }
  const n = Number(v);
  if (v !== '' && !Number.isNaN(n) && /^\d+(\.\d+)?$/.test(v)) return n;
  return stripQuotes(v);
}

function linksOf(fmValue) {
  if (fmValue == null) return [];
  const arr = Array.isArray(fmValue) ? fmValue : [fmValue];
  return arr.flatMap((s) => extractLinks(String(s)));
}

/** 본문에서 특정 헤딩 아래 첫 문단을 뽑는다 (TL;DR, 한 줄 정의 등) */
function sectionFirstText(body, headingPattern) {
  const re = new RegExp(`^#{2,3}\\s*${headingPattern}[^\\n]*\\n([\\s\\S]*?)(?=\\n#{1,3}\\s|$)`, 'm');
  const m = body.match(re);
  if (!m) return '';
  return m[1]
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith('<!--') && !l.startsWith('-->'))
    .join(' ')
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\*\*/g, '')
    .trim()
    .slice(0, 300);
}

function readDirMd(dir) {
  if (!existsSync(dir)) return [];
  return readdirSync(dir)
    .filter((f) => f.endsWith('.md'))
    .map((f) => ({ id: basename(f, '.md'), path: join(dir, f) }));
}

// ── 1. 파일 수집 ─────────────────────────────────────────────
const files = [
  ...readDirMd(join(wikiRoot, 'papers')).map((f) => ({ ...f, type: 'paper' })),
  ...readDirMd(join(wikiRoot, 'concepts')).map((f) => ({ ...f, type: 'concept' })),
  ...readDirMd(join(wikiRoot, 'moc')).map((f) => ({ ...f, type: 'moc' })),
];

if (files.length === 0) {
  console.error(`오류: ${wikiRoot} 아래에서 papers/·concepts/·moc/ md 파일을 찾지 못했습니다.`);
  process.exit(1);
}

// ── 2. 노드 생성 ─────────────────────────────────────────────
const nodes = new Map();
const parsed = new Map();

for (const f of files) {
  const src = readFileSync(f.path, 'utf8');
  const { fm, body } = parseFrontmatter(src);
  parsed.set(f.id, { fm, body, type: f.type });

  const node = {
    id: f.id,
    type: f.type,
    title: fm.title || body.match(/^#\s+(.+)$/m)?.[1]?.trim() || f.id,
    tags: Array.isArray(fm.tags) ? fm.tags : [],
  };
  if (f.type === 'paper') {
    node.year = fm.year || Number(f.id.match(/^(\d{4})/)?.[1]) || null;
    node.authors = fm.authors || '';
    node.venue = fm.venue || '';
    node.status = fm.status || 'studied';
    node.rating = typeof fm.my_rating === 'number' ? fm.my_rating : null;
    node.dateRead = fm.date_read || '';
    node.tldr = sectionFirstText(body, 'TL;DR');
    node.concepts = linksOf(fm.concepts);
  } else if (f.type === 'concept') {
    node.aliases = Array.isArray(fm.aliases) ? fm.aliases : [];
    node.tldr = sectionFirstText(body, '한 줄 정의');
  } else {
    node.tldr = sectionFirstText(body, '이 종합이 답하는 질문');
  }
  nodes.set(f.id, node);
}

// ── 3. 엣지 생성 (강한 관계 → 약한 관계 순으로, 쌍당 1개) ──────
const edges = [];
const seenPair = new Map(); // "a||b" → edge type

function addEdge(source, target, type, directed = false) {
  if (source === target) return;
  if (!nodes.has(source) || !nodes.has(target)) return; // dangling 링크는 무시
  const key = [source, target].sort().join('||');
  if (seenPair.has(key)) return;
  seenPair.set(key, type);
  edges.push({ source, target, type, directed });
}

// 3-1. 승계/모순 (가장 강한 의미 — 먼저 등록해 related 중복을 흡수)
for (const [id, { fm, type }] of parsed) {
  if (type !== 'paper') continue;
  for (const t of linksOf(fm.supersedes)) addEdge(id, t, 'supersedes', true);
  for (const t of linksOf(fm.superseded_by)) addEdge(t, id, 'supersedes', true);
  for (const t of linksOf(fm.contradicts)) addEdge(id, t, 'contradicts');
}

// 3-2. 논문 ↔ 개념 소속 (frontmatter 양방향 합집합)
for (const [id, { fm, type }] of parsed) {
  if (type === 'paper') for (const c of linksOf(fm.concepts)) addEdge(id, c, 'concept');
  if (type === 'concept') for (const p of linksOf(fm.papers)) addEdge(p, id, 'concept');
}

// 3-3. 개념 ↔ 개념
for (const [id, { fm, type }] of parsed) {
  if (type !== 'concept') continue;
  for (const c of linksOf(fm.related_concepts)) addEdge(id, c, 'concept-rel');
}

// 3-4. MOC → 논문/개념
for (const [id, { fm, body, type }] of parsed) {
  if (type !== 'moc') continue;
  const targets = new Set([...linksOf(fm.papers), ...linksOf(fm.concepts), ...extractLinks(body)]);
  for (const t of targets) addEdge(id, t, 'moc', true);
}

// 3-5. 논문 ↔ 논문 관련 (frontmatter related_papers + 본문 링크 보조)
for (const [id, { fm, body, type }] of parsed) {
  if (type !== 'paper') continue;
  const rel = new Set([...linksOf(fm.related_papers), ...extractLinks(body)]);
  for (const t of rel) {
    if (nodes.get(t)?.type === 'paper') addEdge(id, t, 'related');
  }
}

// ── 4. 파생 지표 ─────────────────────────────────────────────
const degree = new Map();
for (const e of edges) {
  degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
  degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
}
for (const n of nodes.values()) {
  n.degree = degree.get(n.id) ?? 0;
  if (n.type === 'concept') {
    n.paperCount = edges.filter((e) => e.type === 'concept' && (e.source === n.id || e.target === n.id)).length;
  }
}
// 논문의 주 개념(첫 번째 concepts 항목) — 궤도 배치의 기준
for (const n of nodes.values()) {
  if (n.type === 'paper') {
    n.primaryConcept = (n.concepts ?? []).find((c) => nodes.get(c)?.type === 'concept') ?? null;
  }
}

// ── 5. 출력 ─────────────────────────────────────────────────
const graph = {
  meta: {
    wikiRoot,
    counts: {
      papers: [...nodes.values()].filter((n) => n.type === 'paper').length,
      concepts: [...nodes.values()].filter((n) => n.type === 'concept').length,
      mocs: [...nodes.values()].filter((n) => n.type === 'moc').length,
      edges: edges.length,
    },
  },
  nodes: [...nodes.values()],
  edges,
};

writeFileSync(outFile, 'window.WIKI_GRAPH = ' + JSON.stringify(graph, null, 2) + ';\n', 'utf8');
console.log(
  `graph-data.js 생성 완료 → ${outFile}\n` +
    `  논문 ${graph.meta.counts.papers} · 개념 ${graph.meta.counts.concepts} · MOC ${graph.meta.counts.mocs} · 엣지 ${graph.meta.counts.edges}`
);
