# Retrieval-Only Baseline — Consolidated Report (5 seeds)

Date: 2026-10-15. Code `bdc559e` + staged print-only diff. Chroma 11,239 chunks.
Runs: `benchmark_runs/20261015_04{2806,3104,3347,3648,3944}_retrieval_seed{0..4}` — 27 questions × 5 seeds = 135 retrieval executions via `app.main()`; generation skipped.
Supplementary measurements (no pipeline change): exact dense rank of every lost answer chunk against all 11,239 embeddings; cross-encoder score of lost chunks if added to the pool; fixed-seed repeat test of the QU LLM fallback; section mix of corpus vs pool vs final.
Labels are **draft, single-labeler** (`review_status: draft`). Rerank replay matched production selection in **135/135** executions, so loss attribution is exact for the recorded runs.

---

## 1. Retrieval Quality Report

### Summary statistics
| Metric | Definition | Level 1 (16 answerable) | Level 2 (9) |
|---|---|---|---|
| Gold article recall @ pool | gold paper has ≥1 chunk in candidate pool | **15/16 (94 %)** every seed | **35–38 / 52 papers (67–73 %)** |
| Gold article recall @ context | gold paper has ≥1 chunk delivered to Qwen | 15/16 (94 %); at E1–E2 14/16 | 16–20 / 52 (31–38 %) |
| Gold chunk visibility | labeled answer chunk delivered | **29/100 chunk-runs (29 %)** | not labeled |
| Fact visibility | expected fact pattern present in a gold-paper block Qwen receives | **126/260 fact-runs (48 %)**; 24–26/52 per seed | — |
| Aspect coverage @ context | aspects with ≥1 gold paper delivered | — | mean 0.38–0.48; pool 0.74–0.77 |
| Questions with zero expected facts visible | seed 0 | 5/16 (L1-01, L1-03, L1-04, L1-11, L1-13) | — |
| Questions with all facts visible | seed 0 | 5/16 (L1-05, L1-07, L1-08, L1-12, L1-16) | — |
| Rerank latency | per question | median 2.4 s, max 3.8 s (pool 20–80) | |

### Findings
- **Paper-level retrieval is strong; chunk-level retrieval is weak.** The right paper reaches Qwen for 15/16 L1 questions, but only 29 % of labeled answer chunks and 48 % of expected facts do.
- **Gold article never retrieved:** L1-13 (PMC13537402) in 5/5 seeds. L2: L2-03 retrieves 1 of 5 papers in every seed; L2-04 and L2-07 lose 3–4 papers before ranking.
- **Section skew starts at dense retrieval** (seed 0, all questions):

  | Section | Corpus | Pool | Delivered | Top-1 |
  |---|---|---|---|---|
  | Results | 27 % | 14 % | 16 % | 2/27 |
  | Methods | 19 % | 8 % | 6 % | 1/27 |
  | Introduction | 10 % | 31 % | 25 % | 5/27 |
  | Discussion/Conclusion | 23 % | 31 % | 34 % | 14/27 |

  Introduction is 3× over-represented in the pool; Results are under-represented by half. The cross-encoder does not reverse this.
- **Expanded queries never surfaced a lost answer chunk:** for all 11 not-retrieved chunks, the best rank over all executed queries equals the original question's rank.

---

## 2. Seed Stability Report

| Metric | Value |
|---|---|
| Classification identical across 5 seeds | **16/27 (59 %)** |
| Final evidence set identical across 5 seeds | 18/27 (67 %) |
| Fact visibility identical across seeds (L1) | 15/16 (only L1-12 varies: 4 vs 2 of 4) |
| L2 aspect coverage identical across seeds | 5/9 (L2-01, -05, -06, -09 vary) |
| top_k changes with seed | 6 questions (L1-01, L1-15, L1-16, L2-01, L2-04, L2-06) |

**Two distinct sources of instability (proven):**
| Source | Questions | Mechanism | Controllable by fixing seed? |
|---|---|---|---|
| Hash-seed tie-break | L1-12, L2-01, L2-04, L2-05, L2-09 | Fast-path confidence 0.63 (tied taxonomy scores); fast-path label varies 2–3 ways; no LLM call | **Yes** |
| QU LLM fallback (`qwen2.5:1.5b`) | L1-01, L1-11, L1-15, L1-16, L2-06, L2-07 | Fast-path confidence 0.0–0.45 < 0.5 → LLM; fast-path label constant, final label 4–5 distinct values over 5 runs; 4–11 s per call | **No** — 3 runs at fixed seed 0 gave 3 different labels for L1-01, L1-15, L2-07, with top_k switching 5 ↔ 8 |

**Most seed-sensitive questions:** L1-15 (5 labels, 4 strategies, 3 evidence sets), L1-01 (5 labels, 3 strategies), L2-01 (3 labels; top_k 3 vs 5; aspect coverage 0.4–0.6), L2-05 (3 labels; aspect coverage 0.5–0.75), L2-09 (aspect coverage 0.17–0.33).
**Stable questions (identical classification and evidence in all seeds):** L1-02 … L1-10, L1-13, L1-14, L1-C1, L1-C2, L2-02, L2-03, L2-08.

### Is seed 0 representative?
| Scope | Verdict | Evidence |
|---|---|---|
| L1 aggregate retrieval metrics | **Yes** | Seed 0 equals the value in 4 of 5 seeds for fact visibility (26/52), gold-paper recall, and answer-chunk locations |
| L2 aggregate | **Approximately; slightly optimistic** | Aspect coverage 0.45 vs 5-seed mean 0.43 (range 0.38–0.48); questions ≥ 0.6: 3 vs range 1–4 |
| Per question | **No for 4/27** | Seed 0 evidence set is not the modal set for L1-15, L2-04, L2-05, L2-09 |
| LLM-fallback questions | **Not applicable** | Seed does not control them; results vary run-to-run |

---

## 3. Evidence Loss Analysis

### Level 1 — where labeled answer chunks are lost (100 chunk-runs)
| Location | Count | Share |
|---|---|---|
| Delivered | 29 | 29 % |
| Not retrieved (not in pool) | 56 | 56 % |
| 2-per-paper limit | 15 | 15 % |
| Reranked out | 0 | 0 % |
| top_k limit | 0 | 0 % |
| Duplicate removal | 0 | 0 % |

### Level 1 — where expected facts are lost (260 fact-runs)
| Location | Count | Share |
|---|---|---|
| Visible to Qwen | 126 | 48 % |
| Not retrieved | 101 | 39 % |
| 2-per-paper limit | 33 | 13 % |
| Context truncation (delivered chunk, fact past 1,200 chars, not visible elsewhere) | 0 | 0 % |

### Not-retrieved answer chunks: candidate-pool depth vs retrieval (seed 0, exact dense rank among 11,239)
| Question | Chunk | Exact rank | retrieval_k | CE rank if it had been pooled | Classification |
|---|---|---|---|---|---|
| L1-07 | _0022 / _0023 | 40 / 54 | 30 | 8 / 32 | Candidate pool (facts still visible via other chunks) |
| L1-13 | PMC13537402_0013 | 75 | 20 | **1 of 36** | Candidate pool (+ QU strategy: FACT_LOOKUP → k 20) |
| L1-02 | _0016 | 119 | 20 | 20 of 37 | Candidate pool / retrieval |
| L1-11 | PMC13479129_0004 | 184 | 30 | **1 of 31** | Retrieval |
| L1-09 | _0024 | 197 | 50 | 26 of 51 | Retrieval |
| L1-03 | PMC13427999_0006 | 233 | 60 | **1 of 61** | Retrieval |
| L1-14 | PMC12522107_0007 | 236 | 60 | 43 of 61 | Retrieval (label review needed) |
| L1-10 | _0005 | 327 | 20 | 7 of 30 | Retrieval |
| L1-06 | PMC13511178_0006 | 466 | 20 | 21 of 21 | Retrieval (label review needed) |
| L1-01 | PMC13564716_0005 | 1,192 | 60 | 5 of 61 | Retrieval |

In 3 cases (L1-03, L1-11, L1-13) the cross-encoder would rank the missing chunk **first** if it were in the pool: dense retrieval, not reranking, is the limiting stage there.

### Level 2 — gold papers (260 paper-runs)
| Location | Count | Share |
|---|---|---|
| Delivered | 89 | 34 % |
| In pool, not delivered (top_k budget; the per-paper cap cannot apply to a paper with no selected chunk) | 93 | 36 % |
| Not retrieved | 78 | 30 % |

Per question: L2-08 has all 5 gold papers in the pool but delivers 1 (top_k 3); L2-03 never retrieves 4 of 5; L2-01 loses 21 paper-runs to retrieval and 20 to the budget.

### Failure classification (primary cause per question; seed 0 unless noted)
| Class | Questions |
|---|---|
| Query Understanding | L1-12 (THERAPY branch halves fact visibility, seed 1); L1-15 (fallback; strategy 30/5–60/8); L2-01, L2-04 (top_k 3 vs 5 by seed); L2-05, L2-09 (tie labels change evidence); L2-06, L2-07 (fallback) |
| Retrieval | L1-01, L1-03, L1-06, L1-09, L1-10, L1-11, L1-14; L2-03, L2-04, L2-07 (papers never pooled) |
| Candidate Pool (answer chunk within ~2–4× retrieval_k) | L1-13 (rank 75 vs k 20; gold article never retrieved), L1-02 (_0016), L1-07 (no fact loss) |
| Reranking | none as direct cause at L1; the CE chooses *which* two chunks of a paper occupy the slots (see 2-per-paper) |
| Duplicate Removal | none observed |
| 2-per-paper Limit | L1-04 (all 4 facts), L1-02 (1 fact), L1-15 (seed-dependent) |
| top_k Limit | L2-08, L2-01, L2-09, L2-05, L2-02, L2-06 (gold papers pooled but cut); none at L1 |
| Context Truncation | none observed as the deciding loss |
| No loss | L1-05, L1-07 (facts), L1-08, L1-16 |

---

## 4. Benchmark Validity Assessment

| Concern | Status | Evidence / consequence |
|---|---|---|
| Measurement fidelity | **Trustworthy** | Production path; replay consistency 135/135; deterministic for 16/27 questions |
| Seed control | **Partial** | Fixes 5 hash-tie questions; cannot fix 6 LLM-fallback questions (proven run-to-run variation at fixed seed) |
| Label completeness | **Weak** | L1-02: answer also present in non-graded chunks; L1-06, L1-14: both dense (rank 466, 236) and CE (21/21, 43/61) rank the labeled chunk low — label or question wording needs review |
| Fact-pattern precision | **Hazard found** | L1-14 pattern `55\.7\|27\.4` matched the Introduction's *primary-analysis* ORR (55.7 % vs 27.1 %), not the final analysis; "visible" overstates correct evidence |
| Truncation measurement | **Possible selection bias** | Facts were drafted from text read near chunk starts; 0 truncation losses may reflect fact choice, not system behavior |
| L2 gold sets | **Lower bound** | Title-derived; other relevant papers exist; aspect coverage is a floor |
| Sample size | **Small** | 16 L1 / 9 L2 questions; per-category rates not yet meaningful |

**Can retrieval quality be trusted before generation benchmarks?** The *measurement* can be trusted; the *labels* need one review pass. Retrieval *quality* is now known well enough to bound generation: for 5/16 L1 questions Qwen receives none of the expected facts and for 6 more only part of them, so a full Level 1 generation run would largely measure the retrieval ceiling.

---

## 5. Proven vs hypotheses

**Proven (this run)**
1. Gold paper reaches Qwen for 94 % of L1 questions; expected facts for 48 %.
2. Not-retrieved is the dominant L1 loss (56 % of answer-chunk runs, 39 % of fact runs); 2-per-paper is second (15 % / 13 %); reranked-out, top_k, dedup, truncation: 0 observed at L1.
3. At L2, losses split ~evenly between not retrieved (30 %) and top_k budget (36 %).
4. Dense retrieval over-selects Introduction/Discussion and under-selects Results/Methods relative to the corpus.
5. Expansions never recovered a lost answer chunk.
6. For 3 lost chunks the CE would rank them first if pooled.
7. Classification instability has two independent sources; the LLM-fallback source is irreproducible at fixed seed.
8. Seed 0 matches the modal value for L1 aggregates; per-question it is non-modal for 4/27.

**Still hypotheses**
- H-A: MedCPT (mean pooling, L2 distance) favors summary-style prose over numeric Results text → would explain the section skew. Untested.
- H-B: Larger `retrieval_k` would recover Candidate-pool cases (L1-13, L1-02, L1-07) without hurting precision. Untested.
- H-C: Fact visibility, not chunk delivery, is the binding constraint on answer correctness. Untested until generation is scored.
- H-D: Labels for L1-06 and L1-14 are mis-specified rather than retrieval failing. Untested.
- H-E: Truncation is a real loss source for facts not yet labeled. Untested.

---

## 6. Next experiments ranked by information gain vs runtime

| Rank | Experiment | Runtime | Information gained |
|---|---|---|---|
| 1 | **Offline recall@k curve**: exact dense rank of every answer chunk and gold paper for all 27 questions (original + executed queries) at k = 20/30/60/100/200/500 | ~5 min, no pipeline run | Separates candidate-pool depth from embedding quality for every question (H-A, H-B) |
| 2 | **Fixed-strategy retrieval run**: `--retrieval-only --strategy-override 60:8 --no-expansions --repeats 1` (seed 0) | ~3 min | Removes QU/strategy effects; isolates retrieval + ranking; quantifies how much L2 loss is budget |
| 3 | **Label review pass** (L1-02, L1-06, L1-14 first; tighten fact patterns to analysis-specific values) | ~1–2 h human, 0 compute | Restores validity of chunk- and fact-level metrics (H-D) |
| 4 | **Targeted generation**: L1-05, L1-07, L1-08, L1-12, L1-16 (all facts visible) + 2 controls, 1 repeat, warm-up on | ~20 min | Generation correctness/faithfulness and prune frequency where retrieval is not the limiter (H-C; wrap/prune rate) |
| 5 | **QU fallback distribution**: 6 fallback questions × 10 QU-only runs | ~10 min | Probability distribution of intent/top_k per question; required to report those questions honestly |
| 6 | Full Level 1 generation, 3 repeats | ~2–3 h | Low marginal value until 1–3 are done; mostly measures the retrieval ceiling |

**Recommendation:** investigate **retrieval** next (experiments 1–2, ~8 min combined), with the label review in parallel. Classification stability is second: it changes evidence for 9/27 questions but changed L1 fact visibility for only 1. Generation should be measured next only on the retrieval-clean subset (experiment 4), not the full suite.
