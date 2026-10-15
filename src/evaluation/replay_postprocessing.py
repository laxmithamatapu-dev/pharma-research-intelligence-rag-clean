import argparse
import contextlib
import glob
import importlib.util
import io
import json
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CITATION_ONLY = re.compile(r"^\s*(?:[-*]\s*)?(?:\[E\d+\][\s.,;]*)+$", re.IGNORECASE)


def load_generator(source, name):
    spec = importlib.util.spec_from_loader(name, loader=None)
    module = importlib.util.module_from_spec(spec)
    exec(compile(source, f"<{name}>", "exec"), module.__dict__)
    with contextlib.redirect_stdout(io.StringIO()):
        return module.QwenGenerator()


def postprocess(generator, raw, context):
    answer = generator.normalize_answer(raw)
    first_errors = generator.validate_answer(answer, context)
    pruned = False
    if first_errors:
        pruned = True
        answer = generator.normalize_answer(generator._retain_cited_claims(answer, context))
        final_errors = generator.validate_answer(answer, context)
    else:
        final_errors = []
    outcome = "fail" if final_errors or not answer else ("pass_after_prune" if pruned else "pass_first")
    body_lines = []
    for line in answer.splitlines():
        if re.match(r"^\s*#+\s*references\s*$", line, re.IGNORECASE):
            break
        if line.strip() and not line.lstrip().startswith("#"):
            body_lines.append(line)
    return {
        "outcome": outcome,
        "first_errors": first_errors,
        "citation_only_lines": sum(1 for line in body_lines if CITATION_ONLY.match(line)),
        "abstention_lines": sum(
            1 for line in body_lines
            if "not established in the supplied evidence" in line.casefold()
        ),
        "answer_chars": len(answer),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Replay stored raw Qwen outputs through old and new post-processing.")
    parser.add_argument("--old-ref", required=True, help="Git ref of the generator before the fixes.")
    parser.add_argument("--runs", default="benchmark_runs/*_full_*")
    args = parser.parse_args(argv)

    old_source = subprocess.run(
        ["git", "show", f"{args.old_ref}:src/generation/generator.py"],
        cwd=PROJECT_ROOT, capture_output=True, text=True, check=True,
    ).stdout
    new_source = (PROJECT_ROOT / "src" / "generation" / "generator.py").read_text(encoding="utf-8")
    old_generator = load_generator(old_source, "generator_old")
    new_generator = load_generator(new_source, "generator_new")

    rows = []
    for path in sorted(glob.glob(str(PROJECT_ROOT / args.runs / "records" / "*.json"))):
        record = json.loads(Path(path).read_text(encoding="utf-8"))
        calls = [call for call in record.get("ollama_calls", []) if call.get("stage") == "generation"]
        if not calls or not calls[-1].get("stdout"):
            continue
        raw = calls[-1]["stdout"]
        context = (record.get("context") or {}).get("text") or ""
        rows.append({
            "run": Path(path).parents[1].name,
            "record": Path(path).stem,
            "old": postprocess(old_generator, raw, context),
            "new": postprocess(new_generator, raw, context),
        })

    summary = {}
    for side in ("old", "new"):
        summary[side] = {
            "outcomes": {},
            "citation_only_lines": sum(row[side]["citation_only_lines"] for row in rows),
            "abstention_lines": sum(row[side]["abstention_lines"] for row in rows),
            "forbidden_phrase_errors": sum(
                1 for row in rows for error in row[side]["first_errors"] if error.startswith("forbidden phrase")
            ),
        }
        for row in rows:
            outcome = row[side]["outcome"]
            summary[side]["outcomes"][outcome] = summary[side]["outcomes"].get(outcome, 0) + 1
    print(json.dumps({"answers": len(rows), "summary": summary, "rows": rows}, indent=2))


if __name__ == "__main__":
    main()
