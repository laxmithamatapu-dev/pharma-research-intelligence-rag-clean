import sys
from pathlib import Path

sys.path.append(
    str(Path(__file__).resolve().parents[1])
)

import time
from dataclasses import dataclass, field

from embeddings.embedder import embed_query
from vector_store.chroma_store import collection, passages_for_paper
from retrieval.reranker import rerank_chunks, select_passages_by_paper
from retrieval.paper_retriever import candidate_papers, paper_margin, prerank_passages, rank_papers
from retrieval.retrieval_strategy import PLAN_SHAPES


@dataclass
class EvidenceSet:
    plan: object
    allocation: tuple
    papers: list
    chunks: list
    telemetry: dict = field(default_factory=dict)
    abstained: bool = False


def retrieve_evidence(question, query_info=None, plan=None):
    """
    Paper-first retrieval: rank papers, then select passages inside the selected papers.
    """
    started = time.perf_counter()
    sources, telemetry, question_vector = candidate_papers(
        question,
        plan.paper_candidates,
        plan.passage_candidates,
    )
    ranked, paper_telemetry = rank_papers(question, sources)
    telemetry.update(paper_telemetry)
    telemetry["top_paper_scores"] = [round(paper.score, 4) for paper in ranked[:8]]

    if plan.paper_floor is not None and (not ranked or ranked[0].score < plan.paper_floor):
        telemetry.update({
            "abstained": True,
            "paper_floor": plan.paper_floor,
            "candidate_papers": [paper.pmcid for paper in ranked],
            "retrieval_seconds": time.perf_counter() - started,
        })
        return EvidenceSet(plan=plan, allocation=(), papers=[], chunks=[], telemetry=telemetry, abstained=True)

    margin = paper_margin(ranked)
    allocation = plan.allocation
    if plan.shape == "adaptive":
        allocation = PLAN_SHAPES["depth"] if margin >= plan.adaptive_margin else PLAN_SHAPES["breadth"]
    selected = ranked[:len(allocation)]

    passage_started = time.perf_counter()
    papers_input = [
        (
            paper.pmcid,
            prerank_passages(
                question_vector,
                passages_for_paper(paper.pmcid),
                plan.passages_considered_per_paper,
            ),
            quota,
        )
        for paper, quota in zip(selected, allocation)
    ]
    chunks = select_passages_by_paper(
        question,
        papers_input,
        (query_info or {}).get("question_type"),
    )
    by_pmcid = {paper.pmcid: paper for paper in selected}
    for chunk in chunks:
        paper = by_pmcid[chunk["pmcid"]]
        chunk["paper_title"] = paper.title
        chunk["paper_score"] = paper.score
        chunk["paper_metadata"] = paper.metadata

    telemetry.update({
        "passage_selection_seconds": time.perf_counter() - passage_started,
        "passages_scored": sum(len(passages) for _, passages, _ in papers_input),
        "considered_chunk_ids": [passage["chunk_id"] for _, passages, _ in papers_input for passage in passages],
        "candidate_papers": [paper.pmcid for paper in ranked],
        "paper_margin": margin,
        "allocation": list(allocation),
        "papers_selected": [paper.pmcid for paper in selected],
        "abstained": False,
        "retrieval_seconds": time.perf_counter() - started,
    })
    return EvidenceSet(plan=plan, allocation=allocation, papers=selected, chunks=chunks, telemetry=telemetry)


def _normalize_queries(
    queries=None,
    question=None,
    original_question=None,
):
    if queries is None:
        if question:
            queries = [question]
        else:
            raise ValueError("Either 'queries' or 'question' must be provided.")
    elif isinstance(queries, str):
        queries = [queries]

    cleaned_queries = []
    for query in queries:
        if isinstance(query, str):
            normalized = query.strip()
            if normalized:
                cleaned_queries.append(normalized)

    if not cleaned_queries:
        raise ValueError("No valid queries were supplied.")

    if original_question is None:
        original_question = question or cleaned_queries[0]

    original_question = str(original_question).strip() or cleaned_queries[0]
    return cleaned_queries, original_question


def retrieve_chunks(
    queries=None,
    original_question=None,
    top_k: int = None,
    retrieval_k: int = None,
    question=None,
    query_info=None,
    strategy=None,
):
    """
    Retrieve and rerank evidence chunks for one or many queries.

    Preferred contract:
    - retrieve_chunks(question='...', query_info=query_info, strategy=strategy)

    Supported compatibility patterns:
    - retrieve_chunks(queries=[...], original_question='...')
    - retrieve_chunks(question='...')
    - retrieve_chunks(queries='single query', original_question='...')
    """
    if strategy is not None:
        if top_k is None:
            top_k = strategy.top_k
        if retrieval_k is None:
            retrieval_k = strategy.retrieval_k

    if query_info is not None:
        expanded_queries = query_info.get("expanded_queries", []) or []

        if queries is None:

            candidate_queries = []

            if question:
                candidate_queries.append(question)

            candidate_queries.extend(expanded_queries)

            queries = list(
                dict.fromkeys(
                    q.strip()
                    for q in candidate_queries
                    if isinstance(q, str) and q.strip()
                )
            )

    if question is not None and original_question is None:
        original_question = question

    cleaned_queries, original_question = _normalize_queries(
        queries=queries,
        question=question,
        original_question=original_question,
    )

    if top_k is None:
        top_k = 8
    if retrieval_k is None:
        retrieval_k = 50

    merged_chunks = {}

    print("\n" + "=" * 80)
    print("MULTI QUERY RETRIEVAL")
    print("=" * 80)

    for query_index, query in enumerate(cleaned_queries, start=1):
        print(f"\n[QUERY {query_index}]")
        print(query)

        try:
            query_embedding = embed_query(query).tolist()
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=retrieval_k,
            )
        except Exception as exc:
            print(f"Retrieval failed for query '{query}': {exc}")
            continue

        ids = results.get("ids", [[]])[0] if results.get("ids") else []
        documents = results.get("documents", [[]])[0] if results.get("documents") else []
        metadatas = results.get("metadatas", [[]])[0] if results.get("metadatas") else []

        for index, chunk_id in enumerate(ids):
            if not chunk_id:
                continue

            if index >= len(documents):
                document = ""
            else:
                document = documents[index]

            if index >= len(metadatas):
                metadata = {}
            else:
                metadata = metadatas[index]

            if not isinstance(metadata, dict):
                metadata = {}

            if not document:
                continue

            if chunk_id not in merged_chunks:
                merged_chunks[chunk_id] = {
                    "chunk_id": chunk_id,
                    "text": document,
                    "pmcid": metadata.get("pmcid"),
                    "section_path": metadata.get("section_path"),
                    "metadata": metadata,
                }

    candidate_chunks = list(merged_chunks.values())

    print("\n" + "=" * 80)
    print("MERGED CANDIDATES BEFORE RERANKING")
    print("=" * 80)
    print(f"Unique candidates: {len(candidate_chunks)}")

    for rank, chunk in enumerate(candidate_chunks[:50], start=1):
        print(f"{rank:02d}. {chunk['chunk_id']} | {chunk.get('section_path', '')}")

    reranked_chunks = rerank_chunks(
        query=original_question,
        chunks=candidate_chunks,
        top_k=top_k,
        question_type=(query_info or {}).get("question_type"),
        diversity_boost=(
            getattr(strategy, "diversity_boost", True)
            if strategy is not None
            else True
        ),
    )

    print("\n" + "=" * 80)
    print("TOP CHUNKS AFTER RERANKING")
    print("=" * 80)

    for rank, chunk in enumerate(reranked_chunks, start=1):
        print(f"{rank:02d}. {chunk['chunk_id']} | {chunk.get('section_path', '')}")

    return reranked_chunks


if __name__ == "__main__":
    question = "What resistance mechanisms emerge after first-line osimertinib?"
    expanded_queries = [
        "resistance mechanisms to osimertinib",
        "EGFR mutations and osimertinib",
        "mechanisms of resistance to first-line osimertinib",
    ]

    results = retrieve_chunks(
        queries=[question] + expanded_queries,
        original_question=question,
        top_k=8,
        retrieval_k=25,
    )

    print("\n" + "=" * 80)
    print("FINAL RETURNED CHUNKS")
    print("=" * 80)

    for chunk in results:
        print("\n")
        print("Chunk ID:", chunk["chunk_id"])
        print("PMCID:", chunk["pmcid"])
        print("Section:", chunk["section_path"])