# LLM EVALUATION — Generation Fidelity & Model Selection

Status: **plan approved for execution; no alternative model tested yet** (updated 2026-10-16).
Question this workstream answers: *Is Qwen 2.5 7B now the primary remaining bottleneck, and can another local model improve answer quality more than further retrieval work?*
Retrieval is treated as stable and complete (see [PROJECT_STATE.md](PROJECT_STATE.md)); it is reopened only if this evaluation produces evidence against it.

---

## 1. Current Qwen baseline

| Item | Value |
|---|---|
| Model | `qwen2.5:7b` (Q4_K_M, 7.6 B parameters, 4.68 GB on disk) |
| Runtime | Ollama 0.40.2 chat API; `num_ctx 8192`, temperature 0, seed 0, 8 threads, keep-alive forever (service) |
| Prompt | System rules + question + 8 evidence blocks (`[E#]`, paper title, design, year, section, ≤ 1,200 chars) |
| Post-processing | Citation normalization → invented-author removal → statistic-bracket fix → sentence-level repair → validation |
| Reference run | `benchmark_runs/20261015_105008_full_final_baseline` (49 questions, 4 threads); thread A/B (13 answers, 8 threads) |

## 2. Current benchmark results

Benchmark: 49 questions — L1 single-paper 16 dev + 8 held-out (68 expected facts), L2 multi-paper 9 + 4, 12 out-of-corpus controls. Gold labels: single labeler, draft status.

| Metric | Dev | Held-out | All |
|---|---|---|---|
| L1 facts in evidence given to the model (visible) | 46 / 52 (88 %) | 13 / 16 (81 %) | 59 / 68 (87 %) |
| L1 facts in raw model output | 37 / 52 | 13 / 16 | 50 / 68 |
| L1 facts in final answer (fact recall) | 37 / 52 (71 %) | 11 / 16 (69 %)¹ | 48 / 68 (71 %) |
| Fact retention (final ÷ visible) | 80 % | 85 %¹ | 81 % |
| Stated facts cited on the same line to the gold paper (citation quality) | 24 / 37 (65 %) | 3 / 11 (27 %) | 27 / 48 (56 %) |
| L2 aspect coverage (lower bound) | 0.66 | 0.53 | — |
| Controls with a claim about the absent topic | — | — | 0 / 12 |
| Controls abstained at retrieval / by the model | — | — | 9 / 3 |
| Validation failures (103 stored answers replayed with current repair) | — | — | 0 |

¹ The 2 held-out facts were lost in post-processing (bracketed statistics, N3), now fixed; on replay held-out recall is 13 / 16 (81 %), retention 100 %.

**Where the 68 L1 facts are lost**

| Stage | Facts lost | Share | Remaining lever |
|---|---|---|---|
| Retrieval (not in evidence) | 9 | 13 % | Hard cases only: passage cut (N1), within-paper ranking (N4, L1-09). Measured lever: longer passages +1 fact for ≈ +23 s |
| **Model omission** (visible but not written) | **9** | **13 %** | Model behaviour; prompt rule did not help (+1 / 42) |
| Post-processing | 0 (after fix) | 0 % | — |
| **Weak citation** (stated, but not cited to the right paper on the same line) | **21 of 48 stated** | 44 % of stated | Model behaviour / answer format |

All 9 model omissions are absent from the raw output (raw = final on dev), so they are generation decisions, not repair damage.

## 3. Current latency measurements

| Measurement | 4 threads (final baseline, 40 answers) | 8 threads (current, 13 answers) |
|---|---|---|
| Prompt reading (prefill) | ≈ 55–64 tok/s | 68.5 tok/s |
| Writing (decode) | ≈ 5.8–6.3 tok/s | 6.88 tok/s |
| Generation time median / p90 | ≈ 110 s / — | 87 s / 111 s |
| End-to-end median / p90 / max | 119 s / 153 s / 225 s | ≈ 95 s (projected: + retrieval 5.4 s) |
| Prompt tokens median / max | 3,298 / 4,107 | same |
| Answer tokens median / max | 361 / 561 | same |
| Out-of-corpus abstention (no LLM) | 3.8 s | same |
| Service cold start after VM boot | pipeline 79 s + model warm 134 s | — |

Rule of thumb: each 100 answer tokens ≈ 15 s; each evidence block ≈ 5 s.

## 4. Infrastructure constraints (measured 2026-10-16)

| Resource | Value | Consequence for model evaluation |
|---|---|---|
| CPU | 8 vCPU (4 cores × 2 threads, Xeon 8573C, AVX-512, AMX), no GPU | Writing speed is set by memory bandwidth (≈ 30 GB/s effective): tok/s ≈ 32 ÷ model GB |
| RAM | 16 GB total, **no swap** | Exceeding RAM kills a process (OOM); model runner must stay ≤ ≈ 11 GB with the service stopped |
| RAM in use (service + Qwen 7B resident) | ≈ 7.5 GB (service 1.7 GB, Qwen runner ≈ 5.5 GB) | Stop the service and unload Qwen before testing 12–14 B models |
| Disk | 29 GB, **14 GB free** (after cleanup) | One model up to 9.3 GB at a time with ≥ 4 GB reserve; never two 12–14 B models together |
| Runtime | Ollama 0.40.2 | Supports `think: false` for Qwen 3 |
| Latency tolerance (owner) | 90–150 s | 7–9 B models fit; 12–14 B models are ≈ 2.5–3.5 min |

## 5. Known strengths and weaknesses of Qwen 2.5 7B (in this system)

| Strengths | Weaknesses |
|---|---|
| Follows the answer template and `[E#]` format (0 failures after repair) | Omits ≈ 15 % of visible facts, mostly secondary statistics beside a correct main finding |
| No claims on out-of-corpus controls; abstains when evidence is irrelevant | Cites per paragraph instead of per claim (56 % same-line citation to the right paper) |
| Correct arithmetic when deriving numbers (6 "unsupported" numbers were valid derivations) | Invents author attributions ("According to X et al.") — repaired in post-processing |
| Fastest model of its quality class on this VM; 5.5 GB RAM | Writes statistics in brackets that collide with citation syntax — repaired |
| Deterministic settings (temperature 0, seed 0) | Prompt instructions (exact-numbers rule) do not change fact retention |

## 6. Is Qwen 2.5 7B now the main bottleneck?

**Generation is now at least as large a quality loss as retrieval, and it is the only stage with an untested lever.**
- Fact loss is split evenly (retrieval 9, model 9 of 68), but the remaining retrieval losses are known hard cases with measured diminishing returns, while the model loss has not been tested against any alternative.
- Citation quality (44 % of stated facts not cited to the right paper on the same line) is purely a generation property and is the largest measured defect in answer grounding.
- The one prompt intervention tried did not move fact retention, so the remaining lever on generation is the model itself (or the answer format, §11 step 6).
- Not yet proven: that a different 7–14 B model does better. That is what this evaluation measures.

## 7. Candidate models (sizes verified against the Ollama registry, 2026-10-16)

| Rank | Model tag | Params | Disk (Q4) | Why | Expected generation time² | Runner RAM (8 K ctx)³ |
|---|---|---|---|---|---|---|
| Baseline | `qwen2.5:7b` | 7.6 B | 4.68 GB | Current production | 87 s (measured) | 5.5 GB (measured) |
| **1** | `qwen3:8b` (non-thinking, `think: false`) | 8.2 B | 5.23 GB | Direct successor; stronger instruction following and reasoning reported; same latency class | ≈ 110 s | ≈ 6.7 GB |
| **2** | `gemma3:12b` | 12.2 B | 8.16 GB | Larger; strong summarization and long-context retention reported; tests whether size buys fidelity | ≈ 160 s | ≈ 9.5–11 GB |
| **3** | `llama3.1:8b` | 8.0 B | 4.92 GB | Different model family; strong long-context instruction following | ≈ 105 s | ≈ 6.3 GB |
| **4** | `phi4:14b` | 14.7 B | 9.05 GB | Science/reasoning oriented; numerical tasks | ≈ 195 s | ≈ 11 GB |
| **5** | `granite3.3:8b` | 8.2 B | 4.94 GB | Built for grounded enterprise RAG and citation | ≈ 105 s | ≈ 6.5 GB |
| **6** | `qwen3:4b-instruct-2507-q4_K_M` | 4.0 B | 2.50 GB | Speed reference: would cut latency ≈ 50 % if quality holds | ≈ 55 s | ≈ 3.5 GB |
| Conditional | `qwen3:14b` (non-thinking) | 14.8 B | 9.28 GB | Only if `qwen3:8b` beats baseline and 12–14 B models show a size effect | ≈ 200 s | ≈ 10.8 GB |
| Optional | `ministral-3:8b`, `mistral-nemo:12b`, `medgemma:4b` | 8–12 B / 4 B | 6.02 / 7.07 / 3.34 GB | Extra families / biomedical domain check if time allows | ≈ 115 / 155 / 60 s | — |

² Generation only, typical question (3,300 prompt + 360 answer tokens), projected from measured bandwidth and compute scaling (prefill ∝ parameters, decode ∝ model bytes). End-to-end adds ≈ 6 s. Tokenizers differ, so prompt token counts and times must be measured.
³ Weights + 8 K KV cache + buffers; Gemma 3 includes a vision projector.

**Excluded (do not fit 16 GB RAM / no swap, or not available):**
| Model | Reason |
|---|---|
| Llama 3.3 | Released only as 70 B (42.5 GB); there is no Llama 3.3 8B |
| `qwen3:30b-a3b` (MoE) | 18.6 GB > RAM, although fast per token |
| `gpt-oss:20b` | 13.8 GB; no headroom without swap |
| `medgemma:27b`, `gemma3:27b` | 17 GB+ |
| `gemma3n:e4b` | 9.8 GB for a 4 B-effective mobile model; poor size/benefit |
| Reasoning-only models (DeepSeek-R1 distills, Qwen 3 thinking mode) | Long hidden reasoning multiplies decode time (minutes per answer) |

## 8. Evaluation design

**Same evidence for every model.** Retrieval already ran once: every record in `benchmark_runs/20261015_105008_full_final_baseline/records/*.json` stores the exact context (`context`) and query analysis (`query_understanding`) given to Qwen. This is the frozen evidence snapshot; no retrieval runs during the comparison.

**Tooling needed (evaluation only, no production change):** `src/evaluation/model_comparison.py`
- Loads the 49 stored contexts; generates with `--model <tag>` through the production generator class (same prompt, same post-processing, `think: false` for Qwen 3).
- Records per answer: raw output, final answer, Ollama stats (prompt tokens, completion tokens, prefill/decode durations, load time), runner RSS and CPU time sampled from `/proc` during generation.
- Scores with the existing `scoring.py` (facts visible/raw/final, same-line grounding, abstention, absent-entity claims) plus `unsupported_numbers()` from `numeric_fidelity_experiment.py`.
- Writes `benchmark_runs/<ts>_model_<tag>/` with records, scores, summary.

**Metrics**
| Metric | Definition | Source |
|---|---|---|
| Fact recall | L1 expected facts in final answer ÷ facts total | automatic |
| Fact retention | facts in final answer ÷ facts visible | automatic |
| Numerical accuracy | numbers stated that appear in the evidence or are verified correct derivations ÷ numbers stated | automatic flag + manual check of flagged numbers |
| Citation quality | stated facts whose line cites a block from the gold paper (automatic); share of claims whose cited block supports the claim (manual, screening set) | automatic + manual |
| Hallucination rate | (unsupported numbers confirmed wrong + claims citing non-supporting blocks + invented entities/attributions in raw output) ÷ answers | automatic flag + manual |
| Out-of-corpus behaviour | controls with a claim about the absent topic; abstention on the 3 controls that reach the LLM | automatic |
| Prompt / completion tokens | Ollama `prompt_eval_count` / `eval_count` | Ollama |
| Generation latency | median / p90 generation seconds; prefill and decode tok/s | Ollama |
| RAM usage | peak runner RSS; `ollama ps` | `/proc` |
| CPU usage | runner CPU seconds ÷ wall seconds (average cores used) | `/proc` |
| Format compliance | validation outcome (pass / repaired / fail) | pipeline |

**Question sets**
| Set | Questions | Purpose |
|---|---|---|
| Screening (20) | L1 with omitted facts: L1-01, L1-02, L1-03, L1-04, L1-09, L1-10, L1-11, L1-12, L1-16, N3 · L1 fully stated (regression guard): L1-05, L1-13, N2, N6 · L2: L2-02, L2-06, M4 · controls reaching the LLM: L1-C2, C7, C10 | Fast elimination (≈ 40 min per 7–9 B model, ≈ 70 min per 12–14 B model) |
| Full (49) | All benchmark questions (9 retrieval-abstained controls replayed to confirm no-claim behaviour on irrelevant evidence) | Decision run for finalists |
| Stability (5) | L1-02, L1-10, L1-16, L2-02, C7, second run | Detects run-to-run noise (observed ± 1 fact) |

## 9. Decision criteria

A model replaces Qwen 2.5 7B only if, on the full set and compared with Qwen re-run on the same snapshot at 8 threads:

| Criterion | Threshold |
|---|---|
| Fact recall | ≥ +5 percentage points (≈ +4 of 68 L1 facts), same direction on dev and held-out |
| Numerical accuracy | ≥ baseline |
| Citation quality | ≥ baseline (automatic and manual) |
| Hallucinations | No additional confirmed hallucinations |
| Out-of-corpus | 0 claims on 12 controls; abstains on L1-C2, C7, C10 as Qwen does |
| Format | 0 validation failures |
| Resources | Runs with the service on the VM without OOM: runner ≤ 11 GB |
| Latency | Median end-to-end ≤ 150 s; a 12–14 B model above that only with explicit owner approval for the measured gain |

Screening gate (to reach the full set): fact retention ≥ baseline + 5 pts on the 14 L1 screening questions **and** 0 control claims **and** 0 validation failures.

## 10. Disk, RAM and latency summary

| | Requirement |
|---|---|
| **Disk** | Peak extra 9.3 GB (largest candidate) on top of current use; 14 GB free → ≥ 4.7 GB reserve. Test sequentially, `ollama rm` after each unless a finalist. Total download ≈ 37 GB over the whole plan (ranks 1–6 + conditional). Results ≈ 5 MB per model |
| **RAM** | 7–9 B: 6.3–6.7 GB runner — can run with the service up (≈ 9 GB total if Qwen 7B is unloaded). 12–14 B: 9.5–11 GB runner — **stop `pharma-rag` and unload Qwen 7B first** (no swap; OOM risk otherwise) |
| **Latency** | 7–9 B: +0 to +25 % (≈ 105–115 s generation) — within tolerance. 12 B: ≈ +85 % (≈ 160 s). 14 B: ≈ +125 % (≈ 195–200 s) — above tolerance. 4 B: ≈ −40 to −50 % |
| **Throughput** | 7–9 B ≈ 30 answers/h; 12 B ≈ 20/h; 14 B ≈ 17/h |
| **Evaluation wall time** | Screening ≈ 40–70 min per model; full set ≈ 1.5 h (7–9 B) / 2.5–3 h (12–14 B); whole plan ≈ 1.5–2 working days, mostly unattended |

## 11. Exact evaluation order

| Step | Action | Time |
|---|---|---|
| 0 | Build `model_comparison.py`; verify it reproduces Qwen results on 3 stored contexts | ≈ 2–3 h |
| 1 | **Baseline**: `qwen2.5:7b`, 8 threads, full 49 + stability 5 | ≈ 1.5 h |
| 2 | Screening `qwen3:8b` (`think: false`) | ≈ 40 min |
| 3 | Screening `llama3.1:8b` | ≈ 40 min |
| 4 | Screening `granite3.3:8b` | ≈ 40 min |
| 5 | Stop service, unload Qwen; screening `gemma3:12b`, then `phi4:14b` (one at a time); restart service | ≈ 2.5 h |
| 6 | Screening `qwen3:4b-instruct-2507` (speed reference) | ≈ 25 min |
| 7 | Conditional `qwen3:14b` (only if step 2 passes and step 5 shows a size effect) | ≈ 70 min |
| 8 | Full set + manual numeric/citation review for ≤ 2 finalists | ≈ 3–5 h |
| 9 | Decision; if a winner meets §9, switch model by configuration and rerun the final baseline end-to-end | ≈ 2 h |
| 10 | If no model meets §9: test one-claim-per-line answer format on Qwen 2.5 7B with the same snapshot | — |

Each step records its row in §12 before the next starts; a model that fails screening is removed (`ollama rm`).

## 12. Results register

| Model | Size / quant | Runner RAM | CPU (avg cores) | Gen. latency median / p90 | Prompt tok | Completion tok | Fact recall | Fact retention | Numerical acc. | Citation quality | Hallucinations | Out-of-corpus | Assessment |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **qwen2.5:7b** (final baseline, 4 thr) | 7.6 B / Q4_K_M, 4.68 GB | ≈ 5.5 GB | ≈ 4 (4 thr) | ≈ 110 s / — | 3,298 | 361 | 71 % | 81 % (dev 80, held-out 85) | No unsupported values found; 6 flagged = valid derivations (13 answers) | 56 % same-line to gold paper | Invented attributions (repaired) | 0 / 12 claims | Baseline — rerun at 8 threads in step 1 |
| qwen2.5:7b (snapshot, 8 thr) | | | | | | | | | | | | | step 1 |
| qwen3:8b | | | | | | | | | | | | | step 2 |
| llama3.1:8b | | | | | | | | | | | | | step 3 |
| granite3.3:8b | | | | | | | | | | | | | step 4 |
| gemma3:12b | | | | | | | | | | | | | step 5 |
| phi4:14b | | | | | | | | | | | | | step 5 |
| qwen3:4b-instruct-2507 | | | | | | | | | | | | | step 6 |

Per-model notes (tag digest, date, failures with examples, decision) are added below this table as each model is tested.

## 13. Risks

| Risk | Effect | Mitigation |
|---|---|---|
| Small benchmark (68 L1 facts; ± 1 fact run noise) | A 5-point difference is ≈ 4 facts — near noise | Stability repeats; require same direction on dev and held-out; manual review of differing facts |
| Single-labeler regex gold | Different phrasing by another model may be scored as missing | Manually review every fact a candidate "loses" vs baseline |
| Prompt tuned on Qwen 2.5 | Other models may be disadvantaged by Qwen-specific wording / repair rules | Keep prompt identical for the decision; note format failures separately |
| OOM with 12–14 B (no swap) | Killed runner or service | Stop service and unload Qwen; one model at a time; monitor RSS |
| Qwen 3 thinking mode left on | Minutes of hidden reasoning, invalid comparison | Pass `think: false`; verify no `<think>` text in output |
| Latency vs quality conflict | Best model may be 12–14 B (≈ 3 min) | Owner decision with measured numbers; 4 B reference shows the opposite trade |
| Disk exhaustion | Failed pulls / index damage | Sequential pulls, `ollama rm` after each, keep ≥ 4 GB free |
| Licence terms | Gemma, Llama have custom licences | Check licence before production adoption |

## 14. Recommendation

**Model evaluation is the highest-value next activity.**
1. Generation now loses as many facts as retrieval (9 vs 9 of 68) and is responsible for the main grounding defect (44 % of stated facts not cited to the right paper on the same line).
2. Retrieval's remaining misses have measured diminishing returns; generation has an untested lever.
3. The comparison is cheap and isolated: evidence is already stored, no production change, ≈ 1.5–2 days mostly unattended, and disk (14 GB free) and RAM allow every viable candidate one at a time.
4. Expected outcome: a 7–9 B model (`qwen3:8b` first) that matches latency with better retention is the best case; if only 12–14 B models win, the owner decides on the latency trade with numbers; if none wins, the answer-format experiment (step 10) is next and Qwen 2.5 7B remains.
