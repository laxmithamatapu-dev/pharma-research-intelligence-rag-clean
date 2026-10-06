import chromadb


COLLECTION_NAME = "pharma_research"


client = chromadb.PersistentClient(
    path="data/chromadb"
)

collection = client.get_or_create_collection(
    name=COLLECTION_NAME
)


def _metadata_value(value, default=""):
    """Convert enriched metadata to Chroma-compatible primitive values."""
    if value is None:
        return default
    if isinstance(value, (list, tuple, set)):
        return "|".join(
            str(item)
            for item in value
            if item is not None and str(item)
        )
    return value


def store_chunks(embedded_chunks):
    """
    Store embedded chunks into ChromaDB.
    """

    ids = []
    embeddings = []
    documents = []
    metadatas = []

    for chunk in embedded_chunks:

        ids.append(
            chunk["chunk_id"]
        )

        embeddings.append(
            chunk["embedding"]
        )

        documents.append(
            chunk["text"]
        )

        metadatas.append({
            "pmcid": _metadata_value(chunk.get("pmcid")),
            "doi": _metadata_value(chunk.get("doi")),
            "section": _metadata_value(chunk.get("section")),
            "subsection": _metadata_value(chunk.get("subsection")),
            "section_path": _metadata_value(chunk.get("section_path")),
            "drug": _metadata_value(chunk.get("drug")),
            "targets": _metadata_value(chunk.get("targets")),
            "disease": _metadata_value(chunk.get("disease")),
            "evidence_type": _metadata_value(chunk.get("evidence_type")),
            "evidence_types": _metadata_value(chunk.get("evidence_types")),
            "study_design": _metadata_value(chunk.get("study_design")),
            "section_category": _metadata_value(chunk.get("section_category")),
            "publication_year": _metadata_value(chunk.get("publication_year")),
            "article_type": _metadata_value(chunk.get("article_type")),
            "source_type": _metadata_value(chunk.get("source_type"), "PMC"),
            "metadata_version": _metadata_value(chunk.get("metadata_version"), "1.0"),
        })

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas
    )

    print(
        f"\nStored {len(ids)} chunks in ChromaDB."
    )


def count_chunks():
    """
    Return total records.
    """

    return collection.count()


def similarity_search(
    query_embedding,
    top_k=5
):
    """
    Retrieve top-k most similar chunks.
    """

    results = collection.query(
        query_embeddings=[
            query_embedding
        ],
        n_results=top_k
    )

    return results