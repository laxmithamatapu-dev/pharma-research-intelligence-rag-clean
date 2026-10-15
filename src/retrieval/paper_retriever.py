import time
from dataclasses import dataclass, field

import numpy as np

from embeddings.embedder import embed_paper_query, embed_query
from retrieval.reranker import reranker
from vector_store.chroma_store import collection, get_papers_collection

PAPER_DISTANCE = "ip"


@dataclass
class RankedPaper:
    pmcid: str
    title: str
    document: str
    metadata: dict
    score: float
    sources: list = field(default_factory=list)


def candidate_papers(question: str, paper_candidates: int, passage_candidates: int):
    """Union of the paper index and the papers of the top passage hits."""
    timings = {}
    papers_collection = get_papers_collection(PAPER_DISTANCE)

    started = time.perf_counter()
    paper_hits = papers_collection.query(
        query_embeddings=[embed_paper_query(question).tolist()],
        n_results=paper_candidates,
    )["ids"][0]
    timings["paper_dense_seconds"] = time.perf_counter() - started

    started = time.perf_counter()
    question_vector = np.asarray(embed_query(question), dtype="float32")
    passage_hits = collection.query(
        query_embeddings=[question_vector.tolist()],
        n_results=passage_candidates,
        include=["metadatas"],
    )["metadatas"][0]
    timings["passage_dense_seconds"] = time.perf_counter() - started

    sources = {}
    for pmcid in paper_hits:
        sources.setdefault(pmcid, []).append("paper_index")
    for metadata in passage_hits:
        pmcid = metadata.get("pmcid")
        if pmcid and "passage_hits" not in sources.setdefault(pmcid, []):
            sources[pmcid].append("passage_hits")
    return sources, timings, question_vector


def rank_papers(question: str, sources: dict):
    """Score candidate papers with the cross-encoder on title + abstract."""
    started = time.perf_counter()
    pmcids = list(sources)
    records = get_papers_collection(PAPER_DISTANCE).get(ids=pmcids, include=["documents", "metadatas"])
    by_id = {
        pmcid: (document, metadata)
        for pmcid, document, metadata in zip(records["ids"], records["documents"], records["metadatas"])
    }
    known = [pmcid for pmcid in pmcids if pmcid in by_id]
    scores = reranker.predict([(question, by_id[pmcid][0]) for pmcid in known]) if known else []
    ranked = [
        RankedPaper(
            pmcid=pmcid,
            title=by_id[pmcid][1].get("title", ""),
            document=by_id[pmcid][0],
            metadata=by_id[pmcid][1],
            score=float(score),
            sources=sources[pmcid],
        )
        for pmcid, score in zip(known, scores)
    ]
    ranked.sort(key=lambda paper: paper.score, reverse=True)
    return ranked, {"paper_rerank_seconds": time.perf_counter() - started, "paper_candidates": len(known)}


def paper_margin(ranked):
    if len(ranked) < 2:
        return float("inf")
    return ranked[0].score - ranked[1].score


def prerank_passages(question_vector, passages, limit):
    """Order a paper's passages by dense similarity and keep the closest `limit`."""
    if len(passages) <= limit:
        return passages
    stored = collection.get(ids=[passage["chunk_id"] for passage in passages], include=["embeddings"])
    ids = stored["ids"]
    vectors = np.asarray(stored["embeddings"], dtype="float32")
    order = np.argsort(((vectors - question_vector) ** 2).sum(axis=1))[:limit]
    by_id = {passage["chunk_id"]: passage for passage in passages}
    return [by_id[ids[index]] for index in order]
