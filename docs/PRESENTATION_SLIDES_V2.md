# Presentation Slides — Version 2 (tables and numbers)

Goal of this version:
1. Show the manager the complete work done.
2. Show the model evaluation results.
3. Show what works on a company laptop with a given amount of RAM.
4. Show how much knowledge fits in a given amount of storage, and how much space each MB of documents takes.

Format: one slide per heading, ready to paste into PowerPoint Copilot. Every chart lists its exact data. Use the numbers as written: percentages are plain numbers on a 0–100 axis, so do **not** apply a % number format to them.
Figures were measured on the project VM unless marked *est.* (estimated).

---

## Slide 1 — Pharma Research Intelligence Assistant
| | |
|---|---|
| What | Private, cited answers from research papers |
| How | Local AI on one company VM |
| Privacy | No document leaves the machine |
| Built | Oct 6–16, 2026 · 35 commits |

Visual: Title slide, document-and-shield icon.

---

## Slide 2 — What I Delivered (complete work)
| Area | Delivered | Number |
|---|---|---|
| Working system | Web page, API, Linux service | 1 VM, 24/7 |
| Knowledge base | Papers indexed / passages | 568 / 11,239 |
| Retrieval redesign | Paper-first retrieval | facts found 50 → 88 % |
| Quality testing | Benchmark questions / automated tests | 49 / 66 |
| Model evaluation | Model configurations / answers scored | 7 / 315 |
| Operations fixes | Memory crash fix, speed tuning | 12.9 → 7.8 GB; 18–25 % faster |
| Documentation | Design, evaluation and operations docs | 22 documents |

Visual: Seven-tile grid with large numbers.

---

## Slide 3 — Work Timeline
| Phase | Work | Outcome |
|---|---|---|
| 1. Discovery | Code review, architecture map | Problems listed |
| 2. Measurement | Benchmark + test harness | Baseline numbers |
| 3. Root cause | 10+ retrieval experiments | Real cause found |
| 4. Redesign | Paper-first retrieval | Facts 50 → 88 % |
| 5. Answer fixes | Repair, API, determinism | Failures 5 → 0 |
| 6. Service | Web page, API, systemd | Usable product |
| 7. Model study | 7 configurations, same evidence | Qwen 2.5 7B kept |
| 8. Hardening | Memory fix, privacy check | Pilot-ready |

Visual: Horizontal 8-step timeline.

---

## Slide 4 — Business Problem
| Today | With the assistant |
|---|---|
| Read many papers manually | Ask one question |
| Slow synthesis, slow checking | Cited answer in ~100 s |
| Public AI leaks data, invents facts | Runs locally, refuses when unsure |
| **[TO FILL]** hours per question | **[TO FILL]** target users |

Visual: Two-column before/after.

---

## Slide 5 — Success Criteria
| Priority | Criterion | Target | Result |
|---|---|---|---|
| 1 | Correct answers | No invented claims | 85 % of facts; 0 invented |
| 2 | Grounded | Every claim cited | Cited + validated |
| 3 | Retrieval | Right evidence found | 88 % / 81 % |
| 4 | Speed | 90–150 s | ~100 s |
| — | Limits | Local, CPU, 16 GB | Met |

Visual: Table with green ticks in the Result column. Put "Local · CPU-only · 16 GB VM" as a footer line, **not** over the table.

---

## Slide 6 — Solution at a Glance
| Step | What happens | Number |
|---|---|---|
| 1 Search papers | Find the right studies | 568 papers |
| 2 Select passages | Best evidence inside them | 8 passages |
| 3 Write locally | Qwen 2.5 7B writes the answer | ~96 s |
| 4 Validate | Check every citation | 0 failures |
| Refuse | No relevant paper → no answer | ~4 s |

Visual: Four boxes with arrows, plus a "Refuse" side branch.

---

## Slide 7 — Architecture
- Offline: XML → parse → paper index + passage index
- Online: question → retrieve → rerank → Qwen → validate
- No external service at runtime

Visual: Architecture diagram (PRESENTATION_PACKAGE.md, Diagram 3.1).

---

## Slide 8 — Key Innovation: Paper-First Retrieval
| Measure | Old method | New method |
|---|---|---|
| Right paper found | 94 % | 94 % (kept) |
| Answer passage found | 35 % | paper searched in depth |
| Facts reaching the AI | 50 % | **88 %** |
| Single-study questions | 2 passages | **6 + 2 passages** |
| Broad questions | mixed | **1 passage × 8 papers** |

Visual: Funnel, 568 papers → top papers → 8 passages.

---

## Slide 9 — How It Was Tested
| Item | Number |
|---|---|
| Benchmark questions | 49 |
| Expected facts | 68 |
| Held-out questions (never used for tuning) | 22 |
| Out-of-scope test questions | 12 |
| Answers scored in the model study | 315 |
| Automated tests | 66 |

Visual: Donut chart, 22 held-out / 27 tuning, with the table beside it.

---

## Slide 10 — Retrieval Results
| Metric | Before | After |
|---|---|---|
| Facts reaching AI (tuning set) | 50 | 88 |
| Facts reaching AI (held-out) | 50 | 81 |
| Multi-paper coverage (tuning set) | 41 | 66 |
| Multi-paper coverage (held-out) | 30 | 53 |
| Questions with no evidence | 5 | 0 |

Chart: grouped bars from rows 1–4; values are percent; **y-axis 0–100**.

---

## Slide 11 — Answer Quality
| KPI | Value |
|---|---|
| Available facts stated | **85 %** |
| Out-of-scope questions with invented claims | **0 of 12** |
| Out-of-scope refused without the AI (~4 s) | **9 of 12** |
| Validation failures | **5 → 0** |
| Remaining gap | Some secondary statistics omitted |

Visual: Four KPI tiles.

---

## Slide 12 — Model Evaluation Results
Same evidence for every model; 8 CPU threads.

| Model | Facts kept (of 40) | Median time | RAM needed | Disk | Verdict |
|---|---|---|---|---|---|
| **Qwen 2.5 7B (Q4)** | **32** | **90–96 s** | **5.2 GB** | **4.7 GB** | **Selected** |
| Qwen 2.5 7B (Q8) | 28 | 116 s | 9.2 GB | 8.1 GB | Slower, no gain |
| Qwen 3 4B | 34 | 128 s | 4.0 GB | 2.5 GB | Small laptops* |
| Qwen 3 8B | 32 | 160–175 s | 6.4 GB | 5.2 GB | Slower |
| Llama 3.1 8B | 27 | 127 s | 6.0 GB | 4.9 GB | Weaker |
| Gemma 3 12B | 33 | 215 s | 9.8 GB | 8.2 GB | Too slow |
| Phi-4 14B | 33 | 224 s | 10.5 GB | 9.1 GB | Too slow |

\* Qwen 3 4B: verbose answers and 2 number errors; validate before use. ± 2 facts is normal run-to-run variation.

Visual: The table, with the Qwen 2.5 7B row highlighted.

---

## Slide 13 — Quality vs Speed Trade-off
Chart: **bubble/scatter**. X = median seconds, Y = facts kept (of 40), bubble size = RAM in GB.

| Model | X (s) | Y (facts) | Bubble (GB) |
|---|---|---|---|
| Qwen 2.5 7B Q4 | 90 | 32 | 5.2 |
| Qwen 2.5 7B Q8 | 116 | 28 | 9.2 |
| Qwen 3 4B | 128 | 34 | 4.0 |
| Llama 3.1 8B | 127 | 27 | 6.0 |
| Qwen 3 8B | 160 | 32 | 6.4 |
| Gemma 3 12B | 215 | 33 | 9.8 |
| Phi-4 14B | 224 | 33 | 10.5 |

Callout: "Bigger models: +1 fact, 2.3× slower, 2× RAM."
Axes: X 0–250, Y 20–40.

---

## Slide 14 — Why Some Facts Are Still Missed
| Tested | Result | Decision |
|---|---|---|
| Bigger model | ± 1–2 facts | Not worth it on CPU |
| Higher precision (Q8) | 28 vs 32 facts, +30 % time | Keep Q4 |
| Fewer passages (4) | 80 % → 59 % | Keep 8 |
| Evidence order | No effect | No change |
| Answer length | No effect | No change |

Diagnosis: the model skips minor statistics, even when the evidence contains them.

---

## Slide 15 — Latency Breakdown
| Part of one answer | Seconds | Share |
|---|---|---|
| AI reads the evidence | 43 | 45 % |
| AI writes the answer | 51 | 54 % |
| Search and selection | 5 | 5 % |
| **Total (median)** | **~100** | p90 ~125 s |
| 8-thread tuning gain | — | 18–25 % faster |
| With a GPU *(est.)* | 10–20 | — |

Chart: **one** horizontal stacked bar: 43 | 51 | 5, labelled "Read 43 s", "Write 51 s", "Search 5 s".

---

## Slide 16 — Resources on the Current VM
| Resource | Used | Available |
|---|---|---|
| CPU | 8 of 8 vCPU while answering | idle otherwise |
| RAM (model) | 5.2 GB (max 7.8–8.6 GB) | 16 GB |
| RAM (app) | 1.2–2.0 GB | — |
| Disk (whole system) | ~9 GB | 29 GB disk |
| Throughput | ~35 answers / hour | one at a time |
| VM | Azure D8ls_v6, CPU only | — |

Visual: Three gauges (CPU 100 %, RAM ≈ 50 %, disk ≈ 31 %).

---

## Slide 17 — Critical Fix: Memory Growth
| | Before fix | After fix |
|---|---|---|
| Model memory after 40 answers | 12.9 GB, still rising | 6.0 GB |
| Highest memory | 13.2 GB at cap (≈ crash on 16 GB) | 7.8–8.6 GB |
| Errors in 75 live answers | — | 0 |
| Answer quality | — | unchanged (107 vs 106 facts) |
| Cost | — | ~6 s reload, between requests |

Chart: line chart, X = answers, Y = GB (axis 4–14).

| Answers | 1 | 10 | 20 | 30 | 40 | 50 |
|---|---|---|---|---|---|---|
| Before fix | 5.2 | 7.0 | 9.0 | 11.0 | 12.9 | 13.2 (cap) |
| After fix | 5.2 | 7.0 | 5.4 | 7.4 | 6.0 | 7.9 |

The "After fix" line is a sawtooth that drops at each reload. These are measured values, not a schematic.

---

## Slide 18 — Company Laptop: What Works by RAM
Office apps, browser and security tools already use ~6–8 GB. The assistant needs model memory plus ~2 GB for the app.

| Laptop RAM | Free for AI | Qwen 3 4B (needs ~6 GB) | Qwen 2.5 7B (needs ~7–10 GB) | 12–14B models (need ~12–13 GB) | Verdict |
|---|---|---|---|---|---|
| 8 GB | ~1–2 GB | ❌ | ❌ | ❌ | Not supported |
| 16 GB | ~8–10 GB | ✅ | ⚠ close other apps | ❌ | Single user, light use |
| 32 GB | ~24 GB | ✅ | ✅ | ⚠ fits, ~4 min answers | **Recommended** |
| 64 GB | ~56 GB | ✅ | ✅ | ⚠ fits, still slow on CPU | Works; GPU better |

Answer time on a laptop CPU: ~1.5–3 min; on Apple Silicon ~20–60 s *(est.)*.

---

## Slide 19 — Storage: How Much Knowledge Fits
The system itself needs **8.9 GB** (Qwen 2.5 7B) or **6.7 GB** (Qwen 3 4B). Each document needs **0.53 MB**, or 0.95 MB with a backup copy. 20 % of the disk is kept free.

| Free disk on laptop | Space left for documents | Documents (no backup) | Documents (with backup) |
|---|---|---|---|
| 20 GB | 7 GB | ~13,000 | ~7,500 |
| 50 GB | 31 GB | ~58,000 | ~33,000 |
| 100 GB | 71 GB | ~134,000 | ~75,000 |
| 250 GB | 191 GB | ~360,000* | ~200,000* |

\* RAM limits this before disk does: the search index needs ~64 KB of RAM per document, so a 16 GB laptop holds ~15–30k documents and a 32 GB laptop ~150k.

Visual: Stacked bars per disk size (system / documents / free reserve).

---

## Slide 20 — Knowledge Storage per MB
| Input | Storage needed | RAM needed |
|---|---|---|
| 1 MB of plain document text | ~10.5 MB of index | ~1.5 MB |
| 1 MB of PubMed XML | ~3.5 MB index + 1 MB source = **~4.5 MB** | ~0.5 MB |
| 1 paper (~20 pages) | **0.53 MB** | 64 KB |
| 1,000 papers | **0.53 GB** (0.95 GB with backup) | 64 MB |
| 10,000 papers | 5.3 GB | 0.64 GB |
| 100,000 papers | 53 GB | 6.4 GB |

Why the index is larger than the text: every passage stores the text, a search vector and a search graph.
Indexing time: ~45 min per 1,000 papers (this VM).

Visual: Simple conversion graphic, "1 MB text → 10.5 MB index", with the table below.

---

## Slide 21 — Deployment Options
| Hardware | Answer time | Users | Documents | Status |
|---|---|---|---|---|
| 16 GB laptop | 1.5–3 min | 1 | 15–30k | *est.* |
| 32 GB laptop | 1.5–2 min | 1–2 | ~150k | *est.* |
| **Current VM (16 GB)** | **~100 s** | **5–10** | **+15k on current disk** | **measured** |
| Small server, CPU, 64 GB | 40–80 s | 15–30 | ~500k | *est.* |
| Department GPU server | 10–20 s | 100–150 | 1M+ | *est.* |

Visual: Ladder from laptop to GPU server.

---

## Slide 22 — Privacy and Security
| Check | Result |
|---|---|
| Documents / questions / answers leave the machine | **No**: network traffic measured, loopback only |
| Cloud AI used | No |
| Telemetry | None |
| Ollama connection to ollama.com | Found; blocked by 1 setting + firewall (admin step) |
| Login / encryption / retention policy | Not yet: next work package |

Visual: Machine boundary with a blocked arrow to ollama.com.

---

## Slide 23 — Results vs Objectives
| Objective | Result | Status |
|---|---|---|
| Correct answers | 85 % of available facts | ✅ |
| No invented claims | 0 of 12 out-of-scope | ✅ |
| Retrieval | 88 % tuning / 81 % held-out | ✅ |
| Speed | ~100 s | ✅ |
| Local, memory-safe | 7.8–8.6 GB max on 16 GB | ✅ |
| Pilot readiness | 2 admin steps left | ⚠ |

---

## Slide 24 — Limitations and Roadmap
| Limitation | Fix | When |
|---|---|---|
| Ollama contacts ollama.com; no auto-start | Admin setting + auto-start | Now (hours) |
| No login or access control | Login, access rules, retention | Next |
| PubMed XML only | PDF/DOCX ingestion + re-test | Next |
| ~15 % of facts omitted | Better answer structure, claim citations | Next |
| ~100 s, one at a time | GPU server | Later |

---

## Slide 25 — Decisions Requested
| # | Decision | Detail |
|---|---|---|
| 1 | Approve pilot | 3–5 researchers, current VM |
| 2 | Approve next work package | Login, PDF/DOCX, answer structure |
| 3 | GPU server? | 10–20 s answers, 100+ users *(est.)* |

Lessons: measure first · bigger models aren't better on CPU · operations matter as much as quality.

---

## Fixes needed in the current PDF (PPTreview2)
| Slide | Problem | Fix |
|---|---|---|
| 3 | "LOCAL • CPU-ONLY • 16 GB VM" text overlaps the pyramid | Move it to the footer (Slide 5 above) |
| 4 | "every claim checked" overflows its box | Shorten to "every claim checked" on one line, or widen the box |
| 6 | Side notes ("Apache 2.0 • fully local") overlap the "Why this mix" column | Use the table (Slide 2 / tech table) or remove the notes |
| 9 | Y-axis shows 0–10000 % | Enter plain numbers (50, 88) with a 0–100 axis, no % format |
| 9 | "+38 pts" | Correct (88 − 50); keep |
| 11 | Scatter plots overall scores (34 vs 35) at x = 1, and puts the 12–14B class *above* Qwen | Replace with the Slide 13 data (latency vs facts, bubble = RAM) |
| 13 | Stacked bar split into two rows; 43 s label missing | One stacked bar: 43 / 51 / 5 |
| 15 | Chart is "schematic"; the after-fix line starts at 7.8 GB and the before-fix line reaches 12.9 GB at 75 answers | Use the measured series in Slide 17: before 12.9 GB at 40 answers; after starts at 5.2 GB, sawtooth |
| 18 | "88 % overall" | It is the tuning set: "88 % tuning / 81 % held-out" |
| Missing | Laptop RAM, storage and per-MB slides; work-done summary | Add Slides 2, 3, 18, 19, 20 |
