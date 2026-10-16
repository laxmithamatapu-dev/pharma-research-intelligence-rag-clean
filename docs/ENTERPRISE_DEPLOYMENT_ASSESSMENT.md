# Enterprise Deployment Assessment — Private, Local-AI Document Intelligence

Date: 2026-10-16 · Basis: measured results on the project VM (Azure, 8 vCPU = 4 cores × 2 threads, 16 GB RAM, no GPU, no swap) from [LLM_EVALUATION.md](LLM_EVALUATION.md), [PIPELINE_REPORT.md](PIPELINE_REPORT.md) and [PROJECT_STATE.md](PROJECT_STATE.md).
Per-model operational detail and risk tables: [MODEL_DEPLOYMENT_COMPARISON.md](MODEL_DEPLOYMENT_COMPARISON.md).
Convention: **measured** values come from this VM; **estimated** values (laptops, servers) are projections from those measurements and public hardware characteristics and must be confirmed with the same benchmark harness before a rollout decision.

---

## 1. Executive Summary

**Yes — a company can run this as a private document-intelligence system without sending documents outside the organization**, with three conditions:
1. **Hardware:** a 32 GB laptop or a small internal VM/server is the realistic minimum for a good experience. A 16 GB laptop works for a single user only with tight memory control. CPU-only answers take **≈ 1.5–2 minutes**; sub-20-second answers need a GPU server.
2. **Two operational fixes:**
   - Bound Ollama's prompt-cache memory, which grows by up to 8 GB per loaded model. **Done 2026-10-16**: the service now keeps the model process at 7.8–8.6 GB on 16 GB (measured over 75 live answers).
   - Block Ollama's outbound connection to ollama.com, measured during normal operation. **Still to apply**: one setting plus a firewall rule, requires an administrator ([OPERATIONS.md §8](OPERATIONS.md)).
3. **Ingestion of internal formats is new work.** Internal formats such as PDF, DOCX and HTML need parsers; the current pipeline ingests PubMed Central XML only.

**Best combination measured:** **Qwen 2.5 7B, Q4_K_M quantization, 8 threads, 8 evidence blocks, 8 K context.** It has the best balance of fact retention (85 %), correct abstention (no claims on any out-of-corpus question), latency (≈ 96 s generation) and RAM (5.2 GB). None of the six alternative models, the Q8_0 quantization, or the prompt and context variants beat it under the project's decision criteria.

**What limits the system next:**
- **Retrieval quality** becomes the main risk as the corpus grows.
- **Generation** stays the main cost in latency and hardware, independent of corpus size.

## 2. Model Comparison Summary

All models received identical stored evidence for the same questions (measured).

| Model / quantization | Disk | RAM (model) | Fact retention¹ | Citations on claim line | Numerical errors | Out-of-corpus | Generation median | Verdict |
|---|---|---|---|---|---|---|---|---|
| **Qwen 2.5 7B Q4_K_M** | 4.7 GB | 5.2 GB | **85 % (full set)**; 32/40 screening | 72 % | 1 | correct, concise | **96 s** | **Production** |
| Qwen 2.5 7B Q8_0 | 8.1 GB | 9.2 GB | 28/40 | 48 % | 0 | correct | 116 s | No gain |
| Qwen 3 8B | 5.2 GB | 6.4 GB | 81 % (full set); 32/40 | 100 % | 0 | correct, verbose | 175 s | Slower, not better |
| Qwen 3 4B-instruct-2507 | 2.5 GB | 4.0 GB | 34/40 | 100 % | 2 | correct, concise | 128 s | Small-device candidate |
| Llama 3.1 8B | 4.9 GB | 6.0 GB | 27/40 | 75 % | 0 | correct | 127 s | Weaker |
| Gemma 3 12B | 8.2 GB | 9.8 GB | 33/40 | 100 % | 0 | correct, off-topic padding | 215 s | Too slow on CPU |
| Phi-4 14B | 9.1 GB | 10.5 GB | 33/40 | 100 % | 0 | correct, off-topic padding | 224 s | Too slow on CPU |

¹ Facts stated ÷ facts present in the evidence; screening = 14 single-paper questions with 40 facts, after manual adjudication of two over-strict gold patterns. Differences of ± 2 facts are within run-to-run noise.

**Is a bigger model worth the extra RAM and latency? No, not on CPU.**
- Gemma 3 12B and Phi-4 14B add about 1 fact (within noise).
- They cost 2.3–2.5× the latency and twice the RAM.
- Their only clear gain is per-claim citation style, which post-processing can enforce more cheaply.
- Revisit them on a GPU server, where their latency drops below 30 s (estimated).

## 3. Recommended Production Model

**Qwen 2.5 7B Instruct, Q4_K_M** (`qwen2.5:7b`, 4.68 GB). Measured reasons:
- Highest fact retention among models with practical latency (85 % full set).
- Concise answers: 370 tokens median versus 440–620 for the others. This is the main reason it is fastest.
- Correct, short abstention on out-of-corpus questions.
- No validation failures.
- 5.2 GB RAM.
- Licence: Apache 2.0 (Qwen 2.5 7B). Confirm with legal for the exact release.

**Option for small devices:** Qwen 3 4B-instruct-2507 Q4_K_M (4.0 GB RAM). Its retention was equal (34/40) and it needs 1.2 GB less RAM. Before production use it needs:
- a full 40-question run;
- an answer-length limit, because its 616-token answers erase its speed advantage;
- a numerical-accuracy check, after 2 errors in one answer.

## 4. Recommended Quantization

**Q4_K_M.** Measured against Q8_0 on the same model and evidence:

| | Q4_K_M | Q8_0 | Change |
|---|---|---|---|
| Disk | 4.68 GB | 8.10 GB | +73 % |
| RAM (runner) | 5.2 GB | 9.2 GB | +4 GB |
| Prefill speed | 77 tok/s | 53 tok/s | −31 % |
| Decode speed | 7.3 tok/s | 6.2 tok/s | −15 % |
| Generation median | 90 s | 116 s | +29 % |
| Facts (screening, adjudicated) | 32/40 | 28/40 | no gain |

Higher precision does not improve fact retention, citations or numbers. Lower precision (Q3_K_M, 3.8 GB) was not tested, so it is not recommended without a run. Q4_K_M is the best trade-off for CPU deployment.

## 5. Laptop Feasibility

Assumptions:
- **Disk:** the base install needs ≈ 8.6 GB:
  - Python environment 1.8 GB
  - retrieval models 1.0 GB
  - Qwen 2.5 7B plus the 1.5B helper model 5.7 GB
  - Ollama 0.1 GB
- **RAM:** the application needs ≈ 1.7 GB plus the model.
- **Corporate laptop load:** Windows or macOS, browser, Teams/Outlook and endpoint security typically use 6–9 GB (estimated).

| | **16 GB laptop** | **32 GB laptop** |
|---|---|---|
| Model fit | Qwen 2.5 7B Q4 (5.2 GB) + app (1.7 GB) ≈ 7 GB → **marginal** with normal office apps open; Qwen 3 4B (4.0 GB) leaves more headroom | Qwen 2.5 7B comfortable; 12–14 B models fit (≈ 12 GB) but are slow |
| Prompt-cache risk (§10) | **High** — the cache can add up to 8 GB; fix is mandatory | Moderate — fix still recommended |
| Expected answer time, x86 CPU (estimated) | ≈ 1.5–3 min (6–8 performance cores; drops on battery and under thermal throttling) | same CPU class → same latency; RAM does not speed up the CPU |
| Expected answer time, Apple Silicon via Metal GPU (estimated) | ≈ 30–60 s on M2/M3-class 16 GB (unified memory is shared with the GPU) | ≈ 20–45 s |
| Corpus capacity — RAM (index ≈ 64 KB per paper) | ≈ 15,000–30,000 papers, using 1–2 GB spare | ≈ 100,000+ papers |
| Corpus capacity — disk (0.53 MB per paper; 50–100 GB free) | ≈ 90,000–180,000 papers | same |
| Indexing (estimated, CPU) | ≈ 45–60 min per 1,000 papers; must run while the laptop is plugged in | same |
| Verdict | **Single user, light use, with memory fix**; prefer Qwen 3 4B after validation | **Recommended laptop tier** for an individual researcher |

Laptop numbers are estimates. Before rollout, run `src/evaluation/model_comparison.py` and `run_benchmark.py` on the target laptop model.

## 6. VM Feasibility

**Current VM** (8 vCPU, 16 GB, CPU only), all values measured:

| Metric | Value |
|---|---|
| Answer time | ≈ 100 s end-to-end (96 s generation + 5–12 s retrieval); p90 ≈ 120 s |
| Out-of-corpus answers | ≈ 4 s (no LLM call) |
| CPU | One answer uses all 8 cores; requests are processed one at a time |
| Throughput | ≈ 35 answers per hour |
| RAM | ≈ 7 GB steady (model 5.2 GB + app 1.7 GB); up to ≈ 15 GB if the prompt cache is not bounded |
| Disk | 29 GB total; 70 % used with two Qwen models and the 568-paper corpus |
| Startup | Cold boot ≈ 3.5 min (79 s loading + 134 s model warm-up); warm restart ≈ 13 s |
| Verdict | **Good for a pilot or a small team** (≈ 5–15 users at a few questions per day each); queueing appears when 2+ users ask at the same time |

**Small department server** (estimated):

| Configuration | Expected answer time | Concurrency | Notes |
|---|---|---|---|
| CPU only, 16–32 cores, 64 GB, 8-channel memory | ≈ 40–80 s | 1–2 parallel | Faster prefill with more cores; memory bandwidth limits decode |
| **1 GPU with 16–24 GB** (e.g. L4, RTX 4000/5000 Ada) + 64 GB RAM | **≈ 10–20 s** with 7B; ≈ 20–40 s with 12–14 B | 4+ parallel requests | Makes Gemma 3 12B / Phi-4 14B practical (re-evaluate there); embedding and indexing ≈ 5–10× faster |
| Verdict | — | — | **Recommended tier for a department (20–100 users)** |

## 7. Capacity Planning

Unit of measure: one *paper-equivalent* ≈ 20 passages of 400 words ≈ 8,000 words ≈ 15–20 pages.

| Per paper-equivalent (measured) | Value |
|---|---|
| Disk (passage index + source + paper record) | ≈ 0.53 MB |
| RAM for vector index (≈ 3.2 KB per passage) | ≈ 64 KB |
| Indexing time on this VM | ≈ 2.7 s (≈ 45 min per 1,000) |

| Corpus size | Disk | Index RAM | Indexing time (this VM) | Query latency |
|---|---|---|---|---|
| 568 (current, measured) | 0.31 GB | ≈ 40 MB | 25 min + 2.5 min paper index | ≈ 100 s |
| 5,000 | 2.7 GB | 0.3 GB | ≈ 4 h | ≈ 100 s (retrieval +1–2 s, estimated) |
| 10,000 | 5.3 GB | 0.6 GB | ≈ 7.5 h | ≈ 100–105 s |
| 50,000 | 27 GB | 3.2 GB | ≈ 1.6 days | ≈ 105–110 s |
| 100,000 | 53 GB | 6.4 GB | ≈ 3 days (a GPU server: ≈ 0.5 day) | ≈ 110 s; needs ≥ 32 GB RAM |

**Which stage becomes the bottleneck as the corpus grows:**
- **Latency:** generation stays dominant, about 95 % of the time. Its cost depends on the fixed amount of evidence (8 blocks), not on corpus size. Retrieval time grows slowly, because vector search scales sub-linearly and reranking covers a fixed 30 candidate papers.
- **Answer quality: retrieval becomes the bottleneck.** Every retrieval threshold was calibrated on 568 papers. With more documents:
  - more near-duplicate papers compete for the 30 candidate slots;
  - the abstention threshold (3.5) may admit off-topic papers or reject valid ones.

  Fact visibility must be re-measured at 5,000 and 50,000 documents.
- **Operations:** indexing time (days at 50,000+ documents on CPU) and a full-index backup (doubles index disk) dominate.

## 8. Storage Growth Projections

| Component | Today | 10,000 docs | 100,000 docs |
|---|---|---|---|
| Python environment (CPU build) | 1.8 GB | 1.8 GB | 1.8 GB |
| Retrieval models (MedCPT encoders, MiniLM cross-encoder) | 1.0 GB | 1.0 GB | 1.0 GB |
| LLMs: Qwen 2.5 7B Q4 + Qwen 2.5 1.5B | 5.7 GB | 5.7 GB | 5.7 GB |
| Ollama runtime | 0.1 GB | 0.1 GB | 0.1 GB |
| Vector database + source documents | 0.31 GB | 5.3 GB | 53 GB |
| Index backup (recommended before rebuilds) | 0.24 GB | 4.2 GB | 42 GB |
| Request logs (`debug_runs/`, ≈ 30–60 KB per question) | < 1 MB | ≈ 1.5 GB per 30,000 questions | same |
| **Total** | **≈ 9 GB** | **≈ 19 GB** | **≈ 105 GB** |

Optional models add their own size: Gemma 3 12B 8.2 GB, Phi-4 9.1 GB, Qwen 2.5 7B Q8 8.1 GB.

## 9. Security and Privacy Benefits

| Property | Status | Evidence |
|---|---|---|
| Documents, questions and answers processed on the machine | **Yes** | Retrieval models, vector database and LLM all run locally |
| Network traffic of the application while answering | **Loopback only** | Measured with `ss` during a live question: the service, Ollama API and model process used only 127.0.0.1 |
| Hugging Face model downloads at runtime | Disabled | `HF_HUB_OFFLINE=1` in the service unit |
| Vector database telemetry | Inactive | Chroma 1.5.9 telemetry client is an empty stub; `posthog` not installed |
| Service exposure | Localhost only | Binds 127.0.0.1:8000 |
| **Ollama daemon outbound connection** | **Present — must be blocked** | Ollama opens a TLS connection to ollama.com (34.36.133.15:443) ≈ 1 s after start-up and forwards requests for `*-cloud` model names there. Prompts to local models stayed on loopback. With `OLLAMA_NO_CLOUD=1` an isolated instance made no outbound connection and refused cloud models. Set it and deny Ollama egress ([OPERATIONS.md §8](OPERATIONS.md)) |
| No third-party AI service | Yes | No API keys or cloud LLM in the code |
| Data residency / GDPR / HIPAA-style controls | Simplified | Data never leaves the host; standard host controls apply |

Controls still needed for enterprise data:
- **Authentication and authorization:** the web page has no login.
- **Per-document access control:** every user can retrieve every indexed document.
- **Encryption at rest** for the index and the logs.
- **A retention policy for `debug_runs/` and `logs/`:** they store questions and answers in plain text.
- **Offline model provisioning:** download once, verify the checksum, copy to the hosts.

## 10. Risks and Limitations

| Risk | Impact | Mitigation |
|---|---|---|
| **Ollama prompt-cache growth** (measured: runner 5.2 → 12.9 GB over 40 answers; up to 8 GB of cache, no setting to change it) | Out-of-memory on 16 GB machines without swap; service killed | **Implemented 2026-10-16**: the service reloads the model between requests (every 20 answers or below 4 GB available, ≈ 6 s) and at start-up; measured runner ≤ 7.8–8.6 GB over 75 answers with unchanged quality ([OPERATIONS.md §7](OPERATIONS.md)). Still add swap on VMs; re-test on every Ollama upgrade |
| Ollama outbound connection | Compliance finding | `OLLAMA_NO_CLOUD=1`, egress firewall, pin the Ollama version |
| CPU latency ≈ 1.5–2 min | User experience; low throughput (≈ 35/hour) | Set expectations in the UI; GPU server for departments |
| One request at a time | Queueing with concurrent users | GPU server with parallel slots, or several instances |
| Ingestion supports PubMed Central XML only | Internal PDF/DOCX/HTML cannot be indexed yet | Build and evaluate parsers before an enterprise rollout |
| Retrieval calibrated on 568 papers | Quality may drop at 10,000+ documents | Re-run the retrieval benchmark at target scale; recalibrate the abstention threshold |
| Small evaluation set (49 questions, single labeler) | Decisions near noise level (± 2 facts) | Expand to domain-specific questions with a second reviewer |
| Fact retention 85 % | Some secondary statistics omitted | Answer-template fix and per-claim citation enforcement (next workstream) |
| No authentication, no access control | Any local user sees all documents | Reverse proxy with SSO; per-collection access rules |
| Startup ≈ 3.5 min after boot | First user waits | Start at boot; health check before use |
| Laptop thermal throttling / battery | Slower answers (estimated 1.5–3 min) | Plugged-in use; prefer 32 GB laptops |
| Model licences (Gemma, Llama custom terms) | Legal review | Qwen 2.5 (Apache 2.0) avoids most issues; confirm |

## 11. Final Recommendation

**Can a company deploy this as a private, local-AI document intelligence system? Yes.**
- Inference, retrieval and storage all run on the company's own hardware.
- The application's traffic was measured to stay on the machine.
- The one external connection observed (Ollama to ollama.com) can be blocked.
- Answer quality on the tested scope: 85 % of available facts stated, no fabricated claims on out-of-corpus questions, citations to the source passages.

**Best model / quantization / hardware combination**

| Deployment | Hardware | Model | Expected experience |
|---|---|---|---|
| **Individual researcher** | 32 GB laptop (or Apple Silicon 16–32 GB) | Qwen 2.5 7B Q4_K_M | ≈ 1.5–2 min per answer on x86 CPU, ≈ 30–60 s on Apple GPU (estimated); 10,000s of documents |
| **Pilot / small team** | 8 vCPU / 16 GB VM (this VM), with swap and the memory fix | Qwen 2.5 7B Q4_K_M | ≈ 100 s per answer (measured), ≈ 35 answers per hour, up to ≈ 20,000 documents on 16 GB |
| **Department** (20–100 users) | Server with 1 GPU (16–24 GB) + 64 GB RAM | Qwen 2.5 7B Q4_K_M, then re-evaluate Gemma 3 12B / Phi-4 14B there | ≈ 10–20 s per answer, parallel users, 100,000+ documents (estimated) |
| Not recommended | 16 GB x86 laptop with normal office load | — | Memory pressure and 2–3 min answers; acceptable only for occasional single-user use with Qwen 3 4B after validation |

**Before production, in order:**
1. ~~Bound Ollama prompt-cache memory in the service.~~ Done 2026-10-16 (measured).
2. Block Ollama egress and set `OLLAMA_NO_CLOUD=1`.
3. Add authentication, access control and log retention.
4. Build ingestion for internal document formats and re-run the retrieval benchmark at the target corpus size.
5. Confirm the laptop and server estimates with the existing benchmark harness on the actual hardware.
