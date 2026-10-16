# Model Deployment Comparison — Operational View for Decision-Makers

Date: 2026-10-16 · Companion to [ENTERPRISE_DEPLOYMENT_ASSESSMENT.md](ENTERPRISE_DEPLOYMENT_ASSESSMENT.md) (deployment strategy) and [LLM_EVALUATION.md](LLM_EVALUATION.md) (quality evidence).
**Measured** = on the project VM (Azure, 8 vCPU = 4 cores × 2 threads, 16 GB RAM, no GPU, no swap, Ollama 0.40.2), identical stored evidence, 8 threads, 8 K context. **Estimated** = projection from those measurements; confirm on target hardware with `src/evaluation/model_comparison.py` before purchase or rollout.

---

## 1. Bottom line

**Best combination for private documents, local inference, acceptable latency, manageable RAM and storage, and good answer quality:**

> **Qwen 2.5 7B Instruct, Q4_K_M** on a **32 GB machine**, which can be a laptop, the current VM size with RAM doubled, or a small server. Run it with the prompt-cache memory bound and Ollama's internet access blocked. For a department, run the same model on **a server with one 16–24 GB GPU**.

Why:
- It has the best fact retention of the models that answer in under 2 minutes (85 %).
- It writes the shortest answers.
- It needs the smallest working memory of the 7–8 B models: 5.2 GB, plus a prompt cache that grows only 0.19 GB per answer, the slowest of all tested models.
- It takes 4.7 GB of disk.
- Its licence is Apache 2.0.

No alternative model or quantization improved quality enough to justify more RAM, disk or latency.

## 2. Per-model operational profile (measured)

| | **Qwen 2.5 7B Q4_K_M** | Qwen 2.5 7B Q8_0 | Qwen 3 4B Q4_K_M¹ | Qwen 3 8B Q4_K_M | Llama 3.1 8B Q4_K_M | Gemma 3 12B Q4_K_M | Phi-4 14B Q4_K_M |
|---|---|---|---|---|---|---|---|
| Ollama tag | `qwen2.5:7b` | `qwen2.5:7b-instruct-q8_0` | `qwen3:4b-instruct-2507-q4_K_M` | `qwen3:8b` | `llama3.1:8b` | `gemma3:12b` | `phi4:14b` |
| Parameters | 7.6 B | 7.6 B | 4.0 B | 8.2 B | 8.0 B | 12.2 B | 14.7 B |
| **Model file size** | **4.68 GB** | 8.10 GB | 2.50 GB | 5.23 GB | 4.92 GB | 8.16 GB | 9.05 GB |
| **RAM when loaded** (runner, 8 K context; range over runs) | **5.2 GB** | 9.2–9.4 GB | 4.0 GB | 6.4–6.9 GB | 6.0 GB | 9.8 GB | 10.5 GB |
| **Prompt-cache growth per answer** | **0.19 GB** | 0.19 GB | 0.53 GB | 0.53 GB | 0.43 GB | 1.16 GB | ≈ 0.68 GB² |
| Answers until cache cap (8 GB) | ≈ 42 | ≈ 42 | ≈ 15 | ≈ 15 | ≈ 19 | ≈ 7 | ≈ 12 |
| **Peak RAM during extended use** (runner + 8 GB cache cap) | **13.2 GB** (12.9 GB observed after 40 answers) | 17.4 GB | 12.0 GB | 14.9 GB | 14.0 GB | 17.8 GB | 18.5 GB |
| Peak RAM, extended use, with cache bound (§5) | **7.8–8.6 GB (measured, 75 answers)** | ≈ 11–12 GB | ≈ 6–7 GB | ≈ 9–10 GB | ≈ 8–9 GB | ≈ 12–13 GB | ≈ 12–13 GB |
| CPU usage | 8 of 8 vCPU (7.96 avg) | 8 (7.96) | 8 (7.95) | 8 (7.95) | 8 (7.95) | 8 (7.95) | 8 (7.97) |
| **Prompt processing** | **77 tok/s** | 53 tok/s | 101 tok/s | 65 tok/s | 67 tok/s | 43 tok/s | 36 tok/s |
| **Generation** | **7.3 tok/s** | 6.2 tok/s | 6.9 tok/s | 4.9 tok/s | 5.4 tok/s | 4.2 tok/s | 3.3 tok/s |
| Answer length (median) | **370 tokens** | 326 | 616 | 566 | 378 | 594 | 442 |
| **Median answer latency** (generation; end-to-end ≈ +6 s) | **96 s** (full set) / 90 s (screening) | 116 s | 128 s | 175 s (full) / 160 s (screening) | 127 s | 215 s | 224 s |
| **P90 latency** (generation) | **114 s** / 106 s | 144 s | 165 s | 209 s / 201 s | 147 s | 244 s | 256 s |
| **Warm-up**: model load from OS cache | 7.5 s | ≈ 10–15 s (est.) | 22.5 s | 9.3 s | ≈ 10–15 s³ | 12.7 s | 14.9 s |
| Warm-up: cold, after VM boot | 134 s (measured, plus 79 s app start) | ≈ 230 s (est.) | ≈ 70 s (est.) | ≈ 150 s (est.) | ≈ 140 s (est.) | ≈ 235 s (est.) | ≈ 260 s (est.) |
| **Answers per hour** (one at a time) | **≈ 35** | ≈ 29 | ≈ 27 | ≈ 20 | ≈ 27 | ≈ 16 | ≈ 15 |
| **Storage required** (model + fixed stack 4.2 GB⁴) | **8.9 GB** | 12.3 GB | 6.7 GB | 9.4 GB | 9.1 GB | 12.4 GB | 13.3 GB |
| Fact retention (quality, adjudicated) | **85 % full set**; 32/40 screening | 28/40 | 34/40 | 81 % full set; 32/40 | 27/40 | 33/40 | 33/40 |
| Out-of-corpus answers | correct, concise | correct, concise | correct, concise | correct, verbose | correct | correct, padded | correct, padded |
| Numerical errors (screening) | 1 | 0 | 2 | 0 | 0 | 0 | 0 (1 unverified) |
| Licence | Apache 2.0 | Apache 2.0 | Apache 2.0 | Apache 2.0 | Llama 3.1 Community | Gemma Terms | MIT |

¹ Qwen 3 4B was measured on the 20-question screening set only.
² Phi-4 reloaded on every answer under the memory guard, so its growth was computed from its architecture (40 layers × 10 KV heads × 128 dims × 2 bytes × ≈ 3,300 tokens). The same formula reproduces the measured values of every other model within ± 0.05 GB.
³ The first Llama load took 102 s directly after download; later loads come from the OS cache.
⁴ Fixed stack:
- Python environment 1.8 GB
- retrieval models 1.0 GB
- Qwen 2.5 1.5B query helper 1.0 GB
- Ollama runtime 0.1 GB
- current corpus 0.3 GB

Licences: verify with legal before adoption.

**Reading the table:**
- **RAM when loaded** is what the model needs at the start.
- **Peak RAM during extended use** is what it reaches after many questions if the prompt cache is not bounded. Ollama keeps up to 8 GB of past prompts in memory per loaded model, and offers no setting to change that.
- On a 16 GB machine without swap, three models exceed physical RAM in extended use: Q8_0, Gemma 3 12B and Phi-4.

## 3. Hardware deployment estimates

Assumptions:
- The application (retrieval models, vector database, web service) needs ≈ 1.2–1.7 GB (measured).
- The operating system needs ≈ 1–2 GB.
- Corporate laptops also run office, browser and security software: ≈ 6–9 GB (estimated).
- Prompt cache bounded as in §5.

| | 16 GB laptop | 32 GB laptop | **Current VM** (8 vCPU, 16 GB) | Small server (16–32 vCPU, 64 GB, CPU only) | Department server (32+ cores, 128 GB, 1–2 GPUs with 24 GB) |
|---|---|---|---|---|---|
| Recommended model | Qwen 3 4B (after full validation) or Qwen 2.5 7B with office apps closed | **Qwen 2.5 7B Q4_K_M** | **Qwen 2.5 7B Q4_K_M** | **Qwen 2.5 7B Q4_K_M** | Qwen 2.5 7B Q4_K_M; re-test Gemma 3 12B / Phi-4 on GPU |
| RAM available for the index after model + app + OS | ≈ 1–2 GB | ≈ 10–14 GB | ≈ 4–6 GB | ≈ 45 GB | ≈ 100 GB |
| **Maximum practical corpus** (RAM ≈ 64 KB per document in the vector index) | ≈ 15,000–30,000 docs | ≈ 150,000 docs | ≈ 50,000 docs (RAM); disk: ≈ 15,000 more on the current 29 GB disk | ≈ 500,000 docs (disk-bound: ≈ 265 GB) | 1,000,000+ docs (indexing time becomes the limit) |
| **Query latency** | ≈ 1.5–3 min on x86 CPU; ≈ 30–60 s on Apple Silicon GPU (est.) | same CPU → same latency; ≈ 20–45 s on Apple Silicon (est.) | **≈ 100 s median, ≈ 120 s p90 (measured)** | ≈ 40–80 s (est.; more cores speed up prompt reading) | ≈ 10–20 s with 7 B; ≈ 20–40 s with 12–14 B (est.) |
| **Indexing** (per 1,000 docs) | ≈ 45–60 min (est.; plugged in) | ≈ 45–60 min (est.) | **≈ 45 min (measured)** | ≈ 20–30 min (est.) | ≈ 5–10 min with GPU embeddings (est.) |
| **Answers per hour** | ≈ 20–35 | ≈ 20–35 | **≈ 35** | ≈ 45–90 | ≈ 200–400 (parallel slots, est.) |
| **Concurrent users** (2–3 questions per user per hour) | 1 | 1–2 | ≈ 5–10 active; 2+ simultaneous users queue (≈ 100 s each) | ≈ 15–30 | ≈ 100–150 |
| Verdict | Marginal: single, occasional user | **Good for an individual** | **Good for a pilot or a small team** | Good for a team | Department scale |

### Disk growth by corpus size (measured rate 0.53 MB per paper-sized document, ≈ 20 pages)

| Corpus | Index + documents | + one index backup | Total disk with Qwen 2.5 7B Q4 stack (8.9 GB) | Indexing time, this VM |
|---|---|---|---|---|
| 1,000 docs | 0.53 GB | 0.95 GB | ≈ 9.9 GB | ≈ 45 min |
| 10,000 docs | 5.3 GB | 9.5 GB | ≈ 18 GB | ≈ 7.5 h |
| 50,000 docs | 27 GB | 48 GB | ≈ 57 GB | ≈ 37 h |
| 100,000 docs | 53 GB | 95 GB | ≈ 104 GB | ≈ 75 h (≈ 3 days) |

Other disk growth:
- Request records: ≈ 20 KB per question (measured), so ≈ 0.6 GB per 30,000 questions.
- Service logs: negligible.
- Each additional model adds its file size from §2.

## 4. Operational risks

Severity: impact if it happens. Probability: on a 16 GB machine running the service continuously, unless stated otherwise.

### 4.1 Risks common to all models

| Risk | Finding (measured) | Severity | Probability | Mitigation |
|---|---|---|---|---|
| **Prompt-cache growth** | Ollama 0.40.2 launches its model server with a RAM prompt cache capped at 8,192 MiB, with no setting. Each answer adds that prompt's working state (§2). Observed: Qwen 2.5 runner 5.2 → 12.9 GB over 40 answers (log: "39 prompts, 7,804 MiB"). **Mitigated 2026-10-16**: runner held at ≤ 7.8–8.6 GB over 75 live answers, 0 errors, no quality change ([OPERATIONS.md §7](OPERATIONS.md)) | High → **Low (residual)** | Was high; now low | Service unloads the model (`keep_alive: 0`) when available RAM < 3.5 GB or every N answers. The reload costs ≈ 8 s, and this approach was validated during the evaluation. Alternatively set `OLLAMA_KEEP_ALIVE` to a finite value. Re-test after every Ollama upgrade |
| **RAM exhaustion** | No swap on the VM, so exceeding RAM gets processes killed. Query helper (Qwen 2.5 1.5B, 1.4 GB) loads alongside the main model when needed | **High** | Medium–high (depends on model; §4.2) | Bound the cache; add 4–8 GB swap on VMs as a safety net; one main model per host; monitor `MemAvailable` |
| **Memory leaks** | None found: service process 1.2 GB after 11 h 19 min uptime (peak 1.7 GB at start-up); Ollama daemon 33 MB. Runner growth is the cache above, not a leak | Low | Low | Keep monitoring RSS; weekly restart is optional |
| **Ollama cache behaviour on model switch** | Loading a different model evicts the previous runner and its cache; keep-alive forever keeps the runner and cache resident indefinitely | Medium | Medium | One production model per host; schedule model changes; avoid ad-hoc `ollama run` on production hosts |
| **Context-window risks** | `num_ctx` 8,192. Largest observed prompt + answer: 4,494 tokens (Qwen 2.5 7B) to 4,943 (Qwen 3 4B, 957-token answer); all answers ended normally (`stop`), none hit the limit. Ollama silently truncates input beyond `num_ctx` | Medium | Low today; **high** if evidence blocks, passage length or answer length are increased | Keep 8 evidence blocks × 1,200 characters; alert when prompt + answer > 7,000 tokens; raising `num_ctx` raises RAM (working state) linearly |
| **Disk exhaustion** | Disk 70 % used; model downloads 2.5–9 GB each; index rebuild needs ≈ 2× index size; request records ≈ 20 KB per question | Medium | Medium on the current 29 GB disk; low on ≥ 128 GB | Keep ≥ 20 % free; alert at 80 %; rotate `debug_runs/` and `logs/`; remove unused models (`ollama rm`) |
| **Long-running service** | Service auto-start is **disabled** (`systemctl is-enabled pharma-rag` = disabled); cold start after boot ≈ 3.5 min; requests are serialized (one at a time); the web page has no login | Medium | High after any reboot | `sudo systemctl enable pharma-rag`; health check before use; show queue status in the UI; add authentication |
| **Ollama egress** | The Ollama daemon opens a TLS connection to ollama.com ≈ 1 s after start-up (before any request) and keeps it open; requests for `*-cloud` model names are forwarded to ollama.com. With `OLLAMA_NO_CLOUD=1`: no connection, cloud models refused (measured on an isolated instance). Application traffic stayed on loopback | High (compliance) | Certain (observed) | `OLLAMA_NO_CLOUD=1`; egress deny for the `ollama` user; pin the Ollama version ([OPERATIONS.md §8](OPERATIONS.md)) |
| **Ollama upgrades** | Cache size, templates and network behaviour are version-specific | Medium | Medium | Pin the version; re-run the benchmark harness before upgrading |

### 4.2 Model-specific risk levels (16 GB host, cache not bounded / bounded)

| Model | Peak RAM unbounded | RAM exhaustion risk (unbounded → bounded) | Cache-growth risk | Context risk | Disk risk (model file) | Long-running service risk | Notes |
|---|---|---|---|---|---|---|---|
| **Qwen 2.5 7B Q4_K_M** | 13.2 GB | **Medium → Low** | Low growth per answer (cap after ≈ 42 answers) | Low (max 4,494 tokens) | Low (4.7 GB) | Low with fix | Best operational profile |
| Qwen 2.5 7B Q8_0 | 17.4 GB | **High → Medium** | Same per answer, higher base | Low | Medium (8.1 GB) | Medium | Exceeds 16 GB unbounded |
| Qwen 3 4B | 12.0 GB | Medium → Low | High growth (cap after ≈ 15 answers) | **Medium** (long answers, max 4,943 tokens) | Low (2.5 GB) | Low–medium | Needs an answer-length limit |
| Qwen 3 8B | 14.9 GB | **High → Medium** | High (≈ 15 answers) | Medium (max 4,567) | Low (5.2 GB) | Medium | Must run with `think: false` (otherwise minutes of hidden reasoning) |
| Llama 3.1 8B | 14.0 GB | High → Low–medium | Medium–high (≈ 19 answers) | Low | Low (4.9 GB) | Medium | — |
| Gemma 3 12B | 17.8 GB | **Critical → Medium** | **Very high** (1.16 GB per answer; cap after ≈ 7) | Medium (max 4,762) | Medium (8.2 GB) | High | Needed 12 reloads in 20 answers |
| Phi-4 14B | 18.5 GB | **Critical → High** | High (≈ 0.68 GB per answer) | Low | Medium (9.1 GB) | High | Needed a reload before every answer on 16 GB |

On 32 GB hosts every risk level drops by one step. On a GPU server, model weights and the per-prompt working state sit in GPU memory, but Ollama's host-RAM prompt cache still applies, so keep the same fix.

## 5. Required operating configuration (all deployments)

1. **Bound prompt-cache memory** — **implemented**: the service reloads the model between requests after 20 answers or when available RAM falls below 4 GB, and at start-up; tune per deployment ([OPERATIONS.md §7.8](OPERATIONS.md)).
2. **Block internet access for Ollama**: set `OLLAMA_NO_CLOUD=1` and an egress firewall rule. Install models offline (download once, verify the checksum, copy to hosts).
3. **Enable auto-start** of the service, plus a health check; add swap on VMs.
4. **Monitor** available RAM, disk use, answer latency and queue length.
5. **Rotate** request records and logs; encrypt the disk; add authentication before multi-user use.

## 6. Final recommendation — total operational comparison

Scores: 5 = best. Quality, latency, RAM and storage scores come from measurements. Scalability, privacy and maintainability are qualitative judgements.

| Criterion | Qwen 2.5 7B Q4 | Qwen 2.5 7B Q8 | Qwen 3 4B | Qwen 3 8B | Llama 3.1 8B | Gemma 3 12B | Phi-4 14B |
|---|---|---|---|---|---|---|---|
| Answer quality (retention, numbers, abstention) | **5** | 3 | 4 | 4 | 2 | 4 | 4 |
| Latency | **5** | 4 | 4 | 2 | 4 | 1 | 1 |
| Memory consumption (incl. cache growth) | **5** | 2 | 4 | 3 | 3 | 1 | 1 |
| Storage consumption | 4 | 2 | **5** | 4 | 4 | 2 | 2 |
| Scalability (answers per hour per host) | **5** | 4 | 4 | 3 | 4 | 2 | 2 |
| Privacy (all local; same stack) | 5 | 5 | 5 | 5 | 5 | 5 | 5 |
| Maintainability (validated, licence, tuning) | **5** (current, fully validated, Apache 2.0) | 4 | 3 (needs full validation + length limit) | 3 (`think` flag) | 3 (licence terms) | 2 (licence; padding) | 3 |
| **Total (of 35)** | **34** | 24 | 29 | 24 | 25 | 17 | 18 |

**Recommendation**
- **Model:** Qwen 2.5 7B Instruct.
- **Quantization:** Q4_K_M.
- **Hardware:**
  - Individual researcher: a 32 GB laptop (Apple Silicon is the fastest option, estimated).
  - Pilot or team: the current 8 vCPU VM class with 32 GB RAM (or 16 GB plus swap and the cache fix).
  - Department: a server with one 16–24 GB GPU and 64–128 GB RAM.
- **Fallback for constrained devices:** Qwen 3 4B Q4_K_M. Use it only after a full-set validation and with an answer-length limit.
- **Not recommended on CPU:**
  - Gemma 3 12B and Phi-4 14B: about 2.3× slower, more than 2× the memory, and no measurable quality gain.
  - Q8_0: higher RAM and disk, and slower, with no quality gain.
- **Conditions:** the five operating rules in §5. With them, documents, questions and answers stay inside the organization. Measured on this VM, the application's traffic stayed on loopback.
