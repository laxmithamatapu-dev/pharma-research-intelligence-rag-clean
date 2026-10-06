from sentence_transformers import CrossEncoder

MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-12-v2"

print("\nLoading CrossEncoder Reranker...")

reranker = CrossEncoder(MODEL_NAME)

print("CrossEncoder loaded.")

QUESTION_TYPE_CUES = {
    "RESISTANCE": (
        "resistance", "resistant", "progression", "acquired", "bypass",
        "secondary mutation", "transformation", "on-target", "off-target",
    ),
    "BIOMARKER": (
        "biomarker", "predictive", "prognostic", "expression", "variant",
        "mutation", "amplification", "assay", "allele frequency",
    ),
    "CLINICAL_TRIAL": (
        "clinical trial", "phase i", "phase ii", "phase iii", "randomized",
        "enrolled", "objective response", "response rate", "progression-free",
        "overall survival", "adverse event",
    ),
    "SAFETY": (
        "safety", "adverse event", "toxicity", "tolerability", "dose-limiting",
        "treatment-related", "discontinuation", "serious adverse",
    ),
    "ADVERSE_EVENT": (
        "adverse event", "toxicity", "tolerability", "dose-limiting",
        "treatment-related", "discontinuation", "serious adverse",
    ),
    "MOA": (
        "mechanism of action", "mode of action", "binding", "inhibits",
        "inhibition", "target engagement", "downstream", "signaling pathway",
        "allosteric", "covalent", "mutant-selective", "mutant selective",
        "egfr inhibitor",
    ),
    "MECHANISM": (
        "mechanism", "binding", "inhibits", "inhibition", "target engagement",
        "downstream", "signaling pathway", "allosteric", "covalent",
        "mutant-selective", "mutant selective", "egfr inhibitor",
    ),
    "EFFICACY": (
        "efficacy", "objective response", "response rate", "tumor response",
        "progression-free survival", "overall survival", "duration of response",
    ),
}

MAX_QUESTION_TYPE_BONUS = 0.30
MECHANISM_SECTION_TITLE_BONUS = 0.15
MECHANISM_SECTION_TITLE_CUES = (
    "mechanism",
    "mode of action",
    "pharmacodynamics",
    "allosteric",
    "covalent",
    "egfr inhibitor",
    "target engagement",
)


def _resolve_question_type(query: str, question_type: str | None) -> str | None:
    if question_type:
        normalized_type = str(question_type).strip().upper()
        if normalized_type in QUESTION_TYPE_CUES:
            return normalized_type

    normalized_query = query.casefold()
    if any(term in normalized_query for term in ("resistance", "resistant", "progression after")):
        return "RESISTANCE"
    if any(term in normalized_query for term in ("clinical trial", "phase i", "phase ii", "phase iii", "randomized")):
        return "CLINICAL_TRIAL"
    if any(term in normalized_query for term in ("safety", "adverse event", "toxicity", "tolerability", "side effect")):
        return "SAFETY"
    if any(term in normalized_query for term in ("biomarker", "predictive marker", "prognostic marker")):
        return "BIOMARKER"
    if any(term in normalized_query for term in ("efficacy", "response rate", "overall survival", "progression-free survival")):
        return "EFFICACY"
    if any(term in normalized_query for term in ("mechanism", "how does", "binding", "inhibit")):
        return "MECHANISM"
    return None


def _question_type_bonus(chunk: dict, question_type: str | None) -> float:
    if question_type not in QUESTION_TYPE_CUES:
        return 0.0

    metadata = chunk.get("metadata") or {}
    section = str(
        metadata.get("section_path")
        or chunk.get("section_path")
        or ""
    ).casefold()
    text = str(chunk.get("text") or "").casefold()
    cues = QUESTION_TYPE_CUES[question_type]

    text_matches = sum(cue in text for cue in cues)
    section_matches = sum(cue in section for cue in cues)
    section_title_bonus = 0.0
    if question_type in {"MOA", "MECHANISM"} and any(
        cue in section
        for cue in MECHANISM_SECTION_TITLE_CUES
    ):
        section_title_bonus = MECHANISM_SECTION_TITLE_BONUS

    return min(
        MAX_QUESTION_TYPE_BONUS,
        text_matches * 0.025 + section_matches * 0.06 + section_title_bonus,
    )


def _source_id(chunk: dict) -> str:
    metadata = chunk.get("metadata") or {}

    return str(
        metadata.get("pmcid")
        or chunk.get("pmcid")
        or "unknown"
    )


def rerank_chunks(
    query: str,
    chunks: list,
    top_k: int = 8,
    max_per_source: int = 2,
    diversity_boost: bool = False,
    question_type: str | None = None,
):
    """
    Production baseline reranker.

    CrossEncoder relevance remains primary; a capped question-type bonus only
    adjusts close rankings before deduplication and source limits are applied.
    """

    if not chunks:
        return []

    # --------------------------------------
    # CrossEncoder scoring
    # --------------------------------------

    pairs = [
        (query, chunk["text"])
        for chunk in chunks
    ]

    scores = reranker.predict(pairs)
    resolved_question_type = _resolve_question_type(query, question_type)
    cross_encoder_scores = [float(score) for score in scores]
    minimum_score = min(cross_encoder_scores)
    score_range = max(cross_encoder_scores) - minimum_score

    ranked_chunks = []

    for chunk, cross_encoder_score in zip(chunks, cross_encoder_scores):
        normalized_score = (
            (cross_encoder_score - minimum_score) / score_range
            if score_range
            else 0.5
        )
        question_type_score = _question_type_bonus(
            chunk,
            resolved_question_type,
        )

        ranked_chunks.append(
            {
                **chunk,
                "rerank_score": cross_encoder_score,
                "normalized_rerank_score": normalized_score,
                "question_type_score": question_type_score,
                "combined_rerank_score": normalized_score + question_type_score,
            }
        )

    ranked_chunks.sort(
        key=lambda x: x["combined_rerank_score"],
        reverse=True
    )

    # --------------------------------------
    # Debug top scores
    # --------------------------------------

    print("\n" + "=" * 80)
    print("RERANK SCORES")
    print("=" * 80)

    for rank, chunk in enumerate(
        ranked_chunks[:20],
        start=1
    ):

        print(
            f"{rank:02d}. "
            f"{chunk['chunk_id']} | "
            f"CE={chunk['rerank_score']:.4f} | "
            f"Norm={chunk['normalized_rerank_score']:.3f} | "
            f"QT=+{chunk['question_type_score']:.3f} | "
            f"{(chunk.get('metadata') or {}).get('section_path', '')}"
        )

    # --------------------------------------
    # Deduplicate
    # --------------------------------------

    deduplicated = []

    seen_signatures = set()

    for chunk in ranked_chunks:

        text = (
            chunk.get("text", "")
            .lower()
            .strip()
        )

        signature = text[:300]

        if signature in seen_signatures:
            continue

        seen_signatures.add(signature)

        deduplicated.append(chunk)

    # --------------------------------------
    # Source diversity
    # --------------------------------------

    final_chunks = []

    source_counts = {}

    for chunk in deduplicated:

        source_id = _source_id(chunk)

        if (
            source_counts.get(source_id, 0)
            >= max_per_source
        ):
            continue

        final_chunks.append(chunk)

        source_counts[source_id] = (
            source_counts.get(source_id, 0)
            + 1
        )

        if len(final_chunks) >= top_k:
            break

    # --------------------------------------
    # Debug final chunks
    # --------------------------------------

    print("\n" + "=" * 80)
    print("TOP CHUNKS AFTER RERANKING")
    print("=" * 80)

    for rank, chunk in enumerate(
        final_chunks,
        start=1
    ):

        print(
            f"{rank:02d}. "
            f"{chunk['chunk_id']} | "
            f"CE={chunk['rerank_score']:.4f} | "
            f"Norm={chunk['normalized_rerank_score']:.3f} | "
            f"QT=+{chunk['question_type_score']:.3f} | "
            f"{(chunk.get('metadata') or {}).get('section_path', '')}"
        )

    return final_chunks