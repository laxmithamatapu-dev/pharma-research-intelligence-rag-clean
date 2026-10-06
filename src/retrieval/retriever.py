import sys
from pathlib import Path

sys.path.append(
    str(Path(__file__).resolve().parents[1])
)

from embeddings.embedder import embed_query
from vector_store.chroma_store import collection
from retrieval.reranker import rerank_chunks


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
        retrieval_hints = query_info.get("retrieval_hints", []) or []
        if queries is None:
            queries = [question] if question else []
            queries.extend(expanded_queries)
            queries.extend(retrieval_hints)

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