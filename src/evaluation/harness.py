import builtins
import contextlib
import dataclasses
import hashlib
import inspect
import io
import json
import os
import platform
import re
import resource
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HF_HUB_DIR = Path.home() / ".cache" / "huggingface" / "hub"
INDEX_MANIFEST_PATH = PROJECT_ROOT / "data" / "manifests" / "index_manifest.json"
REGISTRY_PATH = PROJECT_ROOT / "data" / "registry" / "drugs.yaml"

ORIGINAL_SUBPROCESS_RUN = subprocess.run

ANSI_PATTERN = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|[⠀-⣿]")
OLLAMA_STAT_PATTERN = re.compile(
    r"^(total duration|load duration|prompt eval count|prompt eval duration|"
    r"prompt eval rate|eval count|eval duration|eval rate):\s*(.+)$"
)
GO_DURATION_PATTERN = re.compile(
    r"(?:(?P<h>\d+)h)?(?:(?P<m>\d+)m(?!s))?(?:(?P<v>[\d.]+)(?P<u>ns|us|µs|ms|s))?"
)
DURATION_UNITS = {"ns": 1e-9, "us": 1e-6, "µs": 1e-6, "ms": 1e-3, "s": 1.0}


def go_duration_seconds(value):
    match = GO_DURATION_PATTERN.fullmatch(value.strip())
    if not match:
        return None
    seconds = int(match.group("h") or 0) * 3600 + int(match.group("m") or 0) * 60
    if match.group("v"):
        seconds += float(match.group("v")) * DURATION_UNITS[match.group("u")]
    return seconds


def parse_ollama_stats(stderr):
    stats = {}
    for line in ANSI_PATTERN.sub("", stderr or "").splitlines():
        match = OLLAMA_STAT_PATTERN.match(line.strip())
        if not match:
            continue
        key = match.group(1).replace(" ", "_")
        value = match.group(2).strip()
        if key.endswith("count"):
            number = re.match(r"\d+", value)
            stats[key] = int(number.group()) if number else None
        elif key.endswith("duration"):
            stats[f"{key}_seconds"] = go_duration_seconds(value)
        elif key.endswith("rate"):
            number = re.match(r"[\d.]+", value)
            stats[f"{key}_tokens_per_second"] = float(number.group()) if number else None
    return stats


def chunk_pmcid(chunk):
    metadata = chunk.get("metadata") or {}
    return metadata.get("pmcid") or chunk.get("pmcid")


def _command_output(command, timeout=120):
    try:
        result = ORIGINAL_SUBPROCESS_RUN(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=PROJECT_ROOT,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"unavailable: {exc}"
    return result.stdout.strip()


def _sha256_file(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _hf_revisions():
    revisions = {}
    for model_dir in sorted(HF_HUB_DIR.glob("models--*")):
        ref = model_dir / "refs" / "main"
        revisions[model_dir.name] = ref.read_text().strip() if ref.exists() else None
    return revisions


def _mem_total_kb():
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1])
    except OSError:
        return None
    return None


def sample_ollama_rss_kb():
    output = _command_output(["ps", "-C", "ollama,llama-server", "-o", "comm=,rss="])
    usage = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].isdigit():
            usage[parts[0]] = usage.get(parts[0], 0) + int(parts[1])
    return usage


def collect_fingerprint(collection, options, import_seconds):
    git_diff = _command_output(["git", "diff", "HEAD"])
    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "git_head": _command_output(["git", "rev-parse", "HEAD"]),
        "git_diff_sha256": hashlib.sha256(git_diff.encode("utf-8")).hexdigest(),
        "git_status": _command_output(["git", "status", "--porcelain"]).splitlines(),
        "chroma_collection_count": collection.count(),
        "index_manifest_sha256": _sha256_file(INDEX_MANIFEST_PATH),
        "registry_sha256": _sha256_file(REGISTRY_PATH),
        "ollama_version": _command_output(["ollama", "--version"]),
        "ollama_models": _command_output(["ollama", "list"]).splitlines(),
        "hf_model_revisions": _hf_revisions(),
        "python_version": sys.version,
        "packages": _command_output([sys.executable, "-m", "pip", "freeze"]).splitlines(),
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "mem_total_kb": _mem_total_kb(),
        "load_average": os.getloadavg(),
        "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
        "import_seconds": import_seconds,
        "options": options,
    }


def _score_view(chunk):
    return {
        "chunk_id": chunk.get("chunk_id"),
        "pmcid": chunk_pmcid(chunk),
        "section_path": (chunk.get("metadata") or {}).get("section_path"),
        "rerank_score": chunk.get("rerank_score"),
        "normalized_rerank_score": chunk.get("normalized_rerank_score"),
        "question_type_score": chunk.get("question_type_score"),
        "combined_rerank_score": chunk.get("combined_rerank_score"),
    }


class BenchmarkHarness:

    def __init__(
        self,
        run_dir,
        items,
        retrieval_only=False,
        ollama_verbose=True,
        strategy_override=None,
        disable_expansions=False,
    ):
        self.run_dir = Path(run_dir)
        self.records_dir = self.run_dir / "records"
        self.records_dir.mkdir(parents=True, exist_ok=True)
        self.pending = list(items)
        self.retrieval_only = retrieval_only
        self.ollama_verbose = ollama_verbose
        self.strategy_override = strategy_override
        self.disable_expansions = disable_expansions
        self.records = []
        self.current = None
        self.stage = None
        self.pool_chunks = {}
        self.originals = {}
        self._started = None

    def _record_path(self, record):
        suffix = "warmup" if record["warmup"] else f"r{record['repeat']}"
        return self.records_dir / f"{record['id']}__{suffix}.json"

    def write_record(self, record):
        with self._record_path(record).open("w", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2, ensure_ascii=False, default=str)

    def _start_record(self, item):
        definition = item["definition"]
        self.current = {
            "id": definition["id"],
            "level": definition["level"],
            "category": definition.get("category"),
            "review_status": definition.get("review_status"),
            "question": definition["question"],
            "repeat": item["repeat"],
            "warmup": item["warmup"],
            "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "load_average_start": os.getloadavg(),
            "query_understanding": {},
            "strategy": None,
            "retrieval": {"queries": [], "embed_seconds": 0.0, "chroma_seconds": 0.0},
            "rerank": {},
            "context": {},
            "ollama_calls": [],
            "generation": {},
            "app_metrics": None,
            "answer": None,
        }
        self._started = time.perf_counter()

    def _finalize_record(self):
        if self.current is None:
            return
        record = self.current
        record["wall_seconds"] = time.perf_counter() - self._started
        record["completed"] = record["app_metrics"] is not None
        record["harness_peak_rss_kb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        self.records.append(record)
        self.write_record(record)
        self.current = None

    def next_input(self, prompt=""):
        self._finalize_record()
        if not self.pending:
            return "exit"
        item = self.pending.pop(0)
        self._start_record(item)
        label = "warmup" if item["warmup"] else f"repeat {item['repeat']}"
        print(
            f"[benchmark] {item['definition']['id']} ({label})",
            file=sys.__stderr__,
            flush=True,
        )
        return item["definition"]["question"]

    def install(self, app_module):
        import requests
        import retrieval.retriever as retriever
        from generation.generator import QwenGenerator
        from query_understanding.query_understanding import QueryUnderstanding
        from retrieval.retrieval_strategy import StrategyManager

        harness = self
        self.retriever = retriever
        self.originals = {
            "input": builtins.input,
            "classify": QueryUnderstanding._classify_without_llm,
            "analyze": QueryUnderstanding.analyze,
            "get_strategy": StrategyManager.get_strategy,
            "embed_query": retriever.embed_query,
            "collection_query": retriever.collection.query,
            "rerank_chunks": retriever.rerank_chunks,
            "build_context": app_module.build_context,
            "save_debug_run": app_module.save_debug_run,
            "generate": QwenGenerator.generate,
            "validate_answer": QwenGenerator.validate_answer,
            "subprocess_run": subprocess.run,
            "requests_post": requests.post,
        }
        originals = self.originals

        def classify(self_, question):
            result, confidence = originals["classify"](self_, question)
            harness.current["query_understanding"]["fast_path"] = {
                "question_type": result.get("question_type"),
                "intent": result.get("intent"),
                "confidence": confidence,
                "threshold": self_.confidence_threshold,
            }
            return result, confidence

        def analyze(self_, question):
            harness.stage = "query_understanding"
            started = time.perf_counter()
            try:
                query_info = originals["analyze"](self_, question)
            finally:
                harness.stage = None
            if harness.disable_expansions:
                query_info["expanded_queries"] = []
            record = harness.current["query_understanding"]
            record["seconds"] = time.perf_counter() - started
            record["query_info"] = json.loads(json.dumps(query_info, default=str))
            fast_path = record.get("fast_path") or {}
            record["llm_fallback"] = any(
                call["stage"] == "query_understanding"
                for call in harness.current["ollama_calls"]
            ) or (
                fast_path.get("confidence") is not None
                and fast_path["confidence"] < fast_path.get("threshold", 0)
            )
            return query_info

        def get_strategy(self_, intent_info):
            strategy = originals["get_strategy"](self_, intent_info)
            produced = dataclasses.asdict(strategy)
            if harness.strategy_override:
                retrieval_k, top_k = harness.strategy_override
                strategy = dataclasses.replace(
                    strategy,
                    retrieval_k=retrieval_k,
                    top_k=top_k,
                )
            harness.current["strategy"] = {
                "produced": produced,
                "used": dataclasses.asdict(strategy),
                "overridden": bool(harness.strategy_override),
            }
            return strategy

        def embed_query(text):
            started = time.perf_counter()
            embedding = originals["embed_query"](text)
            retrieval = harness.current["retrieval"]
            retrieval["embed_seconds"] += time.perf_counter() - started
            retrieval["queries"].append({"text": text})
            return embedding

        def collection_query(*args, **kwargs):
            started = time.perf_counter()
            results = originals["collection_query"](*args, **kwargs)
            elapsed = time.perf_counter() - started
            retrieval = harness.current["retrieval"]
            retrieval["chroma_seconds"] += elapsed
            if retrieval["queries"]:
                retrieval["queries"][-1].update({
                    "n_results": kwargs.get("n_results"),
                    "ids": (results.get("ids") or [[]])[0],
                    "distances": (results.get("distances") or [[]])[0],
                    "seconds": elapsed,
                })
            return results

        def rerank_chunks(*args, **kwargs):
            started = time.perf_counter()
            final_chunks = originals["rerank_chunks"](*args, **kwargs)
            elapsed = time.perf_counter() - started
            pool = list(kwargs.get("chunks", args[1] if len(args) > 1 else []))
            harness.pool_chunks[id(harness.current)] = {
                "chunks": pool,
                "kwargs": {
                    key: value
                    for key, value in kwargs.items()
                    if key != "chunks"
                },
            }
            harness.current["rerank"] = {
                "seconds": elapsed,
                "query": kwargs.get("query"),
                "top_k": kwargs.get("top_k"),
                "question_type": kwargs.get("question_type"),
                "diversity_boost": kwargs.get("diversity_boost"),
                "pool": [
                    {"chunk_id": chunk.get("chunk_id"), "pmcid": chunk_pmcid(chunk)}
                    for chunk in pool
                ],
                "final": [_score_view(chunk) for chunk in final_chunks],
            }
            return final_chunks

        def build_context(*args, **kwargs):
            started = time.perf_counter()
            context, evidence_map = originals["build_context"](*args, **kwargs)
            chunks = kwargs.get("chunks", args[0] if args else [])
            harness.current["context"] = {
                "seconds": time.perf_counter() - started,
                "chars": len(context),
                "blocks": len(evidence_map),
                "chunk_text_chars": [
                    len(" ".join((chunk.get("text") or "").split()))
                    for chunk in chunks
                ],
                "evidence_map": evidence_map,
                "text": context,
            }
            return context, evidence_map

        def save_debug_run(question, query_info, strategy, chunks, evidence_map, answer, metrics):
            harness.current["app_metrics"] = dict(metrics)
            harness.current["answer"] = answer
            return harness._record_path(harness.current)

        def generate(self_, question, context, query_info=None):
            generation = harness.current["generation"]
            generation["validations"] = []
            if harness.retrieval_only:
                generation["skipped"] = True
                return ""
            harness.stage = "generation"
            started = time.perf_counter()
            try:
                return originals["generate"](self_, question, context, query_info)
            except Exception as exc:
                generation["error_type"] = type(exc).__name__
                generation["error"] = str(exc)
                raise
            finally:
                harness.stage = None
                generation["seconds"] = time.perf_counter() - started

        def validate_answer(self_, answer, context):
            errors = originals["validate_answer"](self_, answer, context)
            if harness.current is not None:
                harness.current["generation"].setdefault("validations", []).append({
                    "errors": errors,
                    "answer_chars": len(answer),
                })
            return errors

        def subprocess_run(args, *run_args, **run_kwargs):
            if not (isinstance(args, list) and args[:2] == ["ollama", "run"]):
                return originals["subprocess_run"](args, *run_args, **run_kwargs)
            command = (
                args[:2]
                + (["--verbose"] if harness.ollama_verbose else [])
                + args[2:]
            )
            prompt = run_kwargs.get("input") or ""
            call = {
                "stage": harness.stage,
                "model": next((arg for arg in reversed(args[2:]) if not arg.startswith("-")), None),
                "command": command,
                "prompt": prompt,
                "prompt_chars": len(prompt),
            }
            if harness.current is not None:
                harness.current["ollama_calls"].append(call)
            started = time.perf_counter()
            try:
                result = originals["subprocess_run"](command, *run_args, **run_kwargs)
            except Exception as exc:
                call["error"] = f"{type(exc).__name__}: {exc}"
                call["wall_seconds"] = time.perf_counter() - started
                raise
            call["wall_seconds"] = time.perf_counter() - started
            call["returncode"] = result.returncode
            call["stdout"] = result.stdout
            call["stats"] = parse_ollama_stats(result.stderr)
            call["ollama_rss_kb"] = sample_ollama_rss_kb()
            return result

        def requests_post(url, *post_args, **post_kwargs):
            if "/api/generate" not in str(url):
                return originals["requests_post"](url, *post_args, **post_kwargs)
            payload = post_kwargs.get("json") or {}
            call = {
                "stage": harness.stage,
                "model": payload.get("model"),
                "command": ["POST", str(url)],
                "options": payload.get("options"),
                "prompt": payload.get("prompt") or "",
                "prompt_chars": len(payload.get("prompt") or ""),
            }
            if harness.current is not None:
                harness.current["ollama_calls"].append(call)
            started = time.perf_counter()
            try:
                response = originals["requests_post"](url, *post_args, **post_kwargs)
            except Exception as exc:
                call["error"] = f"{type(exc).__name__}: {exc}"
                call["wall_seconds"] = time.perf_counter() - started
                raise
            call["wall_seconds"] = time.perf_counter() - started
            call["returncode"] = response.status_code
            try:
                body = response.json()
            except ValueError:
                body = {}
            call["stdout"] = body.get("response")
            call["stats"] = {
                "total_duration_seconds": (body.get("total_duration") or 0) / 1e9,
                "load_duration_seconds": (body.get("load_duration") or 0) / 1e9,
                "prompt_eval_count": body.get("prompt_eval_count"),
                "prompt_eval_duration_seconds": (body.get("prompt_eval_duration") or 0) / 1e9,
                "eval_count": body.get("eval_count"),
                "eval_duration_seconds": (body.get("eval_duration") or 0) / 1e9,
            }
            call["ollama_rss_kb"] = sample_ollama_rss_kb()
            return response

        builtins.input = self.next_input
        QueryUnderstanding._classify_without_llm = classify
        QueryUnderstanding.analyze = analyze
        StrategyManager.get_strategy = get_strategy
        retriever.embed_query = embed_query
        retriever.collection.query = collection_query
        retriever.rerank_chunks = rerank_chunks
        app_module.build_context = build_context
        app_module.save_debug_run = save_debug_run
        QwenGenerator.generate = generate
        QwenGenerator.validate_answer = validate_answer
        subprocess.run = subprocess_run
        requests.post = requests_post

    def run(self, app_module, log_path):
        with open(log_path, "w", encoding="utf-8") as log, contextlib.redirect_stdout(log):
            app_module.main()
        self._finalize_record()

    def replay_rerank(self):
        from retrieval import reranker

        rerank = self.originals["rerank_chunks"]
        max_per_source = (
            inspect.signature(reranker.rerank_chunks)
            .parameters["max_per_source"]
            .default
        )
        for record in self.records:
            saved = self.pool_chunks.get(id(record))
            if not saved or not saved["chunks"]:
                continue
            pool = saved["chunks"]
            kwargs = dict(saved["kwargs"])
            top_k = kwargs.get("top_k")
            kwargs.update(top_k=len(pool), max_per_source=len(pool))
            with contextlib.redirect_stdout(io.StringIO()):
                ordered = rerank(chunks=pool, **kwargs)

            kept = {chunk["chunk_id"] for chunk in ordered}
            fate = {
                chunk["chunk_id"]: "dedup"
                for chunk in pool
                if chunk["chunk_id"] not in kept
            }
            source_counts = {}
            selected = []
            for chunk in ordered:
                source_id = str(chunk_pmcid(chunk) or "unknown")
                if len(selected) >= top_k:
                    fate[chunk["chunk_id"]] = "below_cutoff"
                elif source_counts.get(source_id, 0) >= max_per_source:
                    fate[chunk["chunk_id"]] = "source_cap"
                else:
                    fate[chunk["chunk_id"]] = "selected"
                    selected.append(chunk["chunk_id"])
                    source_counts[source_id] = source_counts.get(source_id, 0) + 1

            record["rerank"]["replay"] = {
                "max_per_source": max_per_source,
                "order": [_score_view(chunk) for chunk in ordered],
                "fate": fate,
                "consistent": selected == [
                    chunk["chunk_id"] for chunk in record["rerank"]["final"]
                ],
            }
            self.write_record(record)

    def uninstall(self, app_module):
        if not self.originals:
            return
        from generation.generator import QwenGenerator
        from query_understanding.query_understanding import QueryUnderstanding
        from retrieval.retrieval_strategy import StrategyManager

        originals = self.originals
        builtins.input = originals["input"]
        QueryUnderstanding._classify_without_llm = originals["classify"]
        QueryUnderstanding.analyze = originals["analyze"]
        StrategyManager.get_strategy = originals["get_strategy"]
        self.retriever.embed_query = originals["embed_query"]
        self.retriever.collection.query = originals["collection_query"]
        self.retriever.rerank_chunks = originals["rerank_chunks"]
        app_module.build_context = originals["build_context"]
        app_module.save_debug_run = originals["save_debug_run"]
        QwenGenerator.generate = originals["generate"]
        QwenGenerator.validate_answer = originals["validate_answer"]
        subprocess.run = originals["subprocess_run"]
        import requests

        requests.post = originals["requests_post"]
