import argparse
import contextlib
import glob
import io
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
QUESTIONS_PATH = Path(__file__).resolve().parent / "benchmark_questions.json"
DENSE_PAPERS = 30
TOP_PAPERS = (1, 2, 3, 5, 8)


def prepare_imports():
    os.chdir(PROJECT_ROOT)
    for path in (PROJECT_ROOT, PROJECT_ROOT / "src"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))


def query_vector(embedder, text, pooling):
    import torch

    inputs = embedder.query_tokenizer(text, return_tensors="pt", truncation=True, max_length=64, padding=True)
    with torch.no_grad():
        hidden = embedder.query_model(**inputs).last_hidden_state
        if pooling == "cls":
            vector = hidden[:, 0, :]
        else:
            vector = embedder.mean_pooling(hidden, inputs["attention_mask"])
    return vector.squeeze().cpu().numpy().astype("float32")


def dense_rank(matrix, vector, distance):
    if distance == "l2":
        scores = -((matrix - vector) ** 2).sum(axis=1)
    elif distance == "ip":
        scores = matrix @ vector
    else:
        scores = (matrix / np.linalg.norm(matrix, axis=1, keepdims=True)) @ (vector / np.linalg.norm(vector))
    return list(np.argsort(-scores))


def metrics(ranked_pmcids, definition):
    gold = set(definition.get("gold_pmcs", []))
    rank = next((i + 1 for i, pmcid in enumerate(ranked_pmcids) if pmcid in gold), None)
    out = {"first_gold_rank": rank}
    for k in TOP_PAPERS:
        top = set(ranked_pmcids[:k])
        out[f"gold_in_top{k}"] = len(gold & top)
        aspects = definition.get("aspects") or []
        if aspects:
            out[f"aspects_top{k}"] = sum(1 for a in aspects if set(a["gold_pmcs"]) & top) / len(aspects)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description="Session 1 gate: paper ranking quality of the paper index.")
    parser.add_argument("run_dir", help="Retrieval-only run providing production passage pools.")
    args = parser.parse_args(argv)
    prepare_imports()
    with contextlib.redirect_stdout(io.StringIO()):
        import embeddings.embedder as embedder
        from retrieval import reranker
        from vector_store.chroma_store import collection
    from indexing.build_paper_index import collect_paper_records, indexed_paper_counts

    definitions = {d["id"]: d for d in json.loads(QUESTIONS_PATH.read_text())["questions"]}
    records = {
        json.loads(Path(p).read_text())["id"]: json.loads(Path(p).read_text())
        for p in glob.glob(f"{args.run_dir}/records/*.json")
    }
    with contextlib.redirect_stdout(io.StringIO()):
        papers, _ = collect_paper_records(passage_counts=indexed_paper_counts(collection))
    pmcids = [paper["pmcid"] for paper in papers]
    documents = {paper["pmcid"]: paper["document"] for paper in papers}

    matrices, embed_seconds = {}, {}
    for pooling in ("mean", "cls"):
        started = time.perf_counter()
        with contextlib.redirect_stdout(io.StringIO()):
            vectors = embedder.embed_papers([(p["title"], p["abstract"]) for p in papers], pooling=pooling)
        matrices[pooling] = np.asarray(vectors, dtype="float32")
        embed_seconds[pooling] = time.perf_counter() - started
        print(f"[papers] embedded {pooling} in {embed_seconds[pooling]:.0f}s", file=sys.stderr, flush=True)

    ce_cache = {}

    def ce_scores(question, candidates):
        missing = [c for c in candidates if (question, c) not in ce_cache]
        if missing:
            values = reranker.reranker.predict([(question, documents[c]) for c in missing])
            ce_cache.update({(question, c): float(v) for c, v in zip(missing, values)})
        return {c: ce_cache[(question, c)] for c in candidates}

    pool_paper_scores = {}
    for question_id, record in records.items():
        pool_ids = [c["chunk_id"] for c in record["rerank"]["pool"]]
        got = collection.get(ids=pool_ids, include=["documents", "metadatas"])
        values = reranker.reranker.predict([(record["question"], text) for text in got["documents"]])
        best = defaultdict(lambda: -1e9)
        for metadata, value in zip(got["metadatas"], values):
            best[metadata["pmcid"]] = max(best[metadata["pmcid"]], float(value))
        pool_paper_scores[question_id] = best

    methods = defaultdict(dict)
    timing = defaultdict(list)
    for question_id, record in records.items():
        definition = definitions[question_id]
        question = record["question"]
        best = pool_paper_scores[question_id]
        methods["pool_best_chunk"][question_id] = sorted(best, key=best.get, reverse=True)
        for pooling, matrix in matrices.items():
            vector = query_vector(embedder, question, pooling)
            for distance in ("l2", "ip", "cosine"):
                order = [pmcids[i] for i in dense_rank(matrix, vector, distance)]
                methods[f"dense|{pooling}|{distance}"][question_id] = order
                started = time.perf_counter()
                candidates = list(dict.fromkeys(order[:DENSE_PAPERS] + list(best)))
                scores = ce_scores(question, candidates)
                methods[f"union_ce|{pooling}|{distance}"][question_id] = sorted(candidates, key=scores.get, reverse=True)
                timing[f"union_ce|{pooling}|{distance}"].append(time.perf_counter() - started)
        print(f"[papers] ranked {question_id}", file=sys.stderr, flush=True)

    summary = {}
    for method, ranked in methods.items():
        rows = {q: metrics(order, definitions[q]) for q, order in ranked.items()}
        l1 = [q for q, d in definitions.items() if d["level"] == 1 and not d.get("control")]
        l2 = [q for q, d in definitions.items() if d["level"] == 2]
        summary[method] = {
            **{f"l1_gold_top{k}": sum(1 for q in l1 if rows[q][f"gold_in_top{k}"]) for k in TOP_PAPERS},
            **{f"l2_gold_papers_top{k}": sum(rows[q][f"gold_in_top{k}"] for q in l2) for k in TOP_PAPERS},
            **{f"l2_aspects_top{k}": float(np.mean([rows[q][f"aspects_top{k}"] for q in l2])) for k in TOP_PAPERS},
            "l1_first_gold_ranks": [rows[q]["first_gold_rank"] for q in l1],
            "mean_ce_seconds": float(np.mean(timing[method])) if timing.get(method) else None,
            "per_question": rows,
        }
    output = {"embed_seconds": embed_seconds, "papers": len(papers), "summary": summary}
    out = Path(args.run_dir) / "paper_index_eval.json"
    out.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
