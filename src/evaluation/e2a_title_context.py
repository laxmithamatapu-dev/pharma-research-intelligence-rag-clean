import argparse
import contextlib
import io
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
QUESTIONS_PATH = Path(__file__).resolve().parent / "benchmark_questions.json"
METADATA_DIR = PROJECT_ROOT / "data" / "staging" / "phase1" / "metadata"
RUNS_ROOT = PROJECT_ROOT / "benchmark_runs"
K_GRID = (20, 30, 60, 100, 200, 500)
DECISION_RULES = {
    "confirmed": "L1 fact visibility after rerank +10 points or more, L1 gold-paper delivery not lower",
    "reranker_bottleneck": "answer-chunk pool entry improves but fact visibility gain < 10 points",
    "rejected": "no net improvement in pool entry or fact visibility",
}


def prepare_imports():
    os.chdir(PROJECT_ROOT)
    for path in (PROJECT_ROOT, PROJECT_ROOT / "src"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))


def load_titles():
    titles = {}
    for path in METADATA_DIR.glob("*.json"):
        titles[path.stem] = json.loads(path.read_text(encoding="utf-8")).get("title") or ""
    return titles


def command_embed(args):
    prepare_imports()
    import torch

    with contextlib.redirect_stdout(io.StringIO()):
        import embeddings.embedder as embedder
        from vector_store.chroma_store import collection

    everything = collection.get(include=["documents"])
    ids = everything["ids"]
    documents = everything["documents"]
    titles = load_titles()
    missing_titles = sorted({chunk_id.rsplit("_", 1)[0] for chunk_id in ids} - set(titles))
    vectors = np.zeros((len(ids), embedder.article_model.config.hidden_size), dtype="float32")
    started = time.perf_counter()
    for start in range(0, len(ids), args.batch_size):
        batch_ids = ids[start:start + args.batch_size]
        pairs = [
            [titles.get(chunk_id.rsplit("_", 1)[0], ""), documents[start + offset].strip()]
            for offset, chunk_id in enumerate(batch_ids)
        ]
        inputs = embedder.article_tokenizer(
            pairs,
            return_tensors="pt",
            truncation=True,
            max_length=512,
            padding=True,
        )
        with torch.no_grad():
            outputs = embedder.article_model(**inputs)
            pooled = embedder.mean_pooling(outputs.last_hidden_state, inputs["attention_mask"])
        vectors[start:start + len(batch_ids)] = pooled.cpu().numpy()
        if (start // args.batch_size) % 50 == 0:
            done = start + len(batch_ids)
            print(f"[e2a] {done}/{len(ids)} chunks, {time.perf_counter() - started:.0f}s", file=sys.stderr, flush=True)

    run_dir = RUNS_ROOT / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_e2a"
    run_dir.mkdir(parents=True, exist_ok=True)
    np.save(run_dir / "title_context_vectors.npy", vectors)
    (run_dir / "ids.json").write_text(json.dumps(ids), encoding="utf-8")
    (run_dir / "embed_meta.json").write_text(json.dumps({
        "variant": "[title, chunk] pair input, mean pooling, max_length 512",
        "chunks": len(ids),
        "missing_titles": missing_titles,
        "seconds": time.perf_counter() - started,
        "batch_size": args.batch_size,
    }, indent=2), encoding="utf-8")
    print(run_dir)


def _top_ids(matrix, ids, query_vector, k):
    distances = ((matrix - query_vector) ** 2).sum(axis=1)
    order = np.argpartition(distances, k)[:k]
    order = order[np.argsort(distances[order])]
    return [ids[row] for row in order], distances


def _replay_question(record, definition, matrix, ids, documents, metadatas, index, embed_query, rerank_chunks, build_context):
    from evaluation.rca_experiments import section_bucket
    from evaluation.scoring import parse_context_blocks, pmc_of

    strategy = record["strategy"]["used"]
    rerank_meta = record["rerank"]
    queries = [query["text"] for query in record["retrieval"]["queries"]]
    merged = {}
    best_ranks = {}
    for query in queries:
        vector = np.asarray(embed_query(query), dtype="float32")
        top, distances = _top_ids(matrix, ids, vector, strategy["retrieval_k"])
        for chunk_id in top:
            if chunk_id not in merged:
                metadata = metadatas[index[chunk_id]] or {}
                merged[chunk_id] = {
                    "chunk_id": chunk_id,
                    "text": documents[index[chunk_id]],
                    "pmcid": metadata.get("pmcid"),
                    "section_path": metadata.get("section_path"),
                    "metadata": metadata,
                }
        for chunk_id in [c for c, g in definition.get("gold_chunks", {}).items() if g >= 2]:
            rank = int((distances < distances[index[chunk_id]]).sum()) + 1
            best_ranks[chunk_id] = min(best_ranks.get(chunk_id, rank), rank)
    pool = list(merged.values())
    with contextlib.redirect_stdout(io.StringIO()):
        final = rerank_chunks(
            query=record["question"],
            chunks=pool,
            top_k=rerank_meta["top_k"],
            question_type=rerank_meta["question_type"],
            diversity_boost=rerank_meta["diversity_boost"],
        )
        context, evidence_map = build_context(chunks=final)
    gold_pmcs = set(definition.get("gold_pmcs", []))
    pool_ids = {chunk["chunk_id"] for chunk in pool}
    final_ids = [chunk["chunk_id"] for chunk in final]
    blocks = parse_context_blocks(context)
    gold_block_text = [
        text for evidence_id, text in blocks.items()
        if pmc_of(evidence_map[evidence_id]["chunk_id"]) in gold_pmcs
    ]
    facts_visible = sum(
        1 for fact in definition.get("facts", [])
        if any(re.search(fact["pattern"], text, re.IGNORECASE) for text in gold_block_text)
    )
    answer = [c for c, g in definition.get("gold_chunks", {}).items() if g >= 2]
    aspects = definition.get("aspects") or []
    final_pmcs = {pmc_of(chunk_id) for chunk_id in final_ids}
    pool_pmcs = {pmc_of(chunk_id) for chunk_id in pool_ids}
    original_vector = np.asarray(embed_query(record["question"]), dtype="float32")
    top60, _ = _top_ids(matrix, ids, original_vector, 60)
    return {
        "pool_size": len(pool),
        "answer_in_pool": sum(1 for c in answer if c in pool_ids),
        "answer_delivered": sum(1 for c in answer if c in final_ids),
        "answer_chunks": len(answer),
        "answer_best_rank": best_ranks,
        "facts_visible": facts_visible,
        "facts_total": len(definition.get("facts", [])),
        "gold_paper_delivered": bool(gold_pmcs & final_pmcs) if gold_pmcs else None,
        "gold_papers_pooled": len(gold_pmcs & pool_pmcs),
        "gold_papers_delivered": len(gold_pmcs & final_pmcs),
        "gold_papers": len(gold_pmcs),
        "aspect_coverage_final": (
            sum(1 for aspect in aspects if set(aspect["gold_pmcs"]) & final_pmcs) / len(aspects)
            if aspects else None
        ),
        "top60_sections": dict(Counter(section_bucket(metadatas[index[c]].get("section_path")) for c in top60)),
        "final": final_ids,
    }


def command_score(args):
    prepare_imports()
    with contextlib.redirect_stdout(io.StringIO()):
        from embeddings.embedder import embed_query
        from generation.context_builder import build_context
        from retrieval.reranker import rerank_chunks
        from vector_store.chroma_store import collection
    from evaluation.rca_experiments import load_seed_records

    run_dir = Path(args.run_dir)
    title_vectors = np.load(run_dir / "title_context_vectors.npy")
    title_ids = json.loads((run_dir / "ids.json").read_text())
    everything = collection.get(include=["embeddings", "documents", "metadatas"])
    ids = everything["ids"]
    if ids != title_ids:
        raise SystemExit("Chunk ID order differs between Chroma and the E2a vectors.")
    stored_vectors = np.asarray(everything["embeddings"], dtype="float32")
    documents = everything["documents"]
    metadatas = everything["metadatas"]
    index = {chunk_id: row for row, chunk_id in enumerate(ids)}
    definitions = [d for d in json.loads(QUESTIONS_PATH.read_text())["questions"]]
    records = load_seed_records(args.seed)

    results = {}
    for definition in definitions:
        record = records[definition["id"]]
        results[definition["id"]] = {
            variant: _replay_question(record, definition, matrix, ids, documents, metadatas, index,
                                      embed_query, rerank_chunks, build_context)
            for variant, matrix in (("baseline", stored_vectors), ("title_context", title_vectors))
        }
        print(f"[e2a] scored {definition['id']}", file=sys.stderr, flush=True)

    def summarize(variant):
        level1 = [d for d in definitions if d["level"] == 1 and not d.get("control")]
        level2 = [d for d in definitions if d["level"] == 2]
        rows1 = [results[d["id"]][variant] for d in level1]
        rows2 = [results[d["id"]][variant] for d in level2]
        all_answer_ranks = [rank for row in rows1 for rank in row["answer_best_rank"].values()]
        sections = Counter()
        for row in rows1 + rows2:
            sections.update(row["top60_sections"])
        return {
            "l1_fact_visibility": sum(r["facts_visible"] for r in rows1) / sum(r["facts_total"] for r in rows1),
            "l1_facts_visible": sum(r["facts_visible"] for r in rows1),
            "l1_facts_total": sum(r["facts_total"] for r in rows1),
            "l1_answer_chunks_in_pool": sum(r["answer_in_pool"] for r in rows1),
            "l1_answer_chunks_delivered": sum(r["answer_delivered"] for r in rows1),
            "l1_answer_chunks": sum(r["answer_chunks"] for r in rows1),
            "l1_gold_paper_delivered": sum(1 for r in rows1 if r["gold_paper_delivered"]),
            "l1_questions": len(rows1),
            "answer_chunk_recall_at_k": {
                str(k): sum(1 for rank in all_answer_ranks if rank <= k) / len(all_answer_ranks)
                for k in K_GRID
            },
            "l2_gold_papers_pooled": sum(r["gold_papers_pooled"] for r in rows2),
            "l2_gold_papers_delivered": sum(r["gold_papers_delivered"] for r in rows2),
            "l2_gold_papers": sum(r["gold_papers"] for r in rows2),
            "l2_aspect_coverage_mean": sum(r["aspect_coverage_final"] for r in rows2) / len(rows2),
            "top60_results_share": sections["results"] / sum(sections.values()),
            "top60_introduction_share": sections["introduction"] / sum(sections.values()),
        }

    summary = {variant: summarize(variant) for variant in ("baseline", "title_context")}
    base, title = summary["baseline"], summary["title_context"]
    gain = (title["l1_fact_visibility"] - base["l1_fact_visibility"]) * 100
    if gain >= 10 and title["l1_gold_paper_delivered"] >= base["l1_gold_paper_delivered"]:
        decision = "confirmed"
    elif title["l1_answer_chunks_in_pool"] > base["l1_answer_chunks_in_pool"]:
        decision = "reranker_bottleneck"
    else:
        decision = "rejected"
    output = {
        "seed_records": args.seed,
        "decision_rules": DECISION_RULES,
        "fact_visibility_gain_points": gain,
        "decision": decision,
        "summary": summary,
        "per_question": results,
    }
    (run_dir / "e2a_scores.json").write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(json.dumps({key: output[key] for key in ("decision", "fact_visibility_gain_points", "summary")}, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(description="E2a: title-context passage embeddings (side file, read-only).")
    subparsers = parser.add_subparsers(dest="command", required=True)
    embed_parser = subparsers.add_parser("embed")
    embed_parser.add_argument("--batch-size", type=int, default=16)
    embed_parser.set_defaults(handler=command_embed)
    score_parser = subparsers.add_parser("score")
    score_parser.add_argument("run_dir")
    score_parser.add_argument("--seed", default="0")
    score_parser.set_defaults(handler=command_score)
    args = parser.parse_args(argv)
    args.handler(args)


if __name__ == "__main__":
    main()
