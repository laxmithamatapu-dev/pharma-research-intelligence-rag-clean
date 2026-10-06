"""Deterministic article and section evidence classification."""

import re
from typing import Any


EVIDENCE_CUES = {
    "indication": ("indication", "approved", "used for", "treatment of"),
    "mechanism": ("mechanism", "binding", "inhibition", "target engagement", "signaling", "pharmacology"),
    "clinical_trial": ("clinical trial", "randomized", "phase i", "phase ii", "phase iii", "enrollment", "endpoint"),
    "efficacy": ("efficacy", "response rate", "progression-free", "overall survival", "tumor response"),
    "safety": ("safety", "adverse event", "toxicity", "tolerability", "discontinuation", "dose reduction"),
    "biomarker": ("biomarker", "mutation", "amplification", "expression", "predictive", "prognostic", "subgroup"),
    "resistance": ("resistance", "progression", "acquired mutation", "bypass", "transformation", "treatment failure"),
    "comparison": ("comparison", "comparative", "versus", "vs.", "head-to-head", "standard of care"),
    "combination_strategy": ("combination", "synergy", "co-treatment", "cotreatment", "sequencing", "in combination"),
    "review": ("review", "systematic review", "meta-analysis", "overview"),
    "real_world_evidence": ("retrospective", "observational", "registry", "real-world", "claims", "electronic health record"),
    "pharmacodynamics": ("pharmacodynamic", "target engagement", "downstream effect"),
    "pharmacokinetics": ("pharmacokinetic", "bioavailability", "clearance", "half-life", "exposure"),
}

STUDY_DESIGN_CUES = {
    "randomized_phase_I": ("phase i", "randomized"),
    "randomized_phase_II": ("phase ii", "randomized"),
    "randomized_phase_III": ("phase iii", "randomized"),
    "single_arm": ("single-arm", "single arm"),
    "retrospective_cohort": ("retrospective cohort", "retrospective"),
    "prospective_cohort": ("prospective cohort", "prospective"),
    "systematic_review": ("systematic review",),
    "meta_analysis": ("meta-analysis", "meta analysis"),
    "in_vitro": ("in vitro", "cell line"),
    "in_vivo": ("in vivo", "xenograft"),
}


def _matches(text: str, cues: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    return any(cue in lowered for cue in cues)


def normalize_article_type(value: str | None) -> str:
    normalized = str(value or "").casefold().replace("-", "_").replace(" ", "_")
    if "review" in normalized and "systematic" in normalized:
        return "systematic_review"
    if "meta_analysis" in normalized or "meta-analysis" in normalized:
        return "meta_analysis"
    if "review" in normalized:
        return "review"
    if "clinical_trial" in normalized or "clinicaltrial" in normalized:
        return "clinical_trial"
    if normalized in {"research_article", "original_article", ""}:
        return "primary_research"
    return normalized


def infer_study_design(article: dict[str, Any]) -> str:
    text = " ".join(str(article.get(key, "")) for key in ("title", "abstract", "article_type"))
    for design, cues in STUDY_DESIGN_CUES.items():
        if _matches(text, cues):
            return design
    article_type = normalize_article_type(article.get("article_type"))
    if article_type == "systematic_review":
        return "systematic_review"
    if article_type == "meta_analysis":
        return "meta_analysis"
    return "not_reported"


def classify_text(text: str, section_title: str = "", article: dict[str, Any] | None = None) -> list[str]:
    article = article or {}
    combined = " ".join(str(value or "") for value in (
        article.get("article_type", ""),
        article.get("title", ""),
        article.get("abstract", ""),
        section_title,
        text,
    ))
    labels = [label for label, cues in EVIDENCE_CUES.items() if _matches(combined, cues)]
    if not labels:
        labels = ["review"] if "review" in combined.casefold() else ["indication"]
    return labels


def classify_article(article: dict[str, Any]) -> dict[str, Any]:
    labels = classify_text(
        " ".join(str(value or "") for value in (
            article.get("title", ""),
            article.get("abstract", ""),
        )),
        article=article,
    )
    article_type = normalize_article_type(article.get("article_type"))
    if article_type in {"review", "systematic_review", "meta_analysis"} and "review" not in labels:
        labels.append("review")
    if not labels:
        labels = ["indication"]
    return {
        "evidence_types": labels,
        "study_design": article.get("study_design") or infer_study_design(article),
        "article_type": article_type,
    }


def section_category(section_title: str, text: str = "") -> str:
    labels = classify_text(text, section_title=section_title)
    priority = (
        "mechanism", "clinical_trial", "safety", "biomarker", "resistance",
        "combination_strategy", "real_world_evidence", "efficacy", "review",
        "indication",
    )
    return next((label for label in priority if label in labels), labels[0])
