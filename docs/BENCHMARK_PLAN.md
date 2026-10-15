# Baseline Benchmark Suite — Design

Status: design v1 (2026-10-14). Nothing implemented yet. No production code changes required to run it.
**Question set superseded by [PHASE2_INVESTIGATION.md](PHASE2_INVESTIGATION.md) §3 (corpus-verified answer chunks, L0 level added).** Protocol sections here remain valid.
Purpose: establish a reproducible performance baseline of the **current** pipeline (`app.py` path) before any optimization decision.
Historical `debug_runs/` are architectural reference only and are excluded from all baseline numbers.

---

## 1. Principles

1. **Measure the production path.** The harness calls the same objects in the same order with the same arguments as `app.py:85-247`: `QueryUnderstanding().analyze` → `StrategyManager().get_strategy({"intent": …})` → `retrieve_chunks(question=, query_info=, strategy=)` → `build_context(chunks=)` → `QwenGenerator().generate(question=, context=, query_info=)`. `src/evaluation/benchmark_framework.py` is **not** used: it bypasses query understanding and strategy and hard-codes its own queries and k values (`benchmark_framework.py:26-27,160-210`).
2. **Observe without modifying.** Stage internals are captured by wrapping functions at runtime inside the harness process only:
   | Wrapped symbol | Captures |
   |---|---|
   | `retrieval.retriever.collection.query` | per-query result IDs, distances, rank |
   | `retrieval.retriever.rerank_chunks` | the merged candidate pool passed to reranking |
   | `generation.generator.subprocess.run` | raw Ollama stdout, return code, wall time |
   | `query_understanding.query_understanding.subprocess.run` | whether the LLM fallback ran, raw output |
   An untimed analysis pass then calls `rerank_chunks(question, pool, top_k=len(pool), max_per_source=len(pool), question_type=…)` to obtain the full cross-encoder order of the pool for rank metrics.
3. **Gold labels come from the corpus, not memory.** Every expected fact must be quoted from a labeled gold chunk.
4. **Separate variance sources.** Classification variance (hash seed, finding #1 in handbook), LLM variance (no temperature/seed control in `generator.py:449`), and cold/warm start are measured separately.
5. **Baseline first, judgement later.** All metrics are recorded for every run regardless of pass/fail. Success criteria are proposed thresholds for owner sign-off, not tuning targets.

---

## 2. Run protocol

### 2.1 Environment fingerprint (recorded in every report; a mismatch invalidates comparison)
| Item | Baseline value / how to capture |
|---|---|
| Code | `git rev-parse HEAD` + `sha256(git diff HEAD)` |
| Index | Chroma count = 11,239; `sha256(data/manifests/index_manifest.json)` |
| Registry | `sha256(data/registry/drugs.yaml)` |
| LLMs | `ollama list` IDs: `qwen2.5:7b` 845dbda0ea48, `qwen2.5:1.5b` 65ec06548149; `ollama show qwen2.5:7b` parameters |
| Encoders | HF snapshot hashes under `~/.cache/huggingface/hub/models--ncbi--MedCPT-*`, `models--cross-encoder--ms-marco-MiniLM-L-12-v2` |
| Packages | `pip freeze` (chromadb 1.5.9, torch 2.14.1+cpu, sentence-transformers 6.1.0, transformers 5.19.0 at time of writing) |
| Host | `nproc`, `free -g`, GPU presence, load average at start |

### 2.2 Execution rules
- Run from repository root (Chroma path is CWD-relative, `chroma_store.py:8`).
- Single process, sequential questions, no other heavy workloads.
- One cold-start measurement: process start → all imports complete (model loads), plus first Ollama call.
- One warm-up question per model, excluded from statistics.
- **Full pipeline:** each question × 3 repeats with `PYTHONHASHSEED=0`.
- **Classification stability:** each question through `QueryUnderstanding.analyze` only, under `PYTHONHASHSEED ∈ {0,1,2,3,4}` (no generation; cheap).
- Results written to `benchmark_runs/<timestamp>/` (one JSON per run + summary). Never to `debug_runs/`.
- Generation failures (`ValueError` from `generator.py:490`) are recorded as outcomes with captured raw output — not retried, not skipped.

### 2.3 Estimated cost
20 full-pipeline questions × 3 repeats × ~1–5 min generation (CPU, 7B) ≈ 1–5 h. Classification stability pass: minutes.

---

## 3. Gold labeling protocol

For each question:
1. List all chunks of each gold PMC (`src/evaluation/find_chunk.py` / Chroma `get(where={"pmcid": …})`).
2. Grade each chunk: **2** = answer-bearing (directly states a required fact), **1** = supporting context, **0** = irrelevant. Chunks from non-gold PMCs found in runs are graded post-hoc when they appear in the final context.
3. Write **required facts** (L1: 2–5; L2: one per aspect) as short normalized statements plus a regex for automated matching; each fact references the grade-2 chunk(s) it is quoted from.
4. For each grade-2 chunk record the **answer-span offset** in whitespace-collapsed text (needed for the 1,200-char truncation check, `context_builder.py:52,92-98`).
5. Label expected **drug entities** (registry canonical names) for QU accuracy.
6. Second reviewer checks labels; disagreements resolved before the baseline run. Validate all gold IDs exist (`check_chunk_exists.py`).

---

## 4. Code-derived constraints that shape expectations

These follow from current code and determine what the ceiling of each metric is. They are not defects to fix here.

| Constraint | Source | Effect on benchmark |
|---|---|---|
| Max **2 chunks per PMCID** in final context, always | `reranker.py:158,247-268` | L1 gold-chunk recall ceiling = `min(1, 2/|grade-2 chunks|)` |
| `top_k` depends on **intent** only: FACT_LOOKUP 3, PROCEDURE/EXPLANATION/default 5, EVIDENCE/SUMMARY 6, COMPARISON/ANALYSIS/DECISION_SUPPORT 8 | `retrieval_strategy.py:15-76` | L2 PMC-coverage ceiling = `min(|gold PMCs|, top_k)`; minimum distinct PMCs in final = `ceil(top_k/2)` |
| Candidate pool ≤ `|queries| × retrieval_k`; queries = question + template expansions (only for registry drugs and 6 question types) | `retriever.py:69-84`, `query_understanding.py:1065-1116` | Expansion lift measurable only where expansions fire |
| Cross-encoder scores against the original question only | `retriever.py:166-167` | Expanded-query hits must also match the question to survive |
| Dedup on first 300 lowercased chars | `reranker.py:228-244` | Track as a loss reason |
| Evidence text truncated to 1,200 chars after whitespace collapse | `context_builder.py:52,92-98` | Answer span beyond offset 1,200 is invisible to the LLM |
| Abstracts and sections < 100 words are not indexed | `pmc_parser.py:215-225`, `section_chunker.py:26` | Gold facts must be chosen from indexed body chunks |

---

## 5. Level 1 — Single-paper retrieval

### Purpose
Measure whether the pipeline can locate and faithfully report a specific finding that lives primarily in one PMC article. Isolates retrieval precision and grounding without synthesis demands. Other PMCs that mention the same entity (e.g. `KEYNOTE-671` appears in 4 PMCs, `CheckMate 9ER` in 3 — counted by Chroma document scan) are graded as acceptable secondary evidence but not gold.

### Question set (candidates; gold PMC chosen from corpus titles, chunk-level gold pending §3)

| ID | Question | Gold PMC (indexed chunks) | Type exercised | Notes |
|---|---|---|---|---|
| L1-01 | Which EGFR mutation conferred osimertinib resistance in the syngeneic Egfr-mutant mouse model, and how did afatinib perform against it? | PMC13394164 (25) | RESISTANCE | `V804F` occurs in 1 PMC only |
| L1-02 | What bypass alterations were detected after osimertinib resistance in the lung adenocarcinoma case with acquired EML4-ALK fusion, and how was the patient treated? | PMC13508028 (11) | RESISTANCE / case | `EML4-ALK` in 1 PMC |
| L1-03 | What is the role of rebiopsy in EGFR-mutant NSCLC progressing on first-line osimertinib? | PMC13529361 (18) | GENERAL / FACT_LOOKUP | Reuses existing gold chunks in `retrieval_eval.py:36-48` |
| L1-04 | Which pathway is implicated in osimertinib-induced cardiotoxicity? | PMC13368672 (32) | SAFETY / MECHANISM | |
| L1-05 | What outcomes were reported for perioperative pembrolizumab in Japanese participants of KEYNOTE-671? | PMC13595008 (21) | CLINICAL_TRIAL | 3 distractor PMCs mention KEYNOTE-671 |
| L1-06 | What did the final analysis of CheckMate 9ER report for nivolumab plus cabozantinib in advanced renal cell carcinoma? | PMC12522107 (13) | CLINICAL_TRIAL / EFFICACY | 2 distractor PMCs |
| L1-07 | Are anti-adalimumab antibodies associated with loss of response in juvenile idiopathic arthritis? | PMC13273996 (6) | BIOMARKER | Small paper |
| L1-08 | What effect did semaglutide 2.4 mg have on energy intake and appetite over 60 weeks? | PMC13494093 (23) | EFFICACY | |
| L1-09 | How do PDGFRA exon 18 mutations differ in sensitivity to imatinib and avapritinib in GIST? | PMC13333789 (43) | BIOMARKER / COMPARISON | `avapritinib` not in registry |
| L1-10 | How does SPEN inactivation drive resistance to androgen receptor pathway inhibitors in prostate cancer? | PMC13563593 (30) | RESISTANCE / MECHANISM | Fact regex must avoid substring "SPEN" (matches "suspension"; 117 PMCs) |
| L1-11 | How do discontinuation rates unrelated to progression look with trastuzumab deruxtecan in metastatic breast cancer in real-world use? | PMC13564716 (13) | SAFETY | Registry detects `trastuzumab` |
| L1-12 | How did pembrolizumab compare with nivolumab as initial treatment for advanced melanoma? | PMC13624871 (7) | COMPARISON (single source) | Exercises COMPARISON profile with one paper |
| L1-C1 | What is the mechanism of action of teprotumumab? | none (0 chunks contain the term) | Negative control, out-of-registry | Expected abstention |
| L1-C2 | What is the efficacy of imatinib in asthma? | none (0 chunks contain both terms) | Negative control, in-registry drug | Expected abstention |

Coverage check: all 8 registry drugs appear; question types RESISTANCE, SAFETY, MECHANISM, CLINICAL_TRIAL, EFFICACY, BIOMARKER, COMPARISON, general; includes known classifier edge cases (L1-01/L1-10 phrasing vs. finding #2; L1-03 low-confidence path).

### Expected retrieval behavior
1. Gold PMC appears in the candidate pool from the original-question query alone.
2. After reranking, a grade-2 gold chunk is evidence block **E1 or E2**.
3. Final context contains **≤ 2** gold chunks (hard cap); remaining slots come from other PMCs.
4. The answer-bearing span of the top gold chunk lies within the first 1,200 chars.
5. Controls: no chunk mentions the entity/topic pair; the answer either states "Not established in the supplied evidence." without claims about the absent entity, or validation fails — both are recorded; any substantive claim about the absent entity is a hallucination.

### Metrics
| Group | Metric | Definition |
|---|---|---|
| QU | Path | fast path vs LLM fallback |
| QU | Stability | share of 5 hash seeds yielding the modal `question_type` and `intent` |
| QU | Drug entity accuracy | exact match of `entities.DRUG` to labeled set |
| QU | Strategy | resulting `retrieval_k`, `top_k` |
| Dense retrieval | Gold-PMC hit@pool | gold PMC present in merged pool |
| Dense retrieval | Best dense rank | min rank of any grade-2 chunk across all queries; per-query ranks stored |
| Dense retrieval | Expansion lift | grade-2 chunks reached only via expanded queries |
| Rerank | CE rank | rank of first grade-2 chunk in full cross-encoder order; MRR |
| Rerank | Loss attribution | for each pooled grade-2 chunk absent from final: `below_cutoff` / `dedup` / `source_cap` (derived by replaying reranker stages on captured scores) |
| Context | Gold@1, Gold@2 | E1 / E1–E2 from gold PMC |
| Context | Gold chunk recall@final | grade-2 chunks in final ÷ min(2, grade-2 count) |
| Context | Precision@final | final chunks graded ≥1 ÷ top_k |
| Context | Span survival | answer span offset < 1,200 |
| Context | Size | context chars; prompt chars and words |
| Generation | Validation outcome | `pass_first` / `pass_after_prune` / `fail` + error categories from `validate_answer` |
| Generation | Prune loss | non-empty lines in raw output vs final answer |
| Generation | Fact recall | required facts matched ÷ required facts |
| Generation | Citation precision | manual: cited block supports the sentence (supported / partial / unsupported) |
| Generation | Unsupported claims | count of factual sentences whose citations do not support them |
| Generation | Structure adherence | expected profile headings present (`generator.py:28-80`) |
| Generation | Abstention correctness | controls only |
| Variance | Run-to-run | SD of fact recall; Jaccard of cited chunk IDs across 3 repeats |
| System | Latency | QU, embed, Chroma query, rerank, context, generation, total; p50/p90 |
| System | Memory | peak RSS of harness process (`resource.getrusage`), Ollama runner RSS (`/proc`) |

### Success criteria (proposed, pending owner sign-off)
Per question (all must hold, majority of 3 repeats):
- Gold@2 = true
- Validation outcome ≠ `fail`
- Fact recall ≥ 0.8
- Unsupported claims = 0
Controls: no claim about the absent entity in any repeat.
Suite level: ≥ 10/12 answerable questions pass; 2/2 controls pass; QU stability = 1.0 on all questions.

---

## 6. Level 2 — Multi-paper synthesis

### Purpose
Measure whether the pipeline gathers complementary evidence from several PMCs and synthesizes it with correct attribution. Stresses candidate-pool breadth, reranker diversity, the `top_k`/source-cap budget, context size, and the 7B model's ability to use all evidence blocks.

### Question set (candidates; aspects and gold PMCs from corpus titles, chunk-level gold pending §3)

| ID | Question | Aspects → gold PMCs | Type exercised |
|---|---|---|---|
| L2-01 | What resistance mechanisms emerge after first-line osimertinib? | on-target EGFR mutations (PMC13530993, PMC13585410, PMC13563458); bypass fusions/BRAF (PMC13508028, PMC13579456); histologic transformation (PMC13479129, PMC13508615); non-genetic/adaptive (PMC13478582, PMC13520340); real-world rebiopsy findings (PMC13529361) | RESISTANCE; primary benchmark question; known tie case |
| L2-02 | How do outcomes compare between afatinib and osimertinib in EGFR-mutant NSCLC, including uncommon mutations? | first-line OS (PMC13427999); uncommon mutations RWE (PMC13394325, PMC13573738); network comparison (PMC13574751) | COMPARISON |
| L2-03 | What immune-related adverse events have been reported with nivolumab alone or combined with ipilimumab? | liver injury (PMC13600002); thyroid dysfunction (PMC13597272); pneumonitis (PMC13605366); ocular (PMC13583422); renal (PMC13612749) | SAFETY |
| L2-04 | What mechanisms drive resistance to enzalutamide in prostate cancer? | ferroptosis suppression (PMC13394060, PMC13480344); SPEN loss (PMC13563593); lineage plasticity / neuroendocrine (PMC13466754, PMC13447160); lipid/metabolic (PMC13568755, PMC13478015); liquid biopsy predictor (PMC13562513) | RESISTANCE |
| L2-05 | How do abiraterone and enzalutamide compare in efficacy and safety for metastatic prostate cancer? | mCSPC outcomes (PMC13405643); mCRPC efficacy/safety (PMC13427783); falls (PMC13374230); hepatotoxicity (PMC13488195) | COMPARISON |
| L2-06 | How are adalimumab drug levels and anti-drug antibodies related to clinical response? | JIA loss of response (PMC13273996); dosing schedule & ADA (PMC13337933); paediatric uveitis levels (PMC13415550); uveitis cohort (PMC13429708) | BIOMARKER |
| L2-07 | What is the evidence for semaglutide in MASLD/MASH? | mechanisms/metabolites (PMC13515630); clinical reviews (PMC13572791, PMC13575885); fibrosis agonist classes (PMC13589479); preclinical HCC (PMC13588371) | EFFICACY / MECHANISM |
| L2-08 | What safety risks are associated with trastuzumab deruxtecan? | ILD/cardiotoxicity (PMC13609577); discontinuation RWE (PMC13564716); AE management (PMC13537819); pharmacovigilance signals (PMC13597761); ADC network meta-analysis (PMC13494281) | SAFETY |

### Expected retrieval behavior
1. Candidate pool contains chunks from ≥ 1 gold PMC per aspect.
2. Final context draws from multiple PMCs: distinct PMCs ≥ `ceil(top_k/2)` (guaranteed by cap) and ideally one per aspect up to `top_k`.
3. Aspect coverage limited by `top_k`; for intents mapping to `top_k = 5` with 5 aspects, every slot must cover a distinct aspect to reach full coverage.
4. Answer cites ≥ 2 distinct PMCs and attributes each finding to the block that states it.
5. Comparison questions (L2-02, L2-05) select the COMPARISON profile and distinguish head-to-head from indirect evidence (`generator.py:54-71`).

### Metrics
All Level 1 metrics, plus:
| Group | Metric | Definition |
|---|---|---|
| Dense retrieval | Aspect recall@pool | aspects with ≥ 1 grade-2 chunk in pool ÷ aspects |
| Dense retrieval | Gold-PMC recall@pool | gold PMCs in pool ÷ gold PMCs |
| Context | Aspect coverage@final | aspects with ≥ 1 grade-2 chunk in final ÷ aspects |
| Context | Normalized PMC coverage | gold PMCs in final ÷ min(gold PMCs, top_k) |
| Context | Source diversity | distinct PMCs in final; share of slots used by gold PMCs |
| Context | Slot efficiency | aspects covered ÷ top_k |
| Generation | Aspect recall in answer | aspects with a matched fact in the answer |
| Generation | Evidence utilization | distinct E# cited ÷ evidence blocks supplied; cited distinct PMCs |
| Generation | Position bias | fact recall for facts sourced from E1–E2 vs E(n-1)–En |
| Generation | Attribution accuracy | manual: per fact, cited block is a block that states it |
| Generation | Comparison validity | L2-02/L2-05: indirect comparisons not presented as head-to-head (manual) |

### Success criteria (proposed, pending owner sign-off)
Per question (majority of 3 repeats):
- Aspect coverage@final ≥ 0.6
- Normalized PMC coverage ≥ 0.6
- Validation outcome ≠ `fail`
- Aspect recall in answer ≥ 0.6
- Cited distinct PMCs ≥ 2
- Unsupported claims = 0
Suite level: ≥ 6/8 questions pass; QU stability = 1.0.

---

## 7. Reporting

Per run JSON: fingerprint, question ID, repeat, `PYTHONHASHSEED`, full `query_info`, strategy, per-query dense results (IDs, distances), pool, full CE order, final chunks with scores, context, prompt length, raw LLM output, final answer or error, all metrics, stage timings, memory.

Summary report:
1. Stage funnel per level: hit@pool → CE rank → final → span survival → fact in answer (shows where evidence is lost).
2. Loss attribution totals (`below_cutoff` / `dedup` / `source_cap` / `truncation` / `generation_omission` / `validation_prune`).
3. Classification stability table (question × seed).
4. Latency and memory distributions; cold-start cost.
5. Pass/fail against proposed criteria, with per-criterion breakdown.
6. Manual review sheet (citation precision, attribution, comparison validity) with reviewer IDs.

---

## 8. Decisions needed before implementation

| # | Decision | Default if not specified |
|---|---|---|
| 1 | Approve question set or substitute questions | Use §5/§6 as listed |
| 2 | Who labels gold chunks and reviews (SME vs engineer) | Engineer labels, second engineer reviews |
| 3 | Manual review scope for citation precision | All L1 + L2 answers of repeat 1 |
| 4 | Approve proposed success thresholds | Record baseline without pass/fail gating |
| 5 | Harness location | `src/evaluation/baseline_benchmark.py` + `src/evaluation/benchmark_questions.json`, outputs in `benchmark_runs/` (add to `.gitignore`) |

---

## 9. Harness usage (implemented 2026-10-15)

Code in `src/evaluation/`; outputs in `benchmark_runs/` (git-ignored).

| File | Role |
|---|---|
| `benchmark_questions.json` | Question definitions: gold papers, graded gold chunks, fact regexes, L2 aspects, controls, `review_status` |
| `label_tools.py` | Gold labeling: `list`, `show`, `find`, `validate` |
| `run_benchmark.py` | Runner (CLI) |
| `harness.py` | Drives `app.main()` with scripted `input()`; in-process wrappers capture telemetry; rerank replay |
| `scoring.py` | Per-run metrics, pass evaluation, level aggregates |
| `report.py` | `scores.json` + `summary.md` |

**Execution-path fidelity.** The runner imports `app` and calls `app.main()` unchanged. Wrappers observe `QueryUnderstanding`, `StrategyManager`, `retriever.embed_query/collection.query/rerank_chunks`, `app.build_context`, `QwenGenerator.generate/validate_answer`, and `ollama run`. Deviations from production, all observational:
- `ollama run` receives `--verbose` (token/timing stats on stderr; disable with `--no-ollama-verbose`).
- `app.save_debug_run` is replaced by in-memory capture; nothing is written to `debug_runs/`.
- Opt-in experiment controls only: `--retrieval-only` (skips the Qwen call), `--strategy-override R:K`, `--no-expansions`.

**Labeling workflow (single labeler).**
```
python src/evaluation/label_tools.py list PMC13564716                 # chunks, sections, sizes
python src/evaluation/label_tools.py show PMC13564716_0005            # text; marks the 1,200-char cut
python src/evaluation/label_tools.py find PMC13564716 '82\.8\s*%'     # offsets; visible vs CUT
python src/evaluation/label_tools.py validate                         # schema + patterns match evidence
```
Edit `benchmark_questions.json`: grade chunks (`2` answer-bearing, `1` supporting), add facts (`pattern`, `evidence_chunks`), set `review_status` to `verified`. The 27 entries shipped are drafts derived from corpus reading.

**Runs.**
```
# Level 0, production path, no generation
python src/evaluation/run_benchmark.py --retrieval-only --repeats 1
# Level 0, fixed strategy, no expansions
python src/evaluation/run_benchmark.py --retrieval-only --repeats 1 --strategy-override 60:8 --no-expansions --label fixed
# Query-understanding stability across hash seeds
python src/evaluation/run_benchmark.py --qu-stability 0,1,2,3,4
# Level 1 / Level 2 baseline (3 repeats, warm-up excluded)
python src/evaluation/run_benchmark.py --level 1
python src/evaluation/run_benchmark.py --level 2
# Only verified questions
python src/evaluation/run_benchmark.py --status verified
```
The runner re-executes itself with `PYTHONHASHSEED=--seed` (default 0) and runs from the repository root.

**Outputs per run** (`benchmark_runs/<timestamp>_<mode>_<label>/`): `fingerprint.json`, `records/<id>__r<n>.json` (full telemetry incl. prompt, raw Qwen output, per-query dense results, CE replay with loss reasons), `app_stdout.log`, `scores.json`, `summary.md`.

**Not captured:** time-to-first-token (app does not stream); manual unsupported-claim review (`manual_review` field left `null`).
