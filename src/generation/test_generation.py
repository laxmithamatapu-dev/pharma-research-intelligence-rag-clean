import sys
import time
from pathlib import Path

sys.path.append(
    str(Path(__file__).resolve().parents[1])
)

from retrieval.retriever import retrieve_chunks

from generation.context_builder import (
    build_context
)

from generation.generator import (
    QwenGenerator
)


def main():

    question = (
        "What resistance mechanisms emerge "
        "after first-line osimertinib?"
    )

    print("\nQUESTION\n")
    print(question)

    chunks = retrieve_chunks(
        question=question,
        retrieval_k=50,
        top_k=2
    )

    print(
        f"\nRetrieved {len(chunks)} chunks"
    )

    context, evidence_map = (
        build_context(chunks)
    )

    print(
        f"\nContext Length: "
        f"{len(context)} characters"
    )

    generator = QwenGenerator()

    start_time = time.time()

    answer = generator.generate(
        question=question,
        context=context
    )

    generation_time = (
        time.time() - start_time
    )

    print(
        f"\nGeneration Time: "
        f"{generation_time:.2f} seconds"
    )

    print("\n" + "=" * 100)
    print("ANSWER")
    print("=" * 100)

    print(answer)

    print("\n" + "=" * 100)
    print("EVIDENCE MAP")
    print("=" * 100)

    for evidence_id, data in (
        evidence_map.items()
    ):

        print(
            f"{evidence_id}: "
            f"{data['chunk_id']} | "
            f"{data['pmcid']}"
        )


if __name__ == "__main__":
    main()