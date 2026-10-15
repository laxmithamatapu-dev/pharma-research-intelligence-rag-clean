# Engineering Assessment — Pharma Research Intelligence Assistant

Date: 2026-10-14. Baseline: commit `bdc559e` + staged print-only diff in `src/generation/generator.py`.
Evidence sources: source code, `data/manifests/*`, Chroma SQLite, Ollama server configuration/logs, and a **fresh controlled probe** run today (`PYTHONHASHSEED=0`, production call sequence, 3 questions, 1 run each). Historical `debug_runs/` are not used for any performance statement.
Companion docs: [PROJECT_HANDBOOK.md](PROJECT_HANDBOOK.md), [BENCHMARK_PLAN.md](BENCHMARK_PLAN.md).

---

## 1. Project purpose

| | |
|---|---|
| Business goal | Evidence-grounded answers to drug-centric research questions (mechanism, resistance, trials, safety, biomarkers, comparisons) over PMC open-access literature, fully local (no external LLM API). |
| Problem solved | Manual literature synthesis across hundreds of full-text papers; every claim in the answer is tied to a retrieved passage via `[E#]` citations enforced in code (`generator.py:330-395`). |
| End users | Not stated in code. Only interface is a single-user terminal loop (`app.py:97`); no API, UI, auth, or concurrency. **Assumption:** internal pharma/biomedical researchers; current state is a research workbench. |

---

## 2. Architecture

```
Question (stdin, app.py:97)
 → Query Understanding   QueryUnderstanding.analyze: regex patterns + weighted taxonomy → (type, intent, confidence);
                         confidence < 0.5 → Ollama qwen2.5:1.5b JSON prompt (60 s timeout)
 → Grounding             DrugRegistry alias match (8 drugs); entities kept only if present in question or registry-backed
 → Query Expansion       fixed templates per question_type × detected drug (LLM expansions discarded); ≤5 queries
 → Strategy              intent → (retrieval_k, top_k): FACT_LOOKUP 20/3 … COMPARISON 60/8
 → Retrieval             per query: MedCPT-Query embed → Chroma top retrieval_k → merge by chunk_id
 → Reranking             CrossEncoder(question, chunk) → min-max + question-type bonus ≤0.30 → dedup → ≤2/PMCID → top_k
 → Context Builder       [E#] block = 5 metadata lines + text truncated to 1,200 chars
 → Qwen Generation       one `ollama run qwen2.5:7b` subprocess; prompt = template + query JSON + context + question
 → Validation            citation normalization → rule checks → prune uncited lines → re-check → answer or ValueError
```

---

## 3. Codebase summary

| Category | Files |
|---|---|
| Entry point | `app.py` |
| Online critical path | `query_understanding/query_understanding.py`, `processing/drug_registry.py`, `retrieval/retrieval_strategy.py`, `retrieval/retriever.py`, `retrieval/reranker.py`, `embeddings/embedder.py`, `vector_store/chroma_store.py`, `generation/context_builder.py`, `generation/generator.py` |
| Offline critical path | `discovery/pmc_search.py`, `discovery/phase1_corpus.py`, `ingestion/pmc_oai.py`, `processing/pmc_parser.py`, `processing/metadata_enricher.py`, `processing/evidence_classifier.py`, `chunking/section_chunker.py`, `indexing/build_index.py` |
| Evaluation (off production path) | `evaluation/*.py` (`benchmark_framework.py` duplicates retrieval and bypasses QU/strategy) |
| Unused / dead (no importers) | `generation/prompts.py`, `generation/coverage_analyzer.py`, `generation/citation.py` (empty), `query_understanding/{entity_extractor,intent_classifier,query_expander}.py`, `ingestion/article_store.py`, `vector_store.similarity_search`, commented duplicate in `drug_registry.py:1-85`, `deletion/clear_db.py` (prints one chunk; deletes nothing) |
| Tests | `*/test_*.py` are scripts without assertions |

---

## 4. Corpus inventory (measured)

| Item | Value | Source |
|---|---|---|
| Papers discovered | 643 unique PMCIDs (80 searches, 1,600 hits) | `phase1_acquisition_report.json` |
| Papers staged | 595 XML | `data/staging/phase1/xml` |
| Papers indexed | 568 (27 produced no chunks) | `index_manifest.json`; 568 distinct `pmcid` in Chroma |
| Chunks | 11,239 | Chroma `embeddings` table |
| Chunk size | 100–400 words (mean 295); 326–7,433 chars (median 2,185) | Chroma documents |
| Chunks longer than 1,200 chars (truncated in context) | 77.9 % | Chroma documents, whitespace-collapsed |
| Embedding model | `ncbi/MedCPT-Article-Encoder` (index), `ncbi/MedCPT-Query-Encoder` (query); 768-d; mean pooling; max 512 tokens | `embedder.py`, collection dimension |
| Collection | `pharma_research`; HNSW local persisted + SQLite metadata segment; no `hnsw:space` metadata (Chroma default) | `chroma.sqlite3` `segments`, `collection_metadata` |

| Storage | Size |
|---|---|
| Corpus XML / metadata | 69 MB / 2.4 MB |
| Vector DB total (`data/chromadb`) | 224 MB (HNSW segment 36 MB incl. `data_level0.bin` 35.7 MB; remainder SQLite: documents, metadata, embeddings) |
| Separate embedding store | none (embeddings live only in Chroma) |
| Orphan empty Chroma (`data/chroma`) | 188 KB |
| HF models (MedCPT ×2 at 418 MB, CrossEncoder 128 MB) | 966 MB |
| Ollama models (`qwen2.5:7b` 4.7 GB, `qwen2.5:1.5b` 986 MB) | 5.3 GB |
| `.venv` | 5.8 GB |
| Disk | 29 GB, 71 % used |

---

## 5. Retrieval analysis

| Aspect | Behavior (code) |
|---|---|
| Queries | question + template expansions; expansions only for registry drugs and types MECHANISM/MOA, CLINICAL_TRIAL, SAFETY/ADVERSE_EVENT, BIOMARKER, RESISTANCE, DRUG_OVERVIEW (`query_understanding.py:1065-1116`) |
| Dense search | `collection.query(n_results=retrieval_k)` per query; no metadata filter; distances discarded (`retriever.py:115-120`) |
| top_k strategy | by intent only: FACT_LOOKUP 20/3; EXPLANATION, PROCEDURE, GENERAL(default) 30/5; SUMMARY 40/6; EVIDENCE 50/6; ANALYSIS, DECISION_SUPPORT 50/8; COMPARISON 60/8 (`retrieval_strategy.py:15-76`) |
| Reranking | CE `ms-marco-MiniLM-L-12-v2` on (original question, chunk); min-max normalized; + bonus ≤0.30 from cue matches; `diversity_boost` unused (`reranker.py`) |
| Article limit | ≤2 chunks per PMCID, always (`reranker.py:158,247-268`) |
| Chunk limit | `top_k` chunks; each ≤1,200 chars in context |

Fresh probe observations:
| Question | Intent → strategy | Queries | Pool | Final |
|---|---|---|---|---|
| Rebiopsy (single-paper) | FACT_LOOKUP → 20/3 | 1 | 20 | 3 |
| Resistance after first-line osimertinib (multi-paper) | FACT_LOOKUP → 20/3 | 3 | 30 | 3 |
| Abiraterone vs enzalutamide (multi-paper) | COMPARISON → 60/8 | 1 | 60 | 8 |

**Assessment: retrieval quality is not established.** No gold-labeled evaluation has been run on the current code. Code-level facts that bear on quality:
- The multi-paper resistance question is classified FACT_LOOKUP (leading "What"), so it receives 3 chunks. Its `question_type` also varies with hash seed (THERAPY / RESISTANCE / MECHANISM; handbook finding #1).
- Expansions are absent for 2 of 3 probe questions (no matching type template).
- Ranking relies entirely on the CE scoring against the original question; the dense distance is discarded.
- MedCPT is used with mean pooling and Chroma default distance; whether this matches the model's training setup is unverified.

---

## 6. Generation analysis

### 6.1 Construction (code)
- **One** LLM call per question for generation (`generator.py:449`). The QU LLM call occurs only when fast-path confidence < 0.5 (`query_understanding.py:1385`).
- Prompt = fixed instruction template + query-interpretation JSON + section template (3–6 headings by profile) + context + question (`generator.py:96-201`).
- Fixed template without context: 2,285–2,476 chars (~319 words) measured.
- Context per block ≤ ~1,333 chars (133 header + 1,200 text). Bound: top_k 3 → ~4.0 K chars, 5 → ~6.7 K, 6 → ~8.0 K, 8 → ~10.7 K. Because 78 % of chunks exceed 1,200 chars, contexts sit near the bound.
- Answer-length drivers in the prompt: required headings per profile, "Cite every factual sentence", "one claim per bullet or sentence", mandatory `## References`. "Be complete but concise" is the only length guidance. **No token limit is set.**
- Invocation: `subprocess.run(["ollama","run","qwen2.5:7b"], input=prompt)` — no streaming, no timeout, no options. Grep confirms no `num_ctx`, `num_predict`, `temperature`, `seed`, or `keep_alive` anywhere in the codebase.

### 6.2 Runtime configuration (Ollama server, observed)
| Setting | Value | Evidence |
|---|---|---|
| Ollama version | 0.40.2 | `ollama --version` |
| Model | qwen2.5:7b, 7.6 B params, Q4_K_M | `ollama show` |
| Context window | **4,096 tokens** (model supports 32,768) | server log `n_ctx = 4096`, launch args `-c 4096`, `ollama ps` |
| Threads | **4 of 8 vCPU** (`n_threads_batch = 4`) | server `system_info` |
| CPU | Xeon Platinum 8573C, 4 cores × 2 threads, AVX-512, AMX | `lscpu` |
| Kernel path | AMX model buffer 4,249 MiB; flash attention enabled; KV cache 224 MiB | server log |
| Keep-alive | model unloaded ~5 min after last use | `ollama ps` "UNTIL 4 minutes from now" |
| Prompt truncation | 0 events since 2026-10-10 (`truncated = 0` on every request) | server log |

### 6.3 Measured breakdown (fresh probe)
| Question | top_k | Prompt chars | Prompt tokens | Prefill s (tok/s) | Answer tokens | Decode s (tok/s) | Load s | Ollama total s |
|---|---|---|---|---|---|---|---|---|
| Rebiopsy | 3 | 6,187 | 1,435 | 22.9 (62.7) | 501 | 73.5 (6.81) | 5.3 (cold) | 101.7 |
| Resistance | 3 | 6,412 | 1,410 | 19.8 (63.6) | 403 | 58.5 (6.89) | 0.0 | 78.4 |
| Abi vs enza | 8 | 13,566 | 3,151 | 53.3 (56.5) | 536 | 87.7 (6.11) | 0.0 | 141.2 |

Non-LLM stages in the same runs: QU 0.002 s (fast path all 3); embedding 0.05–0.09 s; Chroma 0.04–0.16 s; rerank 1.3 / 2.0 / 4.0 s (pool 20 / 30 / 60); context 0.0001 s. Process import (model loading) 6.0 s; harness peak RSS 1.6 GB. All 3 answers passed validation without pruning.

### 6.4 Proven
1. Generation is the dominant cost: 78–141 s versus ≤ 4.1 s for all other stages combined.
2. **Decode accounts for 62–75 % of generation time.** Rate 6.1–6.9 tok/s; answers 403–536 tokens.
3. **Prefill accounts for 25–38 %.** Rate 56–64 tok/s; prompt 1.4 K tokens at top_k 3, 3.2 K at top_k 8. Prompt size is controlled by top_k, which is controlled by intent.
4. Both rates decline as context grows (prefill 63.6 → 56.5 tok/s; decode 6.9 → 6.1 tok/s).
5. Cold model load cost is ~5 s; warm ~0.
6. Prompt + answer reached 3,686 of 4,096 tokens at top_k 8 (90 % of window), with no truncation.
7. Without any output cap, latency ≈ 22–53 s prefill + answer_tokens / ~6.5 tok/s.

### 6.5 Not proven
1. Answer-length distribution across question types and repeats (n = 3 runs only).
2. What produces observations above ~150 s on this code (candidates: longer answers, cold load, QU fallback swapping models, concurrent CPU load) — none reproduced today.
3. Whether a different thread count changes decode/prefill rates.
4. Whether decode is memory-bandwidth-bound or compute-bound on this VM.
5. Behavior when prompt + answer would exceed 4,096 tokens (top_k 8 with longer answers).
6. Whether `ollama run` CLI differs in latency from the HTTP API.
7. Effect of the QU 1.5b fallback on 7b residency (both fit in RAM; eviction behavior not observed).
8. Validation/pruning time (not timed separately; regex over ~2.5 K chars).

---

## 7. Performance bottleneck hypotheses (ranked)

| Rank | Cause | Facts | Assumptions / unproven |
|---|---|---|---|
| 1 | Answer size × Qwen decode | 403–536 tokens at 6.1–6.9 tok/s = 59–88 s, 62–75 % of generation; no output cap in code | Distribution across question types |
| 2 | Prompt size (prefill) | 1.4–3.2 K tokens at 56–64 tok/s = 20–53 s; scales with top_k (intent-driven) | — |
| 3 | CPU limitations | 4 cores / 8 threads; 4 inference threads; AVX-512 + AMX active | Bandwidth vs compute bound; thread-count sensitivity |
| 4 | Ollama configuration | ctx 4,096 default; no num_predict; 5-min keep-alive; cold load 5.3 s | Context-limit behavior at long answers |
| 5 | Query understanding | 0.002 s on fast path; LLM fallback is a second model call | Fallback latency and model-swap cost on current code (not measured today) |
| 6 | Reranking | 1.3–4.0 s, linear in pool size (20 → 60 candidates) | — |
| 7 | Retrieval (embed + Chroma) | 0.08–0.25 s | — |
| 8 | Context building | 0.0001 s | — |

---

## 8. Current state

**Strengths**
- Fully local stack; deterministic grounding of entities and expansions against a registry.
- Hard citation enforcement with normalization, pruning, and explicit failure.
- Bounded prompt size (1,200-char truncation, fixed top_k), measured within the 4 K context.
- Resumable, checkpointed, logged index build with manifests; per-run JSON artifacts.
- Retrieval stack is fast (≤ 4 s) relative to generation.

**Weaknesses**
- Intent drives top_k from surface phrasing; multi-paper questions starting with "What" get 3 chunks.
- Question-type tie-breaking is hash-seed dependent.
- No generation length control, timeout, or streaming; user waits blind for 80–140 s.
- Validator can reject whole answers on substring matches ("unlikely" ⊃ "likely") and deletes "Not established" lines.
- Abstracts and short sections are not indexed.

**Risks**
- Single-user blocking loop; one CPU-bound LLM call at a time.
- Startup contacts the Hugging Face Hub (unauthenticated-request warning at load) — network dependency at boot.
- Chroma path relative to CWD; wrong CWD silently opens an empty store.
- Unpinned dependencies on a 5.8 GB venv; disk at 71 %.
- Prompt + answer at 90 % of context window for top_k 8.

**Technical debt**
- ~1/3 of `src/` unused; duplicated retrieval loop in evaluation; tests without assertions; import-time model loading (Article encoder loaded but unused online); heavy debug `print` in hot paths; dual import styles (`processing.` vs `src.processing.`).

**Scalability risks**
- Latency grows with context (prefill rate and decode rate both fall as tokens rise).
- Corpus growth affects only retrieval (sub-second today); generation cost is independent of corpus size.
- Registry has 8 drugs; grounding and expansions do not apply to other drugs.
- Concurrency would serialize on one Ollama slot (`-np 1`).

---

## 9. Investigation plan (no optimizations)

### Benchmarks to run next
1. **Baseline suite** in [BENCHMARK_PLAN.md](BENCHMARK_PLAN.md) (L1 × 14, L2 × 8, 3 repeats) — establishes the quality and latency baseline.
2. **Generation latency decomposition matrix** (Ollama only, fixed prompts captured from the suite): top_k ∈ {3,5,8} × 3 repeats → prefill tokens/s, decode tokens/s, answer tokens per profile. Isolates prompt-size vs answer-size effects.
3. **CPU characterization (measurement only)**: same fixed prompt at Ollama thread counts {2,4,6,8} via request options, plus decode rate vs context length — determines bandwidth/compute limits. Results inform, not change, configuration.
4. **QU fallback cost**: questions known to fall back (e.g. "What is nivolumab?") → 1.5b latency and whether 7b is evicted (load duration on the next generation).
5. **Context-limit probe**: top_k 8 prompt with forced long answer → observe Ollama behavior at 4,096 tokens.
6. **Cold vs warm**: first question after >5 min idle vs immediate repeat.

### Metrics to collect
Per request: prompt tokens, answer tokens, prefill duration and rate, decode duration and rate, load duration, time to first token, total wall; stage timings (QU path + time, embed, Chroma, rerank, context, validation); pool size, top_k, intent, question_type, seed; validation outcome and pruned-line count; harness and Ollama RSS; host load average.

### Missing telemetry
| Gap | Evidence |
|---|---|
| Ollama token counts and per-phase durations are not captured | `generator.py:449` uses `ollama run` without `--verbose`; only character/word counts printed |
| No time-to-first-token (no streaming) | `capture_output=True` |
| Retrieval sub-stage timings (embed / Chroma / rerank) not separated | `app.py:175-181` times retrieval as one block |
| QU path (fast vs LLM) and confidence not stored in artifacts | `save_debug_run` stores `query_info` only (`app.py:52-66`) |
| Failed runs leave no artifact | `save_debug_run` is called after successful generation (`app.py:282-298`); `ValueError` path prints only |
| Raw LLM output before normalization/pruning not stored | `generator.py:472-487` |
| No environment fingerprint (git SHA, model digest, index hash) | absent in artifacts |
| No memory telemetry | absent |
| Validation time not measured | absent |
