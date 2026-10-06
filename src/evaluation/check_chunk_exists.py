import sys
from pathlib import Path

sys.path.append(
    str(Path(__file__).resolve().parents[1])
)

from embeddings.embedder import embed_query
from vector_store.chroma_store import collection


QUESTION = (
    "What resistance mechanisms emerge after first-line osimertinib?"
)

GOLD_CHUNK = "PMC13529361_0006"


def main():

    query_embedding = embed_query(
        QUESTION
    ).tolist()

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=300
    )

    ids = results["ids"][0]
    metadatas = results["metadatas"][0]

    gold_rank = None

    for rank, chunk_id in enumerate(
        ids,
        start=1
    ):

        if chunk_id == GOLD_CHUNK:
            gold_rank = rank
            break

    print("\n" + "=" * 80)
    print("GOLD CHUNK RANK")
    print("=" * 80)

    if gold_rank is None:
        print("Gold chunk not found.")
        return

    print(
        f"{GOLD_CHUNK} FOUND AT RANK {gold_rank}"
    )

    start = max(1, gold_rank - 5)
    end = min(len(ids), gold_rank + 5)

    print("\n" + "=" * 80)
    print("NEIGHBORING CHUNKS")
    print("=" * 80)

    for rank in range(start, end + 1):

        idx = rank - 1

        print(
            f"{rank:03d}. "
            f"{ids[idx]} | "
            f"{metadatas[idx].get('section_path')}"
        )

    print("\n" + "=" * 80)
    print("CHECKING NEIGHBOR CHUNKS FROM SAME PAPER")
    print("=" * 80)

    target_chunks = [
        "PMC13529361_0004",
        "PMC13529361_0005",
        "PMC13529361_0006",
        "PMC13529361_0007",
        "PMC13529361_0008"
    ]

    retrieved = collection.get(
        ids=target_chunks,
        include=["documents", "metadatas"]
    )

    for chunk_id, doc, meta in zip(
        retrieved["ids"],
        retrieved["documents"],
        retrieved["metadatas"]
    ):

        print("\n" + "-" * 80)

        print(f"CHUNK: {chunk_id}")

        print(
            f"SECTION: "
            f"{meta.get('section_path')}"
        )

        print(
            f"WORDS: "
            f"{len(doc.split())}"
        )

        print("\nFIRST 400 CHARS:\n")

        print(doc[:400])

        print("\n")


if __name__ == "__main__":
    main()