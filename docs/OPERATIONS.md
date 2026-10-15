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
| `RAG_HOST` / `RAG_PORT` | `127.0.0.1` / `8000` | Service bind address |
| `HF_HUB_OFFLINE` | unset | Set to `1` in production |

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
- One answer at a time; ~25–40 answers per hour.
- First answer after a VM reboot loads the model from disk (up to ~2 min); the service warms the model at start-up.
- Disk is 74 % used; keep ≥ 2 GB free and space for one index backup before rebuilding.
