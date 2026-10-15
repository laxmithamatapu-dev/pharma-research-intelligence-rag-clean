# System Assessment — Product, Architecture, Engineering (2026-10-15)

Perspective: long-term technical owner of an evidence-grounded pharma research assistant on an 8 vCPU / 16 GB / CPU-only Azure VM.
Principle: moderate latency is acceptable; correctness and evidence grounding are not negotiable.
Evidence base: [PROJECT_HANDBOOK.md](PROJECT_HANDBOOK.md), [ENGINEERING_ASSESSMENT.md](ENGINEERING_ASSESSMENT.md), [RETRIEVAL_BASELINE_REPORT.md](RETRIEVAL_BASELINE_REPORT.md), [RETRIEVAL_RCA.md](RETRIEVAL_RCA.md), benchmark runs under `benchmark_runs/`, and new corpus inspection for this document.

---

## Verdict

**The architecture has the right shape for an evidence-grounded assistant; the evidence it delivers is not yet good enough, and answer correctness has not been measured.**
- Shape: local stack, registry-grounded entities, mandatory `[E#]` citations, rule-based validation, per-run artifacts, and now a production-path benchmark harness.
- Gap: only **48 % of expected facts reach Qwen** (L1). One proven post-processing defect can strip claims while keeping their citations. Classification, which sets how much evidence is retrieved, is non-deterministic for 11/27 questions.
- Direction: moving toward production readiness *as a measurable system*; not yet production-ready as a *correct* system.

---

## 1. Biggest strengths (evidence-backed)

| Strength | Evidence |
|---|---|
| Paper-level retrieval is strong | Correct paper reaches Qwen for 15/16 L1 questions in all 5 seeds; L1 gold papers within top-20 dense results for 94 % |
| Citation discipline is enforced in code, not only requested | `validate_answer` + `_retain_cited_claims` (`generator.py`); 4/4 generation runs passed validation |
| Deterministic grounding of entities and expansions | Registry-based; LLM expansions discarded (`query_understanding.py:1256-1257`) |
| Index is reproducible from source | E5: 307 chunks rebuilt with identical text and vectors |
| Retrieval stack is cheap | Embed + Chroma ≤ 0.3 s; rerank 1.3–6.2 s; 224 MB vector DB |
| Cross-encoder recognizes relevant findings when they reach it | 3/11 lost answer chunks would rank **first** if pooled |
| Measurement capability exists | Harness drives `app.main()` unchanged; replay reproduces reranker selection 135/135 |
| Fully local; resource headroom for current corpus | 16 GB RAM: Qwen 7B runner ~5.1 GB + app ~1.6 GB |

## 2. Biggest weaknesses

| Weakness | Dimension | Evidence |
|---|---|---|
| Passage retrieval misses the findings | Evidence / retrieval quality | 29 % of labeled answer chunks and 48 % of expected facts reach Qwen; Results chunks are 27 % of the corpus but 14 % of candidates |
| Within-paper selection prefers summary prose over results | Evidence quality | Answer chunk outranked inside its own paper in 35/44 observations, mostly by Discussion |
| Pruning can corrupt answers while keeping citations | Answer correctness | `ollama run` hard-wraps output; line-based pruning would reduce a claim to "cohort study [E1]" (replayed on real output) |
| Validator over-rejects | Answer availability | Substring forbidden phrases ("likely" ⊂ "unlikely"); pruning deletes the required "Not established…" lines |
| Evidence budget depends on phrasing and is non-deterministic | Evidence quality, reproducibility | top_k 3–8 from intent; 11/27 questions unstable; fallback model varies at fixed seed |
| No relevance floor | Correctness on out-of-corpus questions | Controls receive 3–5 unrelated chunks |
| Answer correctness unmeasured | Answer quality | No faithfulness or fact-recall numbers on generation yet |
| Latency dominated by CPU decode; no length control | Latency | 6–7 tok/s; 400–540 answer tokens; no `num_predict` |
| Cold-start fragility | Infrastructure | 119 s model load and 83 s app import after reboot; startup contacts Hugging Face Hub |
| Prompt near context limit | Generation reliability | 3,686 / 4,096 tokens at top_k 8 |
| Maintainability debt | Engineering | ~1/3 of `src/` unused; unpinned deps; tests without assertions; CWD-relative Chroma path |

## 3. Ranked problems

Ranked by impact on correct, grounded answers; latency considered only as a constraint.

| Rank | Problem | Why it ranks here | Confidence |
|---|---|---|---|
| 1 | **Findings-bearing passages do not reach Qwen** (dense retrieval context/register mismatch + reranker preference + 2-per-paper cap) | Upper bound on answer quality; half of expected facts unavailable | High (measured), mechanism medium-high |
| 2 | **Pruning × word-wrap corrupts cited claims** | Silent correctness failure that passes validation | Mechanism proven; frequency unmeasured |
| 3 | **Answer correctness is unmeasured** | Cannot claim quality without it; blocks every generation decision | Proven gap |
| 4 | **Non-deterministic evidence budget** (hash ties + LLM fallback) | Same question, different evidence, different answer; undermines trust and benchmarking | Proven |
| 5 | **No abstention path for out-of-corpus questions** | Hallucination risk with unrelated evidence | Retrieval behavior proven; generation behavior unmeasured |
| 6 | **Validator over-rejection** | Answers lost or degraded; frequency unknown | Mechanism proven |
| 7 | **Context headroom 10 %** | Raising evidence volume to fix #1 will hit the 4K window | Proven |
| 8 | **Cold start and runtime fragility** (no keep-warm, network at boot, no timeout) | Operational, latency | Proven |
| 9 | **Latency 80–140 s warm** | Acceptable per product stance; second-order | Proven |
| 10 | **Maintainability debt** | Slows every change | Proven |

## 4. Proven facts / assumptions / open questions

**Proven**
1. Generation is 78–141 s warm; decode is 62–75 % of it at 6–7 tok/s; retrieval + rerank ≤ 6.3 s.
2. Ollama runs with `n_ctx 4096`, 4 threads, no options from code; cold loads after reboot ≈ 38 MB/s from disk.
3. L1: paper reaches Qwen 94 %; facts 48 %; answer chunks 29 %. L2: gold papers delivered 34 %, pooled-but-cut 36 %, never retrieved 30 %.
4. Lost answer chunks: not retrieved 56 %, 2-per-paper 15 %; reranked-out, dedup, truncation 0 % in the current question set.
5. Index construction is correct (E5). Truncation of embedding input, distance metric, and caption noise are not causes.
6. Lost chunks are retrievable with content-matched queries (oracle 8/11). Results skew disappears with results-style queries.
7. Embedding a lost chunk with its paper title brings 10/11 within range (asymmetric upper bound).
8. MedCPT is used with mean pooling and no title; its model card specifies CLS pooling and `[title, abstract]` input.
9. `ollama run` wraps output; pruning is line-based; replay shows claim fragments deleted.
10. Classification instability: 5 hash-tie questions (seed-controllable), 6 LLM-fallback questions (not controllable by seed).
11. Fact-pattern hazards exist (L1-14 matched primary-analysis numbers).

**Assumptions (not yet tested)**
- Delivering Results chunks will improve answer correctness (not just fact visibility).
- Title-context embedding helps net of competitors (E2a pending).
- A biomedical-domain reranker would not share the ms-marco Discussion preference.
- Qwen 2.5 7B uses lower-ranked evidence blocks faithfully.
- Answer templates drive answer length.
- More threads or different quantization would improve decode rate.

**Open questions**
- How often does pruning fire in practice, and how often does validation fail outright?
- What do answers say for out-of-corpus questions?
- What fraction of the corpus is abstract-only or short-section content that is not indexed?
- How does quality scale with more evidence blocks given the 4K window?
- Do the conclusions hold beyond 25 answerable benchmark questions?

---

## 5. What to investigate next and immediate priority

**Immediate priority: retrieval, with two correctness defects addressed alongside because they corrupt both answers and measurements.**
- *Retrieval* is the binding constraint on quality: no generation improvement can recover facts Qwen never receives (52 % of expected facts).
- *Correctness defects* (wrap-prune, non-deterministic budget) are cheap to resolve and distort every later measurement.
- *Generation*: measure, do not optimize. Run the targeted generation benchmark on retrieval-clean questions to get the first correctness and faithfulness numbers.
- *Infrastructure*: only the operational items that affect reliability (warm model, offline start, timeout); throughput tuning later.

Next investigations, in order:
1. **E2a**: title-context corpus re-embedding (side file, ~24 min), scored through reranker replay and fact visibility.
2. **Targeted generation run**: L1-05, L1-07, L1-08, L1-12, L1-16 + controls + new truncation questions (N1, N4, N5, N6), 1 repeat, warm-up on (~30 min): fact recall, grounding, prune rate, abstention.
3. **Reranker comparison offline**: replay stored pools with an alternative biomedical cross-encoder (e.g. `ncbi/MedCPT-Cross-Encoder`) vs current; within-paper answer-chunk rank and fact visibility. No pipeline change.
4. **Fixed-strategy retrieval run** (`--strategy-override 60:8 --no-expansions`, ~3 min): budget effect on L2.
5. **Coverage audit** (read-only): fraction of article text not indexed (abstracts, short sections) and boilerplate share of delivered chunks.

---

## 6. Representative benchmark questions from the indexed corpus

The existing 27 questions (in `src/evaluation/benchmark_questions.json`) concentrate on oncology efficacy, resistance, and mechanism. The questions below fill categories with **no current coverage**: pharmacokinetics and drug interaction, pediatric safety, inflammatory biomarker time course, renal outcomes, dosing time, real-world molecular response, real-world toxicity, pharmacovigilance. All papers are indexed; answer chunks and offsets were read directly with `label_tools.py`. Four questions place the key fact **beyond the 1,200-character context cut**, which the current set does not test.

### Level 1 (single paper)
| ID | Question | Paper → answer chunk (fact offset) | Expected facts | Why useful | Component tested |
|---|---|---|---|---|---|
| N1 | Does co-administration with savolitinib alter osimertinib exposure, and was combination treatment a covariate on savolitinib clearance? | PMC13504015 → _0012 (@1,826 **cut**), _0008 (@1,309 **cut**) | Osimertinib exposure not altered; combination tested as covariate on CL/F | PK/DDI category; fact beyond truncation in both chunks | Context truncation, PK retrieval |
| N2 | Is the risk of serious infection different between infliximab and adalimumab in children with inflammatory bowel disease? | PMC13355144 → _0013 (@192) | Pooled HR 1.15 (95 % CI 0.63–2.11); infliximab IR 29/1,000 PY | Pediatric comparative safety in one paper; null result | Safety extraction, null-result faithfulness |
| N3 | How quickly did semaglutide lower hsCRP in the SELECT trial? | PMC13574348 → _0009 (@760) | −12 % by 4 weeks, −19 % by 8 weeks | Biomarker time course; non-oncology | Numeric grounding |
| N4 | Was semaglutide associated with lower kidney-outcome risk in adults with ADPKD? | PMC13519180 → _0013 (@2,321 **cut**) / _0014 (@385, overlap) | HR 0.447 (0.230–0.872); ESKD HR 0.675, not significant | Same fact cut in one chunk, visible in the overlapping next chunk | Chunk overlap vs truncation, 2-per-paper |
| N5 | Does morning versus evening imatinib intake affect progression-free survival in metastatic GIST? | PMC13310552 → _0006 (61.5 @1,194; 26.2 @1,252 **cut**) | Median PFS 61.5 vs 26.2 months; p = 0.22 (not significant) | Fact split across the cut; small paper (9 chunks) | Truncation, null-result faithfulness |
| N6 | What proportion of patients achieved a favorable molecular response at 12 months on first-line imatinib in the southern Morocco CML cohort? | PMC13508003 → _0004 (@2,160 **cut**) | 40/80 (50.0 %) with BCR::ABL1 ≤ 1 % IS | Real-world response; fact deep in chunk | Truncation, RWE retrieval |
| N7 | Which immune-related adverse events were most common during adjuvant pembrolizumab in the real-world early triple-negative breast cancer cohort? | PMC13605040 → _0005 (early) | Hypothyroidism 11.8 %, colitis/diarrhea 7.4 %, dermatitis 7.4 %, neurotoxicity 4.4 % | Real-world vs trial safety contrast | Safety enumeration |
| N8 | Which androgen receptor pathway inhibitor showed the strongest interstitial pneumonia signal in FAERS? | PMC13541453 → _0011 (@192) | Darolutamide ROR 7.30 (5.46–9.76), then apalutamide 5.39; enzalutamide below threshold in one analysis | Pharmacovigilance methodology; ranking question | Comparative extraction within one paper |

### Level 2 (multi-paper)
| ID | Question | Expected papers (aspects) | Why useful | Component tested |
|---|---|---|---|---|
| M1 | What safety signals have pharmacovigilance (FAERS/JADER) analyses identified for the cancer therapies in this corpus? | ARPI pneumonitis PMC13541453 · ICI thyroid PMC13597272 · cachexia PMC13593894 · zolbetuximab PMC13601259 · EGFR-TKI skin PMC13506688 · ARPI CNS PMC13516075 | Retrieval by study *method* across drugs | Diversity, method-level retrieval, top_k budget |
| M2 | What evidence supports cardiometabolic, inflammatory or renal benefits of semaglutide beyond glucose lowering? | hsCRP PMC13574348 · HIV CV risk PMC13573316 · thromboinflammation PMC13565109 · ADPKD kidney PMC13519180 · HFpEF PMC13564011 | Trial + RWE + review mix in non-oncology area | Evidence-type weighting, synthesis |
| M3 | How do imatinib and later-generation TKIs compare for frontline chronic myeloid leukemia across efficacy, safety and cost? | RWE PMC13508003 · frontline choice PMC13492314 · cost PMC13357042 · asciminib trial PMC13291802 · MAIC PMC13461844 · 25-year review PMC13233626 | Registry drug vs non-registry comparators; multiple evidence dimensions | Comparison profile, grounding of non-registry drugs |
| M4 | What is known about the safety and effectiveness of adalimumab and other biologics in pediatric inflammatory disease? | IBD infections PMC13355144 · uveitis vs methotrexate PMC13430079 · uveitis drug levels PMC13415550 · UK access PMC13401782 · post-HSCT JIA PMC13010185 | Population-defined synthesis | Population-level retrieval, aspect coverage |

Not yet added to `benchmark_questions.json`; gold chunks and fact patterns follow the existing labeling workflow (`label_tools.py find/validate`).

---

## 7. Roadmap

Each item lists why it matters, the evidence behind it, how success is verified with the existing harness, and the latency/resource effect on 8 vCPU CPU-only.

### Phase 1 — Critical correctness (days)
| Item | Why | Evidence | Verified by | Latency / resource |
|---|---|---|---|---|
| 1.1 Remove output wrapping from the generation path and make pruning sentence-aware | Pruning can delete claim text and keep the citation | Wrap proven; replay on real answer | Re-score stored raw outputs; prune events no longer produce citation-only fragments | None |
| 1.2 Correct validator false rejections (word-boundary matching; keep "Not established…" lines) | Answers lost or degraded | Code reading; substring rule | Validation outcome distribution on L1/L2 runs | None |
| 1.3 Make the evidence budget deterministic (deterministic tie-break; fallback at temperature 0 / fixed seed, or not allowed to change top_k) | Same question → different evidence | 11/27 unstable; fallback varies at fixed seed | QU stability = 1.0 across seeds and repeats | QU fallback unchanged (4–11 s) |
| 1.4 Explicit Ollama options and timeout (`num_ctx`, `seed`, `temperature`, timeout) | Reproducibility; context headroom 10 % at top_k 8 | No options in code; 3,686/4,096 tokens | Fingerprint shows options; no context overflow | `num_ctx 8192` adds KV memory (~224 MB per 4K, measured) |
| 1.5 Measure, then define abstention for out-of-corpus questions | Hallucination risk | Controls receive unrelated chunks | Control questions: zero cited claims about absent entity | None until a relevance floor is chosen |
| 1.6 First generation-quality baseline (targeted run) | No correctness numbers exist | — | Fact recall, grounding, prune rate, abstention | ~30 min run |

### Phase 2 — Retrieval (1–3 weeks, gated by measurements)
| Item | Why | Evidence | Verified by | Latency / resource |
|---|---|---|---|---|
| 2.1 E2a: title-context embeddings, symmetric | Largest evidence loss (39 % of facts) | E1 (10/11 upper bound), E3 | Recall@k, fact visibility via replay vs baseline | Query-time none; re-index ~24 min CPU |
| 2.2 Within-paper selection: per-paper limit and reranker register | 13 % of facts; gates any retrieval gain | E6 (cap 3 → 40/44); 35/44 outranked by Discussion | Counterfactual replay, then harness run | Each extra delivered chunk ≈ +250 prompt tokens ≈ +4 s prefill |
| 2.3 Evaluate a biomedical cross-encoder offline | Discussion preference may be model-specific | Hypothesis H-R4 | Replay stored pools; within-paper rank of answer chunks | CE cost scales ~0.07 s per candidate (measured 20 → 60 candidates) |
| 2.4 Decouple evidence budget from phrasing; deeper pools for synthesis | L2 papers 62 % at k 20 vs 87 % at k 60 | E4, baseline | L2 aspect coverage | Larger pools: rerank +2–3 s |
| 2.5 Index coverage: abstracts, short sections; exclude boilerplate | Lost content; noise in pool | Short sections dropped; 100+ boilerplate chunks | Coverage audit; fact visibility | Small index growth |
| 2.6 Section metadata accuracy (or stop presenting it to Qwen) | Noisy "Evidence Type" in every block | Introduction → `clinical_trial` | Label precision sample | None |

### Phase 3 — Generation (after Phase 2 delivers better evidence)
| Item | Why | Evidence | Verified by | Latency / resource |
|---|---|---|---|---|
| 3.1 Full L1/L2 generation baseline, 3 repeats | Quality reference for all changes | — | Harness | ~3–4 h per run |
| 3.2 Answer-length policy per profile (after quality baseline) | Decode dominates latency | 62–75 % decode; no cap | Fact recall unchanged at shorter length | −30 to −60 s if answers shrink 200–300 tokens |
| 3.3 Prompt economy (drop non-evidence JSON, noisy metadata) | ~1.1 K fixed prompt tokens | Inferred by difference; G1 pending | G1 token accounting | −10 to −18 s prefill (estimate) |
| 3.4 Evidence-use checks (position bias, unused blocks) | 7B models may ignore later blocks | Hypothesis H6 | L2 evidence utilization | None |
| 3.5 Streaming to the user | Perceived latency, not correctness | No streaming today | Time to first token | None |
| 3.6 Model evaluation (alternative 7–8B instruct, quantization) | Only after quality baseline exists | — | Same benchmark | RAM ≤ ~6 GB per model |

### Phase 4 — Infrastructure (ongoing; reliability items earlier)
| Item | Why | Evidence | Verified by | Latency / resource |
|---|---|---|---|---|
| 4.1 Long-running service with warm models (preload at boot, keep-alive) | 119 s cold load; 83 s import | Observed after reboot | Load duration ≈ 0 on first request | Holds ~5 GB RAM permanently |
| 4.2 Offline model loading; absolute data paths; pinned dependencies | Network at boot; CWD-relative Chroma; reproducibility | HF warning; `chroma_store.py:8` | Start without network; fingerprint stable | None |
| 4.3 Thread and context characterization (G5/G6) | Decode bound on 4 cores | 4 threads of 8 vCPU | Tokens/s per setting | Measurement only |
| 4.4 Disk hygiene (71 % used; venv 5.8 GB; backups) | Re-indexing needs headroom | `df` | Free space before re-embedding | — |
| 4.5 In-app telemetry (token counts, prune events, failures) | Production visibility | Missing telemetry list | Artifacts contain them | None |
| 4.6 Maintainability: remove dead code, convert benchmark checks into tests | Change safety | ~1/3 `src/` unused | CI-style test run | None |

**Capacity note.** At ~20 KB per chunk in Chroma and ~3.2 KB of HNSW per chunk, a 10× corpus (~110 K chunks) is ~2.2 GB on disk and ~360 MB of HNSW. Retrieval stays sub-second. Re-embedding takes ~4 h on this CPU. The LLM, not the corpus, remains the capacity constraint.
