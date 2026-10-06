import sys
from pathlib import Path

sys.path.append(
    str(Path(__file__).resolve().parents[1])
)

from retrieval.retriever import retrieve_chunks


TEST_QUERIES = [

    {
        "question":
        "What resistance mechanisms emerge after first-line osimertinib?",

        "gold_chunks": [

            # Primary gold chunk
            "PMC13529361_0006",

            # Additional relevant chunks
            "PMC13529361_0012",
            "PMC13529361_0013",
            "PMC13529361_0014",

            # Secondary relevant chunk
            "PMC13508028_0006"
        ]
    },

    {
        "question":
        "What is the role of rebiopsy in EGFR-mutant NSCLC?",

        "gold_chunks": [

            # Primary gold chunks
            "PMC13529361_0011",
            "PMC13529361_0018",
            "PMC13529361_0001",

            # Secondary gold chunks
            "PMC13529361_0014",
            "PMC13529361_0006"
        ]
    }
]


for test in TEST_QUERIES:

    print("\n" + "=" * 100)

    print("QUESTION:")
    print(test["question"])

    results = retrieve_chunks(
        question=test["question"],
        top_k=20,
        retrieval_k=50
    )

    found = False

    for rank, chunk in enumerate(
        results,
        start=1
    ):

        if (
            chunk["chunk_id"]
            in
            test["gold_chunks"]
        ):

            found = True

            print(
                f"\nFOUND GOLD CHUNK AT RANK {rank}"
            )

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

            break

    if not found:

        print(
            "\nNO GOLD CHUNK FOUND "
            "IN FINAL RESULTS"
        )

    print("\n" + "=" * 100)
# import sys
# from pathlib import Path

# sys.path.append(
#     str(Path(__file__).resolve().parents[1])
# )

# from retrieval.retriever import retrieve_chunks


# OUTPUT_DIR = Path(
#     "evaluation_outputs"
# )


# def save_question_results(
#     question: str,
#     retrieval_k: int = 50
# ):
#     """
#     Retrieve chunks and save them
#     for manual evaluation.
#     """

#     OUTPUT_DIR.mkdir(
#         exist_ok=True,
#         parents=True
#     )

#     print("\n" + "=" * 100)
#     print("QUESTION")
#     print("=" * 100)
#     print(question)

#     chunks = retrieve_chunks(
#         question=question,
#         retrieval_k=retrieval_k,
#         top_k=retrieval_k
#     )

#     safe_name = "".join(
#         c if c.isalnum() else "_"
#         for c in question[:60]
#     )

#     output_file = (
#         OUTPUT_DIR /
#         f"{safe_name}.txt"
#     )

#     with open(
#         output_file,
#         "w",
#         encoding="utf-8"
#     ) as f:

#         f.write(
#             f"QUESTION:\n{question}\n\n"
#         )

#         f.write(
#             "=" * 120 + "\n"
#         )

#         for rank, chunk in enumerate(
#             chunks,
#             start=1
#         ):

#             f.write(
#                 "\n" +
#                 "#" * 120 +
#                 "\n"
#             )

#             f.write(
#                 f"RANK: {rank}\n"
#             )

#             f.write(
#                 f"CHUNK ID: "
#                 f"{chunk['chunk_id']}\n"
#             )

#             f.write(
#                 f"PMCID: "
#                 f"{chunk['pmcid']}\n"
#             )

#             f.write(
#                 f"SECTION: "
#                 f"{chunk['section_path']}\n"
#             )

#             if "rerank_score" in chunk:

#                 f.write(
#                     f"RERANK SCORE: "
#                     f"{chunk['rerank_score']}\n"
#                 )

#             f.write("\nTEXT:\n\n")

#             f.write(
#                 chunk["text"]
#             )

#             f.write("\n\n")

#     print(
#         f"\nSaved:"
#     )

#     print(output_file)


# def main():

#     questions = [

#         "What resistance mechanisms emerge after first-line osimertinib?",

#         "What is the role of rebiopsy in EGFR-mutant NSCLC?",

#     ]

#     for question in questions:

#         save_question_results(
#             question=question,
#             retrieval_k=50
#         )


# if __name__ == "__main__":
#     main()