import sys
from pathlib import Path

sys.path.append(
    str(Path(__file__).resolve().parents[1])
)

from retrieval.retriever import retrieve_chunks


TEST_QUERIES = [

    "What resistance mechanisms emerge after first-line osimertinib?",

    "What is MET amplification?",

    "How are patients managed after osimertinib progression?",

    "What are common EGFR resistance pathways?",

    "What is the role of rebiopsy in EGFR-mutant NSCLC?",

    "How does adaptive therapy affect progression-free survival?"
]


for query in TEST_QUERIES:

    print("\n" + "=" * 100)
    print("QUESTION:")
    print(query)

    results = retrieve_chunks(
        question=query,
        top_k=5
    )

    print(
        f"\nRETRIEVED CHUNKS: {len(results)}"
    )

    for idx, result in enumerate(
        results,
        start=1
    ):

        print("\n" + "-" * 80)

        print(
            f"RANK #{idx}"
        )

        print("\nCHUNK ID:")
        print(
            result["chunk_id"]
        )

        print("\nPMCID:")
        print(
            result["metadata"].get(
                "pmcid"
            )
        )

        print("\nSECTION PATH:")
        print(
            result["metadata"].get(
                "section_path"
            )
        )

        print("\nTEXT:")
        print(
            result["text"][:400]
        )