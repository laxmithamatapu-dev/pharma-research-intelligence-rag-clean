# Paper-First Retrieval — Implementation Blueprint and Resource Report

Date: 2026-10-15 · Baseline: branch `fix/correctness-2day` (F1–F5 approved)
Deployment: Azure VM, 8 vCPU (4 cores × 2 threads), 16 GB RAM, CPU-only, local Ollama (`qwen2.5:7b` Q4_K_M), ChromaDB, MedCPT, cross-encoder.
Priority: answer quality and evidence grounding over latency.
Evidence base: [PASSAGE_SELECTION_STUDY.md](PASSAGE_SELECTION_STUDY.md), [RETRIEVAL_DESIGN_PAPER_BUDGET.md](RETRIEVAL_DESIGN_PAPER_BUDGET.md), [TWO_DAY_RESULTS.md](TWO_DAY_RESULTS.md), [RETRIEVAL_RCA.md](RETRIEVAL_RCA.md). Measured values are marked **(m)**; projections are marked **(p)** and state their basis.

---

## 0. Summary

| | Current | Paper-first target |
|---|---|---|
| Retrieval unit | flat list of passages | **papers first**, then passages inside selected papers |
| Evidence budget | top_k 3–8 from intent; ≤ 2 passages per paper | **scope-based**: single-study 2 papers × 4 passages; synthesis 6–8 papers × 1 passage; token budget |
| L1 fact visibility (52 facts) | 26 (50 %) **(m)** | 31–36 (60–69 %) **(p, offline-measured on stored pools)** |
| L2 aspect coverage | 0.41 **(m)** | 0.56–0.61 **(p, offline-measured)** |
| Warm end-to-end latency | 40–145 s **(m)** | 90–165 s **(p)** |
| Vector DB | 224 MB **(m)** | ≈ 240–250 MB **(p)** |
| Peak RAM (all processes) | ≈ 8.2 GB **(m)** | ≈ 8.0–8.5 GB **(p)** |

---

## 1. Current architecture (as implemented, after F1–F5)

```
question
 → QueryUnderstanding (rules; qwen2.5:1.5b fallback via API, temp 0)      intent, question_type, drugs
 → StrategyManager: intent → (retrieval_k 20–60, top_k 3–8)
 → retriever: MedCPT-Query embed (question + ≤4 template rewrites)
             → Chroma passage collection (11,239 passages, mean-pooled, no title) top retrieval_k each
             → merged pool (20–105 passages)
 → reranker: MiniLM cross-encoder (question, passage) → min-max + type bonus → dedup → ≤2 per paper → top_k
 → context_builder: [E#] blocks, 5 metadata lines, text ≤1,200 chars
 → QwenGenerator: `ollama run --nowordwrap qwen2.5:7b` (n_ctx 4,096; no seed), 600 s timeout
 → validation (word-boundary rules) → prune → answer
```

**Proven limits of this design**
- Passage-level pools contain only 33 of 52 expected L1 facts, although all 52 are visible in the gold papers.
- Selection inside the pool loses 7 more facts, mainly through the ≤2-per-paper limit.
- One fixed budget shape cannot serve single-study questions (which need depth) and synthesis questions (which need breadth).

---

## 2. Proposed architecture

```
                              ┌────────────────────── OFFLINE INDEX ──────────────────────┐
 PMC XML → parse → enrich ──► │ papers collection  (1 record / paper)                     │
                              │   doc = "title. abstract", MedCPT article encoder           │
                              │   metadata: title, year, journal, design, drugs, n_chunks  │
                              │ passages collection (existing, unchanged vectors)          │
                              │   + abstract passages, merged short sections, no boilerplate│ (session 4)
                              └────────────────────────────────────────────────────────────┘
ONLINE
question
 → 1. Query analysis      intent/type (unchanged) + SCOPE ∈ {single_study, comparison, synthesis}
 → 2. Retrieval plan      scope → papers P, passages per paper q, candidate depth, evidence-token budget
 → 3. Paper candidates    papers collection top 30 (dense)  ∪  papers of passage-dense top 60
 → 4. Paper ranking       cross-encoder(question, "title. abstract") → top P papers  (+ relevance floor)
 → 5. Passage selection   for each selected paper: all its passages → dense pre-rank (top 20)
                          → cross-encoder(question, passage) → top q  (no global per-paper cap)
 → 6. Context             grouped by paper: paper header (title, year, design) + [E#] passages; token budget
 → 7. Generation          Ollama HTTP API: num_ctx 8192, temperature 0, seed 0, timeout
 → 8. Validation          unchanged rules; telemetry for every stage
```

**Scope budgets (from offline measurements)**
| Scope | Papers (P) | Passages per paper (q) | Max passages | Measured basis |
|---|---|---|---|---|
| single_study | 2 | 4 | 8 | 2 × 4 → 36/52 facts; 1 × 4 → 31 |
| comparison | 2 per compared entity, max 6 | 1–2 | 8 | breadth result (6 × 1 → 0.56 coverage) |
| synthesis | 8 | 1 | 8 | 8 × 1 → 0.61 coverage |

Total evidence is capped by a token budget (≈ 3,000 evidence tokens), so the prompt fits `num_ctx 8192` with room for an answer of up to ~1,000 tokens.

---

## 3. Components to modify

| Module | What changes | Why | Expected impact | Complexity |
|---|---|---|---|---|
| `src/processing/pmc_parser.py` | None (already extracts title, abstract, year, article type) | — | — | — |
| **`src/indexing/build_paper_index.py`** (new) | Build one record per paper (title + abstract + metadata) and embed into a `papers` collection; incremental per paper; manifest | Papers are found far more reliably than passages (94 % vs 35 % in top-20); abstracts are not indexed today | Enables stage 3–4; ≈ 5 min to build for 568 papers | **Medium** |
| `src/embeddings/embedder.py` | Add `embed_paper(title, abstract, pooling)` using MedCPT's documented `[title, abstract]` input; lazy-load the article encoder (not needed at query time) | Documented model usage; E2a showed title context helps paper identity | −≈ 0.4 GB app RAM, faster start; paper vectors | **Low** |
| `src/vector_store/chroma_store.py` | Second collection `pharma_papers`; helper `passages_for_paper(pmcid)`; keep absolute paths | New retrieval unit; whole-paper passage access | +≈ 5–10 MB disk | **Low** |
| `src/query_understanding/query_understanding.py` | Add deterministic `scope` field (comparison cues → comparison; study-specific cues such as "in the … cohort/trial/case", trial acronyms → single_study; otherwise synthesis) | Optimal budget shape is opposite for single vs multi-paper; pool signals overlap too much to infer scope | Correct budget per question | **Medium** (rules + tests on 27 + new questions) |
| `src/retrieval/retrieval_strategy.py` | Replace intent → (retrieval_k, top_k) with scope → `RetrievalPlan` | Fixed per-paper limit is conceptually wrong; budgets differ by scope | Removes the phrasing-driven budget mismatch | **Low** |
| **`src/retrieval/paper_retriever.py`** (new) | Stage 3–4: candidate papers (paper dense ∪ passage-dense hits), cross-encoder on title + abstract, relevance floor | Paper ranking is the new first gate; top pool paper is wrong for 4/16 L1 questions today | Paper recall gate; abstention signal | **Medium** |
| `src/retrieval/retriever.py` | New `retrieve_evidence(question, query_info, plan)` returning `EvidenceSet`; keep `retrieve_chunks` behind a flag for comparison | Two-stage flow; side-by-side benchmarking | Fact visibility 50 % → 60–69 % (p) | **Medium** |
| `src/retrieval/reranker.py` | Split into `score_papers` and `select_passages(paper, q)`; no global per-paper cap; keep dedup and the type bonus for passages only | Quota study: cap was the dominant in-pool loss; bonus helped L1 passages | +5 facts within pools; enables depth per paper | **Low–Medium** |
| `src/generation/context_builder.py` | Paper-grouped blocks: paper header from the paper record (title, year, design), then `[E#]` passages; evidence-token budget instead of chunk count; keep 1,200-char cut initially | Accurate study identity in the prompt; replaces noisy keyword "Evidence Type" | Better attribution; prompt +5–10 % (headers) | **Low** |
| `src/generation/generator.py` | Call Ollama HTTP API with `num_ctx 8192`, `temperature 0`, `seed 0`, timeout; small prompt note on grouped evidence | 8 passages need > 4,096 tokens; identical prompts must give identical answers to measure quality | Repeatable quality runs; +≈ 0.2 GB KV memory | **Low–Medium** |
| `src/chunking/section_chunker.py` (session 4) | Merge short sections into neighbours instead of dropping; add abstract as a passage; exclude boilerplate sections | Lost content (sections < 100 words; abstracts) and noise (contributions, disclosures) | More facts reachable; ≈ +5 % passages | **Medium** (requires re-index) |
| `app.py` | Wire `retrieve_evidence`; print paper-grouped references; feature flag `RETRIEVAL_MODE=paper_first|legacy` | Safe cut-over and rollback | — | **Low** |
| `src/evaluation/*` | Harness wrappers for paper and passage stages; scoring adds paper recall@P, passages per paper, abstention | Keep the production-path benchmark valid | Gates for each session | **Medium** |

---

## 4. New data structures

```python
@dataclass(frozen=True)
class RetrievalPlan:
    scope: str                    # "single_study" | "comparison" | "synthesis"
    paper_candidates: int         # dense papers considered (e.g. 30)
    passage_candidates: int       # passage-dense hits used to nominate papers (e.g. 60)
    papers: int                   # P
    passages_per_paper: int       # q
    evidence_token_budget: int    # e.g. 3000
    paper_floor: float | None     # cross-encoder relevance floor (calibrated in session 5)

@dataclass
class Passage:
    chunk_id: str; pmcid: str; section_path: str; text: str
    dense_rank: int | None; ce_score: float; rank_in_paper: int

@dataclass
class EvidencePaper:
    pmcid: str; title: str; year: int | None; study_design: str | None
    paper_score: float; source: str           # "paper_index" | "passage_hits" | "both"
    passages: list[Passage]

@dataclass
class EvidenceSet:
    plan: RetrievalPlan
    papers: list[EvidencePaper]
    abstained: bool
    telemetry: dict                            # stage timings, candidate counts, scores
```

**Chroma `pharma_papers` record**
| Field | Content |
|---|---|
| id | PMCID |
| document | `"{title}. {abstract}"` |
| embedding | MedCPT article encoder, `[title, abstract]` pair (pooling chosen in session 1) |
| metadata | `title`, `publication_year`, `journal`, `article_type`, `study_design`, `drugs` (pipe-joined), `n_passages`, `has_abstract`, `metadata_version` |

The passage collection is unchanged in sessions 1–3. In session 4 it gains `section_bucket` and `is_abstract` metadata.

---

## 5. Impact

| Dimension | Expected change | Basis |
|---|---|---|
| **Fact visibility (L1)** | 26 → 31–36 of 52 (50 % → 60–69 %) | Offline replay on stored pools (paper budget study); paper ranking here used best-pool-chunk ranking, so a paper index is a further, unmeasured upside |
| **Aspect coverage (L2)** | 0.41 → 0.56–0.61 | Same study (6–8 papers × 1 passage) |
| **Answer quality** | Bounded by visibility; expected higher fact recall. Unchanged risks: numeric omission and fabricated attribution (generation-side) | Generation runs show these failures independent of retrieval |
| **Latency (warm)** | 40–145 s → 90–165 s | Below |
| **Storage** | +5–10 MB papers collection; +≈ 11 MB abstract passages (session 4) | 0.39 MB per paper today |
| **Memory** | app −≈ 0.4 GB (lazy article encoder); KV +≈ 0.2 GB (num_ctx 8192); papers HNSW +≈ 2 MB | 224 MiB KV per 4 K context **(m)** |

**Latency budget per request (warm)**
| Stage | Current **(m)** | Paper-first **(p)** | Basis |
|---|---|---|---|
| Query analysis | 0.002 s (fast path); 4–11 s (fallback, 6/27 questions) | same | — |
| Dense search | 0.08–0.35 s | 0.15–0.5 s (two collections) | measured per query |
| Paper cross-encoder | — | 1–2 s (≈ 30 pairs, longer text) | 0.064 s/pair (m) |
| Passage cross-encoder | 1.3–6.2 s (20–105 pairs) | 2.6 s single-study (40 pairs); ≈ 5 s synthesis (80 pairs after pre-rank) | 0.064 s/pair (m) |
| Prompt prefill | 20–55 s (1.4–3.3 K tokens) | 50–70 s (3.5–4.2 K tokens) | 56–76 tok/s (m) |
| Answer decode | 15–90 s (100–540 tokens) | same | 6.1–7.3 tok/s (m) |
| **Total** | **≈ 40–145 s** | **≈ 90–165 s** | — |
| Cold start after reboot | +119 s model load, +83 s import | same unless models are pre-warmed at boot | (m) |

---

## 6. Execution plan (development sessions)

Each session ends with a measurable gate on the existing harness. Legacy retrieval stays available behind the flag until session 5.

| Session | Work | Gate (must pass) |
|---|---|---|
| **S1 · Paper index** | `build_paper_index.py`; `embed_paper`; `pharma_papers` collection; lazy article encoder. Evaluate paper recall for L1/L2 gold papers: dense only vs dense ∪ passage-hits, mean vs CLS pooling | L1 gold paper in top 2 papers ≥ 15/16; L2 gold paper recall in top 8 ≥ current pool (35–38/52 pooled) |
| **S2 · Two-stage retrieval** | `scope` in QU (+ tests); `RetrievalPlan`; `paper_retriever.py`; `retrieve_evidence`; reranker split; harness wrappers | Retrieval-only: L1 facts ≥ 31/52; L2 aspect coverage ≥ 0.56; scope classification correct on all 27 benchmark questions; deterministic across seeds |
| **S3 · Context + generation** | Paper-grouped context; token budget; generation via API (`num_ctx 8192`, seed, temperature 0) | Targeted generation (L1 + L2 subset + controls, 3 repeats): identical outputs across repeats; fact recall ≥ legacy; validation failures not higher; controls abstain; p90 latency ≤ 180 s |
| **S4 · Index content** | Abstract passages; merge short sections; exclude boilerplate; re-index (≈ 25–40 min, with backup) | L0 retrieval-only: facts reachable ≥ previous; no L1/L2 regression |
| **S5 · Abstention + cut-over** | Calibrate paper relevance floor on controls (extend to ≥ 10 controls); telemetry in app artifacts; flag default `paper_first`; docs | Controls: 0 cited claims about absent topics; full L1/L2 run (3 repeats) recorded as the new baseline |

**Rollback:** `RETRIEVAL_MODE=legacy` restores the current path. The papers collection is additive. Session 4's re-index keeps a backup of the previous index.

---

## 7. Resource and capacity report

### 7.1 Current pipeline footprint (measured 2026-10-15)

**Disk**
| Component | Size |
|---|---|
| Ollama models (`qwen2.5:7b` 4.7 GB + `qwen2.5:1.5b` 1.0 GB) | 5,407 MB |
| Python environment (`.venv`) | 5,888 MB |
| Hugging Face models in use (MedCPT query 418 MB, MedCPT article 418 MB, MiniLM cross-encoder 128 MB) | 964 MB |
| MedCPT cross-encoder (downloaded for the study; **unused, removable**) | 419 MB |
| Vector DB `data/chromadb` (11,239 passages; SQLite ≈ 188 MB + HNSW ≈ 36 MB) | 224 MB |
| Article XML (595 papers) + metadata | 72 MB |
| **Corpus-dependent data per paper** | **≈ 0.51 MB** (0.39 MB vector DB + 0.12 MB source) |
| Disk total / used / free | 28.7 GB / 21.4 GB / **7.2 GB** |

**Memory (RSS)**
| Process | RAM |
|---|---|
| Ollama runner, `qwen2.5:7b`, n_ctx 4,096 (weights 4.25 GB + KV 224 MB + compute) | ≈ 5.1 GB |
| Ollama runner, `qwen2.5:1.5b` (only when the fallback classifier is used) | ≈ 1.4 GB |
| App process (MedCPT ×2, cross-encoder, Chroma client, HNSW) | ≈ 1.6 GB |
| Ollama server | 37 MB |
| **Peak, all co-resident** | **≈ 8.2 GB of 16 GB** |

**CPU (8 vCPU = 4 physical cores × 2 threads)**
| Workload | Threads | Notes |
|---|---|---|
| LLM generation (llama.cpp, AMX/AVX-512) | 4 | Prefill 56–76 tok/s, decode 6.1–7.3 tok/s |
| Embedding and cross-encoder (PyTorch) | 4 | `torch.get_num_threads() = 4` |
| Stages run sequentially, so at most 4 cores are busy per request; one request at a time (single Ollama slot) | | |

**Retrieval quality (current, benchmark of 27 questions)**
| Metric | Value |
|---|---|
| Correct paper reaches the LLM (single-paper questions) | 15/16 (94 %) |
| Expected facts visible to the LLM (single-paper) | 26/52 (50 %) |
| Sub-topic coverage (multi-paper) | 0.41 |
| Out-of-corpus controls answered with abstention | 4/4 runs |

**Latency per request (warm, measured)**
| Stage | Time |
|---|---|
| Query understanding | 0.002 s (fast path) · 4–11 s (fallback) |
| Query embedding + vector search | 0.08–0.35 s |
| Cross-encoder reranking | 1.3–6.2 s |
| Context building | < 0.01 s |
| LLM generation | 36–141 s (prompt 1.4–3.3 K tokens; answer 100–540 tokens) |
| **End to end** | **≈ 40–145 s** (≈ 25–40 answers per hour, sequential) |
| First request after VM reboot | + 119 s model load + 83 s app start (cold disk) |

### 7.2 Capacity limits on this VM

| Limit | Bound | Calculation (assumptions explicit) |
|---|---|---|
| **Disk (current free space)** | **≈ 9,800 more papers (≈ 5 GB of documents and index)** without keeping index backups; **≈ 5,700** if a full index backup is kept during re-index | Reserve 2 GB free; 5.2 GB ÷ 0.53 MB per paper (incl. paper index) ≈ 9,800; with a backup copy of the vector DB: 5.2 GB ÷ (0.53 + 0.39) MB ≈ 5,700. Removing the unused 419 MB model adds ≈ 800 papers. Attaching a data disk removes this limit. |
| **RAM** | ≈ 90,000 papers (≈ 1.8 M passages) | Available ≈ 16 − 5.3 (7B + 8 K KV) − 1.4 (1.5B) − 1.2 (app) − 2 (OS) ≈ 6 GB; HNSW ≈ 3.2 KB per passage resident (m: 36 MB / 11,239). SQLite stays on disk. |
| **Indexing time** | ≈ 45 min per 1,000 papers | 0.126 s per passage (m) × 20 passages per paper + ≈ 0.2 s paper record (p). 10,000 papers ≈ 7.5 h of full CPU (serving degraded meanwhile) |
| **Query latency vs corpus size** | Dense search sub-second up to ≥ 100 K passages **(p)**; reranking and generation independent of corpus size | HNSW search grows sub-linearly (assumption; re-measure at 50 K passages). Rerank cost depends on candidates (fixed by the plan), not on corpus size. |
| **Throughput** | ≈ 25–40 answers per hour | One generation at a time; 90–165 s per answer after paper-first (p) |

**Binding constraint:** for the next order of magnitude (5–10 K papers) the limit is **disk space and indexing time**, not RAM or query latency. Generation time per answer is independent of corpus size; the LLM, not retrieval, dominates per-request latency at every corpus size considered.

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| Wrong paper ranked first (4/16 today) | P = 2 for single-study questions; union of paper-dense and passage-hit candidates; gate in S1 |
| Scope misclassified | Deterministic rules with tests; mis-scoped single-study questions still receive 2 papers × 4 passages |
| Longer prompts slow generation | Token budget; paper headers short; quality prioritized per product stance |
| Within-paper ranking still loose (answer passage at rank 1–11) | Depth q = 4; dense pre-rank + cross-encoder; revisit window scoring within a paper (safe there) |
| Generation failures independent of retrieval (numeric omission, fabricated attribution) | Measured in S3; addressed after retrieval cut-over |
