# Retrieval Root-Cause Analysis — Why Expected Evidence Does Not Reach Qwen

Date: 2026-10-15. Measurement phase: no fixes proposed.
Inputs: 5-seed retrieval-only baseline ([RETRIEVAL_BASELINE_REPORT.md](RETRIEVAL_BASELINE_REPORT.md)) plus new read-only measurements on the stored index:
- token counts of all 11,239 chunks under the MedCPT article tokenizer;
- embedding-norm distribution and ranks of lost chunks under L2 / inner product / cosine;
- section mix of the top-60 under each metric (27 questions);
- expansion contribution per question;
- within-paper reranker order for every 2-per-paper loss;
- MedCPT model cards (`huggingface.co/ncbi/MedCPT-Article-Encoder`, `…-Query-Encoder`);
- embedding throughput from `index_build.log` (0.126 s/chunk; 11,239 chunks ≈ 24 min).

Scope: 14 lost answer chunks for seed 0 (11 not retrieved, 3 removed by the 2-per-paper limit) across 12 L1 questions; draft labels.

---

## Cross-cutting facts established today

| # | Fact | Evidence |
|---|---|---|
| F1 | **MedCPT usage differs from its documented usage.** The model cards pool the `[CLS]` token (`last_hidden_state[:, 0, :]`), feed articles as `[title, abstract]` pairs, and use query `max_length=64`. The code mean-pools all tokens (`embedder.py:39-110`), embeds chunk text without title, and uses query `max_length=512`. | model cards; `embedder.py` |
| F2 | 36.3 % of chunks exceed the 512-token encoder limit (median 462, p90 614, max 3,205 tokens); text past 512 tokens is not embedded. Results chunks: median 515 tokens, 51 % over the limit. | tokenizer count |
| F3 | Every expected fact in the 14 lost chunks lies **within the first 330 tokens** (embedded region). | token offsets of fact matches |
| F4 | Chunk embedding norms are near-constant (mean 8.23, CV 1.7 %); L2 and cosine rankings nearly coincide. Inner product re-orders some chunks (L1-07: rank 40 → 3; L1-01: 1,192 → 1,524). | norm stats; per-metric ranks |
| F5 | The section skew is the same under L2, inner product, and cosine (top-60: Results 15–17 % vs 27 % of corpus; Introduction 24–28 % vs 10 %). | top-60 section mix |
| F6 | Results chunks have 2–3× the numeric density of other sections (0.185 numbers/word vs 0.054–0.097) and 77 % contain figure/table references (captions are flattened into chunk text by `pmc_parser._clean_text`). | corpus scan; `pmc_parser.py` |
| F7 | Question lengths are 24–38 query tokens; the query-side limit (64 in the model card, 512 in the code) never truncates. | tokenizer count |

---

## Issue 1 — 39 % of facts lost because their chunk is never retrieved

**Proven**
- 11 answer chunks (seed 0) never enter the pool; exact dense ranks 40–1,192 (median 197) with retrieval_k 20–60.
- Facts are inside the embedded region (F3), so 512-token truncation does not explain these losses.
- The metric is not the cause on its own (F4, F5): cosine ranks track L2 within ±60 for every lost chunk.
- 3 lost chunks would be ranked **first** by the cross-encoder if pooled (L1-03, L1-11, L1-13): the text is judged relevant to the question, but the dense encoder does not place it near the query.
- 9 of 11 lost chunks are Results or case-description sections (A2 table in the probe output).

**Possible causes**
| Cause | Category | Status |
|---|---|---|
| Pooling/input format differ from MedCPT's training setup (F1) | MedCPT configuration | Mismatch proven; impact unmeasured |
| Question wording (conceptual) vs Results wording (numeric, tabular) | Retrieval query construction / embedding | Consistent with F6; unmeasured |
| 400-word chunks mix several sub-topics, diluting the fact's signal | Chunking strategy | Unmeasured |
| Caption and table text inside Results chunks adds noise | Article structure / index construction | Consistent with F6; unmeasured |
| Candidate pool too shallow for near misses (ranks 40–119) | Candidate pool size | Affects 3 chunks; proven by rank |
| Stored vectors do not match current embedding code (stale or corrupted index) | Index construction | Not checked |

**Missing evidence**: ranks of the same chunks under CLS pooling and under title-prefixed input; ranks with an oracle query written in the chunk's own language; per-chunk score when captions are removed or the chunk is narrowed to the fact sentence; vector integrity check.

**Measurements required**: E1, E2, E3, E5 below.

---

## Issue 2 — 13 % of facts lost to the 2-per-paper limit

**Proven**
- All 3 losses (L1-02, L1-04, L1-15) are **Results** chunks displaced by same-paper chunks that the cross-encoder scored higher:

  | Question | Slots taken by (within-paper CE order) | Lost chunk's within-paper rank |
  |---|---|---|
  | L1-02 | Discussion _0025, Discussion _0017 | 3 |
  | L1-04 | Discussion _0019, Methods _0007 | 3 |
  | L1-15 | Discussion _0014, Discussion _0015 | 7 (behind 3 Discussion + 1 Results) |
- The question-type bonus is negligible in these cases (0.0–0.075).
- The gold paper itself was delivered in all 3 cases; only the choice of its two chunks failed.

**Possible causes**
| Cause | Category | Status |
|---|---|---|
| ms-marco cross-encoder prefers narrative Discussion prose over numeric Results text | Reranking (model fit) | 3/3 observed; not tested beyond L1 losses |
| Cap of 2 is below what single-paper questions need | Candidate selection policy | Proven as a cap; impact quantified only for these 3 |
| Discussion chunks restate results less precisely (facts absent) | Article structure | Plausible; unmeasured |

**Missing evidence**: within-paper CE rank of *every* labeled answer chunk (not only lost ones); fact presence in the chunks that took the slots; counterfactual delivery under cap 3/4 from existing replay data.

**Measurements required**: E6.

---

## Issue 3 — Results sections substantially under-retrieved

**Proven**
- Corpus 27 % → pool 14 % → delivered 16 % → top-1 2/27; Introduction 10 % → 31 % → 25 %.
- The skew originates in dense retrieval and persists under all three metrics (F5); the cross-encoder does not correct it.
- Results chunks are longer (51 % exceed 512 tokens), number-dense, and caption-laden (F2, F6).
- Embedding norms do not differ by section (8.20–8.28), so no section is favored by magnitude.

**Possible causes**
| Cause | Category | Status |
|---|---|---|
| Mean pooling over number- and caption-heavy text yields vectors far from natural-language questions | MedCPT configuration + article structure | Unmeasured |
| Questions are phrased like introductions/abstracts ("what is the evidence that…") | Retrieval query construction | Unmeasured |
| Article encoder trained on title+abstract (summary register); body Results text is out of distribution | MedCPT configuration | Training setup proven (F1); effect unmeasured |
| Tail of 51 % of Results chunks not embedded (F2) | Chunking / index construction | Proven truncation; did not affect the 14 lost facts (F3) |

**Missing evidence**: section mix under CLS pooling; section mix under oracle (Results-style) queries; Results-chunk similarity before vs after caption removal.

**Measurements required**: E1, E2, E3.

---

## Issue 4 — Expanded queries recover no missing chunks

**Proven**
- Expansions run for 11/27 questions (seed 0) and only when a registry drug is detected and question_type has a template (`query_understanding.py:1065-1116`).
- Templates contain only `{drug} + generic phrase` ("nivolumab biomarker evidence", "osimertinib mechanism of action", "osimertinib clinical trial evidence"). They never include the question's specific entities (KL-6, myeloperoxidase, Yifeixiaoji, V804F, SPEN).
- Of the 11 lost chunks, 7 belong to questions with **no** expansion executed (L1-01, L1-03, L1-06, L1-09, L1-11, L1-14; L1-09 has no registry drug).
- Where expansions run, they add 8–34 new candidates each, but for L1 they added **0 new gold-paper chunks**. For L2 they added 1–5 gold-paper chunks (L2-01, L2-04, L2-08, L2-09), of which ≤1 was delivered per question.
- The cross-encoder scores candidates against the original question only (`retriever.py:166-167`), so expansion-only hits must also match the original question to be delivered.

**Possible causes**
| Cause | Category | Status |
|---|---|---|
| Templates are drug-generic, so they retrieve drug-level reviews and introductions, not question-specific passages | Retrieval query construction | Strongly supported by template text and zero L1 gold gain |
| Expansion is gated on registry drug + 6 types | Query understanding | Proven gating; explains 7/11 |

**Missing evidence**: section mix of expansion-only candidates; rank of lost chunks under a question-specific (entity-bearing) rewrite.

**Measurements required**: E3 (includes entity-only query variant), plus a section tally of expansion-only candidates (existing records, no run).

---

## Issue 5 — Gold-evidence chunks ranked > 180

Cases: L1-01 (1,192), L1-06 (466), L1-10 (327), L1-14 (236), L1-03 (233), L1-09 (197), L1-11 (184).

**Proven**
- Not caused by embedding truncation (F3), the distance metric (F4), or query truncation (F7).
- 3 of the 7 cases (L1-01 CE 5/61, L1-03 CE 1/61, L1-11 CE 1/31) are judged relevant by the cross-encoder; the dense model is the disagreeing component.
- 2 of the 7 (L1-06 CE 21/21, L1-14 CE 43/61) are also ranked low by the cross-encoder, so label or question wording is a competing explanation (validity issue from the baseline report).
- All 7 are Results or case-description chunks.

**Possible causes**: same as Issue 1, plus label mis-specification for L1-06 and L1-14.

**Missing evidence**: oracle-query rank (can the encoder find the chunk when the query uses its language?); CLS-pooled rank; label review.

**Measurements required**: E1, E2, E3, label review.

---

## Experiments to identify the dominant problem

All experiments are read-only against the production index: alternate vectors are computed into side files under `benchmark_runs/`, and Chroma, `src/`, and the app are untouched.

| ID | Experiment | Runtime | Isolates |
|---|---|---|---|
| **E5** | **Index integrity**: re-run parser → chunker → embedder (current code) for the 12 gold papers; compare chunk text and vectors with Chroma (expect identical text, cosine ≈ 1.0) | ~2 min | Index construction |
| **E3** | **Query variants (per lost chunk, current encoder)**: rank under (a) original question (baseline), (b) entity-only query (question's specific terms), (c) **oracle query** = the fact description written in the chunk's language. Plus section mix of top-60 for (b). | ~3 min | Query construction vs embedding |
| **E1** | **Chunk perturbations (current encoder, lost chunks only)**: distance to query vs the pool cutoff distance (the retrieval_k-th neighbor) for: as stored; title + chunk; captions/table references removed; fact sentence ±1 sentence; first 256 tokens | ~3 min | Chunking strategy, article structure, encoder input format (at chunk level) |
| **E4** | **Recall@k curve (current index)**: for all labeled answer chunks and all L1/L2 gold papers, exact rank → recall at k = 20, 30, 60, 100, 200, 500 | ~5 min | Candidate pool size |
| **E2** | **CLS-pooling corpus**: embed all 11,239 chunks and the 27 questions with `[CLS]` pooling (mean pooling recomputed in the same pass as a reproducibility check); ranks of all answer chunks, recall@k, section mix of top-60. Optional second pass with title prefix. | ~24 min per pass (background) | MedCPT configuration |
| **E6** | **Within-paper reranking audit (existing records)**: within-paper CE rank of every labeled answer chunk across 5 seeds; fact presence in slot-holders; counterfactual delivery with cap 3/4 replayed from stored orders | ~2 min, no run | 2-per-paper vs reranker preference |

Order: E5 → E3 → E1 → E4 → E6 (≈15 min combined), then E2 in the background.

### Decision matrix

| If… | Then the dominant problem is… |
|---|---|
| E5 shows text or vector mismatch | **Index construction**; every other result is invalid until resolved |
| E3 oracle query ranks the chunks in the top-20 while entity-only and original do not | **Retrieval query construction** (vocabulary/register gap between questions and Results text) |
| E3 oracle query also ranks them low (> 100) | **Embedding retrieval / MedCPT configuration**: the encoder cannot place the chunk near any query |
| E2 CLS pooling moves lost chunks and Results share substantially (e.g. median rank of lost chunks drops below retrieval_k; Results share of top-60 approaches corpus share) | **MedCPT configuration** |
| E1 fact-sentence window or caption removal brings a chunk inside the cutoff while the full chunk is outside | **Chunking strategy** (window) or **article structure** (captions/tables) |
| E1 title prefix brings chunks inside the cutoff | **MedCPT input format** (article encoder expects title context) |
| E4 shows most answer chunks between k=60 and k=200 | **Candidate pool size** |
| E4 shows most answer chunks > 200 | Pool size is not the lever; embedding/query problem dominates |
| E6 shows answer chunks ranked below Discussion chunks of the same paper in most cases, independent of cap | **Reranking (model/domain fit)**; the cap is the proximate, not root, cause |

### Evidence still missing after these experiments
- Generation impact of retrieving Results text (whether Qwen uses numeric chunks faithfully): requires the targeted generation run.
- Label validity for L1-06 and L1-14: requires the label review.
- Behavior beyond 16 L1 questions: the per-category sample is small; conclusions are directional until the question set grows.

---

# Results — E5, E3, E1, E4, E6 (run 2026-10-15)

Run: `benchmark_runs/20261015_051554_rca/rca_results.json`; script `src/evaluation/rca_experiments.py` (read-only; seed-0 records for E1/E3/E4, all 5 seeds for E6). E2 not run.
Unit of analysis: the 11 not-retrieved and 3 in-pool-but-not-delivered answer chunks of seed 0 (12 L1 questions); E4 covers all 20 labeled answer chunks and all 68 gold papers.
Effects on: **R** = retrieval quality, **V** = benchmark validity, **G** = generation quality.

## E5 — Index integrity
| | |
|---|---|
| Proven | For all 16 L1 gold papers (307 chunks), re-running parser → enricher → chunker → embedder with current code reproduces the index exactly: same chunk IDs (0 missing, 0 extra), identical text, vectors identical (min cosine 1.0, max component difference 0). |
| Refuted | Index construction defects (stale vectors, text/vector mismatch, chunk-ID drift) as a cause. |
| New hypotheses | None. |
| Impact if confirmed | — (refutation). |
| Affects | **V**: benchmark measurements reflect the current pipeline; results are reproducible. |

## E3 — Query wording (original vs entity-only vs oracle)
Ranks of the 11 not-retrieved chunks (exact, 11,239 chunks):
| Query | Median rank | Within the question's retrieval_k |
|---|---|---|
| Original question | 197 | 0/11 |
| Entity-only (question terms only) | 165 | 2/11 |
| Oracle (fact stated in the chunk's language) | **3** | **8/11** |

Section mix of top-60 (12 questions): original Results 16 % · entity-only 16 % · **oracle 28 %** (corpus 27 %); Introduction 28 % → 27 % → 13 %.

| | |
|---|---|
| Proven | (1) The encoder places 8/11 lost chunks in the top-30 when the query resembles the chunk's content; the chunk representations are retrievable. (2) Re-wording the question with its own entities barely helps (median 197 → 165). (3) The Results under-representation disappears when queries are phrased like results statements: the skew is produced by the *question register*, not by an encoder bias against Results text. |
| Refuted | "The encoder cannot represent Results/numeric chunks" (oracle retrieves them). "Missing question entities in the query" as the dominant cause (entity-only ≈ original). Label mis-specification for L1-06 and L1-14 at the dense level (oracle ranks 1 and 2). |
| New hypotheses | H-R1: questions identify the *study/topic*, while Results chunks state *findings* without the study's identity, so question↔chunk similarity is low even though the content answers the question. 3 lost chunks are not recovered even by the oracle (L1-01 131, L1-09 105, L1-11 204). |
| Impact if confirmed | Determines whether remediation targets the query side or the document side; E1 points to the document side. |
| Affects | **R** (mechanism of the 39 % loss), **V** (labels for L1-06/L1-14 are findable; earlier doubt reduced). |

## E1 — Chunk perturbations (lost chunk re-embedded; all other vectors unchanged)
Equivalent rank if the stored vector were replaced by the variant (original question):
| Variant | Median rank (11 not-retrieved) | Within retrieval_k | Also: in-pool losses (L1-02 _0015, L1-04 _0011, L1-15 _0011) |
|---|---|---|---|
| Stored / recomputed | 197 / 197 | 0/11 | 2 / 11 / 47 |
| **Title + chunk pair** (MedCPT's documented `[title, text]` input; pooling unchanged) | **17** | **10/11** | 1 / 7 / 1 |
| Captions/figure-table sentences removed | worse in 7/11 (e.g. 1,192 → 2,166) | 0/11 | 14 / 7 / 461 |
| Fact sentence ±1 (74–400 words) | mixed (L1-11 184 → 1; L1-06 466 → 554) | 1/11 | 2 / 11 / 1 |
| First 256 tokens | mixed | 2/11 | 2 / 7 / 28 |

| | |
|---|---|
| Proven | (1) Adding the article title as MedCPT's documented first segment moves 10 of 11 not-retrieved chunks inside their question's retrieval_k (only L1-07 _0023 worsens, 54 → 162). (2) Removing caption/table sentences makes ranks worse in most cases: these sentences carry topical terms. (3) Shrinking the chunk to the fact window or the first 256 tokens has no consistent effect. |
| Refuted | Caption/table noise as a cause (H from F6). Chunk size / topic dilution as the dominant cause. |
| New hypotheses | H-R2 (refines H-R1): **chunk embeddings lack article-level context**; MedCPT's article encoder was trained on `[title, abstract]` pairs, and body chunks are embedded without the title. |
| Critical limitation | The test is **asymmetric**: only the lost chunk receives its title; competitors do not. Titles share terms with study-specific questions, so the measured gain is an **upper bound**. A fair estimate requires every chunk to be embedded the same way (E2 with title input). |
| Impact if confirmed | Up to 10/11 not-retrieved answer chunks enter the pool. Delivery is then gated by the reranker: with the current cross-encoder, 3 of these 11 would be delivered (L1-03, L1-11, L1-13; prior measurement). |
| Affects | **R** (primary mechanism candidate), **G** (Results chunks carry the numeric facts Qwen currently lacks). |

## E4 — Candidate pool depth (exact rank; best over executed queries)
| k | 20 | 30 | 60 | 100 | 200 | 500 |
|---|---|---|---|---|---|---|
| Labeled answer chunks (20) | 0.35 | 0.35 | 0.55 | 0.60 | 0.75 | 0.95 |
| L1 gold papers (16) | 0.94 | 0.94 | 0.94 | 1.00 | 1.00 | 1.00 |
| L2 gold papers (52) | 0.62 | 0.69 | 0.87 | 0.94 | 0.98 | 1.00 |

| | |
|---|---|
| Proven | (1) Answer chunks are spread deep: 25 % beyond rank 200; going from k=60 to k=100 adds 1 chunk of 20. (2) L1 papers are found at k≤20 for 15/16. (3) L2 papers are depth-sensitive: 62 % at k=20 (the FACT_LOOKUP budget) vs 87 % at k=60. |
| Refuted | Pool depth as the dominant L1 cause (L1 losses are mostly > 100). |
| New hypotheses | H-R3: L2 paper loss is driven by the intent-selected retrieval_k (20 vs 60) more than by embedding quality. |
| Impact if confirmed | L1: ≤ 1–2 chunks. L2: +25 percentage points of gold papers in pool between k=20 and k=60; delivery still capped by top_k (36 % of L2 paper-runs are already pooled but cut). |
| Affects | **R** (L2 mainly), **V** (L2 results depend on the classification path that sets retrieval_k). |

## E6 — 2-per-paper limit vs reranker preference (5 seeds, 44 answer-chunk observations in pool)
| | |
|---|---|
| Proven | (1) The answer chunk is the top chunk of its own paper in only 9/44 observations; the chunks ranked above it are Discussion 33, Introduction 10, Methods 5, Results 5, other 5. (2) Counterfactual replay: delivered 29/44 at cap 2, **40/44 at cap 3**, 40/44 at cap 4. (3) Fact redundancy differs: L1-02's slot-holders already contain 2 of 3 facts (loss overstated at chunk level); L1-04's contain 0 of 4 (loss is real). (4) L1-15 is not a cap loss: its answer chunk ranks 5th within its paper and is cut by the top_k budget. |
| Refuted | "The cap alone causes the loss": the cap is the proximate cause; the cross-encoder ordering Discussion above Results is the reason the answer chunk is third. |
| New hypotheses | H-R4: the ms-marco cross-encoder systematically prefers narrative summary prose over result statements within a paper (same register effect as H-R1, at the reranking stage). |
| Impact if confirmed | Cap 3 would recover 11 of 15 in-pool losses across seeds (counterfactual; top_k unchanged). |
| Affects | **R**, **V** (chunk-level metric overstates L1-02; fact-level metric is the reliable one), **G**. |

---

## Root-cause ranking

| Rank | Root cause | Stage | Confidence | Severity (share of lost evidence) | Ease of remediation (nature of change, not a recommendation) |
|---|---|---|---|---|---|
| 1 | **Context-free chunk embeddings: body chunks are embedded without article identity, so study-specific questions do not match Results/case chunks** (H-R1/H-R2) | Dense retrieval / MedCPT input format | **Medium-high**: mechanism supported by E3 (oracle 8/11, Results skew vanishes) and E1 (title 10/11); magnitude unproven because E1 is asymmetric | **High**: accounts for the not-retrieved class (56 % of answer-chunk runs, 39 % of fact runs) | Medium: changes the index (full re-embedding ≈ 24 min, re-index), no query-side change |
| 2 | **Reranker prefers summary prose over results within a paper, amplified by the 2-per-paper cap** (H-R4) | Reranking + selection | **High** for the mechanism (E6: 35/44 answer chunks outranked, mostly by Discussion; counterfactual exact) | **Medium**: 13 % of fact runs; also gates delivery of any chunk R1 would recover (only 3/11 pass today) | Cap: low (selection parameter). Reranker preference: medium-high (model or scoring change) |
| 3 | **Intent-selected pool depth too shallow for multi-paper questions** (H-R3) | Strategy → candidate pool | **Medium**: E4 curve proven; causal link to intent shown in the baseline (FACT_LOOKUP → k 20) | Medium for L2 (62 % → 87 % of gold papers between k 20 and 60); low for L1 | Low (strategy parameters), but coupled to classification stability |
| 4 | Query wording / generic expansions | Query construction | High that it is **not dominant** (entity-only ≈ original; expansions add 0 L1 gold chunks) | Low | — |
| — | Refuted: index construction (E5), caption noise (E1), chunk size dilution (E1), embedding truncation (F3), distance metric (F4/F5) | | High | None | — |

**Dominant retrieval failure mechanism (current evidence):** a two-gate **register/context mismatch**. Questions are phrased about a study or topic. The chunks that hold the findings (Results, case narrative) do not carry that identity in their embeddings (gate 1, dense retrieval). Within the delivered paper, the cross-encoder prefers prose that restates the topic over the findings (gate 2, reranking). Pool depth and query wording are secondary.

## Is E2 still necessary?
**Yes, but re-scoped.** The mechanism is identified; its **magnitude** is not, because E1 gave only the lost chunk its title. Only a symmetric corpus-wide test (every chunk embedded the same way) can show whether title context improves ranking net of competitors, which also gain title terms.
- **E2a (first): title + chunk input, current mean pooling**, all 11,239 chunks, ≈ 24 min in background, side file only. Directly tests H-R2 at its strongest observed signal.
- **E2b (second, only if needed): `[CLS]` pooling** (± title). Lower priority: E3 shows the current mean-pooled vectors are already retrievable with matching queries, so pooling is not required to explain the losses.
- Read E2a with the existing harness metrics (recall@k, fact visibility via replayed reranking, section mix) so its effect on *delivery*, not only pool entry, is measured, because gate 2 limits delivery.

## Proven vs hypotheses after this round
**Proven**: index reproducible (E5); encoder can retrieve lost chunks with content-matched queries (E3); Results skew is query-register dependent (E3); title context moves 10/11 lost chunks into range under asymmetric test (E1); captions help rather than hurt (E1); chunk narrowing is not consistently beneficial (E1); answer chunks are deep (25 % > rank 200) and L2 papers are depth-sensitive (E4); answer chunks are outranked within their paper by Discussion/Introduction in 35/44 observations; cap 3 counterfactually delivers 40/44 (E6).
**Hypotheses**: H-R2 magnitude under symmetric embedding (E2a); H-R4 generality beyond 16 questions; H-R3 causal effect on L2 delivery (fixed-strategy run); generation benefit of delivering Results chunks (targeted generation run).
