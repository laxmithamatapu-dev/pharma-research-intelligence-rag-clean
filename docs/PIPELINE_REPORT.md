# Pharma Research Intelligence RAG — Final Pipeline Report

Date: 2026-10-15 · Branch `fix/correctness-2day` · Final baseline run: `benchmark_runs/20261015_105008_full_final_baseline`
Deployment: Azure VM, **8 vCPU** (4 cores × 2 threads, Xeon Platinum 8573C, AVX-512/AMX), **16 GB RAM**, CPU only, local Ollama.
Benchmark: 49 questions — 16 + 8 held-out single-paper (L1), 9 + 4 held-out multi-paper (L2), 12 out-of-corpus controls. Held-out questions were written after the system was designed and were not used to tune it.

---

## 1. Answer quality and evidence grounding

| Metric | Previous pipeline | **Final pipeline** |
|---|---|---|
| L1 expected facts visible to the LLM (16 dev questions, 52 facts) | 26 (50 %) | **46 (88 %)** |
| L1 expected facts stated in the answer (dev) | — | **37 (71 %)** |
| L1 held-out: facts visible / stated (8 questions, 16 facts) | 8 (50 %) / — | **13 (81 %) / 13 (81 %)** |
| L1 questions with no expected fact visible (dev / held-out) | 5 / 4 | **0 / 2** |
| L2 aspect coverage (dev / held-out) | 0.41 / 0.30 | **0.66 / 0.53** |
| L2 distinct gold papers cited per answer | — | 2.3–2.5 |
| Out-of-corpus controls with a claim about the absent topic | — | **0 of 12** |
| Controls answered without an LLM call (retrieval abstention) | — | 9 of 12 (≈ 3.8 s each) |
| Answers lost to validation (103 stored answers replayed) | 5 | **0** |

Notes
- Held-out L2 coverage is a lower bound: gold paper lists were drawn from titles, and inspection shows the selected papers are relevant (e.g. paediatric adalimumab-vs-infliximab cohorts for M4; FAERS pharmacovigilance studies for M1).
- Remaining L1 misses: N1 (fact lies past the 1,200-character passage cut), N4 and L1-09 (answer passage ranks low inside the right paper), L1-06 and L1-14 (partial).
- Known generation-side limits: about 25 % of visible facts are not stated (numbers paraphrased or omitted); citations are often given per paragraph rather than per bullet; study-design labels are keyword-based and approximate for some reviews.

## 2. Architecture (final)

```
Offline:  PMC XML → parse → enrich ─┬─► passage index  (11,239 passages, MedCPT mean pooling)        ≈ 25 min
                                    └─► paper index    (568 papers, title + abstract, MedCPT CLS, IP) ≈ 2.5 min
Online:   question
            → rule-based analysis (intent, type, drugs, scope)                     ≈ 0.002 s
            → candidate papers: paper index top 30 ∪ papers of passage top 60       ≈ 0.1 s
            → cross-encoder ranks papers on title + abstract                         ≈ 2.3 s
                └─ best paper score < 3.5 → abstain ("Not established…"), no LLM
            → budget: single study or clear top paper → 6 + 2 passages; otherwise 8 papers × 1
            → cross-encoder picks passages inside the chosen papers                 ≈ 2–8 s
            → evidence blocks with paper title, design, year, section (≤ 1,200 chars each)
            → Qwen 2.5 7B (Ollama chat API, 8,192 context, temperature 0, seed 0)   ≈ 110 s
            → citation normalization, attribution removal, sentence-level repair
            → answer + references + telemetry (JSON record per run)
Serving:  serve.py (HTTP /health, /ask), model pre-warmed, one answer at a time; CLI app.py; systemd unit
Rollback: RETRIEVAL_MODE=legacy
```

## 3. Latency (measured, final baseline)

| | Value |
|---|---|
| **Generated answers (40)**: end-to-end median / p90 / max | **119 s / 153 s / 225 s** |
| Out-of-corpus abstentions (9): end-to-end median | **3.8 s** |
| Query understanding | ≈ 0 s (rule path); 4–11 s when the small fallback model is used |
| Retrieval + reranking: median / p90 | 5.4 s / 11.3 s |
| Prompt size: median / max | 3,298 / 4,107 tokens |
| Answer size: median / max | 361 / 561 tokens |
| Reading the prompt (prefill): median | 55 s (≈ 64 tokens/s) |
| Writing the answer (decode): median | 59 s (≈ 6.3 tokens/s) |
| Model load (warm service) | ≤ 7.6 s; first request after a VM reboot up to ≈ 119 s unless pre-warmed |

**Thread count (measured after the baseline, same 3,850-token prompt, 2–3 runs each):** Ollama defaults to 4 threads (one per physical core). Using all 8 vCPU threads raises prompt reading from 54.9 to **68.5 tokens/s (+25 %)** and writing from 5.81 to **6.88 tokens/s (+18 %)**; 6 threads was not better than 4. Now the default (`OLLAMA_NUM_THREAD`, falls back to the CPU count). Expected effect on a typical answer (≈ 3,300 prompt + 360 answer tokens): ≈ 122 s → ≈ 100 s, with no change to the model, prompt, or evidence.

**Is this speed normal for a local LLM?** Yes, for a 7B model on CPU with this prompt size:
- *Writing* speed is set by memory bandwidth: every generated token reads all 4.25 GB of weights. At 6.9 tokens/s the VM is moving ≈ 29 GB/s, which is the practical bandwidth of 4 cores; no software setting changes that much. A GPU with ~1 TB/s bandwidth writes the same model at roughly 100 tokens/s or more.
- *Reading* the prompt is compute-bound: ≈ 55–70 tokens/s on 4 cores versus thousands of tokens/s on a GPU. RAG prompts are long (≈ 3,300 tokens of evidence and instructions), so reading alone takes ≈ 50 s.
- Smaller model on the same VM: `qwen2.5:1.5b` reads at 204 and writes at 21.6 tokens/s (≈ 3.7× faster) but its answer quality has not been evaluated here.
- So 1.5–2 minutes per evidence-grounded answer is expected for CPU-only 7B inference; sub-10-second answers require a GPU or a much smaller model.

**Why generation dominates:** each evidence passage adds ≈ 350 prompt tokens (≈ 5.5 s), and each 100 answer tokens cost ≈ 16 s. Writing is limited by memory bandwidth: every generated token reads the full 4.25 GB of quantized weights (≈ 27 GB/s at 6.3 tokens/s). The p90 slightly exceeds 150 s because of long answers (up to 561 tokens ≈ 89 s of writing).

## 4. Resources

| Resource | Usage |
|---|---|
| **vCPU** | Qwen: all 8 threads (llama.cpp, AMX; was 4 during the baseline); embeddings and cross-encoder: 4 PyTorch threads; stages run sequentially, one request at a time |
| **RAM** | Qwen 7B runner with 8 K context ≈ 5.5 GB; Qwen 1.5B (fallback, when loaded) ≈ 1.4 GB; app (MedCPT query encoder, cross-encoder, Chroma) ≈ 1.2–1.6 GB; observed system use with both models resident ≈ 9.4 GB of 16 GB |
| **Disk** | Vector DB 238 MB (passages + papers); source articles 72 MB; HF models in use 964 MB; Ollama models 5.4 GB; Python environment 5.9 GB; disk 28.7 GB, 77 % used, 6.8 GB free |
| **Per paper** | ≈ 0.53 MB (passages ≈ 0.39 MB, source XML ≈ 0.12 MB, paper record ≈ 0.02 MB) |

## 5. Capacity on this VM

| Limit | Bound | Basis |
|---|---|---|
| Disk (current free space, keep 2 GB free) | ≈ 9,000 more papers (≈ 4.8 GB); ≈ 5,200 if one full index backup is kept | 0.53 MB/paper; backup doubles the vector DB share |
| RAM | ≈ 90,000 papers (≈ 1.8 M passages) | ≈ 3.2 KB HNSW per passage resident; ≈ 6 GB free after models |
| Indexing time | ≈ 45 min per 1,000 papers (passages + paper records) | 0.126 s/passage + ≈ 0.25 s/paper |
| Query latency vs corpus | Retrieval stays seconds; generation independent of corpus size | Rerank cost depends on the fixed budget, not corpus size |
| Throughput | ≈ 25–30 answers/hour (one at a time) | ≈ 120 s per answer |

## 6. Reliability and operations
- Long-running HTTP service with model warm-up and keep-alive; health endpoint stays responsive during generation; requests serialized.
- Start-up works offline (`HF_HUB_OFFLINE=1`) and from any directory (absolute index path).
- Every request writes a JSON record, including failures; 600 s generation timeout.
- Deterministic classification and retrieval budget across process restarts.
- Pinned dependencies (`requirements.lock`); systemd unit (`deploy/pharma-rag.service`); operations guide (`docs/OPERATIONS.md`).
- 56 automated tests (`python -m unittest …`, see OPERATIONS.md).

## 7. Recommended next work (by expected effect on correct answers)
1. **Generation fidelity**: measure and reduce dropped numbers and uncited bullets (≈ 25 % of visible facts not stated); evaluate on stored outputs first.
2. **Coverage of the remaining L1 misses**: passage truncation (N1) and within-paper ranking (N4, L1-09) — only if a measured change improves held-out results without a large prompt increase.
3. **Operational**: free disk (unused 419 MB cross-encoder, old benchmark runs) before corpus growth; schedule index rebuilds with backup space.
