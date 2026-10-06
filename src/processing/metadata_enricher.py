"""Enrich parsed PMC articles and chunks with drug-centric metadata."""

from typing import Any

try:
    from processing.drug_registry import DrugRegistry
    from processing.evidence_classifier import classify_article, section_category
except ModuleNotFoundError:
    from src.processing.drug_registry import DrugRegistry
    from src.processing.evidence_classifier import classify_article, section_category


METADATA_VERSION = "1.0"


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _role_for(surface_form: str, text: str) -> str:
    lowered = text.casefold()
    if any(term in lowered for term in ("comparator", "versus", "vs.", "control arm")):
        return "comparator"
    if any(term in lowered for term in ("combination with", "combined with", "co-treatment")):
        return "combination_partner"
    if any(term in lowered for term in ("rescue therapy", "salvage therapy")):
        return "rescue_therapy"
    if any(term in lowered for term in ("background therapy", "background treatment")):
        return "background_therapy"
    if any(term in lowered for term in ("experimental agent", "investigational agent")):
        return "experimental_agent"
    return "intervention"


def _all_sections(sections: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    output = []
    def walk(section: dict[str, Any], path: list[str]) -> None:
        title = section.get("title") or "Untitled"
        current = path + [title]
        output.append((" > ".join(current), section))
        for child in section.get("subsections", []):
            walk(child, current)
    for section in sections:
        walk(section, [])
    return output


def enrich_article(
    article: dict[str, Any],
    registry: DrugRegistry | None = None,
    discovery_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    registry = registry or DrugRegistry()
    discovery_metadata = discovery_metadata or {}
    title = article.get("title", "") or ""
    abstract = article.get("abstract", "") or ""
    section_text = " ".join(
        f"{path} {section.get('text', '')}"
        for path, section in _all_sections(article.get("sections", []))
    )
    mentions = []
    for source, text in (("title", title), ("abstract", abstract), ("section", section_text)):
        mentions.extend(registry.find_mentions(text, source))
    by_drug = {}
    article_text = " ".join((title, abstract, section_text))
    for mention in mentions:
        canonical = mention["canonical_name"]
        current = by_drug.setdefault(canonical, mention.copy())
        current["confidence"] = max(current["confidence"], mention["confidence"])
        current["role"] = _role_for(mention["surface_form"], article_text)
    drugs = list(by_drug.values())
    canonical_drugs = [item["canonical_name"] for item in drugs]
    records = [registry.get(name) or {} for name in canonical_drugs]
    targets = _unique([target for record in records for target in record.get("targets", [])])
    disease_areas = _unique([area for record in records for area in record.get("disease_areas", [])])
    diseases = _unique([disease for record in records for disease in record.get("disease_indications", [])])
    classification = classify_article(article)
    enriched = {
        **article,
        "drugs": drugs,
        "drug": canonical_drugs[0] if canonical_drugs else None,
        "targets": targets,
        "diseases": diseases,
        "disease": diseases[0] if diseases else None,
        "disease_areas": disease_areas,
        "article_type": classification["article_type"],
        "study_design": classification["study_design"],
        "evidence_types": classification["evidence_types"],
        "source_type": "PMC",
        "discovery_profile": discovery_metadata.get("discovery_profile"),
        "retrieval_query": discovery_metadata.get("query"),
        "metadata_version": METADATA_VERSION,
    }
    return enriched


def inherit_chunk_metadata(chunk: dict[str, Any], article: dict[str, Any]) -> dict[str, Any]:
    path = chunk.get("section_path", "")
    category = section_category(chunk.get("subsection") or chunk.get("section") or "", chunk.get("text", ""))
    return {
        **chunk,
        "drug": article.get("drug"),
        "drugs": "|".join(item["canonical_name"] for item in article.get("drugs", [])),
        "disease": article.get("disease"),
        "disease_area": (article.get("disease_areas") or [None])[0],
        "targets": "|".join(article.get("targets", [])),
        "evidence_type": category,
        "evidence_types": "|".join(article.get("evidence_types", [])),
        "section_category": category,
        "article_type": article.get("article_type"),
        "study_design": article.get("study_design"),
        "publication_year": article.get("publication_year"),
        "source_type": article.get("source_type", "PMC"),
        "metadata_version": article.get("metadata_version", METADATA_VERSION),
        "section_path": path,
    }
