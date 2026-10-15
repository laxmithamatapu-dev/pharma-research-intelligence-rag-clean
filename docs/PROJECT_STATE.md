# PROJECT STATE — Source of Truth

Checkpoint: **2026-10-15** · Branch `fix/correctness-2day` (not merged; head at checkpoint `20b1e6b`) · Owner role: technical owner.
Companion documents: [LLM_EVALUATION.md](LLM_EVALUATION.md) (next phase), [NEXT_STEPS.md](NEXT_STEPS.md) (ranked work and plan), [PIPELINE_REPORT.md](PIPELINE_REPORT.md) (final measurements), [OPERATIONS.md](OPERATIONS.md) (run/deploy), [IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md) (session-by-session record), [PROJECT_HANDBOOK.md](PROJECT_HANDBOOK.md) (discovery log).
Status of workstreams: **Retrieval & architecture — complete** (reopen only on new evidence). **Generation fidelity & model evaluation — next.**

---

## 1. Goal

A local, CPU-only pharmaceutical research assistant that answers questions from a fixed corpus of PubMed Central papers with **correct, evidence-grounded answers**: every claim tied to a cited passage, honest abstention when the corpus cannot answer, acceptable latency (≈ 90–150 s), no external services.

Priority order (owner-defined): 1) correct answers, 2) correct evidence grounding, 3) reliable retrieval, 4) acceptable latency.

## 2. Corpus

| Item | Value |
|---|---|
| Source | PubMed Central open-access full text (JATS XML), discovered per drug × evidence profile |
| Drugs (registry) | osimertinib, pembrolizumab, trastuzumab, imatinib, adalimumab, semaglutide, nivolumab, enzalutamide |
| Papers discovered / staged / indexed | 643 / 595 / **568** (27 produced no chunks) |
| Passages | **11,239** (≈ 400 words, 100-word overlap, body sections ≥ 100 words) |
| Paper records | 568 (title + abstract; 3 without abstract) |

## 3. Current architecture

```
Offline   PMC XML → parse → enrich (drugs, design, year) ─┬─► passage index  "pharma_research" (MedCPT article encoder, mean pooling)
                                                           └─► paper index    "pharma_papers"   (title + abstract, MedCPT CLS pooling, inner product)
Online    question
            1. rule-based analysis: intent, type, drugs (registry), scope (single_study | comparison | unspecified)
            2. candidate papers: paper index top 30 ∪ papers of passage top 60
            3. cross-encoder (MiniLM) ranks papers on title + abstract
                 └ best score < 3.5 → abstain ("Not established…"), no LLM call
            4. budget: single study or margin ≥ 2.0 → 6 + 2 passages (depth); else 8 papers × 1 (breadth)
            5. cross-encoder selects passages inside the chosen papers (dense pre-rank ≤ 20 per paper)
            6. evidence blocks: [E#] paper title, design, year, section, text ≤ 1,200 chars
            7. Qwen 2.5 7B Q4_K_M via Ollama chat API: num_ctx 8192, temperature 0, seed 0, 8 threads
            8. citation normalization → invented-author removal → sentence-level repair → answer
Serving   serve.py (HTTP /health, /ask; warm model; serialized), app.py CLI, systemd unit; RETRIEVAL_MODE=legacy rollback
Records   JSON per request (including failures) with timings, paper scores, token counts, evidence
```

### Paper-first retrieval design (why)
- Papers are found far more reliably than passages: gold paper in the dense top-20 for 94 % of single-paper questions vs 35 % for the answer passage.
- Passage-level pools contained only 63 % of expected facts although all were present in the gold papers.
- Single-paper questions need **depth** (answer passage ranks 1–11 inside its paper); multi-paper questions need **breadth** (one passage from many papers). One fixed shape cannot serve both; the cross-encoder margin between the top two papers separates them (single-paper 0.8–7.2; multi-paper < 1.3).

## 4. Benchmark history

| Phase | Data | Key result |
|---|---|---|
| Discovery | code + manifests | Architecture, defects, missing telemetry catalogued |
| Engineering assessment | 3-question probe | Generation ≈ 95 % of latency; decode 62–75 % of it |
| Retrieval-only, 5 seeds | 27 questions × 5 | Paper reaches LLM 94 %; facts visible 48–50 %; 11/27 questions classification-unstable |
| Retrieval RCA (E1–E6) | read-only experiments | Context/register mismatch at dense retrieval; reranker prefers Discussion; quota proximate cause |
| E2a title-context embeddings | full re-embed (side file) | Pool recall up, delivery flat → reranker/selection bottleneck; titles identify papers, not passages |
| Passage-selection study | 32 configurations | Per-paper quota is the in-pool lever; MedCPT cross-encoder worse for L1 and 3× slower |
| Paper/passage budget study | full-paper access | Opposite optimal shapes for L1 (depth) and L2 (breadth) |
| Session 1–2 (paper-first) | 27 questions | L1 facts visible 26 → 44 / 52; L2 coverage 0.41 → 0.66 |
| Session 3 (generation via API) | 10 questions × 2 modes | Facts stated 6 → 13 / 24; latency median 69 → 116 s |
| Session 3b (correctness) | 62 replayed answers | Failures 5 → 0; facts kept 72 → 90 |
| Held-out validation | 22 new questions | Paper-first beats legacy; 6 + 2 depth split adopted (87 % vs 81 % facts visible, same cost) |
| **Final baseline** | **49 questions** | See §8 |
| Post-baseline | thread A/B; prompt A/B | 8 threads −18 to −25 % time; exact-numbers rule not adopted |

## 5. What was investigated, proven, disproven

**Proven (measured, reproducible)**
1. Generation dominates latency; writing is memory-bandwidth-bound (≈ 29 GB/s ≈ 6.9 tokens/s for 4.25 GB of weights).
2. Dense passage retrieval misses findings-bearing (Results) passages because questions and Results text differ in register; paper-level retrieval does not suffer the same way.
3. Title context helps identify papers but halves within-paper discrimination (0.93 → 0.50).
4. The ≤ 2-per-paper cap was the dominant in-pool loss; within-paper ordering is the remaining limit.
5. Classification instability had two sources (hash-seed ties; LLM fallback sampling); both fixed (deterministic).
6. `ollama run` word-wraps output; line-based pruning destroyed cited claims (fixed via API).
7. Study-design labels were wrong for every randomized paper (OR-matched substring cues; 92 papers labeled phase I); fixed.
8. Validation discarded correct answers (invented author attributions, forbidden-word substrings, bracketed statistics); fixed by targeted repair (0 failures over 103 replayed answers).
9. Ollama default 4 threads under-uses the VM; 8 threads is 18–25 % faster.
10. Out-of-corpus questions: retrieval score floor (3.5) separates 12/12 controls from 39/39 answerable questions measured.

**Disproven / rejected**
- Index construction defects (rebuild reproduces vectors exactly).
- Embedding truncation, distance metric, and caption noise as causes of retrieval misses.
- Query-term rewriting / template expansions as a lever (entity-only queries barely help; expansions add 0 L1 gold chunks).
- MedCPT cross-encoder as a reranker upgrade (worse L1, 3× slower).
- Title-context passage embeddings as a passage-index replacement.
- Longer passage cut (2,000 chars): +1 fact for ≈ +23 s.
- "Report numbers exactly" prompt rule: +1/42 facts (noise); removed correct arithmetic.

**Implemented** (all on branch `fix/correctness-2day`)
Benchmark harness on the production path (L0/L1/L2, seeds, replay, scoring, labeling tools); deterministic classification; paper index; paper-first two-stage retrieval with scope + adaptive budget and abstention floor; Ollama API generation (8 K context, temperature 0, seed, 8 threads, keep-alive, warm-up); paper-identity evidence headers; answer repair; failure records and telemetry; HTTP service and systemd unit; pinned dependencies; 56 automated tests; operations guide.

**Open**
- Generation fidelity: ≈ 15–20 % of visible facts not stated; claim-level citations weak (§8).
- Two held-out L1 misses (truncation N1; within-paper rank N4) — accepted, reopen only with new evidence.
- Abstention floor calibrated on 12 controls only.
- Single-labeler draft gold; 49 questions.
- Service not yet installed as a system unit; disk 78 % used.

## 6. Infrastructure

| Item | Value |
|---|---|
| VM | Azure, 8 vCPU (Xeon Platinum 8573C, 4 cores × 2 threads, AVX-512, AMX), 16 GB RAM, no GPU |
| Disk | 29 GB, 78 % used, **6.4 GB free** |
| LLM runtime | Ollama 0.40.2 (llama.cpp); models `qwen2.5:7b` (4.7 GB), `qwen2.5:1.5b` (1.0 GB) |
| Python | 3.x venv 5.9 GB; torch 2.14.1+cpu; chromadb 1.5.9; transformers 5.19.0; sentence-transformers 6.1.0 |

## 7. Storage and capacity

| Component | Size |
|---|---|
| Vector DB (passages + papers) | 238 MB |
| Source XML + metadata | 72 MB |
| Embedding / reranker models in use | 964 MB |
| Unused MedCPT cross-encoder (removable) | 419 MB |
| Ollama models | 5.4 GB |
| Python environment | 5.9 GB |
| **Per paper** | **≈ 0.53 MB** |

| Limit | Bound |
|---|---|
| Disk (keep 2 GB free) | ≈ 8,000 more papers; ≈ 4,800 if an index backup is kept |
| RAM | ≈ 90,000 papers (≈ 1.8 M passages) |
| Indexing time | ≈ 45 min per 1,000 papers |
| Throughput | ≈ 30–40 answers/hour, one at a time |

## 8. Current answer quality and latency

| Metric | Value |
|---|---|
| L1 facts visible to the LLM (dev 16 / held-out 8) | **88 % / 81 %** (was 50 % / 50 %) |
| L1 facts stated in answers (dev / held-out) | **71 % / 81 %** |
| Generation fidelity (stated ÷ visible, dev / held-out) | **80 % / 85 %** (held-out 100 % after the bracket fix) |
| Stated facts cited on the same line to the gold paper (dev / held-out) | 65 % / 27 % |
| L2 aspect coverage (dev / held-out, lower bound) | 0.66 / 0.53 (was 0.41 / 0.30) |
| Out-of-corpus controls with claims about the absent topic | **0 / 12** (9 abstained at retrieval in ≈ 3.8 s) |
| Validation failures (103 replayed answers) | **0** |
| Latency, 4 threads (final baseline, 40 answers) | median 119 s, p90 153 s |
| Latency, 8 threads (13 answers, generation only) | median 87 s, p90 111 s |
| Peak RAM (both Qwen models resident) | ≈ 9.4 GB of 16 GB |
