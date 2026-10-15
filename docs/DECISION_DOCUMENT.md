# Decision Document — Path to a Production Evidence-Grounded Pharma Research Assistant

Date: 2026-10-15 · Owner: technical lead · Status: proposed for decision
Constraints: Azure VM, 8 vCPU, 16 GB RAM, CPU-only, Ollama (Qwen 2.5 7B Q4_K_M), ChromaDB, MedCPT, cross-encoder.
Product stance: moderate latency is acceptable; incorrect or ungrounded answers are not.
Evidence: [SYSTEM_ASSESSMENT.md](SYSTEM_ASSESSMENT.md), [RETRIEVAL_RCA.md](RETRIEVAL_RCA.md), [RETRIEVAL_BASELINE_REPORT.md](RETRIEVAL_BASELINE_REPORT.md), [ENGINEERING_ASSESSMENT.md](ENGINEERING_ASSESSMENT.md), [PROJECT_HANDBOOK.md](PROJECT_HANDBOOK.md).

---

## Decision summary

1. **Do not productionize yet.** Five blockers stand in the way; four are correctness or reliability blockers, not latency.
2. **Approve a small set of code changes now** (Section 4). Each is backed by proven mechanisms, is low-risk, and is verifiable with the existing harness.
3. **Defer all latency optimization** until the correctness items in Section 3 are complete and an answer-quality baseline exists.
4. **Evolve toward a paper-first, passage-second retrieval architecture** served by a warm, long-running process (Section 6). It builds on the one stage that already works well, paper retrieval, rather than tuning the stage that fails.

---

## 1. Top 5 risks blocking production readiness

| # | Risk | Why it blocks | Evidence status |
|---|---|---|---|
| 1 | **Answers are built on the wrong passages.** Only 48 % of expected facts and 29 % of findings-bearing passages reach Qwen; Results text is under-selected at both retrieval and reranking. | An answer can be fully cited and still miss or misstate the study's findings. Citation validity does not imply evidential completeness. | Proven (5-seed baseline, RCA E3/E4/E6) |
| 2 | **Post-processing can corrupt cited answers.** `ollama run` wraps output; line-based pruning keeps the cited fragment and drops the claim. | A user can receive a truncated or misleading claim that passed validation. | Mechanism proven; frequency unmeasured |
| 3 | **Same question, different evidence.** The evidence budget (3–8 passages) follows phrasing-based intent; 11/27 questions change classification across runs, 6 of them irreproducibly (LLM fallback). | Non-reproducible answers are unacceptable for research use and make every quality claim unstable. | Proven |
| 4 | **No measured answer correctness and no abstention behavior.** Out-of-corpus questions receive unrelated evidence; answer faithfulness has never been scored. | The system cannot be shown to be correct, nor to refuse when it should. | Gap proven; behavior unmeasured |
| 5 | **Operational fragility.** CLI-only, single process; 119 s cold model load and 83 s import after reboot; network contact at startup; CWD-relative index path; no generation timeout; 10 % context headroom; validation failures leave no record. | Unpredictable availability and silent failures. | Proven |

---

## 2. Issue map by quality dimension

✔ = directly affects · ○ = indirectly affects

| Issue | Answer correctness | Retrieval correctness | Generation quality | Reliability | Latency |
|---|---|---|---|---|---|
| Findings passages not retrieved (dense context/register mismatch) | ✔ | ✔ | ○ | | |
| Reranker prefers Discussion over Results; 2-per-paper cap | ✔ | ✔ | ○ | | ○ (more passages = longer prompt) |
| Wrap × line-based pruning | ✔ | | ✔ | | |
| Validator substring rejections; deletes "Not established" lines | ✔ | | ✔ | ✔ (hard failures) | |
| Phrasing-driven, non-deterministic evidence budget | ✔ | ✔ | ○ | ✔ | ✔ (top_k 3–8 → prompt 1.4–3.2 K tokens) |
| No relevance floor / abstention | ✔ | ✔ | ✔ | | |
| Abstracts and short sections not indexed; boilerplate indexed | ○ | ✔ | | | |
| Noisy section metadata shown to Qwen | ○ | | ✔ | | ○ |
| 4,096-token context at 90 % use | ○ | | ✔ | ✔ | |
| No Ollama options (seed, temperature, num_ctx), no timeout | ○ | | ✔ | ✔ | ✔ |
| Cold load / network at boot / CWD path | | | | ✔ | ✔ |
| Decode 6–7 tok/s, no length policy | | | ○ | | ✔ |
| Missing telemetry (tokens, prunes, failures) | | | | ✔ | ○ |

---

## 3. Mandatory before optimizing latency

Latency work changes prompt size, answer length, and evidence volume. Each of these can trade away correctness, so it is only safe once correctness is measured and the pipeline is deterministic.

1. **Pruning made sentence-aware and output unwrapped**: latency changes to answer length would otherwise interact with a known corruption path.
2. **Validator corrected**: otherwise shorter answers may be rejected or pruned differently, confounding results.
3. **Deterministic evidence budget**: otherwise latency comparisons mix different prompt sizes for the same question.
4. **Explicit generation options** (seed, temperature, `num_ctx`, timeout): reproducible runs and a known context window.
5. **Answer-quality baseline**: fact recall, citation grounding, abstention on controls, prune and failure rates on a retrieval-clean subset.
6. **In-app telemetry**: token counts, load/prefill/decode time, prune events, failure records.

Only after 1–6: answer-length policy, prompt economy, thread tuning, model or quantization changes.

---

## 4. Findings that justify code changes now

Criteria: mechanism proven, change is local, risk of regression is low, and the effect is verifiable with existing tools.

| Change | Finding | Verification | Risk |
|---|---|---|---|
| **4.1 Generation output unwrapped; pruning by sentence/bullet unit, never leaving citation-only fragments** | Wrap proven by direct test; replay on a real answer deletes claim text | Re-score stored raw outputs from benchmark records; no citation-only fragments | Low |
| **4.2 Validator: word-boundary phrase matching; keep "Not established in the supplied evidence." lines** | Substring logic in `generator.py`; prompt requires the phrase pruning removes | Validation outcome distribution on the targeted generation run | Low |
| **4.3 Deterministic classification: stable tie-break; fallback model cannot change the evidence budget non-deterministically** (temperature 0 + fixed seed, or budget independent of fallback) | 5 hash-tie and 6 fallback-unstable questions; fallback varies at fixed seed | `--qu-stability` across seeds and repeats = 1.0 | Low |
| **4.4 Explicit Ollama options on every call (seed, temperature, `num_ctx`) and a generation timeout** | No options anywhere in code; 3,686/4,096 tokens used | Fingerprint and per-call stats show options; no timeouts on suite | Low; `num_ctx 8192` adds ~224 MB KV per extra 4 K (measured) |
| **4.5 Reliability basics: absolute index path, offline model loading, persist failed runs and raw output** | CWD-relative path; HF network warning; failures leave no artifact | Start without network from another directory; failures produce artifacts | Low |

Not on this list, deliberately: changing embeddings, the per-paper cap, the reranker, top_k values, chunking, or answer length. Each is plausible but needs the evidence in Section 5.

---

## 5. Findings that still need evidence

| Candidate change | Missing evidence | Smallest measurement |
|---|---|---|
| Title-context passage embeddings | Net effect when *all* chunks carry titles (E1 was asymmetric) | E2a: re-embed corpus into side file (~24 min), replay retrieval + rerank, fact visibility |
| Per-paper limit 2 → 3 | Effect on L2 diversity and prompt size; redundancy of extra passages | Counterfactual replay on stored pools (L1 shows 29 → 40/44) plus L2 aspect coverage |
| Biomedical cross-encoder | Whether Discussion preference is model-specific | Offline replay of stored pools with the alternative model |
| Relevance floor / abstention threshold | Score distributions for answerable vs unanswerable questions; Qwen behavior on controls | Targeted generation on controls + score histograms from stored records |
| Indexing abstracts and short sections | How much answer-bearing text is currently excluded | Coverage audit (read-only) |
| Paper-first retrieval (Section 6) | End-to-end fact visibility vs current pipeline | Offline prototype over stored index + harness scoring |
| Answer-length policy | Whether fact recall survives shorter answers | After quality baseline: profile-level length test |
| Larger context / more passages | Whether a 7B model uses later blocks faithfully | Evidence-utilization and position-bias metrics on L2 |
| Thread count / quantization / alternative model | Decode-rate sensitivity on this CPU | G5/G6 measurements with fixed prompts |

---

## 6. Target architecture for the next month

### Design principles derived from evidence
- **Build on what works.** Paper retrieval is strong (94 % of L1 papers in the top 20); passage retrieval is weak (35 % of answer passages in the top 20). Within a delivered paper, allowing three passages recovers 40/44 answer passages.
- **Make the evidence budget a function of question scope, not phrasing**, and make it deterministic.
- **Spend latency on evidence, not on prose.** Prefill for one extra passage costs ~4 s; decode of 200 extra answer tokens costs ~30 s.
- **Fail closed.** When evidence is insufficient, say so; never return a pruned or corrupted claim.

### Architecture (one month horizon)

```
                ┌──────────────────────────── Long-running service (warm) ────────────────────────────┐
 Question ──►   │ 1. Query analysis (deterministic)                                                  │
                │    registry grounding · scope = single-study | synthesis | comparison             │
                │    no LLM in the budget path                                                        │
                │                                                                                     │
                │ 2. Paper retrieval (stage A)                                                        │
                │    paper index: title + abstract + metadata (MedCPT article encoder, as documented) │
                │    + aggregate of passage hits → top N papers (N by scope: 3 single / 8–12 synthesis)│
                │                                                                                     │
                │ 3. Passage selection (stage B, within selected papers)                              │
                │    all passages of the N papers (title-context embeddings if E2a confirms)         │
                │    cross-encoder rerank (current or biomedical, by offline evidence)               │
                │    per-paper quota by scope (e.g. 3 single-study; 1–2 per paper for synthesis)     │
                │    relevance floor → abstain path                                                   │
                │                                                                                     │
                │ 4. Context assembly (token budget, not chunk count)                                 │
                │    num_ctx 8 K · sentence-aware trimming that preserves fact-bearing sentences     │
                │    minimal metadata (study, design, year, section) only if accurate                │
                │                                                                                     │
                │ 5. Generation via Ollama HTTP API                                                   │
                │    fixed seed / low temperature · per-profile length policy · streaming · timeout   │
                │                                                                                     │
                │ 6. Verification                                                                     │
                │    sentence-level claim↔citation check · no line pruning                            │
                │    insufficient evidence → explicit refusal, not an error                           │
                │                                                                                     │
                │ 7. Telemetry: tokens, timings, prune/refusal events, evidence IDs, fingerprint      │
                └─────────────────────────────────────────────────────────────────────────────────────┘
 Offline:  ingestion → parsing (abstracts + short sections kept; boilerplate excluded) → paper records
           + passage records → embeddings → Chroma (papers collection + passages collection)
 Quality gate: benchmark harness (L0 every retrieval change; targeted generation weekly)
```

### Why this fits 8 vCPU / 16 GB
| Resource | Budget |
|---|---|
| RAM | Qwen 7B runner ~5.1 GB + KV at 8 K ~0.45 GB; query encoder + cross-encoder ~1 GB (article encoder needed only offline, not in the serving process); Chroma ~0.3 GB → **~7–8 GB**, leaving page cache for the 4.7 GB model file (avoids 119 s cold reloads) |
| CPU per request | Paper retrieval < 0.5 s; cross-encoder over ~40–80 passages ≈ 3–6 s (measured ~0.07 s/candidate); prefill 2.5–3.5 K tokens at ~56–64 tok/s ≈ 40–60 s; decode 300–450 tokens at ~6.5 tok/s ≈ 45–70 s |
| End-to-end | **≈ 90–135 s**, with first streamed tokens after ≈ 45–65 s, within the current 78–141 s range while carrying better evidence |
| Concurrency | One generation at a time (single Ollama slot); queue additional requests; retrieval can run while queued |
| Disk | Paper collection adds well under 10 % to the 224 MB index; re-embedding ≈ 24 min per pass; free space needed before rebuilds (disk 71 % used) |

### One-month sequence with decision gates
| Week | Work | Gate to proceed |
|---|---|---|
| 1 | Section 4 changes (4.1–4.5); in-app telemetry; targeted generation baseline (retrieval-clean questions, controls, truncation questions N1/N4/N5/N6) | Deterministic classification across seeds; no citation-only fragments; first fact-recall, grounding and abstention numbers recorded |
| 2 | Offline evidence: E2a (title context); reranker comparison on stored pools; per-paper quota counterfactuals; coverage audit; paper-first prototype scored with the harness | Choose passage-embedding format, reranker, and quotas by fact visibility (L1) and aspect coverage (L2), without loss of grounded fact recall |
| 3 | Index rebuild (paper collection; abstracts and short sections; boilerplate excluded; chosen embedding format); scope-based evidence budget; relevance floor; context in tokens with `num_ctx 8192` | Retrieval-only run shows the improvement on all 27 + new questions; controls produce abstentions |
| 4 | Generation policy (length per profile, prompt economy, streaming) under the quality gate; long-running service with warm models, offline start, absolute paths; failure handling | Grounded fact recall not lower than week-1 baseline; latency within the stated budget; service survives restart without cold-start stalls |

### Explicitly out of scope this month
- GPU or larger models.
- Agentic multi-step retrieval: its latency cost on CPU is not justified until single-pass evidence quality is fixed.
- Corpus expansion beyond the current 568 papers, until passage-level retrieval quality is demonstrated.
