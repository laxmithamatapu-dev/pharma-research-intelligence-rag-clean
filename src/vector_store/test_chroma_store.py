import sys
from pathlib import Path

sys.path.append(
    str(
        Path(__file__).resolve().parents[1]
    )
)

from processing.pmc_parser import parse_article
from chunking.section_chunker import create_chunks
from embeddings.embedder import embed_chunks
from vector_store.chroma_store import (
    store_chunks,
    count_chunks
)


xml_path = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "raw"
    / "xml"
    / "PMC13529361.xml"
)

article = parse_article(
    str(xml_path)
)

chunks = create_chunks(
    article
)

embedded_chunks = embed_chunks(
    chunks
)

store_chunks(
    embedded_chunks
)

print(
    "\nTotal Chunks In DB:"
)

print(
    count_chunks()
)