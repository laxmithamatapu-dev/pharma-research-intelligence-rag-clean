import sys
from pathlib import Path

sys.path.append(
    str(Path(__file__).resolve().parents[1])
)

from embeddings.embedder import embed_query
from vector_store.chroma_store import collection

query = (
    "What resistance mechanisms emerge after first-line osimertinib?"
)

query_embedding = embed_query(
    query
).tolist()

results = collection.query(
    query_embeddings=[query_embedding],
    n_results=200
)

ids = results["ids"][0]

target = "PMC13529361_0008"

if target in ids:

    rank = ids.index(target) + 1

    print(
        f"\nFOUND AT RANK {rank}"
    )

else:

    print(
        "\nNOT FOUND IN TOP 200"
    )