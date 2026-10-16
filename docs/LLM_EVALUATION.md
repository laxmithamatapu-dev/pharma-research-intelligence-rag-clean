# LLM EVALUATION — Generation Fidelity & Model Selection

Status: **complete** (2026-10-16). Result: **no tested model, quantization or prompt variant beats Qwen 2.5 7B Q4_K_M under the decision criteria; it remains the production model** (§12–§16). Deployment view: [ENTERPRISE_DEPLOYMENT_ASSESSMENT.md](ENTERPRISE_DEPLOYMENT_ASSESSMENT.md).
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
| CPU | 8 vCPU (4 cores × 2 threads, Xeon 8573C, AVX-512, AMX), no GPU | Writing speed falls with model size (measured 6.9 tok/s at 4 B to 3.3 tok/s at 14 B, §14); at Q4 it is partly compute-bound, not purely bandwidth-bound |
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

**Tooling (built 2026-10-16, evaluation only, no production change):** `src/evaluation/model_comparison.py`
```bash
HF_HUB_OFFLINE=1 .venv/bin/python src/evaluation/model_comparison.py --model qwen3:8b --set screening   # or --set full | stability | --ids L1-02,C7
```
Output: `benchmark_runs/<ts>_model_<tag>[_label]/` with `records/`, `scores.json`, `summary.md`. Other loaded Ollama models are unloaded first (use `--keep-others-loaded` to skip); `think` is off automatically for `qwen3*`. Do not use the service while a comparison runs (timings would mix).
Verified 2026-10-16: replaying 3 stored contexts with `qwen2.5:7b` gives identical prompt tokens (3,360 / 3,120 / 3,149), identical facts stated and identical abstention to the stored baseline; runner used 8.0 cores, 5.8 GB.
The 9 controls that abstain at retrieval have no context and are model-independent; the snapshot replays the 40 answers that reached the LLM (including controls L1-C2, C7, C10).
- Loads the 40 stored contexts; generates with `--model <tag>` through the production generator class (same prompt, same post-processing, `think: false` for Qwen 3).
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
| Full (40) | All 40 benchmark answers that reached the LLM (9 retrieval-abstained controls are model-independent) | Decision run |
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

## 12. Results register (measured 2026-10-16)

All runs: same stored evidence (`benchmark_runs/20261015_105008_full_final_baseline`), same prompt and post-processing, `num_ctx 8192`, temperature 0, seed 0, 8 threads, one model loaded. Run folders: `benchmark_runs/20261016_*_model_*`.

### 12.1 Full set (40 answers that reach the LLM; 24 L1 questions, 59 visible facts)

| Model | Facts stated (auto) | Facts stated (adjudicated¹) | Fact retention (adjudicated) | Gen. median / p90 | Answer tokens (median) | Validation failures |
|---|---|---|---|---|---|---|
| **qwen2.5:7b Q4_K_M** | 50 / 59 | **50 / 59** | **85 %** (dev 80 %, held-out 100 %) | **96 s / 114 s** | 370 | 0 |
| qwen3:8b Q4_K_M (`think: false`) | 45 / 59 | 48 / 59 | 81 % (dev 76 %, held-out 100 %) | 175 s / 209 s | 566 | 0 |

### 12.2 Screening set (20 answers: 14 L1 with 40 visible facts, 3 L2, 3 controls that reach the LLM)

| Configuration | Disk | Runner RAM² | Facts stated auto / adjudicated¹ | Fact line cites gold paper³ | Numerical errors (manual) | Out-of-corpus (manual) | Gen. median / p90 | Prompt / answer tokens | Prefill / decode tok/s |
|---|---|---|---|---|---|---|---|---|---|
| **qwen2.5:7b Q4_K_M (current)** | 4.68 GB | 5.2 GB | 32 / **32** | 72 % | 1 (sign error, L1-04 week 60) | 3/3 correct, concise | **90 / 106 s** | 3,302 / 349 | 77 / 7.3 |
| qwen2.5:7b Q8_0 | 8.10 GB | 9.2 GB | 25 / 28 | 48 % | 0 | 3/3 correct, concise | 116 / 144 s | 3,302 / 326 | 53 / 6.2 |
| qwen3:8b Q4_K_M | 5.23 GB | 6.4 GB | 29 / 32 | 100 % | 0 | 3/3 correct (4 automatic flags were false positives) | 160 / 201 s | 3,289 / 476 | 65 / 5.0 |
| qwen3:4b-instruct-2507 Q4_K_M | 2.50 GB | 4.0 GB | 33 / **34** | 100 % | 2 (wrong difference; kcal = kJ) | 3/3 correct, concise | 128 / 165 s | 3,281 / 616 | 101 / 6.9 |
| llama3.1:8b Q4_K_M | 4.92 GB | 6.0 GB | 24 / 27 | 75 % | 0 | 3/3 correct | 127 / 147 s | 3,174 / 378 | 67 / 5.4 |
| gemma3:12b Q4_K_M | 8.16 GB | 9.8 GB | 33 / 33 | 100 % | 0 | 3/3 correct but padded with off-topic findings | 215 / 244 s | 3,225 / 594 | 43 / 4.2 |
| phi4:14b Q4_K_M | 9.05 GB | 10.5 GB | 30 / 33 | 100 % | 0 (1 unverified derivation) | 3/3 correct but padded with off-topic findings | 224 / 256 s | 3,174 / 442 | 36 / 3.3 |
| qwen2.5:7b, claim-per-bullet prompt | — | 5.2 GB | 26 / 29 | 100 % | 0 | 3/3 correct | 91 / 105 s | 3,343 / 317 | 75 / 7.2 |
| qwen2.5:7b, evidence order reversed | — | 5.2 GB | 30 / 30 | 53 % | 0 | 3/3 correct | 91 / 111 s | 3,302 / 352 | 75 / 7.2 |
| qwen2.5:7b, first 4 blocks only | — | 5.2 GB | 22 / 25 (of 37 visible) | 59 % | 0 | 3/3 correct | 58 / 73 s | 1,916 / 277 | 83 / 7.8 |

¹ Adjudicated: two gold patterns were too narrow — L1-04 accepted only within-group reductions (367/317/200 kcal) although the paper's placebo-adjusted differences (292/240/270 kcal) answer the question equally; L1-05 rejected "no statistically significant". Re-scored for every configuration with the same rules.
² Peak `llama-server` RSS on the first answer (weights + 8 K KV cache + buffers), before prompt-cache growth (§15.4).
³ Share of stated facts whose own line cites a block from the gold paper. All CPU runs used 7.9–8.0 cores on average. All configurations: 0 validation failures, 0 invented author attributions in raw output, no `<think>` output.

**Per-model notes**
- **qwen2.5:7b Q4_K_M** — best balance; concise; occasionally cites per paragraph instead of per line; one arithmetic sign error (described placebo's +69.6 kcal as a reduction).
- **qwen2.5:7b Q8_0** — no quality gain over Q4_K_M (−4 adjudicated facts, within noise but not positive), +30 % time, +4 GB RAM. Quantization is not the bottleneck.
- **qwen3:8b** — cites every claim (best citation behaviour together with the 12–14 B models), quoted the paper's own differences correctly, but writes 50 % longer answers and is 80 % slower; slightly lower retention on the full set (48 vs 50).
- **qwen3:4b-instruct-2507** — highest adjudicated retention (+2 facts, within noise) at the lowest RAM (4.0 GB), but verbose (616 tokens) so not faster; 2 numerical errors in one answer.
- **llama3.1:8b** — lowest retention (27), weakest citation; not competitive.
- **gemma3:12b / phi4:14b** — +1 fact each (noise), per-claim citations, correct numbers, but 2.4–2.5× slower (215–224 s median, p90 > 240 s), 10–10.5 GB RAM, and verbose on out-of-corpus questions. Gemma repeats the section instructions in its headings.

### 12.3 Decision against the criteria (§9)

| Candidate | Fact recall ≥ +5 pts | Numbers ≥ baseline | Citations ≥ baseline | No extra hallucination | Abstention equal | RAM OK | Latency ≤ 150 s | Verdict |
|---|---|---|---|---|---|---|---|---|
| qwen3:8b | ✗ (−3 pts full set) | ✓ | ✓ | ✓ | ✓ (verbose) | ✓ | ✗ (175 s) | Reject |
| qwen3:4b-instruct-2507 | ✗ (+5 pts screening only, = noise) | ✗ (2 errors) | ✓ | ✗ | ✓ | ✓ | ✓ (128 s) | Reject for now |
| llama3.1:8b | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Reject |
| gemma3:12b | ✗ (+2.5 pts) | ✓ | ✓ | ✓ | ✗ (padded) | ⚠ 9.8 GB | ✗ (215 s) | Reject |
| phi4:14b | ✗ (+2.5 pts) | ✓ | ✓ | ✓ | ✗ (padded) | ⚠ 10.5 GB | ✗ (224 s) | Reject |
| qwen2.5:7b Q8_0 | ✗ (−10 pts) | ✓ | ✗ | ✓ | ✓ | ⚠ 9.2 GB | ✓ (116 s) | Reject |

**No candidate meets the replacement criteria. Qwen 2.5 7B Q4_K_M remains the production model.**

## 13. Root-cause analysis of generation quality

| Factor | Experiment | Result | Conclusion |
|---|---|---|---|
| Model architecture / size | 6 models, 4–14 B, same evidence | Adjudicated retention 27–34 of 40; all models within ± 2 facts of Qwen 2.5 except Llama (−5) | Fact retention is **not** model-limited in the 4–14 B range on CPU; larger models improve citation style, not fact count |
| Quantization | Qwen 2.5 7B Q4_K_M vs Q8_0 | 32 vs 28 facts; citations 72 % vs 48 % | Near-lossless precision gives no gain; Q4_K_M is not causing fact loss |
| Prompt / answer structure | Profile sections vs flat claim-per-bullet | 32 vs 29 facts; citations 72 % → 100 % | Structure moves **citation granularity**, not retention; the flat format loses some facts |
| Section template fit | Inspection (L1-04, L1-05) | Quantitative single-study questions classified as COMPARISON get Similarities/Differences/Mechanism/Safety sections; numbers land in odd sections or are replaced by "Not established" boilerplate | Template mismatch is a real but question-specific cause |
| Context size | 8 blocks vs first 4 | Retention 80 % → 68 % of the facts still visible (25/37); 3 facts lost from evidence | Fewer blocks hurt; context size is **not** overloading the model (≈ 3,300 tokens of 8,192) |
| Evidence position | Ranked vs reversed order | 32 vs 30 facts (noise); citation accuracy 72 % → 53 % | No strong lost-in-the-middle effect; block-1 advantage (88 % vs 73 %) is mainly because block 1 holds the main finding |
| Answer length | Correlation over baseline; cross-model | Shorter vs longer half: 78 % vs 81 %; verbose models (qwen3, gemma) do not retain more | Length is not the lever |
| Gold-label scoring | Manual adjudication | 2 of 14 screening questions mis-scored for some models | Part of the measured "loss" is regex scoring, not the model |

**What remains of the ≈ 15 % fact loss:** secondary statistics that the model judges peripheral (e.g. sample sizes, a second p-value, HR beside the main finding) plus template mismatches. No 4–14 B model, quantization or prompt variant tested removes it.

## 14. Latency analysis

Typical answer: 3,302 prompt tokens + 370 answer tokens. Generation time = prompt ÷ prefill rate + answer ÷ decode rate (measured rates, §12.2).

| Configuration | Prefill (s) | Decode (s) | Total at equal tokens | Measured median (own answer length) |
|---|---|---|---|---|
| qwen2.5:7b Q4_K_M | 43 | 51 | **94 s** | 96 s |
| qwen2.5:7b Q8_0 | 62 | 60 | 122 s (+30 %) | 116 s |
| qwen3:4b-instruct-2507 | 33 | 54 | 86 s (−9 %) | 128 s (answers +66 % longer) |
| llama3.1:8b | 49 | 68 | 117 s (+25 %) | 127 s |
| qwen3:8b | 51 | 75 | 126 s (+34 %) | 175 s (answers +53 % longer) |
| gemma3:12b | 78 | 89 | 167 s (+78 %) | 215 s |
| phi4:14b | 92 | 111 | 203 s (+116 %) | 224 s |

| Latency component (current model) | Share / size | Evidence |
|---|---|---|
| Reading the prompt (prefill) | ≈ 45 % (43 s); compute-bound | 77 tok/s on 4 physical cores |
| Writing the answer (decode) | ≈ 54 % (51 s) | 7.3 tok/s |
| Retrieval + rerank | ≈ 5–12 s | measured 5.4 s median; 11.9 s after model reload (cold cache) |
| Each evidence block | ≈ 350 tokens ≈ 4.5 s | 8 → 4 blocks: 3,302 → 1,916 tokens, 90 → 58 s |
| Fixed instructions | ≈ 610 tokens ≈ 8 s | prompt minus context |
| Each 100 answer tokens | ≈ 14 s | 1 ÷ 7.3 tok/s |
| Model size | 4 B → 14 B: prefill 101 → 36 tok/s, decode 6.9 → 3.3 tok/s | §12.2 |
| Quantization | Q4 → Q8: prefill −31 %, decode −15 % | Q8 decode is not 1.7× slower: at Q4 decode is partly compute-bound (dequantization), not purely memory-bandwidth-bound |
| Answer verbosity | Biggest model-to-model difference after size | qwen3 / gemma write 50–70 % more tokens |

## 15. Infrastructure findings

### 15.1 RAM per model (runner, 8 K context, before prompt cache)
Qwen 3 4B 4.0 GB · Qwen 2.5 7B Q4 5.2 GB · Llama 3.1 8B 6.0 GB · Qwen 3 8B 6.4 GB · Qwen 2.5 7B Q8 9.2 GB · Gemma 3 12B 9.8 GB · Phi-4 14B 10.5 GB. The application (retrieval models, Chroma) adds ≈ 1.7 GB.

### 15.2 CPU
Every model used ≈ 8 cores for the whole generation; one answer saturates this VM.

### 15.3 Disk
Model files: 2.5 GB (Qwen 3 4B) to 9.1 GB (Phi-4). Downloads ran at ≈ 80 MB/s (8 GB in ≈ 100 s).

### 15.4 Prompt-cache memory growth (production risk)
Ollama 0.40.2 starts `llama-server` with a host-RAM prompt cache of up to **8,192 MiB** (log: "cache state: 39 prompts, 7,804 MiB") and offers no setting to change it. Each answered prompt adds its KV state: ≈ 0.19 GB (Qwen 2.5 7B) to ≈ 0.5 GB (Qwen 3 8B / 12–14 B models). With keep-alive forever, the Qwen 2.5 runner grew from 5.2 GB to 12.9 GB over 40 answers. On a 16 GB machine without swap this can exhaust memory (runner 13.4 GB + application 1.7 GB + OS). The evaluation avoided it by reloading the model when available RAM fell below 3.5 GB (Gemma: 12 reloads in 20 answers, Phi-4: 20).
**Required production fix (not yet implemented):** the service must bound runner memory — unload the model (`keep_alive: 0`) when available RAM drops below a threshold or after N answers (reload ≈ 8 s from page cache), or use a finite `OLLAMA_KEEP_ALIVE`. Re-check when Ollama is upgraded.

## 16. Deployment recommendation

| Item | Recommendation |
|---|---|
| Production model | **qwen2.5:7b Q4_K_M** (unchanged) |
| Quantization | **Q4_K_M** — Q8_0 costs +30 % time and +4 GB RAM with no quality gain |
| Fallback / small-machine option | qwen3:4b-instruct-2507 Q4_K_M (4.0 GB RAM) — equal retention, but verbose and 2 numerical errors; needs a full-set run and an answer-length limit before use |
| Larger models | Not justified on CPU: +1 fact (noise) for 2.4× latency and 2× RAM; reconsider only with a GPU |
| Next quality lever | Answer template fit (single-study quantitative questions should not get comparison sections) and per-claim citation enforcement in post-processing — evaluate on the same snapshot |
| Required ops fix | Bound Ollama prompt-cache memory (§15.4) |
| Highest-quality configuration that realistically runs here | **Qwen 2.5 7B Q4_K_M, 8 threads, 8 evidence blocks, 8 K context**: 85 % fact retention, 0 out-of-corpus claims, ≈ 96 s generation (≈ 100 s end-to-end), 5.2 GB runner RAM |

## 17. Risks

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

