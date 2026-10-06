import sys
from pathlib import Path

sys.path.append(
    str(Path(__file__).resolve().parents[1])
)

from retrieval.retriever import (
    retrieve_chunks
)


query = (

    "MET amplification after osimertinib"

)

results = retrieve_chunks(
    question=query,
    top_k=5
)

print("\nQUESTION:")
print(query)

print(
    f"\nRETRIEVED CHUNKS: {len(results)}"
)

for result in results:

    print("\n" + "=" * 80)

    print("CHUNK ID:")
    print(result["chunk_id"])

    print("\nSECTION PATH:")
    print(
        result["metadata"]
        .get("section_path")
    )

    print("\nPMCID:")
    print(
        result["metadata"]
        .get("pmcid")
    )

    print("\nTEXT:")
    print(
        result["text"][:500]
    )