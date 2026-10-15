import argparse
import contextlib
import glob
import io
import json
import os
import re
import sys
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
QUESTIONS_PATH = Path(__file__).resolve().parent / "benchmark_questions.json"
ADAPTIVE_MARGINS = (0.5, 1.0, 1.5, 2.0, 3.0)


def prepare_imports():
    os.chdir(PROJECT_ROOT)
    for path in (PROJECT_ROOT, PROJECT_ROOT / "src"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Session 2 gate: paper-first retrieval vs legacy on the benchmark.")
    parser.add_argument("legacy_run_dir", help="Retrieval-only run of the legacy pipeline (baseline and questions).")
    args = parser.parse_args(argv)
    prepare_imports()
    with contextlib.redirect_stdout(io.StringIO()):
        from generation.context_builder import build_context
        from query_understanding.query_understanding import QueryUnderstanding
        from retrieval.paper_retriever import candidate_papers, paper_margin, prerank_passages, rank_papers
        from retrieval.reranker import select_passages_by_paper
        from retrieval.retrieval_strategy import PLAN_SHAPES, plan_for
        from vector_store.chroma_store import collection, passages_for_paper
        query_understanding = QueryUnderstanding()
    from evaluation.scoring import parse_context_blocks

    definitions = {d["id"]: d for d in json.loads(QUESTIONS_PATH.read_text())["questions"]}
    legacy = {
        json.loads(Path(p).read_text())["id"]: json.loads(Path(p).read_text())
        for p in glob.glob(f"{args.legacy_run_dir}/records/*.json")
    }

    def evaluate(definition, chunks):
        with contextlib.redirect_stdout(io.StringIO()):
            context, evidence_map = build_context(chunks=chunks)
        blocks = parse_context_blocks(context)
        gold = set(definition.get("gold_pmcs", []))
        gold_text = [t for e, t in blocks.items() if evidence_map[e]["chunk_id"].rsplit("_", 1)[0] in gold]
        ids = [c["chunk_id"] for c in chunks]
        papers = {i.rsplit("_", 1)[0] for i in ids}
        answer = [c for c, g in definition.get("gold_chunks", {}).items() if g >= 2]
        aspects = definition.get("aspects") or []
        return {
            "facts": sum(1 for f in definition.get("facts", []) if any(re.search(f["pattern"], t, re.I) for t in gold_text)),
            "answer_delivered": sum(1 for c in answer if c in ids),
            "gold_paper_delivered": bool(gold & papers),
            "gold_papers": len(gold & papers),
            "aspects": sum(1 for a in aspects if set(a["gold_pmcs"]) & papers) / len(aspects) if aspects else None,
            "passages": len(ids),
            "context_chars": len(context),
        }

    results = {}
    margins = {}
    seconds = {}
    for question_id, definition in sorted(definitions.items()):
        question = definition["question"]
        with contextlib.redirect_stdout(io.StringIO()):
            query_info = query_understanding.analyze(question)
        started = time.perf_counter()
        sources, telemetry, question_vector = candidate_papers(question, 30, 60)
        ranked, paper_telemetry = rank_papers(question, sources)
        stage_seconds = time.perf_counter() - started
        margins[question_id] = {"margin": paper_margin(ranked), "scope": query_info["scope"],
                                "top_paper_score": ranked[0].score if ranked else None,
                                "gold_rank": next((i + 1 for i, p in enumerate(ranked) if p.pmcid in set(definition.get("gold_pmcs", []))), None)}
        passages_cache = {}

        def run(allocation):
            selected = ranked[:len(allocation)]
            papers_input = []
            for paper, quota in zip(selected, allocation):
                if paper.pmcid not in passages_cache:
                    passages_cache[paper.pmcid] = prerank_passages(question_vector, passages_for_paper(paper.pmcid), 20)
                papers_input.append((paper.pmcid, passages_cache[paper.pmcid], quota))
            t = time.perf_counter()
            with contextlib.redirect_stdout(io.StringIO()):
                chunks = select_passages_by_paper(question, papers_input, query_info.get("question_type"))
            return chunks, time.perf_counter() - t

        rows = {}
        timing = {}
        for shape, allocation in PLAN_SHAPES.items():
            chunks, elapsed = run(allocation)
            rows[f"shape:{shape}"] = evaluate(definition, chunks)
            timing[f"shape:{shape}"] = stage_seconds + elapsed
        for unspecified in ("hedged", "breadth", "depth"):
            plan = plan_for(query_info, unspecified_shape=unspecified)
            rows[f"rules|unspecified={unspecified}"] = rows[f"shape:{plan.shape}"]
            timing[f"rules|unspecified={unspecified}"] = timing[f"shape:{plan.shape}"]
        for threshold in ADAPTIVE_MARGINS:
            plan = plan_for(query_info, unspecified_shape="adaptive", adaptive_margin=threshold)
            if plan.shape == "adaptive":
                shape = "depth" if margins[question_id]["margin"] >= threshold else "breadth"
            else:
                shape = plan.shape
            rows[f"rules|unspecified=adaptive@{threshold}"] = rows[f"shape:{shape}"]
            timing[f"rules|unspecified=adaptive@{threshold}"] = timing[f"shape:{shape}"]
        oracle = "depth" if definition["level"] == 1 and not definition.get("control") else "breadth"
        rows["oracle_level"] = rows[f"shape:{oracle}"]
        timing["oracle_level"] = timing[f"shape:{oracle}"]
        record = legacy[question_id]
        legacy_chunks = []
        got = collection.get(ids=[c["chunk_id"] for c in record["rerank"]["final"]], include=["documents", "metadatas"])
        by_id = {i: {"chunk_id": i, "text": t, "metadata": m} for i, t, m in zip(got["ids"], got["documents"], got["metadatas"])}
        legacy_chunks = [by_id[c["chunk_id"]] for c in record["rerank"]["final"]]
        rows["legacy"] = evaluate(definition, legacy_chunks)
        timing["legacy"] = (record["rerank"].get("seconds") or 0) + (record["retrieval"].get("embed_seconds") or 0) + (record["retrieval"].get("chroma_seconds") or 0)
        results[question_id] = rows
        seconds[question_id] = timing
        print(f"[s2] {question_id} scope={query_info['scope']} margin={margins[question_id]['margin']:.2f}", file=sys.stderr, flush=True)

    l1 = [q for q, d in definitions.items() if d["level"] == 1 and not d.get("control")]
    l2 = [q for q, d in definitions.items() if d["level"] == 2]
    summary = {}
    for key in next(iter(results.values())):
        summary[key] = {
            "l1_facts": sum(results[q][key]["facts"] for q in l1),
            "l1_all_facts": sum(1 for q in l1 if results[q][key]["facts"] == len(definitions[q]["facts"])),
            "l1_zero_facts": sum(1 for q in l1 if results[q][key]["facts"] == 0),
            "l1_answer_delivered": sum(results[q][key]["answer_delivered"] for q in l1),
            "l1_gold_paper": sum(1 for q in l1 if results[q][key]["gold_paper_delivered"]),
            "l2_gold_papers": sum(results[q][key]["gold_papers"] for q in l2),
            "l2_aspects": float(np.mean([results[q][key]["aspects"] for q in l2])),
            "mean_passages": float(np.mean([results[q][key]["passages"] for q in results])),
            "mean_context_chars": float(np.mean([results[q][key]["context_chars"] for q in results])),
            "mean_retrieval_seconds": float(np.mean([seconds[q][key] for q in results])),
            "p90_retrieval_seconds": float(np.percentile([seconds[q][key] for q in results], 90)),
        }
    output = {"summary": summary, "margins": margins, "per_question": results, "seconds": seconds}
    out = Path(args.legacy_run_dir) / "paper_first_eval.json"
    out.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
