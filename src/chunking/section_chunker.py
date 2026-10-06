try:
    from processing.metadata_enricher import inherit_chunk_metadata
    from processing.evidence_classifier import section_category
except ModuleNotFoundError:
    from src.processing.metadata_enricher import inherit_chunk_metadata
    from src.processing.evidence_classifier import section_category


def split_text(
    text,
    chunk_size=400,
    overlap=100,
    min_words=100
):

    words = text.split()

    chunks = []

    start = 0

    while start < len(words):

        end = start + chunk_size

        chunk_words = words[start:end]

        if len(chunk_words) >= min_words:

            chunks.append(
                " ".join(chunk_words)
            )

        start += (
            chunk_size - overlap
        )

    return chunks
def create_chunks(article):
    """
    Convert parsed article into
    overlapping retrieval chunks.
    """

    chunks = []

    counter = 1

    pmcid = article.get("pmcid")

    doi = article.get("doi")

    def walk(section, path):

        nonlocal counter

        current_path = (
            path +
            [section.get("title") or "Untitled"]
        )

        text = section.get(
            "text",
            ""
        ).strip()

        if text:

            text_chunks = split_text(
                text=text,
                chunk_size=400,
                overlap=100
            )

            for part_num, chunk_text in enumerate(
                text_chunks,
                start=1
            ):
                print(
                f"{pmcid}_{counter:04d} "
                f"Words={len(chunk_text.split())}"
                    )


                chunk = {

                    "chunk_id":
                    f"{pmcid}_{counter:04d}",

                    "pmcid":
                    pmcid,

                    "doi":
                    doi,

                    "section":
                    current_path[0],

                    "subsection":
                    current_path[-1]
                    if len(current_path) > 1
                    else None,

                    "section_path":
                    " > ".join(
                        current_path
                    ),

                    "part":
                    part_num,

                    "text":
                    chunk_text
                }
                chunk["section_category"] = section_category(
                    current_path[-1],
                    chunk_text,
                )
                chunks.append(
                    inherit_chunk_metadata(chunk, article)
                )

                counter += 1

        for child in section.get(
            "subsections",
            []
        ):

            walk(
                child,
                current_path
            )

    for section in article.get(
        "sections",
        []
    ):

        walk(
            section,
            []
        )

    return chunks