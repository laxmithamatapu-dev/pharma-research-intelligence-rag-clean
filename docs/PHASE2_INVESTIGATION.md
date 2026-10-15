# Phase 2 — Evidence Review, Benchmark Strategy, Corpus-Derived Questions, Roadmap

Date: 2026-10-14. Code baseline: `bdc559e` + staged print-only diff in `generator.py`. No code changed.
This document supersedes the question set in [BENCHMARK_PLAN.md](BENCHMARK_PLAN.md); the run protocol, labeling protocol, and instrumentation method there remain valid.

Evidence used:
- **E-GEN**: generation probe, 3 questions × 1 run, `PYTHONHASHSEED=0` ([ENGINEERING_ASSESSMENT.md](ENGINEERING_ASSESSMENT.md) §6).
- **E-L0**: preliminary retrieval-only pass run today: 27 questions × 1 run, `PYTHONHASHSEED=0`, production call path, gold judged at **paper level from titles** (not chunk-graded). Directional only; not a baseline.
- **E-CORPUS**: direct inspection of Chroma documents, section paths, and source XML.
- Historical `debug_runs/` are not used.

---

## 1. Evidence review

### 1.1 Conclusively proven (reproducible, measured or read directly from code/config)
| # | Finding | Evidence |
|---|---|---|
| P1 | Generation dominates latency: 78–141 s vs ≤ 4.1 s for all other stages combined | E-GEN |
| P2 | Decode = 62–75 % of generation time at 6.1–6.9 tok/s; answers 403–536 tokens | E-GEN (`ollama run --verbose`) |
| P3 | Prefill = 25–38 % at 56–64 tok/s; prompts 1.4 K tokens (3 chunks) to 3.2 K (8 chunks) | E-GEN |
| P4 | Both rates fall as context grows | E-GEN |
| P5 | Ollama serves with `n_ctx 4096`, 4 threads of 8 vCPU, AMX + flash attention; code sets no options; no timeout, no streaming | server log, `generator.py:449`, grep |
| P6 | Number of chunks reaching Qwen (top_k) is set only by **intent**, which is derived from phrasing | `retrieval_strategy.py`, `app.py:143-154` |
| P7 | Intent assignments in E-L0 do not track question scope: 5 of 16 single-paper questions → COMPARISON (8 chunks); 4 of 9 multi-paper questions → FACT_LOOKUP (3 chunks) | E-L0 |
| P8 | For those 4 multi-paper questions, the candidate pool contained more gold papers than reached the context (e.g. L2-01: 7 of 11 in pool, 3 in final) | E-L0 |
| P9 | `question_type` is hash-seed dependent on score ties | handbook finding #1 (5 seeds reproduced) |
| P10 | Max 2 chunks per paper; 300-char dedup; CE scores against original question only; `diversity_boost` unused | `reranker.py` |
| P11 | 77.9 % of chunks exceed 1,200 chars and are truncated in context; answer text can lie beyond the cut (e.g. `AMPK` at char 1,436 in PMC13368672_0022) | E-CORPUS |
| P12 | Sections < 100 words and abstracts are not indexed (e.g. PMC13537402 "Trial design" 59 w, "Objectives" 62 w; PMC13449031 "3.3 Oncological Outcomes…" 85 w) | E-CORPUS, `section_chunker.py:26` |
| P13 | Boilerplate sections are indexed: Author Contributions 17 chunks, Conflict 24, Disclosure 12, Supplementary 12, Supporting information 16, Ethics 12 | E-CORPUS |
| P14 | Metadata shown to Qwen as "Evidence Type" is keyword-derived and noisy (e.g. "Introduction" → `clinical_trial`, "Conflict of interest" → `safety`) | E-CORPUS, `evidence_classifier.py`, `context_builder.py:73-79` |
| P15 | No relevance threshold: unanswerable control questions still deliver 3–5 unrelated chunks to Qwen | E-L0 (L1-C1, L1-C2) |
| P16 | Retrieval latency 1.3–6.2 s, scaling with pool size (20 → 105 candidates) | E-L0 |

### 1.2 Not yet proven
| # | Open question | Why unproven |
|---|---|---|
| U1 | Retrieval quality (chunk-level) | E-L0 is paper-level, single seed, unlabeled chunks |
| U2 | Reranker effectiveness | E-L0 shows both improvements (L1-09 dense 9 → CE 1) and regressions (L1-03 3 → 5; L2-06, L2-07 1 → 4); no graded relevance |
| U3 | Answer correctness and citation faithfulness | no gold facts scored; no manual review |
| U4 | Answer-length distribution by template/question type | n = 3 |
| U5 | Causes of > 150 s generations on current code | not reproduced |
| U6 | Thread-count sensitivity; bandwidth- vs compute-bound decode | not measured |
| U7 | Behavior when prompt + answer would exceed 4,096 tokens | not observed (max 3,686) |
| U8 | Cost of the QU LLM fallback and effect on 7b residency | not triggered in probes |
| U9 | Validation failure rate | failed runs leave no artifact |
| U10 | Whether MedCPT mean pooling + Chroma default distance is appropriate | model-card/recall comparison not done |
| U11 | Why dense retrieval missed PMC13537402 for L1-13 although "Yifeixiaoji" occurs in 2 indexed chunks (YFXJD in 7) | single observation |

### 1.3 Strong enough to justify investigation
- **Output length (P2):** the largest measured latency component; no limit in code.
- **Intent → top_k coupling (P6–P8):** directly determines prompt size *and* multi-paper coverage; measured mismatch on today's set.
- **Index content quality (P11–P14):** truncation, dropped short sections, boilerplate chunks, and noisy metadata all affect what evidence Qwen sees.
- **No relevance floor (P15):** affects hallucination risk on out-of-corpus questions.

### 1.4 Still hypotheses
| Hypothesis | Status |
|---|---|
| H1 Answer templates (3–6 required headings + References) inflate answer tokens | plausible from prompt text; unmeasured |
| H2 4 threads under-use the CPU | unmeasured; hyperthreads may not help |
| H3 Dense retrieval is weak on rare lexical terms (drug brand/TCM names, trial acronyms) | one observation (U11) |
| H4 CE ms-marco model under-ranks biomedical results sections vs discussion/introduction | top-1 chunks in E-L0 are often Discussion/Introduction (e.g. L1-01 top-1 = PMC13564716_0009 Discussion while numbers are in 0005 Results); not graded |
| H5 Per-paper cap of 2 limits single-paper answers | proven as a cap (P10); impact on correctness unmeasured |
| H6 Long contexts degrade 7B answer faithfulness (later evidence blocks ignored) | unmeasured |

### 1.5 Risks to investigate first (ordered)
1. **Unmeasured answer quality** — no correctness/faithfulness numbers exist; optimizing latency without them risks silently degrading answers.
2. **Intent-driven evidence budget** — wrong top_k for scope, measured on 9 of 25 answerable questions.
3. **Unbounded generation** — no length cap, no timeout; latency variance unknown.
4. **Context window headroom** — 90 % used at top_k 8; overflow behavior unknown.
5. **Out-of-corpus questions** — unrelated evidence always supplied.
6. **Missing failure telemetry** — validation failures are invisible.

### 1.6 Modules to inspect next
| Module | Question to answer |
|---|---|
| `query_understanding.py` `_detect_intent`, `INTENT_CUES`, `INTENT_FALLBACK_PATTERNS` (`:581`, `:416-429`) | Why "What resistance mechanisms…" → FACT_LOOKUP and "How much did semaglutide… compared with placebo" → COMPARISON |
| `reranker.py` `_question_type_bonus` + CE scoring | Contribution of the bonus vs CE to the observed rank changes |
| `section_chunker.py` + `pmc_parser.py` | Exact inventory of dropped text (short sections, abstracts, tables, figure captions merged into text) |
| `evidence_classifier.py` | Precision of `section_category` labels passed to Qwen |
| `generator.py` `build_prompt` / `ANSWER_SECTIONS` | Template-to-answer-length relationship |
| Ollama server config (systemd unit, env) | Where `n_ctx`, threads, keep-alive are determined; per-request override capability |

---

## 2. Benchmark strategy

Common protocol (all levels): environment fingerprint, repo-root CWD, `PYTHONHASHSEED=0` for primary runs plus 5-seed QU stability, production call path with non-invasive wrappers, results in `benchmark_runs/`, gold chunks graded 0/1/2 by two reviewers ([BENCHMARK_PLAN.md](BENCHMARK_PLAN.md) §2–§3).

### LEVEL 0 — Retrieval-only
| | |
|---|---|
| Goal | Quantify retrieval and reranking quality and latency with no LLM in the loop; attribute evidence loss to each retrieval stage |
| Questions | All L1 and L2 questions below (same gold), plus each question run in **two modes**: (a) production (QU → strategy → retrieve_chunks), (b) fixed strategy (retrieval_k 60, top_k 8, no expansions) to separate classifier effects from retrieval effects |
| Measurements | Per query: dense ranks of every gold chunk, pool composition; full CE order of pool; rank change dense → CE; loss reason per pooled gold chunk (`below_cutoff` / `dedup` / `source_cap`); final-set Gold@1/@2, gold-chunk recall, precision@final (graded); L2 aspect and paper coverage; embed / Chroma / CE time; pool size; QU intent/type per seed |
| Derived | Recall@{10,20,50} dense; MRR and nDCG@top_k for dense order vs CE order (reranker lift); expansion lift; seed-stability rate |
| Success criteria (proposed) | L1: gold-chunk Recall@50 (dense) ≥ 0.9; Gold@2 after rerank ≥ 0.85 of questions; reranker nDCG lift ≥ 0 on ≥ 80 % of questions. L2: aspect recall@pool ≥ 0.8; QU stability 1.0 |
| Risks | Title-based paper gold incomplete (other relevant papers exist); chunk grading effort (~400 chunks); CE replay cost doubles rerank time (untimed pass) |
| Expected learning | Whether retrieval or the strategy layer limits evidence; whether CE helps or hurts on this corpus; size of rare-term misses (H3); cost curve of pool size |

### LEVEL 1 — Single-paper
| | |
|---|---|
| Goal | Verify retrieval accuracy, grounding, and answer correctness when the answer lives in one paper |
| Measurements | All L0 metrics + prompt tokens, answer tokens, prefill/decode durations and rates, load duration, time-to-first-token (from a streamed side-run), validation outcome (`pass_first` / `pass_after_prune` / `fail`) with raw output, pruned lines, fact recall vs gold facts, citation precision (manual, supported/partial/unsupported), unsupported-claim count, structure adherence, abstention correctness (controls), run-to-run variance (3 repeats) |
| Success criteria (proposed) | Per question (2 of 3 repeats): gold chunk at E1/E2, validation ≠ fail, fact recall ≥ 0.8, unsupported claims = 0. Suite: ≥ 13 of 16 answerable pass; 2 of 2 controls make no claim about the absent entity |
| Risks | LLM non-determinism (no seed/temperature control) widens variance; manual citation review effort; case-report questions depend on chronology across chunks |
| Expected learning | Baseline correctness and faithfulness; how often grounding fails vs retrieval fails; answer-token distribution per template on comparable evidence |

### LEVEL 2 — Multi-paper synthesis
| | |
|---|---|
| Goal | Verify cross-document synthesis; measure context growth and generation scaling |
| Measurements | All L1 metrics + aspect coverage@final, normalized paper coverage, distinct papers cited, evidence utilization (cited E# ÷ supplied), position bias (fact recall for E1–E2 vs last two blocks), attribution accuracy (manual), comparison validity (manual); generation scaling: prompt tokens vs prefill time, prompt tokens vs decode rate, answer tokens vs profile |
| Success criteria (proposed) | Per question (2 of 3): aspect coverage@final ≥ 0.6, ≥ 2 distinct papers cited, validation ≠ fail, unsupported claims = 0. Suite: ≥ 7 of 9 pass |
| Risks | Ceiling set by top_k (3–8) not retrieval; prompt near 4 K window at top_k 8; longer runs (≈ 2–3 min each × 27) |
| Expected learning | Whether synthesis is limited by evidence budget, by Qwen's use of later blocks, or by validation pruning; the latency cost per extra evidence block |

---

## 3. Corpus-derived questions

Gold papers below are confirmed indexed; **answer-bearing chunks were read** and key facts quoted from them. E-L0 columns: intent → (retrieval_k/top_k); position(s) of gold paper in the final context.

### LEVEL 1 (single-paper)
| ID | Question | PMC (answer chunk) | Key facts in chunk | Why useful | Expected retrieval | Component tested | E-L0 |
|---|---|---|---|---|---|---|---|
| L1-01 Safety | In the real-world cohort of metastatic breast cancer patients who permanently discontinued trastuzumab deruxtecan, what were the reasons for discontinuation? | PMC13564716 (_0005) | 93 discontinued; PD 82.8 %; AEs 14.0 % (fact at char 966 of 2,329) | Numbers near truncation boundary | Results chunk _0005 in final | Truncation, safety extraction | EXPLANATION 30/5; E1–E2 (top-1 is Discussion _0009) |
| L1-02 Safety | Which baseline serum biomarker predicted severe immune-related liver injury after nivolumab plus ipilimumab, and what cutoff was identified? | PMC13600002 (_0015) | KL-6; AUC 0.755; Youden cutoff 418 U/mL; 400 U/mL used | Precise biomarker + numeric threshold | _0015/_0016 | Retrieval precision, numeric grounding | FACT_LOOKUP 20/3; E1–E2 |
| L1-03 Efficacy | What were the response rates, PFS and OS with first-line afatinib versus osimertinib after 3 years of follow-up in EGFR-mutant NSCLC? | PMC13427999 (_0006) | ORR 66.0 vs 60.5 %; mPFS 18.2 vs 13.5 mo (HR 0.79, p 0.24); mOS 37.0 vs 40.5 mo (HR 1.01) | Many competing afatinib/osimertinib papers in corpus | _0006 at E1/E2 | Disambiguation, reranker | COMPARISON 60/8; **E5–E6** |
| L1-04 Efficacy | How much did semaglutide 2.4 mg reduce ad libitum energy intake compared with placebo at weeks 20, 40 and 60? | PMC13494093 (_0011) | −367/−317/−200 kcal vs baseline; 29.9/24.6/24.0 % lower than placebo | Time-series numbers | _0011–_0013 | Numeric fidelity | COMPARISON 60/8, qtype DOSING; E1–E2 |
| L1-05 Outcomes | Did combining radium-223 with enzalutamide improve PFS and OS versus enzalutamide alone in mCRPC? | PMC13449031 (_0009) | mPFS 22 vs 5 mo (p 0.048); OS NR both (p 0.602) | Short results chunk (906 chars); one results subsection unindexed (85 w) | _0009 | Short-section loss, outcome reporting | COMPARISON 60/8; E2–E3 |
| L1-06 Outcomes | Is the EGFR adjusted variant allele frequency associated with progression-free survival on first-line osimertinib? | PMC13511178 (_0006) | No association: HR 1.13 (p 0.70); HR 0.60 (p 0.16); continuous HR 1.00 | Negative finding — tests faithful "no effect" reporting | _0006 | Grounding of null results | FACT_LOOKUP 20/3; E2 |
| L1-07 Mechanism | What molecular mechanism links myeloperoxidase to osimertinib-induced cardiotoxicity? | PMC13368672 (_0022, _0023) | MPO up with osimertinib; reduced AMPK/PI3K/Akt/eNOS phosphorylation; MPO inhibitor partially reverses | Pathway term beyond 1,200 chars in _0022; present at start of _0023 | _0023 in final | Truncation, multi-chunk mechanism | EXPLANATION 30/5; E1–E2 |
| L1-08 Mechanism | How did the Egfr V804F mutation change sensitivity to osimertinib and afatinib in the syngeneic mouse model cells? | PMC13394164 (_0012) | Osimertinib IC50 174–320 vs 30 nM (mean 8.2-fold); afatinib 12.2–12.8 nM | Unique mutation (1 paper) | _0012 | Rare-entity retrieval | EXPLANATION 30/5; E1–E2 |
| L1-09 Mechanism/biomarker | What is the evidence that SPEN alterations are a biomarker of androgen receptor pathway inhibitor resistance in metastatic prostate cancer? | PMC13563593 (_0023, _0024) | 127 pts with SPEN alterations; TTNT HR 2.57; OS HR 1.02 (ns); MSK-IMPACT OS 25.4 vs 64.7 mo | Term "SPEN" collides with substrings | _0023–_0024 | Lexical ambiguity, multi-chunk evidence | EVIDENCE 50/6; E1–E2 (dense rank 9 → CE 1) |
| L1-10 Clinical findings | What alterations were found in the lung adenocarcinoma patient who developed an acquired EML4-ALK fusion and BRAF V600G after osimertinib, and how was the patient treated? | PMC13508028 (_0004, _0005, _0010) | ALK rearrangement confirmed by IHC; PD-L1 TPS 40 %; lorlatinib → marked regression | Case narrative spread over chunks | _0010 + case chunks | Narrative synthesis within one paper; 2-chunk cap | FACT_LOOKUP 20/3; E1–E2 |
| L1-11 Clinical findings | How long was osimertinib given before squamous transformation was confirmed in the EGFR-mutant lung adenocarcinoma case report? | PMC13479129 (_0004) | ~39 mo to first suspected progression; ~52 mo total osimertinib | Chronology / duration reasoning | _0004 | Temporal fact grounding | EXPLANATION 30/5; E2–E3 |
| L1-12 Clinical findings | What resistance alterations were found on rebiopsy after progression on first-line osimertinib in the real-world rebiopsy cohort? | PMC13529361 (_0006) | 38.8 % new alterations; transformation 4.9 % (10 pts); C797S, exon 18; MET amp/ex14, BRAF, KRAS, TP53 | Existing gold in `retrieval_eval.py`; overlaps L2-01 | _0006 | Continuity with prior evaluation | FACT_LOOKUP 20/3; E2 |
| L1-13 Trial design | What is the primary outcome and sample size rationale of the randomized trial of Yifeixiaoji decoction added to osimertinib? | PMC13537402 (_0013) | Primary PFS; FLAURA mPFS 18.9 mo; target HR 0.66; ~176 events | "Trial design" section (59 w) unindexed; rare TCM term | _0013 | Short-section loss, rare-term retrieval | FACT_LOOKUP 20/3; **gold not in pool** |
| L1-14 Trial design/efficacy | In the final analysis of CheckMate 9ER, what were the ORR and duration of response with nivolumab plus cabozantinib versus sunitinib? | PMC12522107 (_0007) | ORR 55.7 vs 27.4 %; CR 13.9 vs 4.6 %; mDOR 22.0 vs 15.2 mo | Trial acronym shared with 2 other papers | _0007 | Acronym disambiguation | COMPARISON 60/8; E1–E2 |
| L1-15 Trial outcomes | In Japanese participants of KEYNOTE-671, how did perioperative pembrolizumab affect nodal downstaging and residual viable tumor? | PMC13595008 (_0011) | Nodal downstaging 39 % vs 21 %; median %RVT 33 % vs 52 % | Subgroup paper among 4 KEYNOTE-671 papers | _0011 | Subgroup disambiguation | EVIDENCE 50/6; E1–E2 |
| L1-16 Clinical findings | Which variables were most associated with loss of response to adalimumab in juvenile idiopathic arthritis? | PMC13273996 (_0003) | ADA_ab and ADA_drug strongest; then ERA subtype, male sex, HLA-B27; n = 184 | Small paper (6 chunks) | _0003 | Ranking of factors | COMPARISON 60/8; E1, E3 |
| L1-C1 Control | What is the mechanism of action of teprotumumab? | none (0 chunks) | — | Out-of-registry, out-of-corpus | No relevant chunk exists | Abstention, hallucination | EXPLANATION 30/5; 5 unrelated chunks supplied |
| L1-C2 Control | What is the efficacy of imatinib in asthma? | none (0 chunks with both terms) | — | In-registry drug, absent topic | No relevant chunk exists | Abstention with plausible-but-wrong evidence | FACT_LOOKUP 20/3; 3 unrelated chunks supplied |

### LEVEL 2 (multi-paper)
| ID | Question | Expected articles (aspects) | Why useful | Expected retrieval | Component tested | E-L0 (gold papers: pool / final of total) |
|---|---|---|---|---|---|---|
| L2-01 Resistance | What resistance mechanisms emerge after first-line osimertinib? | on-target: PMC13530993, PMC13585410, PMC13563458 · bypass: PMC13508028, PMC13579456 · transformation: PMC13479129, PMC13508615 · adaptive/non-genetic: PMC13478582, PMC13520340 · real-world: PMC13529361, PMC13510353 | Primary benchmark question; seed-dependent type | ≥ 1 paper per aspect in final | Strategy budget, diversity, synthesis | FACT_LOOKUP 20/3; 7 / 3 of 11 |
| L2-02 Efficacy comparison | How do outcomes compare between afatinib and osimertinib in EGFR-mutant NSCLC, including uncommon EGFR mutations? | first-line OS: PMC13427999 · uncommon RWE: PMC13394325, PMC13573738 · network MA: PMC13574751 | Head-to-head vs indirect evidence | All 4 in final | COMPARISON profile, comparison validity | COMPARISON 60/8; 4 / 3 of 4 |
| L2-03 Safety synthesis | What immune-related adverse events have been reported with nivolumab alone or combined with ipilimumab? | liver PMC13600002 · thyroid PMC13597272 · pneumonitis PMC13605366 · ocular PMC13583422 · renal PMC13612749 | Organ-system breadth | ≥ 3 organ systems | Pool recall, diversity | FACT_LOOKUP 20/3; **1** / 1 of 5 |
| L2-04 Resistance | What mechanisms drive resistance to enzalutamide in prostate cancer? | ferroptosis PMC13394060, PMC13480344 · SPEN PMC13563593 · plasticity PMC13466754, PMC13447160 · metabolic PMC13568755, PMC13478015 · liquid biopsy PMC13562513 | Many preclinical mechanisms | ≥ 4 aspects | Budget vs breadth | FACT_LOOKUP 20/3; 5 / 2 of 8 |
| L2-05 Efficacy + safety comparison | How do abiraterone and enzalutamide compare in efficacy and safety for metastatic prostate cancer? | mCSPC PMC13405643 · mCRPC PMC13427783 · falls PMC13374230 · hepatotoxicity PMC13488195 | Mixed efficacy/safety, non-registry comparator | All 4 | Comparison synthesis | COMPARISON 60/8; 4 / 2 of 4 |
| L2-06 Evidence synthesis | How are adalimumab drug levels and anti-drug antibodies related to clinical response? | JIA PMC13273996 · dosing/ADA PMC13337933 · paediatric uveitis PMC13415550 · uveitis cohort PMC13429708 | Consistent finding across diseases | All 4 | Reranker (dense 1 → CE 4) | ANALYSIS 50/8; 4 / 3 of 4 |
| L2-07 Evidence synthesis | What is the evidence for semaglutide in MASLD and MASH? | mechanisms PMC13515630 · reviews PMC13572791, PMC13575885 · agonist classes PMC13589479 · preclinical PMC13588371 | Review-heavy corpus region | ≥ 3 | Review vs primary evidence weighting | EVIDENCE 50/6; 3 / 2 of 5 |
| L2-08 Safety synthesis | What safety risks are associated with trastuzumab deruxtecan? | ILD/cardiac PMC13609577 · discontinuation PMC13564716 · AE management PMC13537819 · pharmacovigilance PMC13597761 · ADC NMA PMC13494281 | Pool rich, budget small | ≥ 3 | Budget limiting coverage | FACT_LOOKUP 20/3; 5 / 1 of 5 |
| L2-09 Safety comparison | How do the safety profiles of enzalutamide, apalutamide and darolutamide compare? | ILD signals PMC13541453 · CNS PMC13516075 · falls PMC13374230 · hypertension PMC13480082 · hepatotoxicity PMC13488195 · pharmacology/ADR PMC13421037 | Cross-drug safety with non-registry drugs | ≥ 4 | Comparison + diversity | COMPARISON 60/8; 5 / 2 of 6 |

Gold-labeling still required (§3 of BENCHMARK_PLAN): chunk grades for every gold paper, fact regexes, answer-span offsets, second reviewer.

---

## 4. Generation investigation

### 4.1 What the code and measurements establish
| Element | Fact | Evidence |
|---|---|---|
| Prompt construction | Single user prompt: role + rules (~2.3–2.8 K chars) + query JSON + section template + context + question | `generator.py:96-201` |
| Context assembly | Block = `[E#]` + Drug / Evidence Type / Study Design / Year / Section + text ≤ 1,200 chars | `context_builder.py` |
| Chunk truncation | Hard character cut, mid-sentence; 77.9 % of chunks cut | E-CORPUS |
| Answer templates | MECHANISM 4, CLINICAL_TRIAL 5, COMPARISON 6, DRUG_OVERVIEW 5, default 3 headings + `## References`; "Cite every factual sentence", "one claim per bullet" | `generator.py:28-80,190-201` |
| Prompt growth | ~1.1 K fixed tokens (inferred: 1,410–1,435 total with 3 blocks) + ~0.25 K per block (inferred from 3,151 with 8 blocks); bounded by top_k | E-GEN |
| Ollama invocation | `ollama run` CLI subprocess per call; stdin prompt; stdout captured after completion; Qwen system prompt from Modelfile ("You are Qwen…") still applied | `generator.py:449`, `ollama show` |
| Qwen behavior | 403–536 answer tokens; 6.1–6.9 tok/s; all 3 answers passed validation without pruning | E-GEN |

Per-block token cost and fixed-template token cost are inferred by difference from 2 data points — **not measured directly**.

### 4.2 Experiments to run next (measurement only; no code change to `src/`)
| # | Experiment | Design | Answers |
|---|---|---|---|
| G1 | Prompt-component token accounting | Tokenize with Ollama (`prompt_eval_count`) for: template only; template + 1, 3, 5, 8 blocks; with/without query JSON | Exact fixed vs per-block token cost |
| G2 | Prefill scaling curve | Same question, contexts of 1–8 blocks, 3 repeats | Prefill tokens/s vs length; validates P4 |
| G3 | Answer-length by profile | Fixed 5-block context × each profile (MECHANISM, CLINICAL_TRIAL, COMPARISON, DRUG_OVERVIEW, default) × 3 repeats | H1: does template drive answer tokens? |
| G4 | Answer-length variance | L1 + L2 suite answers, 3 repeats each | Distribution, tail (U4/U5) |
| G5 | Thread sensitivity | Fixed prompt, `num_thread` ∈ {2,4,6,8} via HTTP API request options (harness only), 3 repeats | H2 / U6 |
| G6 | Decode rate vs context length | Fixed answer budget, contexts 0.5 K–3.5 K tokens | Decode slowdown curve |
| G7 | Context-limit behavior | top_k 8 prompt + instruction for long answer; observe `truncated`, stop reason, answer completeness | U7 |
| G8 | Cold / warm / model swap | Run after > 5 min idle; after a 1.5b QU fallback call; immediate repeat | Load cost, U8 |
| G9 | CLI vs HTTP API parity | Same prompt via `ollama run` and `/api/generate` with identical options | Validity of harness measurements |
| G10 | Position use | L2 answers: which E# are cited vs supplied | H6 |

### 4.3 Missing telemetry (required before changing code)
| Gap | Location |
|---|---|
| Ollama `prompt_eval_count/duration`, `eval_count/duration`, `load_duration` not recorded | `generator.py:449` (`ollama run` without `--verbose`) |
| No time-to-first-token | no streaming |
| Raw model output not stored; failed runs leave no artifact | `generator.py:472-492`, `app.py:282-302` |
| Validation outcome class and pruned-line count not recorded | `generator.py:478-487` |
| QU path (fast vs LLM) and confidence not stored | `query_understanding.py:1378-1391`, `app.py:52-66` |
| Retrieval sub-stage timings and pool size not stored | `app.py:175-181` |
| Environment fingerprint (git SHA, model digest, index hash, Ollama options) absent | `save_debug_run` |
| Process / Ollama memory not recorded | absent |

### 4.4 Measurements required before any generation code change
1. G1 + G3 + G4 (where tokens come from; whether templates drive length; variance).
2. L1/L2 quality baseline (fact recall, citation precision, unsupported claims) — every latency change must be judged against it.
3. G7 (safety margin at 4 K).
4. G9 (so harness numbers transfer to the app's invocation path).

---

## 5. Roadmap

### CRITICAL
| Item | Why it matters | Expected impact | Required evidence | Next action |
|---|---|---|---|---|
| C1 Gold labeling of L1/L2 set | Without graded gold, no quality metric exists | Enables every later decision | — | Grade chunks of the 18 L1 + 9 L2 gold papers; second reviewer |
| C2 Benchmark harness (outside `src/` production path) | Reproducible L0/L1/L2 runs with full telemetry via wrappers | Trustworthy baseline | Approval of harness location | Build harness + `benchmark_questions.json`; add `benchmark_runs/` to `.gitignore` |
| C3 L0 baseline | Separates retrieval, rerank, and strategy losses cheaply (~3 min) | Locates evidence loss | C1 | Run production + fixed-strategy modes, 5 seeds |
| C4 L1/L2 quality + latency baseline | Reference for all optimizations | Defines "better" | C1, C2 | 27 questions × 3 repeats (~3–4 h) |
| C5 Generation experiments G1, G3, G4, G7, G9 | Largest latency component is unexplained beyond token counts | Identifies true levers | C2 | Run on captured suite prompts |

### HIGH PRIORITY
| Item | Why it matters | Expected impact | Required evidence | Next action |
|---|---|---|---|---|
| H1 Intent → evidence-budget analysis | P7/P8: budget mismatched to scope on 9 of 25 questions | Coverage and prompt size | C3 (production vs fixed-strategy delta) | Inspect `_detect_intent` cues against L0 results |
| H2 Index content audit | P11–P14 affect evidence quality | Retrieval precision, context quality | Quantify dropped words per paper, boilerplate share of retrieved chunks, truncation of answer spans in L0/L1 | Script over Chroma + XML (read-only) |
| H3 Reranker evaluation | U2: mixed rank changes | Retrieval quality | C3 nDCG dense vs CE vs CE+bonus | Replay with bonus disabled in harness only |
| H4 Generation CPU characterization (G2, G5, G6, G8) | Bounds achievable latency on this VM | Hardware/config decisions | C2 | Run after C5 |
| H5 Out-of-corpus behavior | P15: hallucination risk | Safety of answers | L1-C1/C2 results across repeats | Review control answers manually |
| H6 Failure visibility | U9: unknown validation failure rate | Reliability | C4 outcome classes | Count `fail` / `pass_after_prune` in baseline |

### LOW PRIORITY
| Item | Why it matters | Expected impact | Required evidence | Next action |
|---|---|---|---|---|
| L1 Embedding configuration check (pooling, distance) | U10 | Possibly retrieval recall | C3 baseline to compare against | Read MedCPT model card; offline recall comparison on gold set |
| L2 Dead-code inventory and removal plan | Maintainability | Lower cognitive load | Confirm no external callers | Propose removal list for review |
| L3 Dependency pinning + offline model loading | Reproducibility; startup network dependency | Operational stability | `pip freeze` captured in fingerprint | Draft pinned requirements for review |
| L4 Seed-dependent classification | P9; deterministic runs | Repeatability | Seed-stability rate from C3 | Prioritize by observed instability rate |
| L5 Test suite with assertions | Regression safety | Engineering velocity | Benchmark harness exists | Convert benchmark checks into assertions later |
