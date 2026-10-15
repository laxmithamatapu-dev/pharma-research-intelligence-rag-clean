# Retrieval Design: Paper Budget vs Passage Budget (2026-10-15)

Question: should the per-paper passage limit exist at all, and what selection design is correct long-term for single-paper (L1) and multi-paper (L2) questions?
Data: candidate pools of the post-fix retrieval-only run (`benchmark_runs/20261015_065539_retrieval_postfix_seed0`), all chunks of every candidate paper, current cross-encoder scores, draft gold labels (16 L1 questions with 52 facts; 9 L2 questions with paper-level aspects). Script: `src/evaluation/paper_budget_study.py`; output `paper_budget_study.json`.
"Visible" = within the first 1,200 characters of a chunk (what `build_context` delivers).

---

## 1. How many passages are needed to expose all expected facts (L1)

| Measure | Distribution over 16 questions |
|---|---|
| Facts visible somewhere in the gold paper | **52/52** (no fact exists only past the 1,200-char cut in this set) |
| Facts visible in the current candidate pool | 33/52 |
| **Minimum passages that cover all facts** (oracle set cover) | **1** for 14 questions, **2** for 2 |
| Passages needed **in the reranker's order** (smallest top-k of the paper covering all facts) | 1, 1, 1, 1, 2, 2, 3, 3, 3, 4, 4, 6, 7, 7, 10, 11 (median 3) |
| Chunks in the paper that carry ≥1 expected fact | 1–11 (4 questions: exactly one chunk) |

**Reading.** The evidence a single-paper question needs is **compact**: one passage suffices for 14/16. What varies is how far down the paper's ranked list that passage sits: positions 1 to 11. The per-paper limit is a proxy for **ranking uncertainty within the paper**, not for how much evidence the question needs.

## 2. Is a fixed per-paper limit conceptually correct?

**No, for either level, for different reasons.**

- **L1.** With a fixed limit q, a question is fully served only if its answer passage ranks ≤ q within the paper. In reranker order: q = 2 serves 6/16, q = 3 serves 9/16, q = 4 serves 11/16, q = 7 serves 14/16. A fixed q is simultaneously too small for some questions (L1-06, L1-09 need 10–11) and wasteful for others (4 need 1). The limit's original purpose, diversity across papers, is irrelevant when one paper is the target.
- **L2.** The limit does diversify, but the unit that matters is **papers** (aspects are covered by different papers), and the flat top_k with a cap does not control paper count directly: the current design delivers 5.1 distinct papers on average for 6 passages.

## 3. Should the budget depend on question type? (equal passage budgets)

| Budget (passages) | Best design for **L1** (facts of 52) | Same design on **L2** (aspect coverage) | Best design for **L2** | Same design on **L1** |
|---|---|---|---|---|
| 4 | 1 paper × 4 passages: **31** | 0.11 | 4 papers × 1 passage: **0.41** | 17 |
| 6 | 2 papers × 3 passages: **30** | 0.21 | 6 papers × 1 passage: **0.56** | 17 |
| 8 | 2 papers × 4 passages: **36** | 0.21 | 8 papers × 1 passage: **0.61** | 17 |
| Current (≈ 5.6 L1 / 6 L2 passages, flat top_k, ≤ 2 per paper) | 26 | 0.41 | — | — |

(Paper-first rows use the top papers ranked by their best pool chunk and the top passages from **all** chunks of each paper, scored by the current cross-encoder.)

**Yes.** The optimal allocations are opposite: L1 wants **depth** (few papers, several passages each) and L2 wants **breadth** (many papers, one passage each). Any single fixed shape is wrong for one of the two. At 6 passages, the L1-optimal shape delivers 30 facts but only 0.21 L2 coverage; the L2-optimal shape delivers 0.56 coverage but only 17 L1 facts.

L2 passage depth per paper could not be measured: L2 gold is paper-level. 1 passage per paper is a lower bound on L2 needs.

## 4. Can the pool itself reveal the question's scope?

| Signal | L1 (16) | L2 (9) | Controls (2) |
|---|---|---|---|
| Share of top-10 candidates from the top paper | 0.1–0.8 | 0.1–0.5 | 0.4, 0.1 |
| Distinct papers in top-10 | 3–9 | 6–9 | — |
| Score margin between the two best papers | 0.14–4.82 (≥ 1.6 in 11/16) | 0.04–1.65 (≥ 1.6 in 1/9) | 0.80, 1.84 |
| Top-ranked paper is a gold paper | 12/16 | 4/9 | — |

**Partially.** A large top-paper margin is typical of single-paper questions, but the distributions overlap and the controls fall inside them. Scope should come from **question analysis**, with retrieval signals as supporting evidence, not as the sole switch. The top pool paper is the right paper for only 12/16 L1 questions, so a single-paper design must keep at least 2 candidate papers.

## 5. Evidence for a paper-first architecture

| # | Evidence | Source |
|---|---|---|
| 1 | Papers are found far more reliably than passages: gold paper within top-20 dense results 94 %, answer passage 35 % | RCA E4 |
| 2 | All 52 L1 facts are visible somewhere in the gold papers; passage-level pools contain only 33. **Passage-level retrieval caps evidence at 63 %** before any selection | §1 |
| 3 | Paper-first with passages chosen from the **whole paper** exceeds every pool-based design: 36/52 facts at 8 passages, vs a pool-based ceiling of 33 and 26 today | §3; passage study |
| 4 | At **fewer** passages than today, paper-first is still better: 1 paper × 4 passages gives 31 facts with 4 passages vs 26 with ≈ 5.6 today | §3 |
| 5 | For synthesis, breadth by papers beats the flat design at equal budget: 6 papers × 1 passage → aspect coverage 0.56 vs 0.41 | §3 |
| 6 | Title context improves paper identification (paper recall up, L1-13 rescued) but degrades passage discrimination | E2a |
| 7 | Within a paper, the current cross-encoder places the answer passage in the paper's top 3 for 10/16 papers (11/16 with window scoring) | Passage study |

**Counter-evidence and risks**
- Paper ranking is imperfect: the top pool paper is wrong for 4/16 L1 questions, so paper-first must keep ≥ 2 papers for single-paper questions or use a better paper ranker. The title/abstract paper index is supported by E2a but not yet measured end-to-end.
- Within-paper ranking still varies widely (answer passage at rank 1–11), so depth per paper must be generous, or within-paper ranking must improve.
- Prompt cost scales with passages: each passage ≈ 250–330 prompt tokens ≈ 4–5 s prefill on this CPU. 8 passages ≈ 2,600 evidence tokens: feasible only with `num_ctx` above 4,096.

## 6. Design conclusions (long-term architecture)

1. **Replace the fixed per-paper limit** with two explicit budgets: **papers (breadth)** and **passages per paper (depth)**, chosen by question scope.
2. **Single-study questions**: small paper budget (2: target + fallback), large passage budget within the paper (≈ 4), passages drawn from the **whole paper**, not only from the passage-level pool.
3. **Synthesis / comparison questions**: paper budget sized to the expected number of aspects (≈ 6–8), ≈ 1 passage per paper as the floor. Depth per paper for synthesis is unmeasured and needs passage-level L2 labels.
4. **Scope comes from question analysis** (now deterministic after F3/F4). Retrieval concentration is a secondary signal, not a switch.
5. **Total evidence budget is a token budget** (≈ 6–8 passages) set by context window and latency, then split between breadth and depth by scope.
6. **The pool should be paper-level**, not a flat passage list: rank papers first, then rank passages within the selected papers.

## 7. Evidence still missing
- End-to-end paper ranking with a title/abstract paper index (instead of best-pool-chunk ranking).
- L2 passage-level gold to size depth for synthesis questions.
- Generation impact: whether more passages from one paper improve reported facts (vs only visible facts).
- Multi-seed and larger question set confirmation.
