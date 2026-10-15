import argparse
import contextlib
import glob
import io
import itertools
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
QUESTIONS_PATH = Path(__file__).resolve().parent / "benchmark_questions.json"
TRUNCATION = 1200
PAPER_COUNTS = (1, 2, 3, 4, 5, 6, 8)
PASSAGES_PER_PAPER = (1, 2, 3, 4, 5)


def prepare_imports():
    os.chdir(PROJECT_ROOT)
    for path in (PROJECT_ROOT, PROJECT_ROOT / "src"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))


def visible(text):
    return " ".join((text or "").split())[:TRUNCATION]


def fact_sets(definition, chunks):
    patterns = {fact["id"]: re.compile(fact["pattern"], re.IGNORECASE) for fact in definition["facts"]}
    return {
        chunk["chunk_id"]: {fact_id for fact_id, pattern in patterns.items() if pattern.search(visible(chunk["text"]))}
        for chunk in chunks
    }


def minimum_cover(sets, target, limit=5):
    candidates = [chunk_id for chunk_id, facts in sets.items() if facts & target]
    for size in range(1, limit + 1):
        for combo in itertools.combinations(candidates, size):
            if set().union(*(sets[c] for c in combo)) >= target:
                return size
    return None


def prefix_cover(order, sets, target):
    covered = set()
    for position, chunk_id in enumerate(order, start=1):
        covered |= sets[chunk_id]
        if covered >= target:
            return position
    return None


def chunks_for_ids(collection, ids):
    got = collection.get(ids=list(ids), include=["documents", "metadatas"])
    return {
        chunk_id: {"chunk_id": chunk_id, "text": text, "metadata": metadata,
                   "pmcid": metadata.get("pmcid"), "section_path": metadata.get("section_path")}
        for chunk_id, text, metadata in zip(got["ids"], got["documents"], got["metadatas"])
    }


def paper_chunks(collection, pmcid, cache):
    if pmcid not in cache:
        got = collection.get(where={"pmcid": pmcid}, include=["documents", "metadatas"])
        cache[pmcid] = [
            {"chunk_id": i, "text": t, "metadata": m, "pmcid": m.get("pmcid"), "section_path": m.get("section_path")}
            for i, t, m in zip(got["ids"], got["documents"], got["metadatas"])
        ]
    return cache[pmcid]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Paper/passage budget study on stored candidate pools.")
    parser.add_argument("run_dir")
    args = parser.parse_args(argv)
    prepare_imports()
    with contextlib.redirect_stdout(io.StringIO()):
        from retrieval import reranker
        from vector_store.chroma_store import collection

    definitions = {d["id"]: d for d in json.loads(QUESTIONS_PATH.read_text())["questions"]}
    records = {
        json.loads(Path(p).read_text())["id"]: json.loads(Path(p).read_text())
        for p in glob.glob(f"{args.run_dir}/records/*.json")
    }
    score_cache = {}

    def scores_for(question, chunks):
        missing = [c for c in chunks if (question, c["chunk_id"]) not in score_cache]
        if missing:
            values = reranker.reranker.predict([(question, c["text"]) for c in missing])
            for chunk, value in zip(missing, values):
                score_cache[(question, chunk["chunk_id"])] = float(value)
        return [score_cache[(question, c["chunk_id"])] for c in chunks]

    paper_cache = {}
    output = {"level1_need": [], "concentration": [], "designs": {}}

    for question_id, definition in definitions.items():
        if definition["level"] != 1 or definition.get("control"):
            continue
        question = records[question_id]["question"]
        pmcid = definition["gold_pmcs"][0]
        chunks = paper_chunks(collection, pmcid, paper_cache)
        sets = fact_sets(definition, chunks)
        all_facts = {fact["id"] for fact in definition["facts"]}
        coverable = set().union(*sets.values()) if sets else set()
        full_text_facts = {
            fact["id"] for fact in definition["facts"]
            if any(re.search(fact["pattern"], " ".join(c["text"].split()), re.IGNORECASE) for c in chunks)
        }
        values = scores_for(question, chunks)
        ce_order = [chunks[i]["chunk_id"] for i in np.argsort(values)[::-1]]
        output["level1_need"].append({
            "id": question_id,
            "paper_chunks": len(chunks),
            "facts": len(all_facts),
            "coverable_within_truncation": len(coverable),
            "present_only_past_truncation": len(full_text_facts - coverable),
            "minimum_passages_to_cover": minimum_cover(sets, coverable) if coverable else 0,
            "reranker_order_passages_to_cover": prefix_cover(ce_order, sets, coverable) if coverable else 0,
            "chunks_carrying_any_fact": sum(1 for facts in sets.values() if facts),
        })

    for question_id, record in records.items():
        definition = definitions[question_id]
        pool_ids = [c["chunk_id"] for c in record["rerank"]["pool"]]
        pool = chunks_for_ids(collection, pool_ids)
        pool_chunks = [pool[i] for i in pool_ids]
        values = scores_for(record["question"], pool_chunks)
        order = np.argsort(values)[::-1]
        best_by_paper = defaultdict(lambda: -1e9)
        for chunk, value in zip(pool_chunks, values):
            best_by_paper[chunk["pmcid"]] = max(best_by_paper[chunk["pmcid"]], value)
        ranked_papers = sorted(best_by_paper, key=best_by_paper.get, reverse=True)
        top10 = [pool_chunks[i]["pmcid"] for i in order[:10]]
        top_scores = [best_by_paper[p] for p in ranked_papers[:2]]
        output["concentration"].append({
            "id": question_id,
            "level": definition["level"],
            "control": bool(definition.get("control")),
            "top_paper_share_of_top10": top10.count(ranked_papers[0]) / len(top10) if top10 else None,
            "distinct_papers_in_top10": len(set(top10)),
            "top2_paper_margin": (top_scores[0] - top_scores[1]) if len(top_scores) == 2 else None,
            "top_paper_is_gold": ranked_papers[0] in set(definition.get("gold_pmcs", [])) if ranked_papers else None,
        })

        for papers_n in PAPER_COUNTS:
            for per_paper in PASSAGES_PER_PAPER:
                for source in ("pool", "full_paper"):
                    key = f"{source}|P{papers_n}|q{per_paper}"
                    selected = []
                    for pmcid in ranked_papers[:papers_n]:
                        if source == "pool":
                            candidates = [c for c in pool_chunks if c["pmcid"] == pmcid]
                        else:
                            candidates = paper_chunks(collection, pmcid, paper_cache)
                        candidate_scores = scores_for(record["question"], candidates)
                        best = [candidates[i] for i in np.argsort(candidate_scores)[::-1][:per_paper]]
                        selected.extend(best)
                    output["designs"].setdefault(key, {})[question_id] = [c["chunk_id"] for c in selected]
        output["designs"].setdefault("current", {})[question_id] = [c["chunk_id"] for c in record["rerank"]["final"]]
        print(f"[budget] {question_id}", file=sys.stderr, flush=True)

    texts = {}

    def evaluate(question_id, chunk_ids):
        definition = definitions[question_id]
        missing = [c for c in chunk_ids if c not in texts]
        if missing:
            texts.update({k: v["text"] for k, v in chunks_for_ids(collection, missing).items()})
        gold = set(definition.get("gold_pmcs", []))
        gold_text = [visible(texts[c]) for c in chunk_ids if c.rsplit("_", 1)[0] in gold]
        papers = {c.rsplit("_", 1)[0] for c in chunk_ids}
        aspects = definition.get("aspects") or []
        return {
            "facts": sum(1 for f in definition["facts"] if any(re.search(f["pattern"], t, re.IGNORECASE) for t in gold_text)),
            "gold_papers": len(gold & papers),
            "aspects": sum(1 for a in aspects if set(a["gold_pmcs"]) & papers) / len(aspects) if aspects else None,
            "passages": len(chunk_ids),
        }

    summary = {}
    for key, per_question in output["designs"].items():
        rows = {q: evaluate(q, ids) for q, ids in per_question.items()}
        l1 = [q for q, d in definitions.items() if d["level"] == 1 and not d.get("control")]
        l2 = [q for q, d in definitions.items() if d["level"] == 2]
        summary[key] = {
            "l1_facts": sum(rows[q]["facts"] for q in l1),
            "l1_all_facts": sum(1 for q in l1 if rows[q]["facts"] == len(definitions[q]["facts"])),
            "l1_mean_passages": float(np.mean([rows[q]["passages"] for q in l1])),
            "l2_gold_papers": sum(rows[q]["gold_papers"] for q in l2),
            "l2_aspect_coverage": float(np.mean([rows[q]["aspects"] for q in l2])),
            "l2_mean_passages": float(np.mean([rows[q]["passages"] for q in l2])),
        }
        output["designs"][key] = {"summary": summary[key], "per_question": rows}
    output["summary"] = summary
    out = Path(args.run_dir) / "paper_budget_study.json"
    out.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
