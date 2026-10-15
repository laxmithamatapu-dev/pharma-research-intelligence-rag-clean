# Pharma Research Intelligence RAG — Technical Handbook

Status: Discovery pass 1 (2026-10-14). Covers Sections 1–4 of the onboarding brief.
Sections 5–15 are seeded under "Discovery Log" and will be expanded in later passes.
Commit baseline: `bdc559e` + staged diff in `src/generation/generator.py` (adds prompt/answer word-count prints only).

Evidence convention: every claim cites `file:line` or an artifact. Items marked **ASSUMPTION** are not proven by code.

---

## 1. System Overview

### What it is
A single-user, local, command-line question-answering assistant over open-access biomedical literature (PubMed Central full text). A user types a pharmaceutical research question; the system retrieves passages from an indexed PMC corpus, has a local LLM write a structured answer, and enforces that every claim carries an `[E#]` citation pointing to a retrieved passage.

### Why it exists
To answer drug-centric research questions (mechanism, resistance, trials, safety, biomarkers, comparisons) with traceable evidence, without sending data to an external LLM API. Evidence: all LLM calls are `subprocess.run(["ollama","run",...])` (`src/generation/generator.py:449`, `src/query_understanding/query_understanding.py:1408`); the prompt forbids non-evidence citations and patient-specific advice (`generator.py:166-201`).

### Scope of the knowledge base (facts from `data/manifests/`)
| Item | Value | Source |
|---|---|---|
| Drugs covered | 8: osimertinib, pembrolizumab, trastuzumab, imatinib, adalimumab, semaglutide, nivolumab, enzalutamide | `data/registry/drugs.yaml`, `src/discovery/phase1_corpus.py:35` |
| Discovery profiles | 10 (indication, mechanism, clinical_trial, safety, biomarker, resistance, comparison, combination_strategy, review, real_world_evidence) | `src/discovery/pmc_search.py:28` |
| Search plan | 8 drugs × 10 profiles × 20 results = 80 searches, 1,600 hits, 643 unique PMCIDs | `phase1_acquisition_report.json` |
| Staged XML | 595 articles | `index_manifest.json` |
| Indexed | 568 articles, 11,239 chunks; 27 failed ("no chunks produced") | `index_manifest.json` |
| Vector dim | 768 | `data/chromadb/chroma.sqlite3` collections table |

### Users
**ASSUMPTION:** pharma/biomedical researchers or internal analysts. Code evidence only shows an interactive terminal (`app.py:97`) with heavy debug output; there is no API, UI, auth, or multi-user handling. Current state is a developer prototype / research workbench, not a deployed service.

### Value
- Answers are restricted to retrieved evidence and post-validated for citation format (`generator.py:330-395`, `:470-494`).
- Each run is persisted as a JSON artifact (question, query analysis, chunks, evidence map, answer, timings) in `debug_runs/` (`app.py:36-75`) — useful for audit and offline evaluation.

---

## 2. Architecture

### 2.1 High-level architecture

```
                     OFFLINE (batch, run manually)                                ONLINE (interactive CLI)
 ┌──────────────────────────────────────────────────────────────┐   ┌───────────────────────────────────────────────┐
 │ NCBI E-utilities (esearch/esummary)   PMC OAI-PMH (GetRecord)│   │  User @ terminal  ── app.py main() loop       │
 │            │                                   │             │   │        │                                      │
 │   discovery/pmc_search.py  ──►  discovery/phase1_corpus.py   │   │        ▼                                      │
 │            (drug × profile queries, staging XML + metadata)  │   │  QueryUnderstanding ──(low conf)──► Ollama    │
 │                              │                               │   │   (rules + DrugRegistry)          qwen2.5:1.5b│
 │                 data/staging/phase1/{xml,metadata}           │   │        ▼                                      │
 │                              │                               │   │  StrategyManager (intent → k values)          │
 │   indexing/build_index.py:                                   │   │        ▼                                      │
 │     pmc_parser → metadata_enricher → section_chunker         │   │  retriever: MedCPT-Query embed ×N queries     │
 │       → embedder (MedCPT-Article) → chroma_store.add         │   │     → Chroma query ×N → merge → CrossEncoder  │
 │                              │                               │   │        ▼                                      │
 │                              ▼                               │   │  context_builder ([E#] blocks, 1200 chars)    │
 │        data/chromadb  (Chroma PersistentClient,              │◄──┤        ▼                                      │
 │        collection "pharma_research", 11,239 vectors)         │   │  QwenGenerator ──► Ollama qwen2.5:7b          │
 │        data/manifests/*.json, *.log                          │   │     → normalize → validate → prune → answer   │
 └──────────────────────────────────────────────────────────────┘   │        ▼                                      │
                                                                     │  stdout + debug_runs/run_*.json               │
                                                                     └───────────────────────────────────────────────┘
 Shared by both: data/registry/drugs.yaml (DrugRegistry), HF model cache (~/.cache/huggingface)
```

### 2.2 Component architecture

```
app.py
 ├── query_understanding.QueryUnderstanding           (fast path rules; LLM fallback)
 │     └── processing.DrugRegistry ── data/registry/drugs.yaml
 ├── retrieval.StrategyManager / RetrievalStrategy    (pure config)
 ├── retrieval.retrieve_chunks
 │     ├── embeddings.embed_query        [loads 2 MedCPT models at import]
 │     ├── vector_store.collection       [opens Chroma at import, relative path]
 │     └── retrieval.rerank_chunks       [loads CrossEncoder at import]
 ├── generation.build_context
 └── generation.QwenGenerator            (prompt, Ollama call, validation)

Offline:
indexing/build_index.py
 ├── processing.pmc_parser.parse_article
 ├── processing.metadata_enricher.enrich_article ── DrugRegistry, evidence_classifier
 ├── chunking.section_chunker.create_chunks ── metadata_enricher.inherit_chunk_metadata, evidence_classifier
 ├── embeddings.embed_chunks
 └── vector_store.store_chunks / count_chunks
discovery/phase1_corpus.py ── discovery.pmc_search, ingestion.pmc_oai, DrugRegistry

Not on any runtime path (no importers found by grep):
 generation/prompts.py (SYSTEM_PROMPT), generation/coverage_analyzer.py, generation/citation.py (empty),
 query_understanding/{entity_extractor,intent_classifier,query_expander}.py, ingestion/article_store.py,
 vector_store.similarity_search
```

### 2.3 Data-flow architecture

```
OFFLINE
PMC XML (JATS) ─parse─► article dict {pmcid,pmid,doi,title,abstract,journal,authors,
                                      publication_year,article_type,keywords,subjects,sections[tree]}
  ─enrich─► + {drugs[mentions], drug, targets, diseases, disease, article_type(normalized),
               study_design, evidence_types[], source_type, metadata_version}
  ─chunk──► per body section: 400-word windows, 100 overlap, min 100 words
            chunk {chunk_id=PMCxxx_NNNN, section_path "A > B", part, text, section_category, …inherited}
  ─embed──► + embedding[768] (MedCPT-Article, mean-pooled, max 512 tokens)
  ─store──► Chroma: id, embedding, document=text, metadata (16 primitive fields; lists joined by "|")

ONLINE
question:str
  ─QU──────► query_info {intent, question_type, answer_type, complexity,
                         entities{DRUG,…}, retrieval_hints[], expanded_queries[≤5 or 7]}
  ─strategy► RetrievalStrategy {retrieval_k, top_k, diversity_boost, evidence_depth}
  ─retrieve► [question + expanded_queries] → each: embed → Chroma top retrieval_k
             → merged dict by chunk_id (first-seen wins) → candidates[≤ N×retrieval_k]
  ─rerank──► CE score(question, text) → min-max norm + question-type bonus (≤0.30)
             → sort → dedup (first 300 chars) → ≤2 per PMCID → top_k chunks
  ─context─► "[E1]\nDrug:…\nEvidence Type:…\nStudy Design:…\nPublication Year:…\nSection:…\n<text≤1200 chars>"
             + evidence_map {E#: {pmcid, chunk_id, section_path}}
  ─generate► prompt (instructions + query_info JSON + context + question) → Ollama stdout
  ─validate► normalize citations → validate → (if errors) keep only lines with valid [E#] → re-validate
             → answer:str  or  ValueError
  ─output──► print answer + references; write debug_runs/run_<ts>.json
```

---

## 3. Project Structure Map

Importance: **C** = critical online path, **H** = critical offline path, **M** = support/eval, **L** = unused/legacy.

### Root
| File | Purpose | Inputs → Outputs | Depends on | Imp. |
|---|---|---|---|---|
| `app.py` | CLI loop orchestrating the full pipeline; prints debug; saves run artifacts | stdin question → stdout answer, `debug_runs/*.json` | QU, StrategyManager, retriever, context_builder, generator | C |
| `requirements.txt` | Unpinned deps: requests, lxml, torch, transformers, chromadb, sentencepiece, numpy, pandas, tqdm, sentence-transformers, json-repair | — | — | M |
| `.gitignore` | Excludes `data/`, `debug_runs/`, `.venv/`, models | — | — | L |

### `src/query_understanding/`
| File | Key symbols | Purpose | Imp. |
|---|---|---|---|
| `query_understanding.py` (1,500 lines) | `QueryUnderstanding`: `analyze`, `_classify_without_llm`, `_taxonomy_scores`, `_semantic_scores`, `_detect_intent`, `_estimate_complexity`, `validate_result`, `_ground_entities`, `_build_grounded_retrieval_hints`, `_build_grounded_expanded_queries`, `build_prompt`, `extract_json`, `fallback`; constants `QUESTION_TYPE_TAXONOMY`, `INTENT_CUES`, `MECHANISM_/DRUG_OVERVIEW_QUESTION_PATTERNS`, `LLM_FALLBACK_CONFIDENCE=0.5`, `TAXONOMY_SATURATION=3.0`, `MIN_TYPE_SCORE=0.25` | Question → `query_info` dict. Rule-based fast path; Ollama `qwen2.5:1.5b` fallback (60 s timeout); deterministic grounding of entities and templated expansions | C |
| `entity_extractor.py`, `intent_classifier.py`, `query_expander.py` | `EntityExtractor`, `IntentClassifier`, `QueryExpander` | Earlier LLM-per-step design (qwen2.5:7b). Not imported anywhere | L |
| `__init__.py` | empty | — | L |

### `src/retrieval/`
| File | Key symbols | Purpose | Imp. |
|---|---|---|---|
| `retriever.py` | `retrieve_chunks`, `_normalize_queries` | Multi-query dense retrieval, merge, rerank. Defaults top_k=8, retrieval_k=50 when no strategy | C |
| `reranker.py` | `rerank_chunks`, `_question_type_bonus`, `_resolve_question_type`, `_source_id`; `QUESTION_TYPE_CUES`, `MAX_QUESTION_TYPE_BONUS=0.30`, `MECHANISM_SECTION_TITLE_BONUS=0.15` | CrossEncoder `ms-marco-MiniLM-L-12-v2` scoring + heuristic bonus + dedup + per-source cap (2) | C |
| `retrieval_strategy.py` | `RetrievalStrategy` (frozen dataclass), `StrategyManager.get_strategy` | Intent → {retrieval_k, top_k, diversity_boost, evidence_depth} | C |
| `test_retriever.py`, `test_retrieval_quality.py` | scripts (no asserts) | Manual smoke runs | M |

### `src/embeddings/`, `src/vector_store/`
| File | Key symbols | Purpose | Imp. |
|---|---|---|---|
| `embedder.py` | `embed_query`, `embed_document`, `embed_chunk(s)`, `mean_pooling` | MedCPT Query/Article encoders, CPU, max_length 512, mean pooling. Both models load at import | C/H |
| `chroma_store.py` | `client`, `collection`, `store_chunks`, `count_chunks`, `similarity_search`, `_metadata_value` | `PersistentClient(path="data/chromadb")` (CWD-relative), collection `pharma_research` | C/H |
| `test_*.py` | scripts | Smoke runs | M |

### `src/generation/`
| File | Key symbols | Purpose | Imp. |
|---|---|---|---|
| `generator.py` | `QwenGenerator`: `build_prompt`, `generate`, `normalize_answer`, `_expand_evidence_ids`, `validate_answer`, `_retain_cited_claims`; `ANSWER_SECTIONS`, `FORBIDDEN_PHRASES`, `NON_EVIDENCE_CITATION_PATTERN` | Prompt templating by question profile, Ollama `qwen2.5:7b` (no timeout), citation normalization & enforcement | C |
| `context_builder.py` | `build_context(chunks, coverage=None)`; `MAX_CHARS_PER_CHUNK=1200` | Evidence blocks + evidence_map | C |
| `prompts.py` | `SYSTEM_PROMPT` | Long "silent audit" prompt; not imported | L |
| `coverage_analyzer.py` | `CoverageAnalyzer` | LLM finding-inventory step; not imported (context_builder still accepts `coverage`) | L |
| `citation.py` | empty | — | L |
| `test_*.py` | scripts | Smoke runs | M |

### `src/processing/`
| File | Key symbols | Purpose | Imp. |
|---|---|---|---|
| `drug_registry.py` | `DrugRegistry`: `lookup`, `get`, `find_mentions`, `all_aliases`, `search_query_terms` | Loads `drugs.yaml` (JSON content despite extension); alias → canonical. First 85 lines are a commented-out duplicate | C/H |
| `pmc_parser.py` | `parse_article`, `parse_section`, `_publication_year`, `_clean_text` | JATS XML → article dict with section tree (body only) | H |
| `metadata_enricher.py` | `enrich_article`, `inherit_chunk_metadata`, `_role_for` | Drug mentions, targets, classification → article/chunk metadata | H |
| `evidence_classifier.py` | `EVIDENCE_CUES`, `STUDY_DESIGN_CUES`, `classify_text`, `classify_article`, `section_category`, `infer_study_design`, `normalize_article_type` | Keyword-based labels | H |
| `test_parser.py` | script | Smoke run | M |

### `src/chunking/`, `src/indexing/`, `src/discovery/`, `src/ingestion/`, `src/deletion/`
| File | Purpose | Imp. |
|---|---|---|
| `chunking/section_chunker.py` — `split_text(400/100/min 100)`, `create_chunks` | Section-tree walk → word-window chunks | H |
| `indexing/build_index.py` — `build_index`, `audit_corpus`, `validate_chunks`, checkpoint/manifest writers | Batch index build; `--audit-only` / `--rebuild` (moves `data/chromadb` to `data/backups/`) / `--source-dir`. Default source `data/raw/xml` does not exist; last build used `data/staging/phase1/xml` | H |
| `discovery/pmc_search.py` — `DISCOVERY_PROFILES`, `build_profile_query`, `search_pmc`, `get_pmc_metadata` | NCBI E-utilities queries | H |
| `discovery/phase1_corpus.py` — `_query_plan`, `discover`, `build_report`, `stage_records`, `main` | Acquisition run + coverage report + staging | H |
| `ingestion/pmc_oai.py` — `get_article_xml` | OAI-PMH fetch, 3 retries, 30 s timeout | H |
| `ingestion/article_store.py` — `save_article` | Writes to `data/raw/xml`; not imported | L |
| `deletion/clear_db.py` | Despite name, prints one hard-coded chunk (`PMC13529361_0008`); deletes nothing | L |

### `src/evaluation/`
| File | Purpose | Imp. |
|---|---|---|
| `benchmark_framework.py` | 5 benchmark questions with hand-written queries and expected concepts; re-implements retrieval loop (does not call `retrieve_chunks` or QU); writes `evaluation_outputs/benchmark_report.json` (directory not present → never run on this VM, or output deleted) | M |
| `retrieval_eval.py`, `build_gold_chunks.py`, `check_chunk_exists.py`, `find_chunk.py`, `find_rank.py` | Gold-chunk rank checks against current index (gold IDs verified present) | M |

### Data / runtime directories (git-ignored)
| Path | Content |
|---|---|
| `data/chromadb/` (224 MB) | Live vector store |
| `data/chroma/` (188 KB) | Empty Chroma DB (no collections) — orphan |
| `data/staging/phase1/{xml,metadata}` (71 MB) | 595 XML + metadata JSON |
| `data/manifests/` | acquisition report, index manifest, checkpoint, build log, metadata quality report |
| `data/registry/drugs.yaml` | 8-drug registry |
| `debug_runs/` | 27 run artifacts (2026-10-10 → 2026-10-14) |

### Dependency hierarchy (online path; arrows = imports)
```
app.py
├─► query_understanding.query_understanding ─► processing.drug_registry ─► data/registry/drugs.yaml
│                                            └► json_repair
├─► retrieval.retrieval_strategy
├─► retrieval.retriever ─┬► embeddings.embedder      ─► transformers, torch  (HF: ncbi/MedCPT-*)
│                        ├► vector_store.chroma_store ─► chromadb  (data/chromadb, CWD-relative)
│                        └► retrieval.reranker        ─► sentence_transformers (HF: cross-encoder/ms-marco-MiniLM-L-12-v2)
├─► generation.context_builder
└─► generation.generator ─► ollama CLI (qwen2.5:7b)
```
Import mechanics: `app.py` appends `src/` to `sys.path`; modules use either `from processing…` or fall back to `from src.processing…`.

---

## 4. End-to-End Workflow (online)

Startup cost (one-time per process): importing `retriever` loads MedCPT Query + Article encoders and the CrossEncoder, and opens Chroma (`embedder.py:8-38`, `reranker.py:5-9`, `chroma_store.py:7-13`). The Article encoder is loaded even though only queries are embedded online.

### Stage 1 — Query understanding (`QueryUnderstanding.analyze`, `query_understanding.py:1345`)
1. Strip question. Run `_classify_without_llm` (`:608`):
   - Normalize text (casefold, keep alphanumeric tokens).
   - **Drug detection**: `DrugRegistry.find_mentions` over all aliases, longest first, boundary regex (`drug_registry.py:148`). TARGET entities = registry targets of detected drugs that literally appear in the question.
   - **Type**: if any `MECHANISM_QUESTION_PATTERNS` regex matches → `MECHANISM`, conf 1.0; elif any `DRUG_OVERVIEW_QUESTION_PATTERNS` → `DRUG_OVERVIEW`, 1.0; else taxonomy scoring: per type `1 − exp(−Σweights/3.0)`, drop < 0.25, top type wins, `confidence = top + 0.5·(top − runner_up)`; none → `GENERAL_RESEARCH`, 0.0. Semantic layer weight is 0 because `app.py:87` constructs `QueryUnderstanding()` without `embed_fn`.
   - **Intent**: first matching `INTENT_CUES` (COMPARISON, SUMMARY, PROCEDURE, DECISION_SUPPORT, ANALYSIS, EVIDENCE) → else taxonomy's default intent → else `^why|how|explain|describe` → EXPLANATION, `^what|which|…` → FACT_LOOKUP → else GENERAL.
   - **Complexity**: point system (≥2 drugs, analytic intent, >25 words, ≥2 " and ").
2. If `confidence ≥ 0.5` → `validate_result(fast_result)`. Otherwise call Ollama `qwen2.5:1.5b` with a JSON-schema prompt (`:680`), parse with `extract_json` (+`json_repair`), then `validate_result`. Any LLM failure → `validate_result(fast_result)`.
3. `validate_result` (`:1118`): coerce enums to allowed sets; **ground** entities (keep only values present in question or registry-backed aliases/targets of detected drugs; always add registry drugs); re-apply mechanism / drug-overview regex overrides; **discard any LLM retrieval_hints/expanded_queries** and rebuild them from fixed templates per question_type and drug (`:1037-1116`).
   - Output: `query_info` dict. `expanded_queries` always starts with the question; ≤5 entries (DRUG_OVERVIEW: question + 6 per drug, uncapped).

### Stage 2 — Strategy (`StrategyManager.get_strategy`, `retrieval_strategy.py:94`)
Only `intent` is used. Table in `retrieval_strategy.py:15-76`; GENERAL and unknown → default (retrieval_k 30, top_k 5).

### Stage 3 — Retrieval (`retrieve_chunks`, `retriever.py:42`)
- Queries = dedup([question] + expanded_queries).
- For each query: `embed_query` (MedCPT-Query, mean pooling) → `collection.query(n_results=retrieval_k)`; no metadata `where` filter; no distance threshold; distances discarded.
- Merge by chunk_id (first occurrence kept). Candidates ≤ queries × retrieval_k.

### Stage 4 — Reranking (`rerank_chunks`, `reranker.py:154`)
- CrossEncoder scores `(original_question, chunk_text)` for all candidates (expanded queries are not used for scoring).
- Min–max normalize scores within the candidate set; add `question_type_bonus` = min(0.30, 0.025·text cue hits + 0.06·section cue hits + 0.15 mechanism section title bonus). Question type comes from `query_info.question_type` if it is a cue key, else keyword inference from the question.
- Sort by combined score → dedup by first 300 lowercased chars → cap 2 chunks per PMCID → take `top_k`.
- `diversity_boost` is passed in but never read inside `rerank_chunks`; the per-source cap applies to every strategy.
- Output chunk adds `rerank_score` (raw CE), `normalized_rerank_score`, `question_type_score`, `combined_rerank_score`.

### Stage 5 — Context assembly (`build_context`, `context_builder.py:1`)
For chunk i: id `E{i}`; whitespace-collapse; truncate to 1,200 chars; header lines Drug / Evidence Type / Study Design / Publication Year / Section. Join with blank lines. `coverage` is never supplied by `app.py`. Output: `context` string + `evidence_map`.
Upper bound: top_k 8 × (~1,200 + header) ≈ 10–11 K chars of evidence.

### Stage 6 — Generation (`QwenGenerator.generate`, `generator.py:428`)
- `build_prompt` picks a section profile: COMPARISON (if intent COMPARISON or type COMPARISON/COMPARATIVE_EFFECTIVENESS), MECHANISM (MECHANISM/MOA), CLINICAL_TRIAL (CLINICAL_TRIAL/TRIAL), DRUG_OVERVIEW (DRUG/DRUG_OVERVIEW/OVERVIEW), else generic (Executive Summary / Key Findings / Evidence Limitations). Embeds a JSON of intent/question_type/answer_type/complexity/entities/retrieval_hints, citation rules, context, question.
- `subprocess.run(["ollama","run","qwen2.5:7b"], input=prompt)` — no timeout, no temperature/seed/num_ctx control, entire stdout captured.

### Stage 7 — Validation (`generator.py:470-494`)
1. `normalize_answer`: strip ANSI/terminal artifacts; rewrite `[E1, E2]`, `[E1-E3]`, `(E2)` → `[E1] [E2]…`; attach citation-only lines to previous line.
2. `validate_answer`: errors for unknown IDs, any `[...]` that is not `E#`, bare `E#`, DOI/PMID/PMCID/“et al.”/“Word (2019)” patterns, forbidden phrases (substring match: “likely”, “possibly”, “may suggest”, “it may be”, …).
3. If errors: `_retain_cited_claims` keeps headings and only lines whose citations are all valid; drops lines without citations (including “Not established in the supplied evidence.”); rebuilds `## References`. Re-normalize, re-validate.
4. If still errors or empty → `ValueError`, caught in `app.py:302` and printed as `Error: …` (no answer shown).

### Stage 8 — Final response (`app.py:254-300`)
Prints timings, answer, references (`E# : chunk_id | pmcid | section_path`), and writes `debug_runs/run_<timestamp>.json`.

### Historical latency (from `debug_runs/`, 12 most recent) — architectural reference only
Not a baseline: runs used varying code versions and uncontrolled conditions. Baseline performance is defined solely by the suite in [BENCHMARK_PLAN.md](BENCHMARK_PLAN.md).

| Stage | Range |
|---|---|
| Query understanding | 0.0 s (fast path) or 7–20 s (LLM fallback) |
| Retrieval + rerank | 2–9 s |
| Generation | 62–291 s |
| Total | 66–298 s |

---

## Discovery Log (verified findings to carry into later sections)

Each item is a fact with evidence; no fixes proposed yet.

1. **Non-deterministic question_type on ties.** `_classify_without_llm` builds `combined` from `set(lexical) | set(semantic)` and sorts by score only (`query_understanding.py:642-649`). Ties are broken by set order, which depends on `PYTHONHASHSEED`. Verified: "What resistance mechanisms emerge after first-line osimertinib?" (the primary benchmark question) yields THERAPY, RESISTANCE, or MECHANISM at confidence 0.63 under seeds 1/2/3. This changes expansions, reranker bonus, and prompt profile.
2. **"mechanism of resistance" routes to MECHANISM.** Regex `\bmechanism\s+of\s+.+` (`:29`) matches; "What is the mechanism of resistance to imatinib?" → MECHANISM, conf 1.0, overriding RESISTANCE.
3. **Short drug questions fall to the LLM.** "What is nivolumab?" scores 0.0 → LLM fallback; logged run classified it as DISEASE. Same question "Did nephrotic syndrome recur after nivolumab rechallenge?" got DIAGNOSTIC / OTHER in separate runs (LLM non-determinism).
4. **LLM expansions discarded.** `validate_result` replaces LLM `expanded_queries`/`retrieval_hints` with templates (`:1256-1257`); expansions exist only for MECHANISM/MOA, CLINICAL_TRIAL, SAFETY/ADVERSE_EVENT, BIOMARKER, RESISTANCE, DRUG_OVERVIEW and only when a registry drug is detected.
5. **Semantic classifier layer inactive** (`embed_fn` never passed).
6. **`diversity_boost` unused** inside `rerank_chunks`; per-PMCID cap of 2 always applies.
7. **Chroma distance metric is default** — collection created without `hnsw:space` metadata (`chroma_store.py:11`; `collection_metadata` table empty). Chroma's default is L2. **ASSUMPTION (to verify against MedCPT model card):** MedCPT is trained with CLS-token pooling and dot-product similarity; the code uses mean pooling (`embedder.py:41`) and L2.
8. **Chunker drops sections under 100 words** (`section_chunker.py:26`) and never indexes the abstract (only `<body>` sections, `pmc_parser.py:215-225`). 27/595 articles produced zero chunks.
9. **Validator hard-fails on common words.** `FORBIDDEN_PHRASES` are substring checks; "likely" also matches "unlikely". A cited line containing them survives pruning, so validation fails again → `ValueError`, no answer returned. The prune step also removes "Not established in the supplied evidence." lines the prompt requires.
10. **No timeout on generation** Ollama call (`generator.py:449`); QU call has 60 s.
11. **Import-time side effects**: models and Chroma load on import; Chroma path is CWD-relative (`data/chromadb`), so running from another directory silently creates an empty store (likely origin of the orphan `data/chroma/`, **ASSUMPTION**).
12. **Duplicate retrieval logic** in `benchmark_framework.py:164` vs `retriever.py:115`; benchmark bypasses QU and strategy, so it does not measure the production path.
13. **Tests are scripts without assertions**; no test runner configuration.
14. **Dependencies unpinned** (`requirements.txt`); installed: chromadb 1.5.9, torch 2.14.1+cpu, sentence-transformers 6.1.0, transformers 5.19.0.

## Generation runtime facts (fresh probe 2026-10-14; details in [ENGINEERING_ASSESSMENT.md](ENGINEERING_ASSESSMENT.md) §6)
- Ollama 0.40.2 serves qwen2.5:7b Q4_K_M with `n_ctx = 4096`, 4 threads of 8 vCPU, AMX + flash attention; code sets no Ollama options.
- Prefill 56–64 tok/s, decode 6.1–6.9 tok/s. Decode = 62–75 % of generation time; answers 403–536 tokens; prompts 1.4 K (top_k 3) – 3.2 K (top_k 8) tokens.
- Non-LLM stages total ≤ 4.1 s; rerank is the largest (1.3–4.0 s, scales with pool size).

## Infrastructure snapshot (observed 2026-10-14)
- Azure VM, 8 vCPU, 15 GB RAM, no swap, no GPU (`nvidia-smi` absent, `torch.cuda.is_available() == False`), 29 GB disk at 71% used.
- Ollama at `/usr/local/bin/ollama`; models `qwen2.5:7b` (4.7 GB), `qwen2.5:1.5b` (986 MB).
- HF cache holds MedCPT Query/Article encoders and ms-marco-MiniLM-L-12-v2.

## Open items for next discovery pass
| Topic | What to inspect |
|---|---|
| Embedding correctness | MedCPT model card pooling + similarity; measure recall with CLS vs mean on `retrieval_eval.py` gold set |
| Reranker effectiveness | Compare gold-chunk rank pre/post rerank (`find_rank.py`, `retrieval_eval.py`) |
| Ollama context window | `ollama show qwen2.5:7b` for `num_ctx`; compare to prompt token counts in debug runs |
| Validation failure rate | Count `Error:` outcomes; debug_runs only stores successful runs (`save_debug_run` runs after generation) |
| Discovery details | `pmc_search.search_pmc` / `get_pmc_metadata` rate limits and API key use |
| Metadata quality | `data/manifests/metadata_quality_report.json` |

## Discovery Log — pass 3 (2026-10-14, see [PHASE2_INVESTIGATION.md](PHASE2_INVESTIGATION.md))
15. **Intent does not track question scope.** Preliminary retrieval pass (27 questions, seed 0): 5/16 single-paper questions → COMPARISON (8 chunks); 4/9 multi-paper questions → FACT_LOOKUP (3 chunks), while their candidate pools held more gold papers than reached context.
16. **Boilerplate is indexed**: section paths matching Author Contributions (17 chunks), Conflict (24), Disclosure (12), Supplementary (12), Supporting information (16), Ethics (12).
17. **`section_category` / "Evidence Type" labels are keyword-derived and noisy** (e.g. Introduction → `clinical_trial`); these labels are shown to Qwen in every evidence block.
18. **Answer text can sit beyond the 1,200-char cut** (e.g. `AMPK` at char 1,436 in PMC13368672_0022).
19. **No relevance floor**: out-of-corpus questions still receive 3–5 unrelated chunks.
20. **Rare-term miss**: PMC13537402 not in pool for a "Yifeixiaoji" question although the term appears in 2 indexed chunks (cause unproven).
21. Retrieval latency 1.3–6.2 s scales with pool size (20–105 candidates).

## Discovery Log — pass 4 (2026-10-15, benchmark harness smoke runs)
22. **Cold model load can dominate a request.** Generation smoke run (L1-02): Ollama `load_duration` 119.2 s of 159.6 s total (prefill 18.4 s, decode 22.0 s for 161 tokens). Earlier probe measured 5.3 s cold load. Single observation; load conditions (page cache, idle eviction) not yet characterized. App import was 83 s in the same cold state (6 s warm).
23. **`ollama run` hard-wraps stdout even when piped.** Verified directly: output contains cursor-edit escapes and newlines at terminal width. `normalize_answer` (`generator.py:233`) removes the escapes but keeps the line breaks; `_retain_cited_claims` (`generator.py:367`) prunes line by line, so wrapped continuation lines without `[E#]` are dropped whenever pruning runs. `ollama run --nowordwrap` exists. 26/27 historical answers contain mid-sentence line breaks (architectural reference).
24. Harness in `src/evaluation/` (see [BENCHMARK_PLAN.md](BENCHMARK_PLAN.md) §9). Hash-seed instability reproduced in harness: L1-12 and L2-01 → THERAPY under seed 1, RESISTANCE under seeds 0 and 2.
25. **119 s load explained (cold page cache after VM reboot).** VM booted 2026-10-15 03:44; first 7b load 04:11:46 → 04:13:45 during `load_tensors` with mmap disabled (`reason=cpu`): ~4.5 GB in 119 s ≈ 38 MB/s. First 1.5b load the same morning: 22 s for ~1 GB ≈ 45 MB/s. Loads on 2026-10-14 (warm page cache): 1–5 s. Latency-only; no correctness impact.
26. **Pruning destroys wrapped claims (mechanism proven on real output).** Replaying `_retain_cited_claims` on the L1-02 harness answer turns "Baseline serum KL-6 levels of ≥400 U/mL predicted … cohort study [E1]" into "cohort study [E1]" and a 4-line limitation sentence into "[E1]." Frequency = rate of `pass_after_prune`, not yet measured (0 of 4 generation runs so far).

## Discovery Log — pass 5 (2026-10-15, retrieval-only baseline, 5 seeds; see [RETRIEVAL_BASELINE_REPORT.md](RETRIEVAL_BASELINE_REPORT.md))
27. Gold paper reaches Qwen for 15/16 L1 questions, but only 48 % of expected facts and 29 % of labeled answer chunks do. Dominant L1 loss: not retrieved (56 % of answer-chunk runs); then 2-per-paper limit (15 %). No reranked-out, top_k, dedup or truncation losses observed at L1.
28. L2 gold papers: 34 % delivered, 36 % pooled but cut by top_k, 30 % never retrieved.
29. Dense retrieval over-selects Introduction (10 % of corpus → 31 % of pool) and under-selects Results (27 % → 14 %).
30. QU instability has two sources: hash-seed ties (5 questions, seed-controllable) and the `qwen2.5:1.5b` fallback (6 questions, irreproducible at fixed seed — 3 runs gave 3 labels).
31. Benchmark hazard: fact patterns with alternatives can match the wrong analysis (L1-14 matched the primary-analysis ORR in the Introduction).

## Discovery Log — pass 6 (2026-10-15, retrieval RCA measurements; see [RETRIEVAL_RCA.md](RETRIEVAL_RCA.md))
32. **MedCPT used differently from its model cards (proven):** cards use `[CLS]` pooling, `[title, abstract]` article input, query `max_length=64`; code uses mean pooling, chunk text only, query `max_length=512`. Impact on retrieval unmeasured.
33. 36.3 % of chunks exceed 512 encoder tokens (Results: 51 %), but all facts in the 14 lost answer chunks sit within the first 330 tokens — truncation did not cause those losses.
34. Embedding norms are near-constant (CV 1.7 %); L2 ≈ cosine. Section skew identical under L2/IP/cosine — not a metric artifact.
35. Results chunks: 0.185 numbers/word (2–3× other sections), 77 % contain flattened figure/table references.
36. All 3 two-per-paper losses: Results chunk displaced by Discussion/Methods chunks of the same paper ranked higher by the cross-encoder.
37. Expansion templates are drug-generic (`{drug} biomarker evidence` etc.); 7 of 11 lost chunks belong to questions with no expansion at all; L1 expansions added 0 gold-paper chunks.
38. Full re-embedding cost: 0.126 s/chunk → ~24 min for 11,239 chunks (from `index_build.log`).

## Discovery Log — pass 7 (2026-10-15, RCA experiments E5/E3/E1/E4/E6; see [RETRIEVAL_RCA.md](RETRIEVAL_RCA.md) "Results")
39. Index reproducible exactly from source for 16 gold papers (E5).
40. Lost chunks are retrievable with content-matched (oracle) queries: 8/11 within retrieval_k; Results share of top-60 returns to corpus rate (28 %) — skew is query-register driven (E3).
41. Embedding a lost chunk as MedCPT's documented `[title, text]` pair moves 10/11 inside retrieval_k (asymmetric upper bound) (E1). Removing captions worsens ranks.
42. Answer-chunk recall@k: 0.35 @20, 0.55 @60, 0.75 @200; L2 papers 0.62 @20 → 0.87 @60 (E4).
43. Answer chunk is outranked within its own paper (mostly by Discussion) in 35/44 observations; cap 3 counterfactually delivers 40/44 vs 29/44 (E6).
44. Dominant mechanism (current evidence): question↔chunk register/context mismatch at dense retrieval, compounded by cross-encoder preference for summary prose. E2 re-scoped to title-pair corpus re-embedding first.

## Discovery Log — pass 8 (2026-10-15, system assessment; see [SYSTEM_ASSESSMENT.md](SYSTEM_ASSESSMENT.md))
45. Corpus questions added to coverage plan (N1–N8, M1–M4) for PK/DDI, pediatric safety, biomarker time course, renal outcomes, dosing time, RWE response, real-world toxicity, pharmacovigilance. Four L1 facts lie beyond the 1,200-char cut (PMC13504015_0012 @1826, PMC13519180_0013 @2321, PMC13310552_0006 @1252, PMC13508003_0004 @2160) — tests for truncation loss, which the original set could not show.
46. Priority stance: retrieval first, with two correctness defects (wrap-prune, non-deterministic evidence budget) resolved alongside; generation measured, not optimized; infrastructure limited to reliability items.

## Decision record (2026-10-15; see [DECISION_DOCUMENT.md](DECISION_DOCUMENT.md))
- Not production-ready: blockers are evidence quality, output corruption by pruning, non-deterministic evidence budget, unmeasured correctness/abstention, operational fragility.
- Proposed immediate code changes (pending approval): unwrapped output + sentence-aware pruning; validator word-boundary + keep "Not established"; deterministic classification/budget; explicit Ollama options + timeout; absolute paths, offline load, failure artifacts.
- Target architecture: warm service; paper-first (title+abstract paper index), passage-second (rerank within selected papers, scope-based quotas, relevance floor); token-budgeted context at num_ctx 8192; sentence-level citation verification; telemetry; harness as quality gate.

## Discovery Log — pass 9 (2026-10-15, two-day execution; see [TWO_DAY_RESULTS.md](TWO_DAY_RESULTS.md))
47. F1–F5 merged on branch `fix/correctness-2day`: wrap artifacts 57 → 0 escapes, 38 → 0 broken lines; classification stable 27/27 across seeds (268/270 over 10 processes); index path and generation timeout fixed.
48. E2a (title-context passage vectors): answer-chunk recall@20 0.35 → 0.60, pool entry 9 → 14/20, but delivery unchanged (6/20) and fact visibility +3.8 pts → decision `reranker_bottleneck`. Title context halves within-paper discrimination (0.93 → 0.50) and reduces pool diversity (18 → 12 papers). Use titles for paper retrieval, not passage ranking.
49. Generation: fabricated author attribution ("Huang et al. [E2]") causes total answer loss (L1-16, 2/2 runs); numbers omitted despite being in evidence (L1-05, L1-12); identical prompt yields different fact recall (L1-08) — generation lacks seed/temperature control.
50. Controls abstained with 0 cited claims in 4/4 runs.
