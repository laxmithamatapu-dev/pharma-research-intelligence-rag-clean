import sys
from pathlib import Path

sys.path.append(
    str(Path(__file__).resolve().parents[1])
)

from vector_store.chroma_store import collection


def print_chunks(chunk_ids):
    """
    Print chunk metadata and text
    for manual inspection.
    """

    for chunk_id in chunk_ids:

        result = collection.get(
            ids=[chunk_id]
        )

        if not result["ids"]:
            print(
                f"\nChunk not found: {chunk_id}"
            )
            continue

        metadata = result["metadatas"][0]
        document = result["documents"][0]

        print("\n" + "=" * 100)

        print(
            f"CHUNK ID: {chunk_id}"
        )

        print(
            f"PMCID: "
            f"{metadata.get('pmcid', 'N/A')}"
        )

        print(
            f"SECTION: "
            f"{metadata.get('section_path', 'N/A')}"
        )

        print(
            f"WORDS: "
            f"{len(document.split())}"
        )

        print("\nTEXT:\n")

        print(document)

        print("\n")


if __name__ == "__main__":

    print_chunks([

        "PMC13508028_0006",

        "PMC13510353_0015"

    ])