import argparse
import contextlib
import copy
import io
import json
import os
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from statistics import median

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
QUESTIONS_PATH = Path(__file__).resolve().parent / "benchmark_questions.json"
DEFAULT_SNAPSHOT = PROJECT_ROOT / "benchmark_runs" / "20261015_105008_full_final_baseline"
SCREENING_IDS = (
    "L1-01,L1-02,L1-03,L1-04,L1-09,L1-10,L1-11,L1-12,L1-16,N3,"
    "L1-05,L1-13,N2,N6,L2-02,L2-06,M4,L1-C2,C7,C10"
)
STABILITY_IDS = "L1-02,L1-10,L1-16,L2-02,C7"
ATTRIBUTION = re.compile(r"\b[A-Z][A-Za-z'-]+\s+et\s+al\.?")
BLOCK_START = re.compile(r"(?m)^\[E\d+\]\s*$")
STRUCTURE_SECTION = re.compile(r"REQUIRED ANSWER STRUCTURE\n.*?(?=If a requested section is not established)", re.S)
CLAIMS_STRUCTURE = (
    "REQUIRED ANSWER STRUCTURE\n"
    "Use these headings in this order and address each one:\n"
    "## Answer: State the direct answer to the question in one or two sentences.\n"
    "## Findings: List every finding in the evidence that is relevant to the question, one bullet per finding. "
    "Each bullet gives the finding with all reported numbers (values with units, comparison groups, confidence "
    "intervals, p-values, sample sizes) as written, and ends with the citation of the evidence block that reports it.\n"
    "## Limitations: State important gaps, conflicts, or limitations in the supplied evidence.\n"
)
CONCISE_RULE = "- Be complete but concise. Use one claim per bullet or sentence."
CLAIMS_RULE = "- One finding per bullet; do not merge findings from different evidence blocks into one bullet."


def transform_context(text, max_blocks=None, order="ranked"):
    starts = [match.start() for match in BLOCK_START.finditer(text)]
    if not starts:
        return text
    preamble = text[:starts[0]]
    blocks = [text[start:end] for start, end in zip(starts, starts[1:] + [len(text)])]
    if max_blocks:
        blocks = blocks[:max_blocks]
    if order == "reversed":
        blocks = list(reversed(blocks))
    blocks = [block.rstrip("\n") + "\n\n" for block in blocks]
    return (preamble + "".join(blocks)).rstrip("\n") + "\n"


def apply_prompt_variant(generator, variant):
    if variant == "default":
        return
    original = generator.build_prompt

    def build_prompt(question, context, query_info=None):
        prompt = original(question, context, query_info)
        prompt = STRUCTURE_SECTION.sub(lambda _: CLAIMS_STRUCTURE, prompt, count=1)
        return prompt.replace(CONCISE_RULE, CLAIMS_RULE, 1)

    generator.build_prompt = build_prompt
CLOCK_TICKS = os.sysconf("SC_CLK_TCK")
PAGE_KB = os.sysconf("SC_PAGE_SIZE") // 1024


def runner_pids():
    pids = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if (entry / "comm").read_text().strip() in {"llama-server", "ollama_llama_se"}:
                pids.append(int(entry.name))
        except OSError:
            continue
    return pids


def runner_cpu_seconds(pids):
    total = 0
    for pid in pids:
        try:
            fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
            total += int(fields[11]) + int(fields[12])
        except (OSError, IndexError, ValueError):
            continue
    return total / CLOCK_TICKS


def runner_rss_kb(pids):
    total = 0
    for pid in pids:
        try:
            total += int(Path(f"/proc/{pid}/statm").read_text().split()[1]) * PAGE_KB
        except (OSError, IndexError, ValueError):
            continue
    return total


class ResourceSampler:

    def __init__(self, interval=0.5):
        self.interval = interval
        self.peak_rss_kb = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.is_set():
            self.peak_rss_kb = max(self.peak_rss_kb, runner_rss_kb(runner_pids()))
            self._stop.wait(self.interval)

    def __enter__(self):
        self.cpu_start = runner_cpu_seconds(runner_pids())
        self.wall_start = time.perf_counter()
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join()
        self.wall_seconds = time.perf_counter() - self.wall_start
        self.cpu_seconds = runner_cpu_seconds(runner_pids()) - self.cpu_start
        return False


def ollama_base():
    host = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434").strip()
    if not host.startswith(("http://", "https://")):
        host = f"http://{host}"
    return host.rstrip("/")


def unload_other_models(model):
    loaded = requests.get(f"{ollama_base()}/api/ps", timeout=30).json().get("models") or []
    for item in loaded:
        name = item.get("name") or item.get("model")
        if name and name != model:
            requests.post(f"{ollama_base()}/api/generate", json={"model": name, "keep_alive": 0}, timeout=120)


def mem_available_gb():
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) / 1024 / 1024
    return None


def reload_model(generator):
    """Unload and reload the model: the only way to empty llama-server's prompt cache (up to 8 GB, no Ollama setting)."""
    requests.post(f"{ollama_base()}/api/generate", json={"model": generator.model_name, "keep_alive": 0}, timeout=120)
    with contextlib.redirect_stdout(io.StringIO()):
        generator.warm_up()


def loaded_model_info(model):
    loaded = requests.get(f"{ollama_base()}/api/ps", timeout=30).json().get("models") or []
    for item in loaded:
        if (item.get("name") or item.get("model")) == model:
            return {"size": item.get("size"), "digest": item.get("digest"), "context_length": item.get("context_length")}
    return {}


def load_snapshot(snapshot_dir, ids):
    records = {}
    for path in sorted((Path(snapshot_dir) / "records").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("warmup") or record.get("repeat") != 1:
            continue
        if not (record.get("context") or {}).get("text"):
            continue
        records[record["id"]] = record
    if ids:
        missing = [item for item in ids if item not in records]
        if missing:
            raise SystemExit(f"not in snapshot or abstained at retrieval: {', '.join(missing)}")
        return [records[item] for item in ids]
    return list(records.values())


def make_generator(model, think):
    with contextlib.redirect_stdout(io.StringIO()):
        from generation import generator as generator_module

        generator = generator_module.QwenGenerator(model_name=model)
    original_post = generator_module.requests.post
    captured = {}

    def post(url, *args, **kwargs):
        payload = kwargs.get("json")
        if think is not None and isinstance(payload, dict) and str(url).endswith("/api/chat"):
            payload = dict(payload, think=think)
            kwargs["json"] = payload
        response = original_post(url, *args, **kwargs)
        if str(url).endswith("/api/chat"):
            captured["prompt"] = ((payload or {}).get("messages") or [{}])[-1].get("content", "")
            try:
                captured["body"] = response.json()
            except ValueError:
                captured["body"] = {}
        return response

    validations = []
    original_validate = generator.validate_answer

    def validate(answer, context):
        errors = original_validate(answer, context)
        validations.append({"errors": errors, "answer_chars": len(answer)})
        return errors

    generator.validate_answer = validate
    generator_module.requests.post = post
    return generator, captured, validations


def stats_from_body(body):
    stats = {
        "total_duration_seconds": (body.get("total_duration") or 0) / 1e9,
        "load_duration_seconds": (body.get("load_duration") or 0) / 1e9,
        "prompt_eval_count": body.get("prompt_eval_count"),
        "prompt_eval_duration_seconds": (body.get("prompt_eval_duration") or 0) / 1e9,
        "eval_count": body.get("eval_count"),
        "eval_duration_seconds": (body.get("eval_duration") or 0) / 1e9,
    }
    if stats["prompt_eval_count"] and stats["prompt_eval_duration_seconds"]:
        stats["prompt_eval_rate_tokens_per_second"] = stats["prompt_eval_count"] / stats["prompt_eval_duration_seconds"]
    if stats["eval_count"] and stats["eval_duration_seconds"]:
        stats["eval_rate_tokens_per_second"] = stats["eval_count"] / stats["eval_duration_seconds"]
    return stats


def generate_record(snapshot_record, generator, captured, validations, model, repeat, max_blocks=None, block_order="ranked"):
    from numeric_fidelity_experiment import unsupported_numbers

    record = copy.deepcopy(snapshot_record)
    context = record["context"]["text"]
    if max_blocks or block_order != "ranked":
        context = transform_context(context, max_blocks, block_order)
        record["context"]["text"] = context
        record["context"]["chars"] = len(context)
    query_info = (record.get("query_understanding") or {}).get("query_info")
    captured.clear()
    validations.clear()
    error = None
    answer = None
    with ResourceSampler() as sampler, contextlib.redirect_stdout(io.StringIO()):
        try:
            answer = generator.generate(record["question"], context, query_info)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
    body = captured.get("body") or {}
    raw = (body.get("message") or {}).get("content") or ""
    call = {
        "stage": "generation",
        "model": model,
        "command": ["POST", f"{ollama_base()}/api/chat"],
        "options": dict(generator.options),
        "prompt": captured.get("prompt", ""),
        "prompt_chars": len(captured.get("prompt", "")),
        "stdout": raw,
        "thinking": (body.get("message") or {}).get("thinking"),
        "done_reason": body.get("done_reason"),
        "stats": stats_from_body(body),
        "ollama_rss_kb": {"llama-server": sampler.peak_rss_kb},
        "wall_seconds": sampler.wall_seconds,
    }
    record["ollama_calls"] = [c for c in record.get("ollama_calls", []) if c.get("stage") != "generation"] + [call]
    record["generation"] = {"validations": list(validations), "seconds": sampler.wall_seconds}
    if error:
        record["generation"]["error"] = error
    record["answer"] = answer
    record["app_error"] = error
    record["completed"] = error is None
    record["repeat"] = repeat
    record["comparison"] = {
        "model": model,
        "snapshot_answer": snapshot_record.get("answer"),
        "runner_peak_rss_kb": sampler.peak_rss_kb,
        "runner_cpu_seconds": sampler.cpu_seconds,
        "runner_avg_cores": sampler.cpu_seconds / sampler.wall_seconds if sampler.wall_seconds else None,
        "unsupported_numbers": unsupported_numbers(answer or "", context),
        "raw_attributions": ATTRIBUTION.findall(raw),
        "think_tag_in_output": "<think>" in raw,
    }
    return record


def summarize(scored_rows, definitions):
    def split_of(row):
        return definitions[row["id"]].get("split", "dev")

    summary = {"answers": len(scored_rows), "outcomes": {}, "l1": {}, "l2": {}, "controls": {}, "resources": {}}
    for row in scored_rows:
        outcome = row["answer"]["outcome"]
        summary["outcomes"][outcome] = summary["outcomes"].get(outcome, 0) + 1
    for row in scored_rows:
        if row["level"] != 1 or row["control"]:
            continue
        bucket = summary["l1"].setdefault(split_of(row), {"facts": 0, "visible": 0, "raw": 0, "stated": 0, "grounded_paper": 0, "questions": 0})
        bucket["questions"] += 1
        for fact in row["facts"]:
            bucket["facts"] += 1
            bucket["visible"] += fact["visible_in_any_block"]
            bucket["raw"] += fact["in_raw_output"]
            bucket["stated"] += fact["in_answer"]
            bucket["grounded_paper"] += fact["in_answer"] and fact["grounded_paper"]
    for bucket in summary["l1"].values():
        bucket["fact_recall"] = bucket["stated"] / bucket["facts"] if bucket["facts"] else None
        bucket["fact_retention"] = bucket["stated"] / bucket["visible"] if bucket["visible"] else None
        bucket["citation_quality"] = bucket["grounded_paper"] / bucket["stated"] if bucket["stated"] else None
    l2 = [row for row in scored_rows if row["level"] == 2]
    if l2:
        summary["l2"] = {
            "questions": len(l2),
            "cited_gold_papers_median": median(row["answer"]["cited_gold_papers"] for row in l2),
            "cited_papers_median": median(row["answer"]["cited_papers"] for row in l2),
        }
    controls = [row for row in scored_rows if row["control"]]
    if controls:
        summary["controls"] = {
            "questions": len(controls),
            "abstained": sum(1 for row in controls if row["answer"]["abstained"]),
            "absent_entity_claims": sum(row["answer"]["absent_entity_claims"] for row in controls),
        }
    timing = [row["timing"] for row in scored_rows if row["timing"].get("generation_seconds")]

    def stat(key):
        values = sorted(value for value in (item.get(key) for item in timing) if value is not None)
        if not values:
            return None
        return {"median": median(values), "p90": values[min(len(values) - 1, int(round(0.9 * (len(values) - 1))))], "max": values[-1]}

    summary["timing"] = {key: stat(key) for key in (
        "generation_seconds", "prompt_tokens", "answer_tokens", "prefill_tokens_per_second", "decode_tokens_per_second", "load_seconds",
    )}
    summary["hallucination_flags"] = {
        "answers_with_unsupported_numbers": sum(1 for row in scored_rows if row["comparison"]["unsupported_numbers"]),
        "unsupported_numbers": sum(len(row["comparison"]["unsupported_numbers"]) for row in scored_rows),
        "answers_with_raw_attributions": sum(1 for row in scored_rows if row["comparison"]["raw_attributions"]),
        "answers_with_think_tags": sum(1 for row in scored_rows if row["comparison"]["think_tag_in_output"]),
    }
    summary["resources"] = {
        "runner_peak_rss_gb": max((row["comparison"]["runner_peak_rss_kb"] for row in scored_rows), default=0) / 1024 / 1024,
        "runner_avg_cores_median": median(row["comparison"]["runner_avg_cores"] or 0 for row in scored_rows) if scored_rows else None,
    }
    return summary


def summary_markdown(meta, summary, rows):
    lines = [
        f"# Model comparison — {meta['model']}",
        "",
        f"Snapshot: `{meta['snapshot']}` · questions: {meta['questions']} · repeat: {meta['repeat']} · think: {meta['think']} · started {meta['started_at']}",
        f"Model: digest {meta['model_info'].get('digest')}, loaded size {meta['model_info'].get('size')}",
        "",
        "| L1 split | Questions | Facts | Visible | Raw | Stated | Recall | Retention | Cited same line to gold paper |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for split, bucket in sorted(summary["l1"].items()):
        lines.append(
            f"| {split} | {bucket['questions']} | {bucket['facts']} | {bucket['visible']} | {bucket['raw']} | {bucket['stated']} | "
            f"{bucket['fact_recall']:.0%} | {(bucket['fact_retention'] or 0):.0%} | {(bucket['citation_quality'] or 0):.0%} |"
        )
    lines += ["", f"Outcomes: {summary['outcomes']}", f"L2: {summary['l2']}", f"Controls: {summary['controls']}",
              f"Hallucination flags: {summary['hallucination_flags']}", f"Resources: {summary['resources']}", "", "| Timing | Median | p90 | Max |", "|---|---|---|---|"]
    for key, value in summary["timing"].items():
        if value:
            lines.append(f"| {key} | {value['median']:.1f} | {value['p90']:.1f} | {value['max']:.1f} |")
    lines += ["", "| Question | Outcome | Facts stated / visible | Unsupported numbers | Gen. s | Answer tokens |", "|---|---|---|---|---|---|"]
    for row in rows:
        facts = row["facts"]
        lines.append(
            f"| {row['id']} | {row['answer']['outcome']} | {sum(f['in_answer'] for f in facts)} / {sum(f['visible_in_any_block'] for f in facts)} | "
            f"{', '.join(row['comparison']['unsupported_numbers']) or '—'} | {row['timing'].get('generation_seconds') or 0:.0f} | {row['timing'].get('answer_tokens')} |"
        )
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate answers with one Ollama model on stored evidence and score them.")
    parser.add_argument("--model", required=True, help="Ollama model tag, e.g. qwen3:8b")
    parser.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT), help="Benchmark run whose stored contexts are replayed")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--ids", help="Comma-separated question ids")
    group.add_argument("--set", choices=["screening", "stability", "full"], default="full")
    parser.add_argument("--think", choices=["auto", "on", "off"], default="auto", help="Ollama 'think' flag; auto = off for qwen3 models")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--keep-others-loaded", action="store_true", help="Do not unload other Ollama models first")
    parser.add_argument("--label", default="")
    parser.add_argument("--prompt-variant", choices=["default", "claims"], default="default",
                        help="claims = flat one-finding-per-bullet structure instead of profile sections")
    parser.add_argument("--max-blocks", type=int, help="Keep only the first N evidence blocks")
    parser.add_argument("--block-order", choices=["ranked", "reversed"], default="ranked")
    parser.add_argument("--min-free-gb", type=float, default=3.5,
                        help="Reload the model (clearing Ollama's prompt cache) when available RAM falls below this")
    args = parser.parse_args(argv)

    os.chdir(PROJECT_ROOT)
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    sys.path.insert(0, str(PROJECT_ROOT / "src" / "evaluation"))
    from scoring import score_record

    if args.ids:
        ids = [value.strip() for value in args.ids.split(",") if value.strip()]
    else:
        ids = {"screening": SCREENING_IDS, "stability": STABILITY_IDS, "full": ""}[args.set]
        ids = [value for value in ids.split(",") if value]
    think = {"on": True, "off": False, "auto": False if args.model.startswith("qwen3") else None}[args.think]
    definitions = {item["id"]: item for item in json.loads(QUESTIONS_PATH.read_text())["questions"]}
    snapshot = load_snapshot(args.snapshot, ids)

    if not args.keep_others_loaded:
        unload_other_models(args.model)
    generator, captured, validations = make_generator(args.model, think)
    apply_prompt_variant(generator, args.prompt_variant)
    started_load = time.perf_counter()
    with contextlib.redirect_stdout(io.StringIO()):
        generator.warm_up()
    load_seconds = time.perf_counter() - started_load

    tag = re.sub(r"[^A-Za-z0-9.]+", "-", args.model)
    name = f"{datetime.now():%Y%m%d_%H%M%S}_model_{tag}" + (f"_{args.label}" if args.label else "")
    run_dir = PROJECT_ROOT / "benchmark_runs" / name
    (run_dir / "records").mkdir(parents=True)
    meta = {
        "model": args.model,
        "snapshot": str(Path(args.snapshot).relative_to(PROJECT_ROOT)) if Path(args.snapshot).is_absolute() else args.snapshot,
        "questions": len(snapshot),
        "repeat": args.repeat,
        "think": think,
        "prompt_variant": args.prompt_variant,
        "max_blocks": args.max_blocks,
        "block_order": args.block_order,
        "options": dict(generator.options),
        "load_seconds": load_seconds,
        "model_info": loaded_model_info(args.model),
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }
    print(f"[compare] {args.model}: {len(snapshot)} questions, load {load_seconds:.1f}s -> {run_dir.relative_to(PROJECT_ROOT)}", flush=True)

    rows = []
    meta["reloads"] = 0
    for index, snapshot_record in enumerate(snapshot, 1):
        available = mem_available_gb()
        if available is not None and available < args.min_free_gb:
            print(f"[compare] {available:.1f} GB available < {args.min_free_gb} GB: reloading model to clear prompt cache", flush=True)
            reload_model(generator)
            meta["reloads"] += 1
        record = generate_record(snapshot_record, generator, captured, validations, args.model, args.repeat,
                                 args.max_blocks, args.block_order)
        (run_dir / "records" / f"{record['id']}__r{args.repeat}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False, default=str))
        row = score_record(record, definitions[record["id"]])
        row["comparison"] = record["comparison"]
        rows.append(row)
        facts = row["facts"]
        print(
            f"[compare] {index}/{len(snapshot)} {record['id']}: {row['answer']['outcome']}, "
            f"facts {sum(f['in_answer'] for f in facts)}/{sum(f['visible_in_any_block'] for f in facts)}, "
            f"{row['timing'].get('generation_seconds') or 0:.0f}s, {row['timing'].get('answer_tokens')} tokens",
            flush=True,
        )

    summary = summarize(rows, definitions)
    meta["finished_at"] = datetime.now().isoformat(timespec="seconds")
    (run_dir / "scores.json").write_text(json.dumps({"meta": meta, "summary": summary, "runs": rows}, indent=2, default=str))
    (run_dir / "summary.md").write_text(summary_markdown(meta, summary, rows))
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
