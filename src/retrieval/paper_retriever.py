import re
import time
from dataclasses import dataclass, field

import numpy as np

from embeddings.embedder import embed_paper_query, embed_query
from retrieval.reranker import reranker
from vector_store.chroma_store import collection, get_papers_collection

PAPER_DISTANCE = "ip"

# Trial names and registry numbers (the forms that also mark a single-study question): KEYNOTE-522,
# CheckMate 9ER, NCT03036488. The cross-encoder scores near-identical studies with different
# identifiers almost equally (KEYNOTE-522 4.13 vs KEYNOTE-671 4.19), so an exact match decides.
TRIAL_IDENTIFIER = re.compile(r"\b(?:NCT\d{8}|[A-Z]{4,}-\d+[A-Z]?|[A-Z][a-z]+[A-Z][a-z]+ \d+[A-Z]*)\b")
IDENTIFIER_BONUS = 3.0
SEPARATORS = r"[\s\-‐‑‒–—]*"

_paper_documents = None


@dataclass
class RankedPaper:
    pmcid: str
    title: str
    document: str
    metadata: dict
    score: float
    sources: list = field(default_factory=list)
    rerank_score: float | None = None
    identifier_match: bool = False


    @property
    def floor_score(self) -> float:
        return self.score if self.rerank_score is None else self.rerank_score


def trial_identifiers(question: str) -> list:
    return list(dict.fromkeys(match.group(0) for match in TRIAL_IDENTIFIER.finditer(question or "")))


def identifier_patterns(identifiers):
    """Match each identifier regardless of case and of the separators between its letter and digit parts."""
    return [
        re.compile(
            r"(?<![A-Za-z0-9])" + SEPARATORS.join(map(re.escape, re.findall(r"[A-Za-z]+|\d+", identifier)))
            + r"(?![A-Za-z0-9])",
            re.IGNORECASE,
        )
        for identifier in identifiers
    ]


def paper_documents() -> dict:
    """Title + abstract of every paper, loaded once (568 papers ≈ 1 MB)."""
    global _paper_documents
    if _paper_documents is None:
        records = get_papers_collection(PAPER_DISTANCE).get(include=["documents"])
        _paper_documents = dict(zip(records["ids"], records["documents"]))
    return _paper_documents


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

    patterns = identifier_patterns(trial_identifiers(question))
    if patterns:
        for pmcid, document in paper_documents().items():
            if any(pattern.search(document) for pattern in patterns):
                sources.setdefault(pmcid, []).append("identifier")
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
    patterns = identifier_patterns(trial_identifiers(question))
    ranked = []
    for pmcid, score in zip(known, scores):
        matched = any(pattern.search(by_id[pmcid][0]) for pattern in patterns)
        ranked.append(RankedPaper(
            pmcid=pmcid,
            title=by_id[pmcid][1].get("title", ""),
            document=by_id[pmcid][0],
            metadata=by_id[pmcid][1],
            score=float(score) + (IDENTIFIER_BONUS if matched else 0.0),
            sources=sources[pmcid],
            rerank_score=float(score),
            identifier_match=matched,
        ))
    ranked.sort(key=lambda paper: paper.score, reverse=True)
    return ranked, {
        "paper_rerank_seconds": time.perf_counter() - started,
        "paper_candidates": len(known),
        "identifier_matches": [paper.pmcid for paper in ranked if paper.identifier_match],
    }


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
