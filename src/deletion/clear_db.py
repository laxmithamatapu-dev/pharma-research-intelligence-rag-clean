from vector_store.chroma_store import collection

result = collection.get(
    ids=["PMC13529361_0008"]
)

print(result["documents"][0])