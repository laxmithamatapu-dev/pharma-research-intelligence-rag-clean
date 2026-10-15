# Paper-First Implementation Log

Blueprint: [PAPER_FIRST_BLUEPRINT.md](PAPER_FIRST_BLUEPRINT.md). Branch: `fix/correctness-2day`.

## Session 1 — Paper index (2026-10-15) — gate PASSED

**Changes**
| File | Change |
|---|---|
| `src/embeddings/embedder.py` | Article encoder loaded lazily via `get_article_encoder()`; new `embed_papers(papers, pooling)` encodes `[title, abstract]` pairs (mean or CLS) |
| `src/vector_store/chroma_store.py` | `pharma_papers` collection (`get_papers_collection`, `reset_papers_collection`, `store_papers`); `passages_for_paper(pmcid)` |
| `src/indexing/build_paper_index.py` (new) | One record per indexed paper: document `"title. abstract"`, metadata (title, year, journal, article type, study design, drugs, passage count, abstract flags, pooling); manifest `data/manifests/paper_index_manifest.json` |
| `src/evaluation/paper_index_eval.py` (new) | Gate evaluation: paper-ranking variants vs current pool-based ranking |
| `src/evaluation/e2a_title_context.py`, `rca_experiments.py` | Use `get_article_encoder()` |
| Tests | `src/embeddings/test_lazy_article_encoder.py`, `src/indexing/test_paper_index.py` (21 tests total pass) |

**Build**: `HF_HUB_OFFLINE=1 .venv/bin/python src/indexing/build_paper_index.py --pooling cls --distance ip`. 568 papers, 0 failures, 3 without abstract (title only), 127 s. Vector DB 224 → 235 MB.

**Gate result** (27 benchmark questions, production passage pools from `benchmark_runs/20261015_065539_retrieval_postfix_seed0`)
| Paper ranking | L1 gold first | L1 gold top-2 | L2 gold papers in top 8 (of 52) | L2 aspect coverage, top 8 |
|---|---|---|---|---|
| Current (best pool chunk) | 12/16 | 14/16 | 28 | 0.61 |
| Paper index, mean pooling, L2 | 11/16 | 15/16 | 20 | 0.46 |
| **Paper index, CLS pooling, inner product (chosen)** | **16/16** | **16/16** | 25 | 0.59 |
| **Paper index ∪ passage-hit papers, cross-encoder on title + abstract** | **16/16** | **16/16** | 29–30 | 0.64–0.69 |

- Gate (L1 top-2 ≥ 15/16): **passed, 16/16 at rank 1**. Includes L1-13, which the current pipeline never retrieves.
- Chroma HNSW search agrees with exact ranking on 27/27 questions; paper query 4 ms. Union + cross-encoder costs ≈ 2.3 s per question.
- Choice: paper vectors use MedCPT's documented configuration (CLS pooling, inner product) and are queried with CLS-pooled query vectors, `max_length 64`. Passage vectors are unchanged (mean pooling); E2a showed title context hurts passage ranking.

**Operational notes**
- `build_index.py --rebuild` moves the whole `data/chromadb` directory; run `build_paper_index.py` again after any passage rebuild.
- `.gitignore` contains a bare `embeddings/` rule that also matches `src/embeddings/`; new files there need `git add -f` until the rule is narrowed to the data directory.

**Next (Session 2)**: deterministic `scope` in query analysis; `RetrievalPlan`; `paper_retriever.py` (paper index ∪ passage hits → cross-encoder on title + abstract); `retrieve_evidence` selecting passages within papers; harness wrappers; gate: L1 facts ≥ 31/52, L2 aspect coverage ≥ 0.56, scope correct on all 27 questions.

## Session 2 — Two-stage retrieval (2026-10-15) — gate PASSED (outcome gate; scope-label gate revised)

**Changes**
| File | Change |
|---|---|
| `src/embeddings/embedder.py` | `embed_paper_query` (CLS pooling, `max_length 64`) for the paper index |
| `src/query_understanding/query_understanding.py` | Deterministic `scope` ∈ {single_study, comparison, unspecified} from explicit wording only (definite study references, "the … patient", case report, trial identifiers such as KEYNOTE-671, CheckMate 9ER, NCT numbers) |
| `src/retrieval/retrieval_strategy.py` | `RetrievalPlan`, `PLAN_SHAPES` (depth 4+4, breadth 8×1, hedged, comparison), `plan_for`: single_study → depth; otherwise **adaptive** (depth if the top paper's cross-encoder margin over the second ≥ 2.0, else breadth) |
| `src/retrieval/paper_retriever.py` (new) | Candidate papers = paper index top 30 ∪ papers of passage top 60; cross-encoder on title + abstract; margin; dense pre-rank of a paper's passages (≤ 20) |
| `src/retrieval/reranker.py` | `select_passages_by_paper` (same scoring as production; per-paper quota; dedup). Legacy `rerank_chunks` unchanged |
| `src/retrieval/retriever.py` | `retrieve_evidence` → `EvidenceSet` with telemetry. Legacy `retrieve_chunks` unchanged |
| `app.py` | `RETRIEVAL_MODE=legacy|paper_first` (default `legacy`); invalid values stop at startup |
| `src/evaluation/harness.py`, `run_benchmark.py` | Harness records paper-first plan, papers, considered passages; fingerprint records mode |
| `src/evaluation/paper_first_eval.py` (new) | Gate evaluation across shapes and policies |
| Tests | `src/retrieval/test_paper_first.py` (12); suite 33 tests pass |

**Scope-label gate revised.** Only 9/16 single-paper benchmark questions contain any wording that signals a single study; a rule labeling all 27 correctly would be fitted to the benchmark. Scope therefore uses explicit cues only, and the budget for everything else is decided by the paper-score margin. Single-study precision: 11/11 (8 benchmark + 3 held-out questions not used to write the rules); no multi-paper question or control labeled single_study.

**Gate results** (27 questions; outcome gate L1 facts ≥ 31/52, L2 aspect coverage ≥ 0.56)
| Policy | L1 facts (of 52) | L1 all-facts / zero-fact questions | L1 answer chunks delivered (of 20) | L2 gold papers (of 52) | L2 aspect coverage | Retrieval s mean / p90 |
|---|---|---|---|---|---|---|
| Legacy | 26 | 5 / 5 | 6 | 17 | 0.41 | 2.8 / 3.8 |
| Depth for all | 44 | 11 / 0 | 12 | 11 | 0.29 | 4.6 / 5.2 |
| Breadth for all | 27 | 5 / 5 | 6 | 29 | 0.66 | 10.8 / 12.0 |
| Rules + hedged | 40 | 10 / 1 | 11 | 24 | 0.57 | 7.1 / 8.9 |
| **Rules + adaptive (τ = 2.0) — chosen** | **44** | **11 / 0** | **12** | **29** | **0.66** | **7.4 / 11.0** |
| Oracle (true level) | 44 | 11 / 0 | 12 | 29 | 0.66 | 7.2 / 11.4 |

- Through `app.main()` (`benchmark_runs/20261015_081327_retrieval_paper_first`): L1 44/52, L2 0.66, retrieval 7.6 s mean / 11.4 s p90 — identical to the offline evaluation.
- Margin separation: L1 margins 0.8–7.2 (14/16 ≥ 1.5); L2 margins 0.07–1.25. Plateau: τ 1.5–2.5 give identical results; τ 1.0 gives L2 0.64; τ 3.0 gives L1 40. τ was chosen on these 27 questions; held-out confirmation needed.
- Legacy mode unchanged (identical final passages for spot-checked questions).
- Prompt evidence grows from ≈ 7.4 K to ≈ 10.6 K characters (8 passages) → ≈ +800 prompt tokens ≈ +13 s prefill (projection, to be measured in S3).
- Abstention signal: top-paper cross-encoder score is 5.1–10.0 for all answerable questions; controls −2.6 and 4.0. Too few controls to set a floor; calibrate in S5 with more controls.
- Remaining L1 losses (8 facts): L1-06, L1-09, L1-14 (1/3 each), L1-10 (3/4), L1-15 (1/2) — answer passages beyond within-paper rank 4.

**Next (Session 3)**: paper-grouped context with paper headers; generation via Ollama API (`num_ctx 8192`, temperature 0, seed); targeted generation with 3 repeats vs legacy.

## Session 3 — Context + generation (2026-10-15) — gate PARTIALLY passed

**Changes**
| File | Change |
|---|---|
| `src/generation/generator.py` | Generation via Ollama `/api/chat` (`num_ctx 8192`, `temperature 0`, `seed 0`, 600 s timeout); per-call stats in `last_stats`; applies to both retrieval modes |
| `src/generation/context_builder.py` | Paper-first blocks carry `Paper:` title and `Study Design | Publication Year` from the paper record instead of the keyword "Evidence Type"; legacy block format unchanged |
| `src/evaluation/harness.py` | Records `/api/chat` calls (prompt, output, token stats, rates, done reason) |
| Tests | Generator API payload/timeout/HTTP error; context format (legacy unchanged, paper-first parsable). Suite passes |

Runtime check: Ollama loads `qwen2.5:7b` with context 8,192 (runner 5.5 GB vs 5.1 GB at 4,096).

**Comparison** (10 questions: L1-02, L1-04, L1-05, L1-08, L1-12, L1-13, L1-16, L2-01, L2-03, L1-C1; 2 repeats + warm-up per mode; runs `20261015_091600_full_s3_legacy`, `20261015_093613_full_s3_paper_first`; repeat 1 used for quality and latency)

| Metric | Legacy | Paper-first |
|---|---|---|
| L1 expected facts visible to Qwen (8 questions, 24 facts) | 15 | **24** |
| Expected facts stated in the answer | 6 | **13** |
| … of which cited to the gold paper | 6 | 9 (L1-13 states 4 facts without citations) |
| Validation outcome | 9 pass_first, 1 fail | 8 pass_first, 1 pass_after_prune, 1 fail |
| Control (L1-C1) | abstained, 0 claims | abstained, 0 claims |
| L2 aspect coverage (L2-01 / L2-03) | 0.4 / 0.2 | 0.6 / 0.6 |
| Prompt tokens (median) | 2,113 | 3,450 |
| Answer tokens (median) | 314 | 313 |
| Generation time median / p90 | 66 / 112 s | 111 / 133 s |
| **End-to-end median / p90 / max** | 69 / 122 / 122 s | **116 / 138 / 139 s** |
| Identical output across repeats | 4/10 | **3/10** |

**Gate**
| Criterion | Result |
|---|---|
| Fact recall ≥ legacy | **Pass** (13 vs 6 facts in answers) |
| Validation failures not higher | **Pass with caveat** (1 = 1 fail; paper-first adds 1 destructive prune, L1-12) |
| Controls abstain | **Pass** |
| p90 latency ≤ 180 s | **Pass** (138 s) |
| Identical outputs across repeats | **Fail** |

**Findings**
1. **Non-determinism tracks the prompt cache.** In all 13 differing pairs, repeat 1 processed the full prompt (50–70 s prefill) and repeat 2 reused the cached prompt (0.2 s). Identical pairs had matching cache states (e.g. L1-02, cached in both repeats via the warm-up). Temperature 0 and seed 0 are necessary but not sufficient. Production impact is small (distinct questions rarely hit the cache); benchmark impact is large.
2. **Uncited sentences pass validation** (L1-13: all 4 facts stated without citations).
3. **Study-design labels are wrong in some paper headers.** `infer_study_design` matches cues by substring, so "phase i" fires inside "phase ii/iii" (L1-13 shown as "randomized phase I"). The paper header now exposes this label to Qwen.
4. **Pruning can delete a correct answer.** L1-12: a legitimate "less likely to undergo rebiopsy" triggers the forbidden-phrase rule; pruning keeps only cited lines; the raw answer's facts were in uncited bullets, so the final answer is headings and citations only.
5. Fabricated attribution (L1-16) persists in both modes.

**Next**
- **Session 3b (generation hygiene, small)**: make benchmark repeats cache-independent (cold repeats) or disable prompt caching for evaluation; fix the study-design substring match or drop the design from the header; decide the policy for uncited factual sentences; stop pruning from deleting uncited answer content wholesale.
- Then Session 4 (index content) and Session 5 (abstention + cut-over) as planned.

## Session 3b — Answer correctness fixes (2026-10-15)

Priority set by the owner: **answers must be right**; latency must be explained, not traded against correctness. Evaluation uses first (cold-cache) runs; run-to-run determinism is not pursued further.

| Fix | Problem (measured) | Change | Effect (measured) |
|---|---|---|---|
| Study-design labels | Cues OR-matched by substring and `randomized_phase_I` checked first → every paper mentioning "randomized" labeled phase I (92 papers; 0 phase II/III). The label is shown to Qwen in the paper header (L1-13 answer repeated "randomized phase I") | Phase designs need a whole-word phase term **and** randomization; reviews/meta-analyses checked first; cues match at word starts | 106 paper labels corrected (e.g. CheckMate 9ER → phase III, OPTIM → phase II, 22 systematic reviews and 4 meta-analyses no longer "phase I"); paper index rebuilt (568 papers, 140 s). Passage metadata used by legacy mode is corrected at the next passage re-index |
| Invented author attribution | "According to Huang et al. [E2]" made the whole answer fail (L1-16 in every run) | Strip the invented attribution, keep the claim and its `[E#]` citation | L1-16 now passes with 2–3 expected facts |
| Destructive pruning | One forbidden word (e.g. "less likely to undergo rebiopsy") pruned every uncited line; L1-12 lost all facts | Drop only failing sentences; cited-line pruning only as a last resort | L1-12: 0 → 3 facts |

**Replay of all 62 stored raw answers (old vs new post-processing, no LLM):** failed answers 5 → **0**; expected facts in final answers 72 → **90 (+25 %)**; no answer lost a fact.

Tests: `src/processing/test_evidence_classifier.py` (6), answer-repair tests (5); full suite passes.

Known residuals: keyword design labels remain approximate (some narrative reviews that mention randomized trials read "randomized_trial"); uncited factual sentences still pass validation (L1-13) — the facts are correct but not linked to evidence.

## Where generation time goes (measured, Session 3 runs, first runs only)

| | Legacy | Paper-first |
|---|---|---|
| Prompt tokens (median) | 2,152 | 3,468 |
| Answer tokens (median) | 325 | 314 |
| **Reading the prompt (prefill)** | 33 s (42 %) | **58 s (52 %)** |
| **Writing the answer (decode)** | 47 s (50 %) | **53 s (45 %)** |
| Retrieval | 2.8 s (4 %) | 4.9 s (4 %) |
| Query understanding | ≈ 0 s | ≈ 0 s |
| **Total (median)** | **69 s** | **121 s** |

- Rates on this VM: prefill **≈ 64 tokens/s** (56–71), decode **≈ 6.3 tokens/s** (5.6–7.3), with 4 llama.cpp threads.
- Prompt size: tokens ≈ 451 + 263 per 1,000 evidence characters (R² 0.95); **each evidence passage ≈ 350 tokens ≈ 5.5 s of prefill**; **each 100 answer tokens ≈ 16 s of decode**.
- Why decode is slow (calculation): every generated token reads the full 4.25 GB of quantized weights; 6.3 tokens/s × 4.25 GB ≈ 27 GB/s, i.e. decode is limited by memory bandwidth on this CPU, not by the code. Prefill processes the prompt in parallel batches and is about 10× faster per token.
- Paper-first costs ≈ +1,300 prompt tokens (+25 s prefill) for ≈ 2× the expected facts in answers.
- Model load: 0–8 s when warm; up to 119 s for the first request after a VM reboot (weights read from disk).

## Post-baseline measurements (2026-10-15)

**Ollama thread count** (same 3,850-token prompt, cache-busted, 2–3 runs per setting): 4 threads (Ollama default) prefill 54.9 / decode 5.81 tokens/s; 6 threads not better; **8 threads 68.5 / 6.88 tokens/s**. Adopted as default (`OLLAMA_NUM_THREAD`, CPU count). In the A/B run below, generation median fell to **87 s** (p90 111 s) from 119 s end-to-end in the 4-thread final baseline.

**Exact-numbers prompt rule — not adopted.** A/B on identical evidence, 13 questions (10 with dropped facts in the final baseline + 3 guards), `benchmark_runs/20261015_133652_numeric_fidelity`:
| | Baseline prompt | + exact-numbers rule |
|---|---|---|
| Expected facts stated (42) | 31 | 32 |
| Numbers not found verbatim in evidence | 6 (all L1-04) | 0 |
| Failures | 0 | 0 |
| Generation median / p90 | 87 / 111 s | 87 / 111 s |

- The 6 "unsupported" numbers were correct derived values (e.g. 367.0 − 75.1 = 291.9 kcal); the rule removed the arithmetic, not an error.
- +1 fact is within noise. Remaining misses are secondary statistics next to correctly stated main findings (cohort size, AUC, secondary HRs), plus L1-09 whose facts are not retrieved.
- Conclusion: prompt wording is not an effective lever for the remaining gap; no change made.
