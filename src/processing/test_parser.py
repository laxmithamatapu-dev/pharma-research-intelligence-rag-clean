from pathlib import Path

from pmc_parser import parse_article


xml_path = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "raw"
    / "xml"
    / "PMC13529361.xml"
)

article = parse_article(str(xml_path))

print("\nPMCID:")
print(article["pmcid"])

print("\nPMID:")
print(article["pmid"])

print("\nDOI:")
print(article["doi"])

print("\nTITLE:")
print(article["title"])

print("\nJOURNAL:")
print(article["journal"])

print("\nABSTRACT:")
print(article["abstract"])

print("\nAUTHOR COUNT:")
print(len(article["authors"]))

print("\nAUTHORS:")
for i, author in enumerate(article["authors"], start=1):
    print(f"{i}. {author}")


def print_section(section, level=0):

    indent = "    " * level

    print(
        f"{indent}- {section['title']}"
    )

    if section["text"]:
        print(
            f"{indent}  TEXT: "
            f"{section['text'][:200]}"
        )

    for subsection in section["subsections"]:
        print_section(
            subsection,
            level + 1
        )


print("\nSECTIONS:")

for section in article["sections"]:
    print_section(section)