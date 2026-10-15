import argparse
import contextlib
import io
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
QUESTIONS_PATH = Path(__file__).resolve().parent / "benchmark_questions.json"
NUMERIC_RULE = (
    "- When the evidence states numbers (percentages, counts, durations, hazard ratios, confidence\n"
    "  intervals, p-values, doses), report them exactly as written, with units and comparison groups.\n"
    "  Do not round them or replace them with words such as \"significant\" or \"substantial\".\n"
)
NUMBER = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)(\s*%)?")


def unsupported_numbers(answer, context):
    body = answer.split("## References")[0]
    body = re.sub(r"\[E\d+\]", "", body)
    flat_context = " ".join(context.split())
    missing = []
    for match in NUMBER.finditer(body):
        value = match.group(1)
        if "." not in value and not match.group(2) and len(value) < 2:
            continue
        if value not in flat_context:
            missing.append(match.group(0).strip())
    return missing


def main(argv=None):
    parser = argparse.ArgumentParser(description="A/B test of an exact-numbers instruction on the same evidence.")
    parser.add_argument("--ids", required=True)
    args = parser.parse_args(argv)
    os.chdir(PROJECT_ROOT)
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    with contextlib.redirect_stdout(io.StringIO()):
        from generation.context_builder import build_context
        from generation.generator import QwenGenerator
        from query_understanding.query_understanding import QueryUnderstanding
        from retrieval.retrieval_strategy import plan_for
        from retrieval.retriever import retrieve_evidence

        class NumericRuleGenerator(QwenGenerator):
            def build_prompt(self, question, context, query_info=None):
                prompt = super().build_prompt(question, context, query_info)
                return prompt.replace("- Finish with ## References", NUMERIC_RULE + "- Finish with ## References", 1)

        query_understanding = QueryUnderstanding()
        arms = {"baseline": QwenGenerator(), "numeric_rule": NumericRuleGenerator()}

    definitions = {d["id"]: d for d in json.loads(QUESTIONS_PATH.read_text())["questions"]}
    rows = []
    for question_id in [value.strip() for value in args.ids.split(",") if value.strip()]:
        definition = definitions[question_id]
        with contextlib.redirect_stdout(io.StringIO()):
            query_info = query_understanding.analyze(definition["question"])
            evidence = retrieve_evidence(definition["question"], query_info, plan_for(query_info))
            context, _ = build_context(chunks=evidence.chunks)
        for arm, generator in arms.items():
            started = time.perf_counter()
            error = None
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    answer = generator.generate(definition["question"], context, query_info)
            except Exception as exc:
                answer, error = "", f"{type(exc).__name__}: {exc}"
            rows.append({
                "id": question_id,
                "arm": arm,
                "facts_total": len(definition["facts"]),
                "facts_stated": sum(1 for f in definition["facts"] if re.search(f["pattern"], answer, re.IGNORECASE)),
                "unsupported_numbers": unsupported_numbers(answer, context),
                "error": error,
                "answer_tokens": generator.last_stats.get("eval_count"),
                "prompt_tokens": generator.last_stats.get("prompt_eval_count"),
                "seconds": time.perf_counter() - started,
                "answer": answer,
            })
            print(f"[numeric] {question_id} {arm}: facts {rows[-1]['facts_stated']}/{rows[-1]['facts_total']} "
                  f"unsupported {len(rows[-1]['unsupported_numbers'])} {rows[-1]['seconds']:.0f}s {error or ''}",
                  file=sys.stderr, flush=True)
    out_dir = PROJECT_ROOT / "benchmark_runs" / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_numeric_fidelity"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(out_dir / "results.json")


if __name__ == "__main__":
    main()
