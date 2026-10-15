import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QUESTIONS_PATH = Path(__file__).resolve().parent / "benchmark_questions.json"
RUNS_ROOT = PROJECT_ROOT / "benchmark_runs"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run benchmark questions through the app.py execution path.",
    )
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS_PATH)
    parser.add_argument("--ids", default="", help="Comma-separated question IDs.")
    parser.add_argument("--level", type=int, choices=(1, 2), help="Run only this level.")
    parser.add_argument(
        "--status",
        choices=("all", "draft", "verified"),
        default="all",
        help="Filter questions by review_status.",
    )
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--seed", type=int, default=0, help="PYTHONHASHSEED for the run.")
    parser.add_argument(
        "--retrieval-only",
        action="store_true",
        help="Level 0: run the full app path but skip the Qwen generation call.",
    )
    parser.add_argument(
        "--strategy-override",
        default="",
        help="Force retrieval_k:top_k, e.g. 60:8 (Level 0 fixed-strategy mode).",
    )
    parser.add_argument(
        "--no-expansions",
        action="store_true",
        help="Clear expanded_queries after query understanding.",
    )
    parser.add_argument("--no-warmup", action="store_true")
    parser.add_argument(
        "--no-ollama-verbose",
        action="store_true",
        help="Do not add --verbose to ollama run (disables token telemetry).",
    )
    parser.add_argument(
        "--qu-stability",
        default="",
        help="Comma-separated seeds; run only query understanding under each seed.",
    )
    parser.add_argument("--label", default="")
    parser.add_argument("--qu-only", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def ensure_seed(seed):
    if os.environ.get("PYTHONHASHSEED") == str(seed):
        return
    environment = dict(os.environ, PYTHONHASHSEED=str(seed))
    os.execve(sys.executable, [sys.executable, *sys.argv], environment)


def prepare_imports():
    os.chdir(PROJECT_ROOT)
    for path in (PROJECT_ROOT, PROJECT_ROOT / "src"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))


def load_definitions(args):
    payload = json.loads(args.questions.read_text(encoding="utf-8"))
    definitions = payload["questions"]
    ids = [value.strip() for value in args.ids.split(",") if value.strip()]
    if ids:
        known = {definition["id"] for definition in definitions}
        unknown = [value for value in ids if value not in known]
        if unknown:
            raise SystemExit(f"Unknown question IDs: {', '.join(unknown)}")
        definitions = [definition for definition in definitions if definition["id"] in ids]
    if args.level:
        definitions = [definition for definition in definitions if definition["level"] == args.level]
    if args.status != "all":
        definitions = [
            definition for definition in definitions
            if definition.get("review_status") == args.status
        ]
    if not definitions:
        raise SystemExit("No questions selected.")
    return definitions


def build_items(definitions, repeats, warmup):
    items = []
    if warmup:
        items.append({"definition": definitions[0], "repeat": 0, "warmup": True})
    for repeat in range(1, repeats + 1):
        items.extend(
            {"definition": definition, "repeat": repeat, "warmup": False}
            for definition in definitions
        )
    return items


def run_query_understanding_only(definitions):
    from query_understanding.query_understanding import QueryUnderstanding
    from retrieval.retrieval_strategy import StrategyManager

    results = {}
    with contextlib.redirect_stdout(io.StringIO()):
        query_understanding = QueryUnderstanding()
        strategy_manager = StrategyManager()
        for definition in definitions:
            _, confidence = query_understanding._classify_without_llm(definition["question"])
            query_info = query_understanding.analyze(definition["question"])
            strategy = strategy_manager.get_strategy({"intent": query_info.get("intent", "GENERAL")})
            results[definition["id"]] = {
                "intent": query_info.get("intent"),
                "question_type": query_info.get("question_type"),
                "fast_path_confidence": confidence,
                "llm_fallback": confidence < query_understanding.confidence_threshold,
                "expanded_queries": len(query_info.get("expanded_queries") or []),
                "retrieval_k": strategy.retrieval_k,
                "top_k": strategy.top_k,
            }
    print(json.dumps(results))


def run_query_understanding_stability(args, definitions, run_dir):
    seeds = [int(value) for value in args.qu_stability.split(",") if value.strip()]
    by_seed = {}
    for seed in seeds:
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--qu-only",
            "--seed", str(seed),
            "--questions", str(args.questions),
            "--status", args.status,
        ]
        if args.ids:
            command += ["--ids", args.ids]
        if args.level:
            command += ["--level", str(args.level)]
        print(f"[benchmark] query understanding, seed {seed}", file=sys.stderr, flush=True)
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            env=dict(os.environ, PYTHONHASHSEED=str(seed)),
            cwd=PROJECT_ROOT,
        )
        if result.returncode != 0:
            raise SystemExit(f"Seed {seed} failed:\n{result.stderr}")
        by_seed[str(seed)] = json.loads(result.stdout.strip().splitlines()[-1])

    questions = {}
    for definition in definitions:
        question_id = definition["id"]
        labels = {
            seed: [values[question_id]["intent"], values[question_id]["question_type"]]
            for seed, values in by_seed.items()
        }
        counts = Counter(tuple(label) for label in labels.values())
        modal, modal_count = counts.most_common(1)[0]
        questions[question_id] = {
            "stability": modal_count / len(labels),
            "modal": list(modal),
            "by_seed": labels,
            "top_k_by_seed": {seed: values[question_id]["top_k"] for seed, values in by_seed.items()},
        }
    stability = {"seeds": seeds, "questions": questions, "raw": by_seed}
    with (run_dir / "qu_stability.json").open("w", encoding="utf-8") as handle:
        json.dump(stability, handle, indent=2)
    return stability


def main(argv=None):
    args = parse_args(argv)
    ensure_seed(args.seed)
    prepare_imports()
    definitions = load_definitions(args)

    if args.qu_only:
        run_query_understanding_only(definitions)
        return

    mode = "qu-stability" if args.qu_stability else ("retrieval" if args.retrieval_only else "full")
    run_name = "_".join(
        part for part in (datetime.now().strftime("%Y%m%d_%H%M%S"), mode, args.label) if part
    )
    run_dir = RUNS_ROOT / run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    if args.qu_stability:
        from evaluation.report import _table

        stability = run_query_understanding_stability(args, definitions, run_dir)
        rows = [
            [question_id, entry["stability"], entry["modal"], json.dumps(entry["by_seed"], sort_keys=True)]
            for question_id, entry in stability["questions"].items()
        ]
        (run_dir / "summary.md").write_text(
            "# Query-understanding stability\n\n"
            + _table(["ID", "Stability", "Modal (intent, type)", "By seed"], rows)
            + "\n",
            encoding="utf-8",
        )
        print(run_dir)
        return

    strategy_override = None
    if args.strategy_override:
        retrieval_k, top_k = (int(value) for value in args.strategy_override.split(":"))
        strategy_override = (retrieval_k, top_k)

    options = {
        "run_name": run_name,
        "mode": mode,
        "question_ids": [definition["id"] for definition in definitions],
        "repeats": args.repeats,
        "warmup": not args.no_warmup and not args.retrieval_only,
        "seed": args.seed,
        "strategy_override": args.strategy_override or None,
        "no_expansions": args.no_expansions,
        "ollama_verbose": not args.no_ollama_verbose,
        "questions_file": str(args.questions),
        "retrieval_mode": os.environ.get("RETRIEVAL_MODE", "legacy"),
    }

    print("[benchmark] loading app (models, Chroma)", file=sys.stderr, flush=True)
    started = time.perf_counter()
    import app
    import_seconds = time.perf_counter() - started

    from evaluation.harness import BenchmarkHarness, collect_fingerprint
    from evaluation.report import write_report
    from evaluation.scoring import score_run
    from retrieval.retriever import collection

    fingerprint = collect_fingerprint(collection, options, import_seconds)
    with (run_dir / "fingerprint.json").open("w", encoding="utf-8") as handle:
        json.dump(fingerprint, handle, indent=2, default=str)

    harness = BenchmarkHarness(
        run_dir=run_dir,
        items=build_items(definitions, args.repeats, options["warmup"]),
        retrieval_only=args.retrieval_only,
        ollama_verbose=not args.no_ollama_verbose,
        strategy_override=strategy_override,
        disable_expansions=args.no_expansions,
    )
    harness.install(app)
    try:
        harness.run(app, run_dir / "app_stdout.log")
    finally:
        harness.uninstall(app)
    harness.replay_rerank()

    scores = score_run(harness.records, definitions)
    summary_path = write_report(run_dir, fingerprint, scores)
    print(summary_path)


if __name__ == "__main__":
    main()
