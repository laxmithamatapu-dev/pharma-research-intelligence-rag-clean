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

print(
    f"\nChunks Created: {len(chunks)}"
)

embedded_chunks = embed_chunks(
    chunks
)

print(
    f"\nEmbedded Chunks: {len(embedded_chunks)}"
)

print(
    "\nFirst Chunk ID:"
)

print(
    embedded_chunks[0]["chunk_id"]
)

print(
    "\nSection Path:"
)

print(
    embedded_chunks[0]["section_path"]
)

print(
    "\nEmbedding Dimension:"
)

print(
    len(
        embedded_chunks[0]["embedding"]
    )
)