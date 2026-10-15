# Two-Day Execution — Results (2026-10-15)

Branch: `fix/correctness-2day` (not pushed, not merged). Plan: correctness fixes F1–F5 + experiment E2a.

## Commits
| Commit | Content |
|---|---|
| `ed354ee` | Pre-existing staged change (prompt/answer size prints), committed separately |
| `9ed377e` | Benchmark harness, labeling tools, RCA experiments, investigation docs |
| `334aa35` | **F1** `ollama run --nowordwrap` for generation |
| `1586b3b` | **F2** forbidden phrases on word boundaries; abstention lines survive pruning (+ tests) |
| `d43233a` | **F3** query-type ties resolved in taxonomy order, not hash order |
| `558d7ee` | **F4** fallback classifier via Ollama API, `temperature 0`, `seed 0`; failures fall back to fast path (+ tests; harness records HTTP calls) |
| `664007a` | **F5** Chroma path from project root; 600 s generation timeout (+ tests) |
| `4528cb9` | E2a experiment and post-processing replay tools |

Tests: 12 unit tests (`src/generation/test_answer_validation.py`, `src/query_understanding/test_classification_determinism.py`), all passing. Run: `.venv/bin/python -m unittest src/generation/test_answer_validation.py src/query_understanding/test_classification_determinism.py`.
Operational: start with `HF_HUB_OFFLINE=1` (verified: models and index load without network, from any directory).

## Correctness fixes — measured effect

| Metric | Before | After | Evidence |
|---|---|---|---|
| Cursor-edit escapes in raw generation output (8 answers) | 57 | **0** | before/after runs |
| Mid-sentence line breaks in final answers (8 answers) | 38 | **0** | before/after runs |
| `--nowordwrap` direct test | wrapped at ~80 chars with escapes | one 248-char line, 0 escapes | CLI test |
| Questions classified identically across 5 hash seeds | 16/27 | **27/27** (run b); 25/27 (run a) | 2 × 5-seed stability runs |
| Classification agreement over 10 independent processes | — | **268/270** | same |
| Modal label and top_k identical between two full runs | — | 27/27 | same |
| Substring false-positive rejections in stored answers | 0 of 10 | 0 of 10 | replay through old vs new post-processing |
| Startup from another directory | silently opened an empty store | opens the project index (count 11,239) | test |
| Unbounded generation | no timeout | 600 s → explicit error | test |

**Notes**
- F2 is **preventive**: no stored answer triggered the substring defect, so it had no measurable effect in this sample. The only replay difference is one abstention line retained in an already failed answer.
- The 2 residual classification deviations (L1-15, L2-07) occurred in a single process that ran concurrently with an unrelated request to the same `qwen2.5:1.5b` server. Hypothesis: llama.cpp prompt-cache state affects temperature-0 output. Not proven.
- F3 is deterministic, not semantically better: L2-01 and L2-04 (resistance questions) now always resolve to MECHANISM/EXPLANATION (top_k 5) by taxonomy order.

## Generation observations (before vs after, same 8 questions, 1 repeat each)
| | Before | After |
|---|---|---|
| Outcomes | 7 pass_first, 1 fail | 7 pass_first, 1 fail |
| Prompts | — | identical token counts for 7/8 (retrieval and context unchanged by fixes) |
| Controls (teprotumumab; imatinib in asthma) | abstained, 0 claims | abstained, 0 claims |
| Generation time (excl. prompt-cache case) | 36–100 s | 38–105 s (answer-length variance) |

Findings from these runs (new, proven on real outputs):
1. **Fabricated attribution causes total answer loss.** L1-16 failed in both runs: Qwen wrote "According to Huang et al. [E2]". The validator correctly rejects it; pruning cannot remove it because the line also carries a valid citation. The raw output contained all 3 expected facts.
2. **Numbers are dropped although present in the evidence.** L1-05 reported "significant improvement in PFS" without 22 vs 5 months; L1-12 "a significant portion" instead of 38.8 %.
3. **Generation varies on identical input.** L1-08 prompt hash identical before/after (`742451c4d61e`); fact recall 1.0 → 0.33 because the second answer omitted the IC50 values. Generation has no seed/temperature control (`ollama run` cannot set them). Single-repeat quality numbers are therefore not reliable.
4. **Uncited sentences pass validation** (e.g. L1-12 Executive Summary).
5. Prompt cache: a repeated identical prompt (warm-up = first question) has ~0 s prefill; repeated-question timings are not comparable.

## E2a — title-context passage embeddings

Setup: all 11,239 chunks embedded as `[title, chunk]` pairs (mean pooling unchanged), 2,333 s on CPU, side file only. Replay of retrieval → current cross-encoder → context for 27 questions with identical queries and settings; exact nearest neighbours for both vector sets.

| Metric | Stored vectors | Title context |
|---|---|---|
| Answer-chunk recall @20 / @60 / @200 | 0.35 / 0.55 / 0.75 | **0.60 / 0.80 / 0.95** |
| L1 answer chunks in pool (of 20) | 9 | **14** |
| L1 answer chunks delivered to Qwen | 6 | 6 |
| L1 fact visibility | 50.0 % | 53.8 % (**+3.8 points**) |
| L1 gold paper delivered | 15/16 | **16/16** (L1-13 rescued: 0 → 4/4 facts) |
| L2 gold papers in pool / delivered (of 52) | 38 / 20 | 33 / 19 |
| L2 aspect coverage (mean) | 0.45 | 0.46 |
| Distinct papers in top-k (mean) | 18.0 | **12.2** |
| Largest single-paper share of top-k | 19 % | 30 % |
| Within-paper distance spread (relative to corpus) | 0.93 | **0.50** |
| Results share of top-60 | 17.3 % | 18.5 % |

**Decision (pre-registered rule): `reranker_bottleneck`.** Pool entry improved substantially but fact visibility rose < 10 points.

Mechanism (measured): title context is a **paper-identity** signal. It pulls a matching paper's chunks toward the query (paper recall up; L1-13 rescued), but halves within-paper discrimination and reduces pool diversity, so the pool fills with fewer papers and the cross-encoder + 2-per-paper limit choose among near-identical candidates, still preferring Discussion/Introduction. Regressions: L1-08 (3 → 0 facts), L2 pooled papers 38 → 33.

Implication: title context should identify **papers**, not rank **passages**. This is direct evidence for the paper-first, passage-second design (DECISION_DOCUMENT §6). Replacing the passage index with title-context embeddings is **not** supported.

## What is now proven / still open
**Proven**: wrap defect eliminated; classification deterministic across hash seeds; index path and timeout fixed; title context improves paper/pool recall but not delivery; within-paper selection (reranker + cap) is the binding constraint for delivery; controls abstain correctly in 4/4 runs; fabricated attribution and numeric omission occur in generation.
**Open**: residual fallback non-determinism under concurrent requests; generation non-determinism (needs seed/temperature via API); reranker alternative; per-paper quota; paper-first prototype; abstention beyond 2 controls.

## Recommended next steps (evidence-ranked)
1. **Offline within-paper selection study** (no index change): on stored pools, compare current CE vs a biomedical cross-encoder, and per-paper quota 2/3; metric = answer chunks delivered and fact visibility. E2a shows this is the gate.
2. **Paper-first prototype** (offline): papers via title-context vectors (or title+abstract), passages via stored vectors + reranker within top papers.
3. **Generation determinism**: move the generation call to the Ollama API with seed/temperature and `num_ctx`, so quality runs become repeatable; then run 3-repeat quality baselines.
4. **Citation-format failure handling**: measure frequency of fabricated attribution across a larger run before deciding how to handle it.
