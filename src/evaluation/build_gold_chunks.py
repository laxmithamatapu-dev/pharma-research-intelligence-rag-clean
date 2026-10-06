import sys
from pathlib import Path

sys.path.append(
    str(Path(__file__).resolve().parents[1])
)

from retrieval.retriever import retrieve_chunks


def inspect_question(
    question: str,
    retrieval_k: int = 50
):
    """
    Retrieve chunks and print their
    full content for manual labeling.
    """

    print("\n" + "=" * 120)
    print("QUESTION")
    print("=" * 120)
    print(question)

    chunks = retrieve_chunks(
        question=question,
        retrieval_k=retrieval_k,
        top_k=retrieval_k
    )

    print("\n" + "=" * 120)
    print(f"RETRIEVED {len(chunks)} CHUNKS")
    print("=" * 120)

    for rank, chunk in enumerate(
        chunks,
        start=1
    ):

        print("\n" + "#" * 120)

        print(f"RANK: {rank}")

        print(
            f"CHUNK ID: "
            f"{chunk['chunk_id']}"
        )

        print(
            f"PMCID: "
            f"{chunk['pmcid']}"
        )

        print(
            f"SECTION: "
            f"{chunk['section_path']}"
        )

        if "rerank_score" in chunk:

            print(
                f"RERANK SCORE: "
                f"{chunk['rerank_score']:.4f}"
            )

        print("\nTEXT:\n")

        print(chunk["text"])

        print("\n")


if __name__ == "__main__":

    QUESTIONS = [

        "What resistance mechanisms emerge after first-line osimertinib?",

        "What is the role of rebiopsy in EGFR-mutant NSCLC?"

    ]

    for question in QUESTIONS:

        inspect_question(
            question=question,
            retrieval_k=50
        )

        print(
            "\n\n" +
            "=" * 120 +
            "\nEND OF QUESTION\n" +
            "=" * 120
        )