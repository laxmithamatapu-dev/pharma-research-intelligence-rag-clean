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
