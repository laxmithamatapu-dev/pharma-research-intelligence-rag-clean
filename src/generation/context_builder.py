def build_context(
    chunks,
    coverage=None
):
    """
    Build LLM context from retrieved chunks.

    Returns:
        context: str
        evidence_map: dict
    """

    evidence_map = {}
    blocks = []

    # --------------------------------------------------
    # Coverage Summary
    # --------------------------------------------------

    if coverage:

        coverage_summary = (
            coverage.get(
                "coverage_summary",
                ""
            )
        )

        if coverage_summary:

            blocks.append(
                f"""
COVERAGE SUMMARY

{coverage_summary}

The answer should address all
relevant findings identified above.
"""
            )

    # --------------------------------------------------
    # Evidence Blocks
    # --------------------------------------------------

    MAX_CHARS_PER_CHUNK = 1200

    for index, chunk in enumerate(
        chunks,
        start=1
    ):

        evidence_id = f"E{index}"

        metadata = chunk.get(
            "metadata",
            {}
        )

        evidence_map[evidence_id] = {
            "pmcid":
                metadata.get(
                    "pmcid",
                    ""
                ),
            "chunk_id":
                chunk.get(
                    "chunk_id",
                    ""
                ),
            "section_path":
                metadata.get(
                    "section_path",
                    ""
                )
        }

        text = chunk.get(
            "text",
            ""
        )

        text = " ".join(
            text.split()
        )

        text = text[
            :MAX_CHARS_PER_CHUNK
        ]

        # --------------------------------------------------
        # Metadata
        # --------------------------------------------------

        drug = metadata.get(
            "drug",
            "unknown"
        )

        evidence_type = metadata.get(
            "evidence_type",
            metadata.get(
                "section_category",
                "unknown"
            )
        )

        study_design = metadata.get(
            "study_design",
            "unknown"
        )

        publication_year = metadata.get(
            "publication_year",
            ""
        )

        section_path = metadata.get(
            "section_path",
            ""
        )

        block = f"""
[{evidence_id}]

Drug: {drug}
Evidence Type: {evidence_type}
Study Design: {study_design}
Publication Year: {publication_year}
Section: {section_path}

{text}
"""

        blocks.append(
            block
        )

    # --------------------------------------------------
    # Final Context
    # --------------------------------------------------

    context = "\n\n".join(
        blocks
    )

    print(
        f"\nContext Length: "
        f"{len(context)} characters"
    )

    print(
        f"Evidence Blocks: "
        f"{len(blocks)}"
    )

    return (
        context,
        evidence_map
    )