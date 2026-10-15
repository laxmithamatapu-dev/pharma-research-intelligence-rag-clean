# Passage Selection Study (2026-10-15)

Question: within the candidate pool, is evidence lost mainly to **reranker behavior**, **passage quota**, or **passage scoring**?
Method: offline replay on the 27 candidate pools of a fresh retrieval-only run with F1–F5 (`benchmark_runs/20261015_065539_retrieval_postfix_seed0`). Every pool is scored once per scorer; selection is then simulated for every combination of scorer × scoring mode × per-paper quota, with top_k fixed at the production value. Context is assembled with the production `build_context` (1,200-char truncation). Fact visibility counts expected facts present in gold-paper blocks Qwen would receive.
Validation: the production setting (MiniLM, production scoring, quota 2) reproduces the recorded selection for **27/27** questions.
Script: `src/evaluation/passage_selection_study.py`; output: `passage_selection_study.json` in the run directory. No production code changed.

**Configurations**
- **Scorers**: `minilm` (current `cross-encoder/ms-marco-MiniLM-L-12-v2`); `minilm_window` (same model, max over 128-word windows, stride 64); `medcpt` (`ncbi/MedCPT-Cross-Encoder`, chunk text); `medcpt_title` (MedCPT, documented `title. text` input).
- **Scoring modes**: `production` (per-pool min-max normalization + question-type bonus ≤ 0.30, as in `reranker.py`); `raw` (cross-encoder score only).
- **Quotas**: 2 (current), 3, 4, unlimited.

---

## 1. Ceiling: what passage selection can recover at all

| | Count |
|---|---|
| L1 expected facts | 52 |
| Facts present in pooled gold-paper text (first 1,200 chars of each chunk) | **33** |
| Facts delivered today | 26 |
| **Recoverable by passage selection** | **7** |
| Unreachable without retrieval change (not in pool, or only past the 1,200-char cut) | 19 |

Passage selection can address **7 of the 26 lost L1 facts (27 %)**. The remaining 73 % is a retrieval and pool problem (E2a, RCA). Labeled answer chunks in the pool: 9/20.

## 2. Results (L1 = 16 answerable questions; L2 = 9)

| Configuration | L1 answer chunks delivered | **L1 facts visible** | L1 all-facts questions | L1 zero-fact questions | L2 gold papers delivered | L2 aspect coverage | Mean context chars |
|---|---|---|---|---|---|---|---|
| **MiniLM, production, quota 2 (current)** | 6 | **26** | 5 | 5 | 17 | 0.41 | 7,425 |
| **MiniLM, production, quota 3** | **8** | **31** | **7** | **4** | 17 | 0.41 | 7,413 |
| MiniLM, production, quota 4 | 8 | 31 | 7 | 4 | 17 | 0.41 | 7,413 |
| MiniLM, production, unlimited | 9 | 32 | 8 | 4 | 17 | 0.41 | 7,445 |
| MiniLM, raw, quota 2 | 4 | 21 | 4 | 7 | 19 | 0.45 | 7,393 |
| MiniLM, raw, quota 3 | 7 | 29 | 6 | 3 | 19 | 0.45 | 7,393 |
| MiniLM window, production, quota 2 | 6 | 22 | 5 | 8 | 14 | 0.33 | 7,498 |
| MiniLM window, production, quota 3 | 8 | 29 | 7 | 6 | 14 | 0.33 | 7,463 |
| MedCPT, production, quota 2 | 5 | 23 | 5 | 5 | 20 | 0.44 | 7,297 |
| MedCPT, production, quota 3 | 6 | 25 | 5 | 5 | 20 | 0.44 | 7,269 |
| MedCPT, raw, quota 2 | 4 | 21 | 5 | 7 | 21 | 0.46 | 7,250 |
| MedCPT + title, raw, unlimited | 8 | 29 | 7 | 4 | 19 | 0.38 | 7,352 |

(Full grid of 32 configurations in the JSON. L1 gold paper delivered: 15/16 for all MiniLM and MedCPT configurations, 13/16 for window scoring.)

**Per-question changes**
- Quota 2 → 3 (MiniLM, production): L1-04 0 → 4 facts, L1-02 2 → 3. **No regressions** at L1 or L2.
- Quota 3 → unlimited: L1-15 1 → 2.
- MiniLM → MedCPT (quota 2): L1 gains L1-04 (+4), L1-02 (+1); L1 losses L1-08 (−3), L1-12 (−3), L1-10 (−2) → net −3. L2 papers +1 on 5 questions, −1 on 3 → net +3.
- Production → raw scoring (MiniLM, quota 2): L1-12 (−4), L1-09 (−1); L2-01, L2-04 (+1 paper each).

## 3. Reranker behavior inside a paper

**Section preference (mean within-pool percentile of the score; 0.5 = average)**
| Section | MiniLM | MiniLM window | MedCPT | MedCPT + title |
|---|---|---|---|---|
| Results | **0.45** | 0.46 | **0.43** | 0.47 |
| Discussion | **0.55** | 0.53 | 0.50 | 0.51 |
| Introduction | 0.51 | 0.54 | 0.52 | 0.49 |
| Methods | 0.41 | 0.40 | 0.50 | 0.47 |
| Case description | 0.64 | 0.58 | 0.81 | 0.85 |

**Numeric density vs score (mean rank correlation within pools):** MiniLM −0.02, MedCPT −0.11. Numbers are not what the current model penalizes.

**Answer chunk's rank within its own paper (pooled chunks only)**: MiniLM ranks it first in 2 of 9 papers (L1-08, L1-10). Window scoring ranks it first in 5 of 9 (L1-02, L1-05, L1-09, L1-16 improve). MedCPT is better on some (L1-02, L1-05) and much worse on others (L1-08 8th, L1-12 9th).

**Answer chunk's rank among *all* chunks of the gold paper** (6–32 chunks per paper):
| Rank | MiniLM | MiniLM window | MedCPT |
|---|---|---|---|
| 1 | 4/16 | 6/16 | 2/16 |
| ≤ 2 | 6/16 | 9/16 | 7/16 |
| ≤ 3 | **10/16** | **11/16** | 9/16 |

## 4. Why Discussion beats Results

| Proven | Evidence |
|---|---|
| The preference is **not specific to the ms-marco model** | MedCPT also places Results below average (0.43); both models favor Discussion/Introduction or case narratives |
| It is **not a penalty on numbers** | Rank correlation with numeric density ≈ 0 (MiniLM) |
| **Whole-chunk scoring dilutes the answer sentence** within a paper | Max-over-windows moves the answer chunk to first place within its paper in 3 more papers |
| Within-paper preference becomes evidence loss **only through the quota** | Unlimited quota delivers 9/9 pooled answer chunks' facts that fit the budget (32/33 ceiling) with unchanged context size |

**Mechanism (supported, not fully proven):** questions are phrased about a study ("In the … cohort, what were …"). Discussion and Introduction passages restate the study and topic in the question's register. Results passages state measurements whose topical framing sits in a few sentences diluted by tables and figure text. Both cross-encoders reward the restatement. With two slots per paper, the restatements take both slots.

**Why window scoring is not the answer:** it improves within-paper order but lowers cross-paper ranking (L1 gold paper delivered 15 → 13; L2 papers 17 → 14). Max-over-windows inflates the scores of long, loosely related chunks from other papers.

## 5. Determination: dominant cause within passage selection

| Candidate cause | Effect when changed (L1 facts, from 26) | L2 effect | Verdict |
|---|---|---|---|
| **Passage quota** (2 → 3) | **+5 (31)**; unlimited +6 (32) of 7 recoverable | none (17 papers, 0.41 coverage) | **Dominant** |
| Reranker model (→ MedCPT) | −3 (23) at quota 2; −6 vs quota-3 MiniLM | +3 papers | **Refuted** as an L1 improvement; small L2 gain at 3× cost |
| Passage scoring: question-type bonus off | −5 (21) | +2 papers | Bonus helps L1, hurts L2 slightly; not the cause of loss |
| Passage scoring: window max | −4 (22) | −3 papers | Better within paper, worse across papers |

**Conclusion.** Within the pool, the dominant cause of evidence loss is the **2-per-paper quota**. The reranker's Discussion preference is real and shared by both models, but it causes loss only because the quota leaves no room for the third-ranked passage. Changing the model or the scoring does not beat quota 3 and costs latency or Level 2 coverage.

## 6. Deployment fit (8 vCPU, CPU-only)

| Option | Rerank cost | Prompt size | L1 facts | L2 |
|---|---|---|---|---|
| Quota 3, current model | unchanged (0.064 s/candidate; 1.3–6.2 s per question) | unchanged (top_k fixed; 7,413 vs 7,425 chars) | 31 / 33 ceiling | unchanged |
| MedCPT cross-encoder | **3.0×** (0.193 s/candidate → ~11.6 s for a 60-candidate pool) | unchanged | 23–25 | +3 papers |
| Window scoring | 0.036 s/pair × ~3–6 windows per chunk ≈ 2–3× | unchanged | 22–29 | worse |

Model RAM: MedCPT cross-encoder 418 MB on disk.

## 7. Implications (evidence-based; not yet implemented)

1. **Quota 3 is the highest-value, lowest-risk selection change**: +5 L1 facts (+10 points, 50 % → 60 %), 2 more questions with all facts visible, 0 regressions, no latency or prompt cost. Quota 4 adds nothing over 3 in this set.
2. **Do not switch to the MedCPT cross-encoder** on this evidence: it lowers L1 fact visibility, is 3× slower, and its L2 gain (+3 papers) is smaller than the L1 loss.
3. **Passage selection has a hard ceiling of 33/52 facts (63 %)** with current pools. Further gains need retrieval: the paper-first design. Its supporting evidence: with the current model, scoring *all* chunks of the right paper puts the answer chunk in the top 3 for 10/16 papers (11/16 with window scoring, which is safe within a single paper where the cross-paper inflation does not apply). Today only 6/20 answer chunks are delivered.

## 8. Limitations
- Single seed (0), one pool per question; 16 L1 / 9 L2 questions; draft single-labeler gold.
- Fact visibility is pattern-based; it measures what Qwen *can* see, not what it reports.
- Quota counterfactuals hold top_k fixed; with larger top_k, results may differ.
- MedCPT was used as documented (512 tokens, logits). Its weaker L1 result may partly reflect the chunk-not-abstract input domain.

## 9. Recommended next measurements
1. **Generation check for quota 3** (targeted run on L1-02, L1-04 + unchanged controls, 3 repeats with fixed generation seed once available): confirm that the extra Results passage changes reported facts.
2. **Paper-first prototype (offline)**: top papers from the pool, then all chunks of each paper scored with MiniLM (whole or window), top 3 per paper; compare fact visibility against quota 3.
3. **Multi-seed confirmation** of quota 3 on the 11 classification-sensitive questions (cheap replay on existing 5-seed pools).
