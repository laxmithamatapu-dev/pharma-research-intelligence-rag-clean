# LLM EVALUATION — Generation Fidelity & Model Selection

Workstream status: **planned, not started** (checkpoint 2026-10-15). This document records every generation model tested, with identical evidence and the same scoring.

## 1. Is Qwen 2.5 7B now the limiting factor?

**Probably the largest remaining quality limit, but not yet proven to be model-specific.**

| Evidence | Value | Interpretation |
|---|---|---|
| Facts visible to the LLM (L1 dev / held-out) | 88 % / 81 % | Retrieval delivers most evidence |
| Facts stated ÷ facts visible | 80 % / 85 % | The model drops 15–20 % of what it is given |
| Stated facts cited on the same line to the gold paper | 65 % / 27 % | Claim-level citation is weak |
| Exact-numbers prompt rule (A/B, 13 questions) | +1 / 42 facts | Prompt wording does not move the gap |
| Missing facts (manual review) | mostly secondary statistics beside correct main findings | Selection/compression behaviour of a 7B model |
| Generation failures after repair | 0 / 103 | Format compliance is acceptable |

A prompt change did not help; the remaining losses are model behaviour on long (≈ 3,300-token) evidence. Whether a different local model does better is an **empirical question** answered only by the evaluation below.

## 2. Hardware envelope (what can run)

| Constraint | Consequence |
|---|---|
| 16 GB RAM; app ≈ 1.5 GB; OS/page cache ≈ 2–3 GB | Model + 8 K KV cache must stay ≤ ≈ 10 GB (Q4 weights ≤ ≈ 9 GB) |
| Decode is memory-bandwidth-bound (≈ 29 GB/s) | Writing speed ≈ 29 / model GB tokens/s → 7–9B Q4 ≈ 5.5–7 tok/s; 12–14B Q4 ≈ 3–3.5 tok/s |
| Prefill ≈ 55–70 tok/s for 7B; scales ≈ inversely with parameters | 14B ≈ 30–35 tok/s → ≈ 100 s just to read a 3,300-token prompt |
| Latency tolerance 90–150 s | 7–9B fits; 12–14B ≈ 3–4 min per answer (exceeds tolerance unless quality gain is large) |
| **Disk free 6.4 GB** | One 7–9B model (≈ 5 GB) fits; a 12–14B model (≈ 8–9 GB) needs ≈ 3 GB freed first |

Speed estimates for untested models are projections from the measured bandwidth; record measured values when tested.

## 3. Candidate models

Selection criteria: instruction following with long context (≥ 8 K), scientific/biomedical text, numerical fidelity, citation-format compliance, Ollama availability, fits the envelope. **Verify exact tags and availability with `ollama pull` before testing**; tags below are the expected Ollama library names.

| Priority | Model (expected tag) | Params / Q4 size | Why test | Expected speed vs Qwen 2.5 7B |
|---|---|---|---|---|
| Baseline | `qwen2.5:7b` | 7.6 B / 4.7 GB | Current production | 1.0× |
| **1** | `qwen3:8b` (non-thinking mode) | 8 B / ≈ 5.2 GB | Successor family; same tokenizer style; stronger reasoning/instruction following reported | ≈ 0.9× |
| **2** | `llama3.1:8b` | 8 B / ≈ 4.9 GB | Different family; strong long-context instruction following | ≈ 0.95× |
| **3** | `gemma3:12b` | 12 B / ≈ 8 GB | Larger; strong summarization/fact retention reported; tests whether size buys fidelity | ≈ 0.55× (≈ 3–4 min) |
| **4** | `phi4:14b` | 14 B / ≈ 9 GB | Reasoning/science-oriented; numerical tasks | ≈ 0.5× |
| 5 | `qwen2.5:14b` | 14.7 B / ≈ 9 GB | Same family, larger — isolates the effect of size | ≈ 0.5× |
| Reference | `qwen2.5:3b` / `phi4-mini` | 3–4 B / ≈ 2–2.5 GB | Speed floor; shows how much quality small models lose | ≈ 2× |
| Domain check (optional) | biomedical fine-tunes (e.g. Meditron / BioMistral GGUF) | 7 B / ≈ 4–5 GB | Domain pretraining; older bases with weaker instruction following and citation compliance — include only if available as GGUF | ≈ 1× |

Not viable on this VM: ≥ 27 B dense models and large MoE models (weights alone exceed RAM at Q4); unquantized models.

## 4. Evaluation protocol

**Principle: identical evidence for every model.** Retrieval is frozen: for each question the evidence context (paper-first, current settings) is captured once and replayed to every model. Differences are then attributable to generation only.

| Step | Detail |
|---|---|
| Evidence snapshot | For all 49 questions, store `query_info`, evidence chunks, and the built context (one retrieval pass) |
| Screening set (≈ 20 questions) | 10 L1 with dropped facts, 4 L1 fully stated, 3 L2, 3 controls that pass the retrieval floor (L1-C2, C7, C10) |
| Full set | All 49 questions, for models that pass screening |
| Settings | Same prompt, `num_ctx 8192`, temperature 0, seed 0, 8 threads, keep-alive, warm model, one model loaded at a time |
| Repeats | 1 (cold-cache first run); 2nd run on 5 questions to confirm stability |
| Post-processing | Current production pipeline (normalization, attribution removal, repair, validation) |
| Resource capture | `ollama ps` (RAM), `ps` RSS of the runner, Ollama token stats (prompt/answer tokens, prefill/decode rates, load time) |
| Manual review | Numerical accuracy and citation accuracy on the screening set (two passes) |
| Disk hygiene | Remove each tested model after recording results unless it is a finalist |

**Metrics**
| Metric | Definition |
|---|---|
| Fact visibility | Expected facts present in the evidence given to the model (same for all models by construction) |
| Fact recall | Expected facts stated in the final answer ÷ facts total |
| Generation fidelity | Facts stated ÷ facts visible |
| Numerical accuracy | Stated numbers that match the evidence or are arithmetically correct derivations ÷ numbers stated (manual check of derived values) |
| Citation accuracy | Stated facts whose sentence cites a block that contains the fact ÷ facts stated |
| Hallucination | Unsupported numbers, claims citing blocks that do not support them, invented entities/attributions (before repair) |
| Out-of-corpus behaviour | Controls answered with abstention and no claim about the absent topic |
| Format compliance | Validation outcome (pass_first / repaired / fail) |
| Latency | End-to-end and generation; prefill and decode tokens/s |
| Resources | RAM (runner RSS), CPU threads, disk size |

**Decision rule**
A model replaces Qwen 2.5 7B only if, on the full set: generation fidelity +5 points or more, numerical accuracy and citation accuracy not lower, 0 claims on controls, 0 validation failures, and median end-to-end latency ≤ 150 s (or the owner explicitly accepts a longer time for the measured gain).

## 5. Results register

### 5.1 Comparison table

| Model | Size / Quant | RAM (runner) | CPU threads | Latency median / p90 | Prompt tok (median) | Answer tok (median) | Fact visibility | Fact recall | Fidelity | Numerical accuracy | Citation accuracy | Hallucination | Out-of-corpus | Assessment |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **qwen2.5:7b** (baseline) | 7.6 B / Q4_K_M, 4.7 GB | ≈ 5.5 GB (8 K ctx) | 8 | 87 / 111 s generation (8 thr); 119 / 153 s end-to-end (4 thr) | 3,298 | 361 | L1 88 % dev / 81 % held-out | 71 % / 81 % | 80 % / 85 % | Not manually reviewed; 6 "unsupported" numbers in 13 answers were correct derivations | 65 % / 27 % same-line to gold paper | Invented author attribution observed (repaired); no unsupported claims in controls | 12/12 no claims (9 retrieval abstain, 3 model abstained) | Production baseline; fidelity gap is the main weakness |
| qwen2.5:1.5b (speed reference only) | 1.5 B / Q4, 1.0 GB | ≈ 1.4 GB | 4 | not measured end-to-end | 3,853 (probe) | 150 (probe) | — | — | — | — | — | — | — | Prefill 204 tok/s, decode 21.6 tok/s (3.7× faster); quality not evaluated |

### 5.2 Per-model records
Add one section per tested model: tag and digest, date, settings, resource capture, metric table, notable failures with examples, and decision.
