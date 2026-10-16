# Operations Guide — Pharma Research Intelligence RAG

Target host: Azure VM, 8 vCPU (4 cores × 2 threads), 16 GB RAM, CPU only, local Ollama.

## 1. Install

```bash
python3 -m venv .venv
.venv/bin/pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.lock
ollama pull qwen2.5:7b        # answer generation (4.7 GB)
ollama pull qwen2.5:1.5b      # query-understanding fallback (1.0 GB)
```
`requirements.lock` pins every package (121); `torch==2.14.1+cpu` comes from the PyTorch CPU index.
Hugging Face models (MedCPT query/article encoders, MiniLM cross-encoder) download on first run; afterwards run with `HF_HUB_OFFLINE=1` so start-up never needs the network.

## 2. Build the indexes

```bash
# Passage index (≈ 25 min for 568 papers; moves the old index to data/backups/)
HF_HUB_OFFLINE=1 .venv/bin/python src/indexing/build_index.py --rebuild --source-dir data/staging/phase1/xml
# Paper index (≈ 2.5 min) — run again after every passage rebuild
HF_HUB_OFFLINE=1 .venv/bin/python src/indexing/build_paper_index.py --pooling cls --distance ip
```
Manifests: `data/manifests/index_manifest.json`, `data/manifests/paper_index_manifest.json`.

## 3. Run

| Mode | Command |
|---|---|
| Interactive CLI | `HF_HUB_OFFLINE=1 .venv/bin/python app.py` |
| HTTP service | `HF_HUB_OFFLINE=1 OLLAMA_KEEP_ALIVE=-1 .venv/bin/python serve.py` |
| systemd | `sudo cp deploy/pharma-rag.service /etc/systemd/system/ && sudo systemctl enable --now pharma-rag` |

Web page: open `http://localhost:8000/` (question box, answer with clickable [E#] citations, evidence list). From another machine, forward port 8000 (VS Code Ports tab, or `ssh -L 8000:localhost:8000 azureuser@<vm-ip>`).

Service API (binds `127.0.0.1:8000` by default):
```bash
curl -s localhost:8000/health
curl -s -X POST localhost:8000/ask -H 'Content-Type: application/json' \
     -d '{"question": "Which biomarker predicted severe immune-related liver injury after nivolumab plus ipilimumab?"}'
```
Response: `answer`, `references` (evidence ID → PMCID, chunk, paper title), `abstained`, `error`, `metrics_seconds` (per stage), `telemetry` (paper scores, allocation, token counts), `artifact` (path of the JSON run record).
Questions are answered one at a time (single CPU-bound generation); `/health` stays responsive while busy. Logs: `logs/service.log`; every run: `debug_runs/run_*.json` (also failed runs, with `error`).

## 4. Configuration

| Variable | Default | Meaning |
|---|---|---|
| `RETRIEVAL_MODE` | `paper_first` | `legacy` restores the previous flat passage retrieval (rollback) |
| `OLLAMA_KEEP_ALIVE` | `30m` | How long Ollama keeps the model loaded; `-1` = always (recommended for the service) |
| `OLLAMA_HOST` | `127.0.0.1:11434` | Ollama endpoint |
| `OLLAMA_NUM_THREAD` | CPU count (8) | Threads for Qwen; 8 is ≈ 18–25 % faster than Ollama's default of 4 on this VM |
| `RAG_HOST` / `RAG_PORT` | `127.0.0.1` / `8000` | Service bind address |
| `HF_HUB_OFFLINE` | unset | Set to `1` in production |
| `RAG_MODEL_RELOAD_EVERY` | `20` | Free Ollama's prompt cache by reloading the model after this many generated answers (≈ 6–8 s, done after the response is sent); `0` disables |
| `RAG_MIN_AVAILABLE_GB` | `3.0` | Also free the cache when available RAM falls below this (checked after each answer and before each generation); `0` disables |

Fixed in code (evidence-based values): generation `num_ctx 8192`, `temperature 0`, `seed 0`, timeout 600 s; plan shapes depth = top paper 6 + second paper 2 passages, breadth = 8 papers × 1; adaptive margin 2.0; paper relevance floor 3.5 (`src/retrieval/retrieval_strategy.py`).

## 5. Verify

```bash
HF_HUB_OFFLINE=1 .venv/bin/python -m unittest test_pipeline_service.py src/retrieval/test_paper_first.py \
  src/indexing/test_paper_index.py src/embeddings/test_lazy_article_encoder.py src/generation/test_answer_validation.py \
  src/query_understanding/test_classification_determinism.py src/processing/test_evidence_classifier.py
# Retrieval-only benchmark (≈ 4 min) and full benchmark (≈ 60–90 min)
HF_HUB_OFFLINE=1 .venv/bin/python src/evaluation/run_benchmark.py --retrieval-only --repeats 1
HF_HUB_OFFLINE=1 .venv/bin/python src/evaluation/run_benchmark.py --repeats 1
```
Results go to `benchmark_runs/<timestamp>_<mode>_<label>/summary.md`.

## 6. Known operational limits
- One answer at a time; ≈ 35 answers per hour (≈ 100 s each).
- Ollama's prompt cache is bounded by the service (§7); check `/health` → `memory` if RAM looks high.
- First answer after a VM reboot loads the model from disk (up to ~2 min); the service warms the model at start-up.
- Disk is 70 % used; keep ≥ 2 GB free and space for one index backup before rebuilding.

## 7. Memory management — Ollama prompt cache

### 7.1 Root cause
Ollama 0.40.2 runs each model in a `llama-server` process started with a **host-RAM prompt cache of 8,192 MiB** (Ollama log: `use --cache-ram 0 to disable the prompt cache`; `cache state: … (limits: 8192.000 MiB …)`). After every request the server saves that request's attention state (KV cache) in RAM so a later request with the same prefix can reuse it. Our prompts share almost no prefix (each carries different evidence), so the cache gives no measurable speed benefit but keeps growing until it reaches 8 GB. Ollama exposes no setting for `--cache-ram`; the cache is freed only when the model is unloaded. The service keeps the model loaded forever (`OLLAMA_KEEP_ALIVE=-1`), so the cache is never freed.

### 7.2 Measured growth (2026-10-16)
| Model | Runner RSS at load | Growth per answer | Observed |
|---|---|---|---|
| Qwen 2.5 7B Q4_K_M (production) | 5.2 GB | 0.19 GB | 5.2 → 12.9 GB after 40 answers; Ollama log "39 prompts, 7,804 MiB" |
| Qwen 3 8B / Qwen 3 4B | 6.4 / 4.0 GB | 0.53 GB | — |
| Llama 3.1 8B | 6.0 GB | 0.43 GB | — |
| Gemma 3 12B | 9.8 GB | 1.16 GB | — |
| Phi-4 14B | 10.5 GB | ≈ 0.68 GB (computed) | — |
Growth per answer equals the model's KV-cache size for one ≈ 3,300-token prompt (layers × KV heads × head size × 2 × 2 bytes × tokens).

### 7.3 Worst case
Cache full (8 GB) after ≈ 42 answers with Qwen 2.5 7B: runner ≈ 13.2 GB + service ≈ 1.2–1.7 GB + query helper (Qwen 2.5 1.5B, when loaded) ≈ 1.4 GB + OS ≈ 1 GB ≈ **16.8–17.3 GB on a 16 GB machine without swap** → the kernel OOM killer terminates the runner or the service; the request fails and the next one pays a cold model load. Growth only happens while answering (idle time does not grow the cache), so exposure is proportional to usage: ≈ 1 day of normal team use.

### 7.4 Impact by deployment
| Deployment | Impact without mitigation |
|---|---|
| 16 GB laptop | **Critical**: office apps already use 6–9 GB; out-of-memory after ≈ 10–20 answers; the laptop becomes unresponsive |
| 32 GB laptop | Medium: peak ≈ 15–17 GB fits, but takes 8 GB from the user's applications |
| Current VM (8 vCPU, 16 GB, no swap) | **High**: OOM after ≈ 40 answers (one busy day) |
| Department server (64–128 GB, GPU) | Low for RAM capacity, but 8 GB host RAM per loaded model; with several models or parallel slots this multiplies |

### 7.5 Mitigation (implemented 2026-10-16)
The service frees the cache by unloading and reloading the model (the only control Ollama offers):
| Trigger | When checked | Effect on users |
|---|---|---|
| `RAG_MODEL_RELOAD_EVERY` answers (default 20) | after each answer is delivered | none (reset runs between requests; a question arriving during the ≈ 6 s reset waits) |
| Available RAM < `RAG_MIN_AVAILABLE_GB` + 1 GB headroom (default 4 GB) | after each answer is delivered | none |
| Available RAM < `RAG_MIN_AVAILABLE_GB` (default 3 GB) | just before generating | ≈ 6–8 s added to that answer (safety net) |
| Service start-up | always | start-up ≈ 6 s; clears a cache left by a previous service process (Ollama keeps the model loaded across service restarts) |
The reset waits until Ollama reports the model unloaded (`/api/ps`) before reloading, because Ollama unloads asynchronously. Resets are recorded in `logs/service.log` (`[memory] prompt cache reset`) and in `/health` → `memory` (`available_gb`, `answers_since_cache_reset`, `cache_resets`, `last_cache_reset`). The retrieval and generation code paths, prompt and model settings are unchanged.

### 7.6 Measurements (live service, Qwen 2.5 7B Q4_K_M, this VM)
| | Before fix (40 answers, model kept loaded) | After fix: 50-answer run | After tuning: 25-answer run |
|---|---|---|---|
| Model runner RSS | 5.2 → **12.9 GB** (still growing) | 5.2 → max **8.6 GB**, sawtooth | 5.2 → max **7.8 GB**, sawtooth |
| Lowest available RAM | not recorded (projected < 1 GB at cap) | 2.7 GB | **3.8 GB** |
| Cache resets | 0 | 2 (7.7 s, 8.0 s), both in the request path | 1 between requests (+1 at start-up); **0 in the request path** |
| Errors | 0 | **0 / 50** | **0 / 25** |
| Retrieval: same evidence as stored baseline | — | **50 / 50** | **25 / 25** |
| Expected facts stated (vs stored baseline) | — | **70 vs 69** | **37 vs 37** |
| Generation median / p90 | 96 / 114 s | 98 / 118 s | 98 / 114 s |
| End-to-end median / p90 (HTTP) | — | 107 / 128 s | 106 / 125 s |
| Service process RSS (max) | 1.2–1.7 GB | 2.0 GB | 1.9 GB |
Run folders: `benchmark_runs/20261016_054029_model_qwen2.5-7b_baseline8t`, `…_160048_service_soak50`, `…_173042_service_soak25-headroom` (`memory.csv` sampled every 5 s). The 25-answer run exposed an asynchronous-unload race (one reset returned in 0.008 s and the next answer paid a 7.6 s load); fixed by waiting for the unload, verified with 5 consecutive live resets (5.5–7.6 s each, new runner at 5.19 GB every time).

### 7.7 100-answer projection
| | Without fix | With fix |
|---|---|---|
| Runner RSS | reaches the 8 GB cache cap at ≈ answer 42 → ≈ 13.2 GB from then on | sawtooth 5.2 → ≈ 7.8 GB, reset every ≈ 14 answers on this VM |
| System RAM on 16 GB | runner 13.2 + service 2.0 + query helper 1.4 + OS ≈ 1 GB ≈ **17.6 GB → out-of-memory ≈ answers 35–42** | peak ≈ 12 GB in use; ≥ 3.5 GB available |
| Resets per 100 answers | 0 | ≈ 7, ≈ 6–8 s each, between requests (≈ 50 s of model time per ≈ 3 h of answers, < 0.5 %) |
| Answer and retrieval quality | — | unchanged (same code path; verified above) |

### 7.8 Settings by deployment
| Deployment | `RAG_MODEL_RELOAD_EVERY` | `RAG_MIN_AVAILABLE_GB` |
|---|---|---|
| 16 GB laptop (office apps open) | 10 | 3.0 |
| 16 GB VM (this VM) | 20 (default) | 3.0 (default) |
| 32 GB laptop / VM | 40 | 4.0 |
| Department server | 40 per model | 8.0 |
| Models with large cache growth (Gemma 3 12B: 1.16 GB/answer) | 5 | 4.0 |

## 8. Network hardening — Ollama outbound connection

### 8.1 Finding (measured 2026-10-16)
| Test | Result |
|---|---|
| Production Ollama log at start-up | `Ollama cloud disabled: false`; `OLLAMA_REMOTES:[ollama.com]` |
| Production, live question (`ss` every 1 s) | Application traffic on 127.0.0.1 only; the Ollama daemon held a TLS connection to **ollama.com (34.36.133.15:443)** |
| Isolated Ollama instance, empty model folder, default settings | Connection to ollama.com opened **≈ 1 s after start-up, before any request**, and stayed open (45/45 samples) |
| Same, request for a cloud model tag (`gpt-oss:20b-cloud`) | Request **forwarded to ollama.com** (answered `Unauthorized`): a prompt sent to a `*-cloud` model would leave the machine |
| Same with `OLLAMA_NO_CLOUD=1` | **No outbound connection** (0/45 samples); cloud model refused locally: `ollama cloud is disabled: remote model is unavailable` |
Root cause: Ollama 0.40 ships "cloud" features (remote inference and web search) enabled by default and keeps a background connection to ollama.com. Local prompts were not observed on it (generation stayed on loopback), but the content is encrypted and cannot be audited, and a mistyped or misconfigured model name ending in `-cloud` would send prompts and evidence off the machine.

### 8.2 Hardening (recommended; requires sudo, not applied automatically)
```bash
# 1. Disable Ollama cloud features
sudo systemctl edit ollama          # add the two lines below, save
#   [Service]
#   Environment="OLLAMA_NO_CLOUD=1"
sudo systemctl restart ollama
sudo journalctl -u ollama -n 50 | grep "cloud disabled"     # expect: Ollama cloud disabled: true
sudo ss -tnp | grep ollama | grep -v 127.0.0.1               # expect: no output

# 2. Deny outbound internet for the Ollama service user (defence in depth)
sudo iptables -A OUTPUT -m owner --uid-owner ollama ! -o lo -j REJECT
#    (persist with iptables-persistent / nftables, or an Azure NSG outbound rule;
#     temporarily allow during planned `ollama pull`, or provision models offline)

# 3. Pin the Ollama version (installed by script, no auto-update on Linux);
#    re-run the benchmark and this network check before any upgrade.
```
After hardening, re-run the check in 8.1: the expected result is application and Ollama traffic on loopback only.
