import sys
from pathlib import Path

sys.path.append(
    str(Path(__file__).resolve().parents[1])
)

from processing.pmc_parser import parse_article
from chunking.section_chunker import create_chunks


xml_path = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "raw"
    / "xml"
    / "PMC13529361.xml"
)

print("\nXML PATH:")
print(xml_path)

print("\nFILE EXISTS:")
print(xml_path.exists())

article = parse_article(
    str(xml_path)
)

print("\nPMCID:")
print(article["pmcid"])

print("\nTITLE:")
print(article["title"])

print("\nSECTIONS:")
print(len(article["sections"]))

chunks = create_chunks(article)

print(
    f"\nTOTAL CHUNKS: {len(chunks)}"
)

for chunk in chunks:

    print("\n" + "=" * 80)

    print("CHUNK ID:")
    print(chunk["chunk_id"])

    print("\nSECTION:")
    print(chunk["section"])

    print("\nSUBSECTION:")
    print(chunk["subsection"])

    print("\nSECTION PATH:")
    print(chunk["section_path"])

    print("\nTEXT:")
    print(chunk["text"][:300])