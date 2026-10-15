import json
from pathlib import Path


def _fmt(value, digits=2):
    if value is None:
        return "–"
    if isinstance(value, bool):
        return "Y" if value else "N"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    if isinstance(value, (list, tuple)):
        return ",".join(str(item) for item in value) or "–"
    return str(value)


def _stats_cell(stats, digits=1):
    if not stats:
        return "–"
    return f"{_fmt(stats['median'], digits)} / {_fmt(stats['p90'], digits)}"


def _table(headers, rows):
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    lines.extend("| " + " | ".join(_fmt(cell) for cell in row) + " |" for row in rows)
    return "\n".join(lines)


def build_markdown(fingerprint, scores, qu_stability=None):
    options = fingerprint.get("options") or {}
    lines = [
        f"# Benchmark run {options.get('run_name', '')}",
        "",
        f"- Created: {fingerprint.get('created_at')}",
        f"- Git HEAD: `{fingerprint.get('git_head')}`; diff sha256 `{str(fingerprint.get('git_diff_sha256'))[:12]}`",
        f"- Chroma count: {fingerprint.get('chroma_collection_count')}; index manifest sha256 `{str(fingerprint.get('index_manifest_sha256'))[:12]}`",
        f"- PYTHONHASHSEED: {fingerprint.get('pythonhashseed')}; import seconds: {_fmt(fingerprint.get('import_seconds'))}",
        f"- Options: `{json.dumps(options, sort_keys=True)}`",
        f"- Proposed criteria (not owner-approved): `{json.dumps(scores['criteria'], sort_keys=True)}`",
        "",
        "## Level summary",
        "",
    ]
    level_rows = []
    for level, summary in scores["levels"].items():
        level_rows.append([
            level,
            summary["questions"],
            summary["questions_majority_pass"],
            summary["runs"],
            json.dumps(summary["outcomes"], sort_keys=True),
            summary["retrieval_pass_rate"],
            _stats_cell(summary["fact_recall"], 2),
            _stats_cell(summary["aspect_coverage_final"], 2),
            _stats_cell(summary["rerank_seconds"]),
            _stats_cell(summary["generation_seconds"]),
            _stats_cell(summary["app_total_seconds"]),
            _stats_cell(summary["prompt_tokens"], 0),
            _stats_cell(summary["answer_tokens"], 0),
            _stats_cell(summary["decode_tokens_per_second"]),
            json.dumps(summary["answer_chunk_loss"], sort_keys=True),
        ])
    lines.append(_table(
        [
            "Level", "Questions", "Majority pass", "Runs", "Outcomes", "Retrieval pass rate",
            "Fact recall med/p90", "Aspect cov. med/p90", "Rerank s med/p90",
            "Generation s med/p90", "Total s med/p90", "Prompt tok med/p90",
            "Answer tok med/p90", "Decode tok/s med/p90", "Answer-chunk loss",
        ],
        level_rows,
    ))

    lines.extend(["", "## Runs", ""])
    run_rows = []
    for run in scores["runs"]:
        retrieval = run["retrieval"]
        answer = run["answer"]
        timing = run["timing"]
        run_rows.append([
            run["id"],
            run["repeat"],
            run["review_status"],
            retrieval["intent"],
            retrieval["question_type"],
            retrieval["llm_fallback"],
            f"{retrieval['retrieval_k']}/{retrieval['top_k']}",
            retrieval["pool_size"],
            f"{retrieval['pool_gold_papers']}/{retrieval['gold_papers']}",
            retrieval["dense_best_rank_answer_chunk"] or retrieval["dense_best_rank_gold_paper"],
            retrieval["ce_rank_answer_chunk"] or retrieval["ce_rank_gold_paper"],
            retrieval["final_gold_paper_positions"],
            retrieval["final_answer_chunk_positions"],
            retrieval.get("aspect_coverage_final"),
            f"{run['context']['facts_visible']}/{run['context']['facts_total']}",
            answer["outcome"],
            answer["fact_recall"],
            f"{answer['facts_grounded_paper']}/{answer['facts_matched']}",
            answer["cited_gold_papers"],
            timing["prompt_tokens"],
            timing["answer_tokens"],
            timing["prefill_seconds"],
            timing["decode_seconds"],
            timing["app_total_seconds"],
            run["evaluation"]["pass"],
        ])
    lines.append(_table(
        [
            "ID", "Rep", "Status", "Intent", "Type", "QU LLM", "k", "Pool", "Gold papers in pool",
            "Dense rank", "CE rank", "Gold paper pos", "Answer chunk pos", "Aspect cov.",
            "Facts visible", "Outcome", "Fact recall", "Grounded/matched", "Cited gold papers",
            "Prompt tok", "Answer tok", "Prefill s", "Decode s", "Total s", "Pass",
        ],
        run_rows,
    ))

    if qu_stability:
        lines.extend(["", "## Query-understanding stability", ""])
        stability_rows = [
            [
                question_id,
                entry["stability"],
                entry["modal"],
                json.dumps(entry["by_seed"], sort_keys=True),
            ]
            for question_id, entry in qu_stability["questions"].items()
        ]
        lines.append(_table(["ID", "Stability", "Modal (intent, type)", "By seed"], stability_rows))

    lines.extend([
        "",
        "## Notes",
        "",
        "- Dense/CE rank: best rank of a labeled answer chunk; falls back to gold paper when no chunk is labeled.",
        "- Facts visible: expected facts whose pattern occurs in the truncated text of a labeled evidence chunk supplied to Qwen.",
        "- Grounded/matched: facts found in the answer whose line cites a block from the expected paper.",
        "- Unsupported-claim review is manual and not reflected in Pass.",
    ])
    return "\n".join(lines) + "\n"


def write_report(run_dir, fingerprint, scores, qu_stability=None):
    run_dir = Path(run_dir)
    with (run_dir / "scores.json").open("w", encoding="utf-8") as handle:
        json.dump(scores, handle, indent=2, ensure_ascii=False, default=str)
    summary_path = run_dir / "summary.md"
    summary_path.write_text(build_markdown(fingerprint, scores, qu_stability), encoding="utf-8")
    return summary_path
