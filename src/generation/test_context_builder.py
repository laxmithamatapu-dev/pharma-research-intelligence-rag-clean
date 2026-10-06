import sys
from pathlib import Path

sys.path.append(
    str(Path(__file__).resolve().parents[1])
)

from retrieval.retriever import retrieve_chunks
from generation.context_builder import build_context


QUESTION = (
    "What resistance mechanisms emerge after first-line osimertinib?"
)


def main():

    chunks = retrieve_chunks(
        question=QUESTION,
        top_k=10,
        retrieval_k=50
    )

    print("\n" + "=" * 80)
    print("TOP 10 CHUNKS")
    print("=" * 80)

    for rank, chunk in enumerate(
        chunks,
        start=1
    ):

        print("\n" + "=" * 80)
        print(f"RANK {rank}")

        print(
            f"Chunk ID:\n"
            f"{chunk['chunk_id']}"
        )

        print(
            f"\nSection:\n"
            f"{chunk['metadata']['section_path']}"
        )

        print(
            f"\nText:\n"
            f"{chunk['text']}"
        )

    context, evidence_map = build_context(
        chunks
    )

    print("\n" + "=" * 80)
    print("STRUCTURED CONTEXT")
    print("=" * 80)

    print(context)

    print("\n" + "=" * 80)
    print("EVIDENCE MAP")
    print("=" * 80)

    print(evidence_map)


if __name__ == "__main__":
    main()