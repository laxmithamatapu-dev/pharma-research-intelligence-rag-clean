# NEXT STEPS — Ranked Workstreams and Execution Plan

Checkpoint 2026-10-15. Retrieval & architecture: complete. Next phase: **generation fidelity & model evaluation**, with production hardening alongside.

## 1. Project maturity assessment

| Area | Maturity | Basis |
|---|---|---|
| Retrieval | **Production-ready for this corpus** | 88 % / 81 % of expected facts reach the LLM (dev / held-out); no L1 dev question without evidence; paper-first validated on held-out questions |
| Abstention | **Good, thinly calibrated** | 12/12 controls without false claims; floor separates 12 controls from 39 answerable questions; only 12 controls |
| Generation | **Functional, main quality gap** | 80–85 % of visible facts stated; claim-level citations 27–65 %; 0 failures after repair |
| Evaluation | **Mature** | Production-path harness, held-out set, replay tools, decision gates |
| Operations | **Pilot-ready** | Warm HTTP service, records, pinned deps, docs; not yet installed as a unit; single-request throughput; disk 78 % |
| **Overall** | **Pilot / beta** | Correct and grounded on the tested scope; generation fidelity and scale of evaluation limit "production" status |

## 2. Highest-risk items

| # | Risk | Impact | Evidence |
|---|---|---|---|
| 1 | Generation drops 15–20 % of visible facts; secondary statistics omitted | Incomplete answers | Final baseline; prompt A/B |
| 2 | Claim-level citations are weak | Users cannot verify individual claims | 65 % / 27 % same-line citation to gold paper |
| 3 | Small, single-labeler evaluation set (49 questions) | Conclusions may not generalize | Held-out L1 81 % vs dev 88 % |
| 4 | Abstention floor from 12 controls; margin 0.5 between highest control (4.37) and lowest answerable (4.84) | Some out-of-scope questions reach the LLM; some edge questions could abstain wrongly | Calibration data |
| 5 | ~~Disk 78 % used~~ resolved: 14 GB free (2026-10-15) | — | `df` |
| 6 | One request at a time (≈ 30–40/hour) | Queueing under concurrent use | Single Ollama slot |
| 7 | Service has no authentication (binds to localhost) | Exposure if bound publicly | `serve.py` |

## 3. Ranked next workstreams

| Rank | Workstream | Why | Expected value | Cost |
|---|---|---|---|---|
| **1** | **Model benchmarking (Qwen replacement decision)** | Largest remaining quality gap is generation; prompt changes did not move it; fixed-evidence evaluation isolates the model cheaply | High: decides whether fidelity can rise without architecture change | ≈ 1–1.5 h per 7–9 B model, ≈ 3 h per 12–14 B model, mostly unattended |
| **2** | **Citation fidelity / structured answer generation** | Claim-level verifiability is a product requirement; current citations are paragraph-level | High for trust; also likely improves fact retention (one claim per evidence item) | Medium: prompt/format + validator changes, evaluated on the same evidence snapshot |
| **3** | **Production hardening** | Required before real users regardless of model | Medium-high, low risk | Small: install unit, disk cleanup, monitoring, backup, auth if exposed |
| 4 | Numerical fact preservation | Folded into 1 and 2; dedicated prompt rule showed no gain | Low as a separate item | — |
| 5 | Better generation fidelity (generic) | Subsumed by 1 and 2 | — | — |
| 6 | Qwen replacement (deployment) | Only after 1 produces a winner that meets the decision rule | Conditional | Small once decided |

**Why this order.** Retrieval already delivers most evidence; the measurable loss is between evidence and answer. A model comparison on frozen evidence is the cheapest way to learn whether that loss is model-bound. Citation structure is the next lever if models are similar. Hardening is necessary but does not change answer quality, so it runs in parallel.

## 4. Success criteria for the next phase

| Criterion | Target |
|---|---|
| Generation fidelity (facts stated ÷ visible) | ≥ 90 % on the full set |
| Citation accuracy (stated facts cited to a supporting block) | ≥ 85 % |
| Numerical accuracy | ≥ 98 % (no unsupported numbers except verified derivations) |
| Out-of-corpus | 0 claims; ≥ 20 controls; abstention correct on all |
| Validation failures | 0 |
| Latency | median ≤ 150 s end-to-end, warm |
| Regression guard | L1 facts visible ≥ 88 % dev / 81 % held-out; L2 coverage ≥ 0.66 / 0.53 |

## 5. Detailed execution plan

| Step | Work | Output | Gate |
|---|---|---|---|
| 0 | **Prerequisites** (disk done: 14 GB free; branch merged): merge or tag the branch; free disk (remove unused MedCPT cross-encoder, old benchmark runs, `qwen2.5:1.5b` only if fallback is replaced); add 10 more controls (≥ 22) | Clean baseline, ≥ 9 GB free | Disk ≥ 9 GB free |
| 1 | **Evidence snapshot**: one retrieval pass for all questions; store context + query info; add `--model` / `--snapshot` options to the evaluation runner (no production change) | `benchmark_runs/<ts>_snapshot/` | Snapshot reproduces current fact visibility |
| 2 | **Baseline on snapshot**: qwen2.5:7b, 8 threads | Row 1 of LLM_EVALUATION.md | Matches final baseline within noise |
| 3 | **Screening (≈ 20 questions)**: qwen3:8b, llama3.1:8b, gemma3:12b, phi4:14b (one at a time; remove after recording) | Rows in comparison table | Fidelity ≥ baseline + 5 pts and 0 control claims to advance |
| 4 | **Full set** for finalists (≤ 2 models) | Full metrics incl. manual numerical and citation review | Decision rule in LLM_EVALUATION.md §4 |
| 5 | **Structured citation experiment** on the best model: one-claim-per-line answers with a citation per claim, validator enforces claim-level citations | Citation accuracy and fidelity deltas | Citation accuracy ≥ 85 % without fidelity loss |
| 6 | **Adopt** winner (model tag + prompt/format) behind configuration; rerun final baseline | Updated PROJECT_STATE.md, PIPELINE_REPORT.md | All success criteria met or owner sign-off |
| 7 | **Hardening (parallel)**: install systemd unit, log rotation, nightly index/backup check, disk alert, auth/reverse proxy if exposed | Ops checklist complete | Service survives reboot warm |

## 6. Is evaluating alternative LLMs justified now?

**Yes.**
- Retrieval delivers 81–88 % of expected facts; the next measurable loss (15–20 % of visible facts, weak claim-level citations) sits in generation.
- The one prompt-level intervention tested did not change fact recall, which points to model behaviour rather than instructions.
- The evaluation is cheap and low-risk: frozen evidence, existing harness, no production change, about a day of mostly unattended runs.
- The hardware envelope admits several 7–14 B candidates. 7–9 B models keep current latency; 12–14 B models (≈ 3–4 min) are worth testing only to learn whether size buys fidelity.
- Precondition: free disk space first (6.4 GB free today).

## 7. Handoff notes for future development
- Read [PROJECT_STATE.md](PROJECT_STATE.md) first, then [OPERATIONS.md](OPERATIONS.md).
- Never judge changes from `debug_runs/`; use the benchmark harness (`src/evaluation/run_benchmark.py`) and record results in the relevant document.
- Rebuild the paper index after any passage-index rebuild.
- Reopen retrieval work only if held-out fact visibility drops or new question types appear.
- Keep `RETRIEVAL_MODE=legacy` available until the next model decision is complete.
