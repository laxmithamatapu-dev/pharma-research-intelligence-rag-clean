import json
import math  # NEW
import os
import re
import unicodedata
from typing import Any, Callable, Dict, List, Optional, Tuple  # CHANGED: added Callable, Optional, Tuple

import requests
from json_repair import repair_json

try:
    from processing.drug_registry import DrugRegistry
except ModuleNotFoundError:
    from src.processing.drug_registry import DrugRegistry


class QueryUnderstanding:

    MECHANISM_QUESTION_PATTERNS = (
        (
            "how_does_work",
            re.compile(r"\bhow\s+does\s+.+?\s+work\b", re.IGNORECASE),
        ),
        (
            "mechanism_of_action",
            re.compile(r"\bmechanism\s+of\s+action\s+of\s+.+", re.IGNORECASE),
        ),
        (
            "mechanism_of",
            re.compile(r"\bmechanism\s+of\s+.+", re.IGNORECASE),
        ),
        (
            "mode_of_action",
            re.compile(r"\bmode\s+of\s+action\s+of\s+.+", re.IGNORECASE),
        ),
        (
            "moa_of",
            re.compile(r"\bmoa\s+of\s+.+", re.IGNORECASE),
        ),
        (
            "how_does_inhibit_or_activate",
            re.compile(
                r"\bhow\s+does\s+.+?\s+(?:inhibit|activate)\s+.+",
                re.IGNORECASE,
            ),
        ),
        (
            "target_of",
            re.compile(r"\btarget\s+of\s+.+", re.IGNORECASE),
        ),
    )

    DRUG_OVERVIEW_QUESTION_PATTERNS = (
        (
            "what_is_used_for",
            re.compile(r"\bwhat\s+is\s+.+?\s+used\s+for\b", re.IGNORECASE),
        ),
        (
            "what_are_the_indications",
            re.compile(r"\bwhat\s+are\s+the\s+indications\s+of\s+.+", re.IGNORECASE),
        ),
        (
            "approved_uses",
            re.compile(r"\bapproved\s+uses\s+of\s+.+", re.IGNORECASE),
        ),
        (
            "clinical_uses",
            re.compile(r"\bclinical\s+uses\s+of\s+.+", re.IGNORECASE),
        ),
        (
            "conditions_treated",
            re.compile(r"\bwhat\s+conditions\s+does\s+.+?\s+treat\b", re.IGNORECASE),
        ),
        (
            "cancers_treated",
            re.compile(r"\bwhat\s+cancers\s+does\s+.+?\s+treat\b", re.IGNORECASE),
        ),
        (
            "indications_for",
            re.compile(r"\bindications\s+for\s+.+", re.IGNORECASE),
        ),
    )

    VALID_INTENTS = {
        "EXPLANATION",
        "COMPARISON",
        "ANALYSIS",
        "SUMMARY",
        "PROCEDURE",
        "EVIDENCE",
        "DECISION_SUPPORT",
        "FACT_LOOKUP",
        "GENERAL",
    }

    VALID_QUESTION_TYPES = {
        "RESISTANCE",
        "BIOMARKER",
        "CLINICAL_TRIAL",
        "SAFETY",
        "REGULATORY",
        "MOA",
        "EFFICACY",
        "MECHANISM",
        "DRUG_OVERVIEW",
        "DISEASE",
        "DRUG",
        "TARGET",
        "GENE",
        "PROTEIN",
        "THERAPY",
        "DIAGNOSTIC",
        "PHARMACOKINETICS",
        "PHARMACODYNAMICS",
        "ADVERSE_EVENT",
        "DRUG_INTERACTION",
        "DOSING",
        "PROGNOSIS",
        "EPIDEMIOLOGY",
        "COMPARATIVE_EFFECTIVENESS",
        "GENERAL_RESEARCH",
        "OTHER",
    }

    VALID_ANSWER_TYPES = {
        "FACTUAL",
        "EXPLANATORY",
        "COMPARATIVE",
        "ANALYTICAL",
        "SUMMARY",
        "EVIDENCE_BASED",
        "PROCEDURAL",
        "DECISION_SUPPORT",
        "GENERAL",
    }

    VALID_COMPLEXITIES = {
        "LOW",
        "MEDIUM",
        "HIGH",
    }

    RETRIEVAL_HINTS_BY_TYPE = {
        "DRUG_OVERVIEW": (
            "Prioritize approved indication and FDA approval evidence",
            "Look for approved cancer indications and tumor types",
            "Look for regulatory approval and label expansion evidence",
            "Look for clinical use evidence",
            "Look for clinical evidence and safety considerations",
        ),
        "MECHANISM": (
            "Look for mechanism of action evidence",
            "Look for target biology evidence",
        ),
        "MOA": (
            "Look for mechanism of action evidence",
            "Look for target biology evidence",
        ),
        "CLINICAL_TRIAL": (
            "Look for clinical trial evidence",
            "Look for study design and outcome evidence",
        ),
        "SAFETY": (
            "Look for safety and adverse event evidence",
        ),
        "ADVERSE_EVENT": (
            "Look for adverse event evidence",
        ),
        "BIOMARKER": (
            "Look for biomarker evidence",
        ),
        "RESISTANCE": (
            "Look for resistance mechanism evidence",
        ),
        "EFFICACY": (
            "Look for efficacy and outcome evidence",
        ),
        "COMPARATIVE_EFFECTIVENESS": (
            "Look for comparative effectiveness evidence",
            "Look for study design and outcome evidence",
        ),
        "COMPARISON": (
            "Look for comparative evidence",
            "Look for similarities and differences in reported outcomes",
        ),
    }

    # ------------------------------------------------------------------ #
    # NEW: fast (non-LLM) classification settings
    # ------------------------------------------------------------------ #

    # Below this confidence the question is sent to the LLM fallback.
    LLM_FALLBACK_CONFIDENCE = 0.5
    LLM_OPTIONS = {"temperature": 0, "seed": 0}
    # Raw weighted score at which a taxonomy score reaches ~0.63.
    TAXONOMY_SATURATION = 3.0
    # A type scoring below this is treated as "not detected".
    MIN_TYPE_SCORE = 0.25

    # Pharma vocabulary. Terms ending in * are prefix matches (mechanis* matches
    # mechanism / mechanisms / mechanistic). Weights: 3 strong, 2 medium, 1 weak.
    # "patterns" are regexes over normalized text. "examples" feed the optional
    # semantic layer. Extend this dict (or pass `taxonomy=`) to grow coverage.
    QUESTION_TYPE_TAXONOMY = {
        "MECHANISM": {
            "intent": "EXPLANATION",
            "terms": {
                "mechanis*": 3, "mode of action": 3, "moa": 3, "inhibit*": 1.5,
                "agonist*": 1.5, "antagonist*": 1.5, "pathway*": 1.5,
                "activat*": 1, "signal*": 1, "binds": 1, "binding": 1,
                "receptor*": 1, "target*": 1,
            },
            "patterns": {
                r"\bhow (?:does|do) (?:(?!trial|study|studies).)+? work\b": 3,
                r"\bhow (?:does|do) .+? (?:inhibit|activate|block|bind|target|modulate)\b": 3,
            },
            "examples": [
                "How does this drug work at the molecular level?",
                "What is the biological basis of this drug's activity?",
            ],
        },
        "DRUG_OVERVIEW": {
            "intent": "EXPLANATION",
            "terms": {
                "indication*": 2, "used to treat": 3, "used for": 2,
                "clinical use*": 3, "tell me about": 1.5, "overview": 1,
            },
            "patterns": {
                r"\bwhat (?:is|are) .+? (?:used|approved|indicated) (?:for|to treat)\b": 3,
                r"\bwhat (?:conditions|cancers|diseases) (?:does|do) .+? treat\b": 3,
            },
            "examples": [
                "What is this drug used for?",
                "Which cancers can this therapy treat?",
            ],
        },
        "RESISTANCE": {
            "terms": {
                "resist*": 3, "refractory": 2.5, "relaps*": 1.5, "escape": 1.5,
                "bypass": 2,
            },
            "patterns": {
                r"\bmechanisms? of (?:acquired |drug |treatment )?resistance\b": 3,
                r"\bwhy (?:do|does|did) .+? (?:stop working|fail|lose)\b": 2.5,
            },
            "examples": [
                "Why do tumours stop responding to this drug over time?",
                "What mutations cause acquired resistance?",
            ],
        },
        "BIOMARKER": {
            "terms": {
                "biomarker*": 3, "marker*": 1.5, "mutation*": 1.5, "mutated": 1.5,
                "variant*": 1.5, "alteration*": 1.5, "fusion*": 1.5,
                "amplification": 1.5, "expression": 1.5, "predict*": 1.5,
                "genotyp*": 2, "tmb": 2, "msi": 1.5, "ctdna": 2,
            },
            "patterns": {r"\b[a-z]\d{2,4}[a-z]\b": 1.5},
            "examples": [
                "Which patients are likely to respond based on their genetic profile?",
                "Does PD-L1 expression predict benefit?",
            ],
        },
        "CLINICAL_TRIAL": {
            "terms": {
                "clinical trial*": 3, "trial*": 2, "stud*": 1, "randomi*": 2,
                "endpoint*": 2, "enrol*": 2, "cohort*": 1, "study design": 3,
                "placebo": 1.5, "double blind": 2, "open label": 2,
            },
            "patterns": {
                r"\bnct\d{8}\b": 5,
                r"\bphase (?:1|2|3|4|i|ii|iii|iv)\b": 3,
            },
            "examples": [
                "What were the results of the pivotal phase 3 study?",
                "What was the primary endpoint of the study?",
            ],
        },
        "COMPARATIVE_EFFECTIVENESS": {
            "intent": "COMPARISON",
            "terms": {
                "compar*": 3, "versus": 3, "vs": 3, "better than": 3,
                "head to head": 3, "difference* between": 3, "superior*": 2,
                "inferior*": 2,
            },
            "patterns": {r"\bwhich .+? (?:is )?(?:better|more effective|safer)\b": 3},
            "examples": [
                "Which of these two drugs works better?",
                "How does the new therapy compare with standard chemotherapy?",
            ],
        },
        "EFFICACY": {
            "terms": {
                "efficacy": 3, "effective*": 2.5, "response rate*": 3, "orr": 2.5,
                "overall survival": 3, "progression free": 3, "pfs": 2.5,
                "survival": 1.5, "hazard ratio": 2.5, "outcome*": 1.5,
                "remission": 2, "duration of response": 3,
            },
            "examples": [
                "How well does this drug shrink tumours?",
                "Does the treatment improve overall survival?",
            ],
        },
        "ADVERSE_EVENT": {
            "terms": {
                "adverse": 3, "side effect*": 1.5, "immune related": 2.5,
                "irae*": 2.5, "discontinuation": 1.5,
            },
            "patterns": {r"\bgrade [1-5]\b": 2.5},
            "examples": [
                "What are the most common adverse events?",
                "How often do patients stop treatment because of toxicity?",
            ],
        },
        "SAFETY": {
            "terms": {
                "safe*": 3, "toxic*": 3, "side effect*": 3, "tolerab*": 2.5,
                "boxed warning": 3, "contraindicat*": 3, "risk*": 1.5,
                "warning*": 1.5, "precaution*": 2, "hepatotox*": 2.5,
                "cardiotox*": 2.5,
            },
            "examples": [
                "Is this drug safe for patients with liver disease?",
                "What risks should clinicians monitor for?",
            ],
        },
        "REGULATORY": {
            "terms": {
                "fda": 2, "ema": 2, "pmda": 2, "nmpa": 2, "cdsco": 2, "mhra": 2,
                "regulator*": 2.5, "approv*": 1.5, "label*": 1.5,
                "accelerated approval": 3, "breakthrough": 1.5,
                "priority review": 2.5, "marketing authori*": 3,
            },
            "examples": [
                "When did the FDA approve this drug?",
                "What is the regulatory status in Europe?",
            ],
        },
        "DOSING": {
            "terms": {
                "dos*": 3, "mg": 2, "schedule*": 2, "regimen*": 2, "administ*": 2,
                "titrat*": 2.5, "how much": 2.5, "frequency": 1.5, "infusion": 1.5,
            },
            "examples": [
                "What is the recommended dose?",
                "How often should this drug be administered?",
            ],
        },
        "PHARMACOKINETICS": {
            "terms": {
                "pharmacokinetic*": 3, "pk": 2.5, "half life": 3, "clearance": 2.5,
                "bioavailab*": 3, "absorption": 2.5, "metaboli*": 2.5,
                "excret*": 2.5, "cmax": 3, "auc": 3, "elimination": 2.5,
                "cyp*": 1.5,
            },
            "examples": [
                "How is this drug absorbed and eliminated?",
                "What is the elimination half-life?",
            ],
        },
        "PHARMACODYNAMICS": {
            "terms": {
                "pharmacodynamic*": 3, "dose response": 3, "receptor occupancy": 3,
                "target engagement": 3, "exposure response": 3,
            },
            "examples": ["How does drug exposure relate to its biological effect?"],
        },
        "DRUG_INTERACTION": {
            "terms": {
                "interact*": 3, "co administ*": 3, "coadminist*": 3,
                "concomitant": 2, "inducer*": 2, "contraindicated with": 2.5,
            },
            "patterns": {r"\bcyp\w+ (?:inhibitor|inducer)s?\b": 3},
            "examples": ["Which medicines should not be combined with it?"],
        },
        "DIAGNOSTIC": {
            "terms": {
                "diagnos*": 3, "companion diagnostic*": 3, "screening": 2.5,
                "assay*": 2, "testing": 2, "detect*": 2, "biopsy": 2,
                "sequencing": 2, "ngs": 2,
            },
            "examples": ["How is this condition diagnosed?"],
        },
        "PROGNOSIS": {
            "terms": {
                "prognos*": 3, "survival rate*": 3, "life expectancy": 3,
                "outlook": 2,
            },
            "examples": ["What is the outlook for patients with this disease?"],
        },
        "EPIDEMIOLOGY": {
            "terms": {
                "incidence": 3, "prevalence": 3, "epidemiolog*": 3,
                "mortality": 2.5, "risk factor*": 2.5, "how common": 3,
            },
            "examples": ["How common is this cancer worldwide?"],
        },
        "THERAPY": {
            "terms": {
                "treatment option*": 3, "standard of care": 3, "first line": 3,
                "second line": 3, "adjuvant": 2.5, "neoadjuvant": 2.5,
                "combination therapy": 3, "guideline*": 2.5, "nccn": 3, "esmo": 3,
            },
            "examples": [
                "What is the standard treatment for this stage of disease?",
            ],
        },
        "DISEASE": {
            "terms": {
                "pathophysiolog*": 3, "etiolog*": 3, "symptom*": 2.5,
                "subtype*": 2, "staging": 2, "causes of": 2.5,
            },
            "examples": ["What causes this disease and how does it progress?"],
        },
    }

    # Intent cues, checked in order. A match overrides the type's default intent.
    INTENT_CUES = (
        ("COMPARISON", ("compar*", "versus", "vs", "better than", "head to head", "difference* between")),
        ("SUMMARY", ("summar*", "overview of")),
        ("PROCEDURE", ("how to", "how do i", "how can i", "step by step", "protocol*", "procedure*")),
        ("DECISION_SUPPORT", ("should i", "should we", "recommend*", "best option", "best treatment")),
        ("ANALYSIS", ("analy*", "assess*", "evaluat*", "implication*")),
        ("EVIDENCE", ("evidence", "data on", "data for", "studies show")),
    )

    # Used only when neither a cue nor the type's default intent applies.
    INTENT_FALLBACK_PATTERNS = (
        ("EXPLANATION", r"^(?:why|how|explain|describe)\b"),
        ("FACT_LOOKUP", r"^(?:what|which|who|when|where|list|name|is|are|does|do)\b"),
    )

    SINGLE_STUDY_PATTERNS = (
        re.compile(
            r"\b(?:in|of|from|for) (?:the|this) [^?]{0,80}?\b"
            r"(?:cohort|trial|study|analysis|case report|case|registry|model|participants|subgroup)\b",
            re.IGNORECASE,
        ),
        re.compile(r"\bthe [^?.]{0,60}?\bpatient\b", re.IGNORECASE),
        re.compile(r"\bcase report\b", re.IGNORECASE),
        re.compile(r"\b[A-Z]{4,}-\d+[A-Z]?\b"),
        re.compile(r"\b[A-Z][a-z]+[A-Z][a-z]+ \d+[A-Z]*\b"),
        re.compile(r"\bNCT\d{8}\b"),
    )

    INTENT_TO_ANSWER_TYPE = {
        "EXPLANATION": "EXPLANATORY",
        "COMPARISON": "COMPARATIVE",
        "ANALYSIS": "ANALYTICAL",
        "SUMMARY": "SUMMARY",
        "PROCEDURE": "PROCEDURAL",
        "EVIDENCE": "EVIDENCE_BASED",
        "DECISION_SUPPORT": "DECISION_SUPPORT",
        "FACT_LOOKUP": "FACTUAL",
        "GENERAL": "GENERAL",
    }

    @staticmethod
    def _debug_stage(stage: str, value: Any) -> None:
        print(f"\nDEBUG {stage}:")
        if isinstance(value, str):
            print(value)
        else:
            print(json.dumps(value, indent=2, ensure_ascii=False, default=str))

    @staticmethod
    def _ollama_generate_url() -> str:
        host = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434").strip()
        if not host.startswith(("http://", "https://")):
            host = f"http://{host}"
        return f"{host.rstrip('/')}/api/generate"

    def __init__(
        self,
        model_name: str = "qwen2.5:1.5b",
        registry: DrugRegistry | None = None,
        # NEW parameters (all optional; defaults keep old call sites working)
        embed_fn: Optional[Callable[[List[str]], Any]] = None,
        confidence_threshold: Optional[float] = None,
        llm_timeout: float = 60.0,
        semantic_weight: float = 0.4,
        semantic_floor: float = 0.35,
        semantic_ceiling: float = 0.75,
        taxonomy: Optional[Dict[str, Dict[str, Any]]] = None,
    ):
        self.model_name = model_name
        self.registry = registry or DrugRegistry()

        # NEW
        self.llm_timeout = llm_timeout
        self.confidence_threshold = (
            self.LLM_FALLBACK_CONFIDENCE
            if confidence_threshold is None
            else confidence_threshold
        )
        self.taxonomy = taxonomy or self.QUESTION_TYPE_TAXONOMY
        self._compiled_taxonomy = self._compile_taxonomy(self.taxonomy)
        self._compiled_intent_cues = [
            (intent, [self._compile_term(term) for term in terms])
            for intent, terms in self.INTENT_CUES
        ]
        self._compiled_intent_fallbacks = [
            (intent, re.compile(pattern))
            for intent, pattern in self.INTENT_FALLBACK_PATTERNS
        ]
        self._embed_fn = embed_fn
        self._semantic_weight = semantic_weight if embed_fn else 0.0
        self._semantic_floor = semantic_floor
        self._semantic_ceiling = semantic_ceiling
        self._prototype_matrix = None
        self._prototype_owners: List[str] = []
        if embed_fn is not None:
            self._build_prototypes()

    # ------------------------------------------------------------------ #
    # NEW: taxonomy + semantic scoring (no LLM)
    # ------------------------------------------------------------------ #

    @classmethod
    def _compile_term(cls, term: str) -> "re.Pattern[str]":
        """'mechanis*' -> prefix match; 'half life' -> exact token phrase."""
        prefix = term.endswith("*")
        core = cls._normalize_grounding_text(term.rstrip("*"))
        if not core:
            raise ValueError(f"Empty taxonomy term: {term!r}")
        body = " ".join(re.escape(token) for token in core.split())
        return re.compile(rf"\b{body}\w*" if prefix else rf"\b{body}\b")

    @classmethod
    def _compile_taxonomy(cls, taxonomy: Dict[str, Dict[str, Any]]):
        compiled = {}
        for question_type, spec in taxonomy.items():
            if question_type not in cls.VALID_QUESTION_TYPES:
                raise ValueError(f"Unknown question type in taxonomy: {question_type}")
            intent = spec.get("intent")
            if intent is not None and intent not in cls.VALID_INTENTS:
                raise ValueError(f"{question_type}: unknown intent {intent}")
            matchers = [
                (cls._compile_term(term), float(weight))
                for term, weight in spec.get("terms", {}).items()
            ] + [
                (re.compile(pattern), float(weight))
                for pattern, weight in spec.get("patterns", {}).items()
            ]
            compiled[question_type] = {
                "intent": intent,
                "matchers": matchers,
            }
        return compiled

    def _build_prototypes(self) -> None:
        """Embed the taxonomy's example questions once at start-up."""
        import numpy as np  # local import: not needed unless semantic layer is on

        self._np = np
        texts, owners = [], []
        for question_type, spec in self.taxonomy.items():
            for example in spec.get("examples", []):
                texts.append(example)
                owners.append(question_type)
        if not texts:
            self._embed_fn = None
            self._semantic_weight = 0.0
            return
        self._prototype_owners = owners
        self._prototype_matrix = self._unit_vectors(
            np.asarray(self._embed_fn(texts), dtype="float32")
        )

    def _unit_vectors(self, array):
        norms = self._np.linalg.norm(array, axis=-1, keepdims=True)
        return array / self._np.clip(norms, 1e-9, None)

    def _taxonomy_scores(self, normalized_text: str) -> Dict[str, float]:
        scores = {}
        for question_type, spec in self._compiled_taxonomy.items():
            raw = sum(
                weight
                for regex, weight in spec["matchers"]
                if regex.search(normalized_text)
            )
            if raw:
                scores[question_type] = 1.0 - math.exp(-raw / self.TAXONOMY_SATURATION)
        return scores

    def _semantic_scores(self, question: str) -> Dict[str, float]:
        if self._embed_fn is None or self._prototype_matrix is None:
            return {}
        np = self._np
        vector = self._unit_vectors(
            np.asarray(self._embed_fn([question]), dtype="float32")
        )[0]
        similarities = self._prototype_matrix @ vector
        best: Dict[str, float] = {}
        for owner, similarity in zip(self._prototype_owners, similarities):
            best[owner] = max(best.get(owner, -1.0), float(similarity))
        span = max(self._semantic_ceiling - self._semantic_floor, 1e-6)
        return {
            owner: min(1.0, max(0.0, (similarity - self._semantic_floor) / span))
            for owner, similarity in best.items()
        }

    def _detect_intent(self, normalized_text: str, question_type: str) -> str:
        for intent, regexes in self._compiled_intent_cues:
            if any(regex.search(normalized_text) for regex in regexes):
                return intent
        default_intent = self._compiled_taxonomy.get(question_type, {}).get("intent")
        if default_intent:
            return default_intent
        for intent, regex in self._compiled_intent_fallbacks:
            if regex.search(normalized_text):
                return intent
        return "GENERAL"

    @staticmethod
    def _estimate_complexity(
        normalized_text: str, intent: str, drug_count: int
    ) -> str:
        words = len(normalized_text.split())
        points = (
            (drug_count >= 2)
            + (intent in {"COMPARISON", "ANALYSIS", "DECISION_SUPPORT"})
            + (words > 25)
            + (normalized_text.count(" and ") >= 2)
        )
        if points == 0 and words <= 12:
            return "LOW"
        return "HIGH" if points >= 3 else "MEDIUM"

    def _classify_without_llm(self, question: str) -> Tuple[Dict[str, Any], float]:
        """Fast path: returns (LLM-shaped result, confidence in [0, 1]).

        The returned dict has the same keys the LLM used to produce, so it can
        go straight into validate_result() (grounding, deterministic overrides,
        hint/expansion building) unchanged.
        """
        normalized_text = self._normalize_grounding_text(question)
        normalized_question = self._normalize_mechanism_question(question)

        # DrugRegistry grounding: drugs and their known targets come from the
        # registry, never from a model.
        detected_drugs = self._detected_drug_records(question)
        padded_text = f" {normalized_text} "
        targets_in_question = []
        for record in detected_drugs.values():
            for target in record.get("targets", []):
                if target and self._normalize_grounding_text(str(target)) and (
                    f" {self._normalize_grounding_text(str(target))} " in padded_text
                ):
                    targets_in_question.append(str(target))

        # Existing deterministic patterns are authoritative (confidence 1.0).
        if any(p.search(normalized_question) for _, p in self.MECHANISM_QUESTION_PATTERNS):
            question_type, confidence = "MECHANISM", 1.0
        elif any(
            p.search(normalized_question)
            for _, p in self.DRUG_OVERVIEW_QUESTION_PATTERNS
        ):
            question_type, confidence = "DRUG_OVERVIEW", 1.0
        else:
            lexical = self._taxonomy_scores(normalized_text)
            semantic = self._semantic_scores(question)
            weight = self._semantic_weight
            combined = {
                name: (1.0 - weight) * lexical.get(name, 0.0)
                + weight * semantic.get(name, 0.0)
                for name in self._compiled_taxonomy
                if name in lexical or name in semantic
            }
            ranked = sorted(
                ((n, s) for n, s in combined.items() if s >= self.MIN_TYPE_SCORE),
                key=lambda item: -item[1],
            )
            if ranked:
                question_type, top = ranked[0]
                runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
                confidence = max(0.0, min(1.0, top + 0.5 * (top - runner_up)))
            else:
                question_type, confidence = "GENERAL_RESEARCH", 0.0

        intent = self._detect_intent(normalized_text, question_type)
        entities = {
            "DRUG": list(detected_drugs),
            "TARGET": list(dict.fromkeys(targets_in_question)),
        }
        result = {
            "intent": intent,
            "question_type": question_type,
            "answer_type": self.INTENT_TO_ANSWER_TYPE[intent],
            "complexity": self._estimate_complexity(
                normalized_text, intent, len(detected_drugs)
            ),
            "entities": entities,
            "retrieval_hints": [],
            "expanded_queries": [],
        }
        return result, round(confidence, 2)

    # ------------------------------------------------------------------ #
    # Everything below is the original code (unchanged) except analyze()
    # ------------------------------------------------------------------ #

    def build_prompt(
        self,
        question: str
    ) -> str:

        return f"""
Return ONLY valid JSON.

intent must be one of:

[
"EXPLANATION",
"COMPARISON",
"ANALYSIS",
"SUMMARY",
"PROCEDURE",
"EVIDENCE",
"DECISION_SUPPORT",
"FACT_LOOKUP",
"GENERAL"
]

question_type must be one of:

[
"RESISTANCE",
"BIOMARKER",
"CLINICAL_TRIAL",
"SAFETY",
"REGULATORY",
"MOA",
"EFFICACY",
"MECHANISM",
"DRUG_OVERVIEW",
"DISEASE",
"DRUG",
"TARGET",
"GENE",
"PROTEIN",
"THERAPY",
"DIAGNOSTIC",
"PHARMACOKINETICS",
"PHARMACODYNAMICS",
"ADVERSE_EVENT",
"DRUG_INTERACTION",
"DOSING",
"PROGNOSIS",
"EPIDEMIOLOGY",
"COMPARATIVE_EFFECTIVENESS",
"GENERAL_RESEARCH",
"OTHER"
]

complexity must be:

[
"LOW",
"MEDIUM",
"HIGH"
]

Generate:

1. Intent
2. Question Type
3. Answer Type
4. Complexity
5. Entities
6. Retrieval Hints
7. Retrieval Expansions

Question:

{question}

Return ONLY:

{{
  "intent": "",
  "question_type": "",
  "answer_type": "",
  "complexity": "",

  "entities": {{
      "DRUG": [],
      "GENE": [],
      "PROTEIN": [],
      "TARGET": [],
      "BIOMARKER": [],
      "DISEASE": [],
      "THERAPY": [],
      "TRIAL": [],
      "COMPANY": [],
      "DOCUMENT": [],
      "REGULATORY_ENTITY": [],
      "OTHER": []
  }},

  "retrieval_hints": [],

  "expanded_queries": []
}}
"""

    def extract_json(
        self,
        response: str
    ) -> Dict[str, Any]:

        response = response.replace(
            "```json",
            ""
        )

        response = response.replace(
            "```",
            ""
        )

        start = response.find("{")
        end = response.rfind("}")

        if start == -1 or end == -1:
            raise ValueError(
                "No valid JSON found."
            )

        json_text = response[
            start:end + 1
        ]

        try:
            return json.loads(
                json_text
            )

        except Exception:

            repaired = repair_json(
                json_text
            )

            return json.loads(
                repaired
            )

    def normalize_string(
        self,
        value: Any
    ) -> str:

        if not isinstance(
            value,
            str
        ):
            return ""

        return value.strip()

    def normalize_list(
        self,
        value: Any
    ) -> List[str]:

        if not isinstance(
            value,
            list
        ):
            return []

        cleaned = []

        for item in value:

            if isinstance(
                item,
                str
            ):

                item = item.strip()

                if item:
                    cleaned.append(
                        item
                    )

        return list(
            dict.fromkeys(
                cleaned
            )
        )

    def validate_entities(
        self,
        entities: Any
    ) -> Dict[str, List[str]]:

        entity_types = [
            "DRUG",
            "GENE",
            "PROTEIN",
            "TARGET",
            "BIOMARKER",
            "DISEASE",
            "THERAPY",
            "TRIAL",
            "COMPANY",
            "DOCUMENT",
            "REGULATORY_ENTITY",
            "OTHER",
        ]

        result = {
            entity_type: []
            for entity_type
            in entity_types
        }

        if not isinstance(
            entities,
            dict
        ):
            return result

        for entity_type in entity_types:

            result[
                entity_type
            ] = self.normalize_list(
                entities.get(
                    entity_type,
                    []
                )
            )

        return result

    @staticmethod
    def _normalize_grounding_text(value: str) -> str:
        """Normalize text for phrase matching while retaining biomedical tokens."""
        value = re.sub(
            r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))",
            "",
            value,
        )
        value = "".join(
            " " if unicodedata.category(character) in {"Cc", "Cf"} else character
            for character in value
        )
        return " ".join(re.findall(r"[^\W_]+", value.casefold()))

    @classmethod
    def _phrase_is_present(cls, phrase: str, text: str) -> bool:
        normalized_phrase = cls._normalize_grounding_text(phrase)
        normalized_text = cls._normalize_grounding_text(text)
        return bool(normalized_phrase) and (
            f" {normalized_phrase} " in f" {normalized_text} "
        )

    def _detected_drug_records(self, question: str) -> dict[str, dict[str, Any]]:
        """Return registry drug records whose aliases occur in the question."""
        records = {}
        for mention in self.registry.find_mentions(question, "question"):
            canonical_name = mention["canonical_name"]
            if canonical_name not in records:
                records[canonical_name] = (
                    self.registry.get(canonical_name) or {}
                )
        return records

    def _ground_entities(
        self,
        entities: Dict[str, List[str]],
        question: str,
        detected_drugs: dict[str, dict[str, Any]],
    ) -> tuple[Dict[str, List[str]], list[str]]:
        """Remove entities not stated in the question or supported by detected drugs."""
        grounded = {
            entity_type: []
            for entity_type in entities
        }
        removed = []
        detected_drug_names = set(detected_drugs)
        known_drug_aliases = set()
        known_targets = set()

        for canonical_name, record in detected_drugs.items():
            known_drug_aliases.add(
                self._normalize_grounding_text(canonical_name)
            )
            known_drug_aliases.update(
                self._normalize_grounding_text(str(alias))
                for alias in (
                    record.get("generic_name", ""),
                    *record.get("synonyms", []),
                    *record.get("brand_names", []),
                    *record.get("development_codes", []),
                )
                if alias
            )
            known_targets.update(
                self._normalize_grounding_text(str(target))
                for target in record.get("targets", [])
                if target
            )

        for entity_type, values in entities.items():
            accepted = grounded[entity_type]
            for value in values:
                normalized_value = self._normalize_grounding_text(value)
                appears_in_question = self._phrase_is_present(value, question)

                if entity_type == "DRUG":
                    registry_match = self.registry.lookup(value)
                    if registry_match:
                        canonical = registry_match["canonical_name"]
                        allowed_alias = (
                            canonical in detected_drug_names
                            and normalized_value in known_drug_aliases
                        )
                        if appears_in_question or allowed_alias:
                            accepted.append(canonical)
                        else:
                            removed.append({
                                "entity_type": entity_type,
                                "value": value,
                            })
                    elif appears_in_question:
                        accepted.append(value)
                    else:
                        removed.append({
                            "entity_type": entity_type,
                            "value": value,
                        })
                    continue

                is_registry_target = (
                    entity_type in {"TARGET", "GENE", "PROTEIN"}
                    and normalized_value in known_targets
                )
                if appears_in_question or is_registry_target:
                    accepted.append(value)
                else:
                    removed.append({
                        "entity_type": entity_type,
                        "value": value,
                    })

            grounded[entity_type] = list(dict.fromkeys(accepted))

        # Add registry-resolved drug entities even if the LLM omitted them.
        grounded["DRUG"] = list(dict.fromkeys([
            *detected_drugs.keys(),
            *grounded["DRUG"],
        ]))
        return grounded, removed

    def _build_grounded_retrieval_hints(
        self,
        question_type: str,
        drug_names: list[str],
        detected_drugs: dict[str, dict[str, Any]],
    ) -> list[str]:
        """Create retrieval instructions from fixed strategy templates only."""
        hints = list(self.RETRIEVAL_HINTS_BY_TYPE.get(question_type, ()))

        if question_type == "DRUG_OVERVIEW":
            for drug_name in drug_names:
                hints.extend((
                    f"Search for approved indications for {drug_name}",
                    f"Look for FDA approval and label expansion evidence for {drug_name}",
                ))
        elif question_type in {"MECHANISM", "MOA"}:
            for drug_name in drug_names:
                hints.append(
                    f"Search for {drug_name} mechanism of action evidence"
                )
                record = detected_drugs.get(drug_name, {})
                for target in record.get("targets", []):
                    hints.append(
                        f"Look for {target} pathway evidence"
                    )

        return list(dict.fromkeys(hints))[:10]

    def _build_grounded_expanded_queries(
        self,
        question: str,
        question_type: str,
        drug_names: list[str],
        detected_drugs: dict[str, dict[str, Any]],
    ) -> list[str]:
        """Build deterministic search rewrites grounded in the question and registry."""
        if question_type == "DRUG_OVERVIEW":
            overview_templates = (
                "approved indications for {drug}",
                "FDA approved uses of {drug}",
                "cancers treated with {drug}",
                "tumor types treated with {drug}",
                "regulatory approvals for {drug}",
                "approved clinical indications for {drug}",
            )
            overview_queries = [
                question,
                *[
                    template.format(drug=drug_name)
                    for drug_name in drug_names
                    for template in overview_templates
                ],
            ]
            return list(dict.fromkeys(
                query for query in overview_queries if query
            ))

        queries = [question] if question else []
        for drug_name in drug_names:
            if question_type in {"MECHANISM", "MOA"}:
                queries.append(f"{drug_name} mechanism of action")
                for target in detected_drugs.get(drug_name, {}).get("targets", []):
                    queries.append(f"{drug_name} {target} pathway")
            elif question_type == "CLINICAL_TRIAL":
                queries.append(f"{drug_name} clinical trial evidence")
            elif question_type in {"SAFETY", "ADVERSE_EVENT"}:
                queries.append(f"{drug_name} safety evidence")
            elif question_type == "BIOMARKER":
                    queries.extend([
                        f"{drug_name} biomarker evidence",
                       
                    ])
            elif question_type == "RESISTANCE":
                    queries.extend([
                    f"{drug_name} resistance evidence",
                    
                    f"{drug_name} acquired resistance",
                ])

        return list(dict.fromkeys(query for query in queries if query))[:5]

    def validate_result(
        self,
        result: Dict[str, Any],
        question: str
    ) -> Dict[str, Any]:

        intent = self.normalize_string(
            result.get("intent")
        ).upper()

        if intent not in self.VALID_INTENTS:
            intent = "GENERAL"

        question_type = self.normalize_string(
            result.get("question_type")
        ).upper()

        if question_type not in self.VALID_QUESTION_TYPES:
            question_type = "GENERAL_RESEARCH"

        answer_type = self.normalize_string(
            result.get("answer_type")
        ).upper()

        if answer_type not in self.VALID_ANSWER_TYPES:
            answer_type = "GENERAL"

        complexity = self.normalize_string(
            result.get("complexity")
        ).upper()

        if complexity not in self.VALID_COMPLEXITIES:
            complexity = "MEDIUM"

        extracted_entities = self.validate_entities(
            result.get("entities")
        )

        extracted_retrieval_hints = self.normalize_list(
            result.get("retrieval_hints")
        )

        extracted_expanded_queries = self.normalize_list(
            result.get("expanded_queries")
        )

        detected_drugs = self._detected_drug_records(question)
        entities, removed_entities = self._ground_entities(
            extracted_entities,
            question,
            detected_drugs,
        )

        validated_result = {

            "intent":
                intent,

            "question_type":
                question_type,

            "answer_type":
                answer_type,

            "complexity":
                complexity,

            "entities":
                entities,

            "retrieval_hints":
                [],

            "expanded_queries":
                [],
        }

        self._debug_stage(
            "QUERY OUTPUT BEFORE GROUNDING",
            {
                "entities": extracted_entities,
                "retrieval_hints": extracted_retrieval_hints,
                "expanded_queries": extracted_expanded_queries,
            },
        )

        original_intent = validated_result["intent"]
        original_question_type = validated_result["question_type"]
        print(f"\nMechanism detection question: {question}")
        print(f"Mechanism detection question repr: {question!r}")
        normalized_question = self._normalize_mechanism_question(question)
        print(f"Normalized mechanism question: {normalized_question!r}")
        print(f"Normalized drug overview question: {normalized_question!r}")
        mechanism_override = self._is_mechanism_question(normalized_question)
        print("Evaluating Drug Overview override inside validate_result().")
        drug_overview_override = self._is_drug_overview_question(
            normalized_question
        )

        print(
            "\nOriginal classification: "
            f"intent={original_intent}, "
            f"question_type={original_question_type}"
        )

        override_reason = None
        if mechanism_override:
            validated_result["intent"] = "EXPLANATION"
            validated_result["question_type"] = "MECHANISM"
            override_reason = "matched deterministic mechanism-question pattern"
        elif drug_overview_override:
            validated_result["intent"] = "EXPLANATION"
            validated_result["question_type"] = "DRUG_OVERVIEW"
            override_reason = "matched deterministic drug-overview question pattern"
        print(f"Override reason: {override_reason or 'none'}")

        validated_result["scope"] = self._detect_scope(
            question,
            validated_result["intent"],
            validated_result["question_type"],
        )

        grounded_retrieval_hints = self._build_grounded_retrieval_hints(
            validated_result["question_type"],
            entities["DRUG"],
            detected_drugs,
        )
        grounded_expanded_queries = self._build_grounded_expanded_queries(
            question,
            validated_result["question_type"],
            entities["DRUG"],
            detected_drugs,
        )

        removed_retrieval_hints = [
            hint
            for hint in extracted_retrieval_hints
            if hint not in grounded_retrieval_hints
        ]
        removed_expanded_queries = [
            query
            for query in extracted_expanded_queries
            if query not in grounded_expanded_queries
        ]
        validated_result["retrieval_hints"] = grounded_retrieval_hints
        validated_result["expanded_queries"] = grounded_expanded_queries

        self._debug_stage(
            "QUERY OUTPUT AFTER GROUNDING",
            {
                "entities": entities,
                "retrieval_hints": grounded_retrieval_hints,
                "expanded_queries": grounded_expanded_queries,
            },
        )
        self._debug_stage("REMOVED ENTITIES", removed_entities)
        self._debug_stage("REMOVED RETRIEVAL HINTS", removed_retrieval_hints)
        self._debug_stage("REMOVED EXPANDED QUERIES", removed_expanded_queries)

        print(
            "Final classification: "
            f"intent={validated_result['intent']}, "
            f"question_type={validated_result['question_type']}"
        )

        print(
            "\nValidated Query Understanding:"
        )

        print(
            json.dumps(
                validated_result,
                indent=2
            )
        )

        return validated_result

    @classmethod
    def _detect_scope(cls, question: str, intent: str, question_type: str) -> str:
        """Return single_study, comparison, or unspecified from explicit wording only."""
        if any(pattern.search(question or "") for pattern in cls.SINGLE_STUDY_PATTERNS):
            return "single_study"
        if intent == "COMPARISON" or question_type == "COMPARATIVE_EFFECTIVENESS":
            return "comparison"
        return "unspecified"

    @classmethod
    def _is_mechanism_question(cls, question: str) -> bool:
        """Return whether the normalized question explicitly asks about mechanism."""
        matched = False
        for name, pattern in cls.MECHANISM_QUESTION_PATTERNS:
            pattern_matched = pattern.search(question) is not None
            print(
                f"Mechanism regex {name!r} ({pattern.pattern!r}): "
                f"{'MATCH' if pattern_matched else 'no match'}"
            )
            matched = matched or pattern_matched
        return matched

    @classmethod
    def _is_drug_overview_question(cls, question: str) -> bool:
        """Return whether the normalized question asks about a drug's uses."""
        matched = False
        for name, pattern in cls.DRUG_OVERVIEW_QUESTION_PATTERNS:
            pattern_matched = pattern.search(question) is not None
            print(
                f"Drug overview regex {name!r} ({pattern.pattern!r}): "
                f"{'MATCH' if pattern_matched else 'no match'}"
            )
            matched = matched or pattern_matched
        return matched

    @staticmethod
    def _normalize_mechanism_question(question: str) -> str:
        """Normalize terminal artifacts, whitespace, and punctuation for matching."""
        question = re.sub(
            r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))",
            "",
            question,
        )
        normalized = []
        for character in question.casefold():
            category = unicodedata.category(character)
            if category in {"Cc", "Cf"}:
                normalized.append(" " if character.isspace() else "")
            else:
                normalized.append(character)

        normalized_question = "".join(normalized).strip()
        while normalized_question and (
            normalized_question[0].isspace()
            or unicodedata.category(normalized_question[0]).startswith("P")
        ):
            normalized_question = normalized_question[1:].lstrip()
        while normalized_question and (
            normalized_question[-1].isspace()
            or unicodedata.category(normalized_question[-1]).startswith("P")
        ):
            normalized_question = normalized_question[:-1].rstrip()
        return normalized_question

    def analyze(
        self,
        question: str
    ) -> Dict[str, Any]:

        question = question.strip()

        # CHANGED: the fast-path result (if any) is kept so a failed LLM call
        # degrades to it instead of the empty generic fallback.
        fast_result: Optional[Dict[str, Any]] = None

        def return_fallback() -> Dict[str, Any]:
            if fast_result is not None:
                final_result = self.validate_result(fast_result, question)
                self._debug_stage(
                    "FINAL VALUE RETURNED BY analyze() (fast-path fallback)",
                    final_result,
                )
                return final_result
            final_result = self.fallback(question)
            self._debug_stage(
                "FINAL VALUE RETURNED BY analyze() (fallback)",
                final_result,
            )
            return final_result

        if not question:
            return return_fallback()

        # ------------------------------------------------------------------
        # NEW: fast path. Taxonomy scoring + DrugRegistry grounding + optional
        # semantic similarity. No LLM call unless confidence is low.
        # ------------------------------------------------------------------
        fast_result, confidence = self._classify_without_llm(question)
        print(
            f"\nFast classification: type={fast_result['question_type']}, "
            f"confidence={confidence:.2f} "
            f"(LLM fallback below {self.confidence_threshold:.2f})"
        )

        if confidence >= self.confidence_threshold:
            validated_result = self.validate_result(fast_result, question)
            self._debug_stage(
                "FINAL VALUE RETURNED BY analyze() (fast path, no LLM)",
                validated_result,
            )
            return validated_result

        print("\nLow confidence; using LLM fallback.")

        # ------------------------------------------------------------------
        # Original LLM path (now only reached for low-confidence questions)
        # ------------------------------------------------------------------
        prompt = self.build_prompt(
            question
        )

        print(
            f"\nQuery Prompt Length: "
            f"{len(prompt)} chars"
        )

        try:
            http_response = requests.post(
                self._ollama_generate_url(),
                json={
                    "model": self.model_name,
                    "prompt": prompt,
                    "stream": False,
                    "options": dict(self.LLM_OPTIONS),
                },
                timeout=self.llm_timeout,
            )
            http_response.raise_for_status()
            raw_output = http_response.json().get("response", "")
        except (requests.RequestException, ValueError) as error:

            print(
                f"\nQuery Understanding Error: {error}"
            )
            return return_fallback()

        self._debug_stage("RAW OLLAMA OUTPUT", raw_output)

        response = raw_output.strip()

        try:
            parsed_result = self.extract_json(response)
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            print(
                f"\nQuery Understanding Parse Error: {error}"
            )
            return return_fallback()

        self._debug_stage("PARSED JSON", parsed_result)
        if not isinstance(parsed_result, dict):
            return return_fallback()

        self._debug_stage("OUTPUT BEFORE validate_result()", parsed_result)
        validated_result = self.validate_result(
            parsed_result,
            question
        )
        self._debug_stage("OUTPUT AFTER validate_result()", validated_result)
        self._debug_stage(
            "FINAL VALUE RETURNED BY analyze()",
            validated_result,
        )
        return validated_result

    def fallback(
        self,
        question: str
    ) -> Dict[str, Any]:

        self._debug_stage(
            "RAW OLLAMA OUTPUT",
            "<unavailable; fallback path used>",
        )
        self._debug_stage(
            "PARSED JSON",
            "<unavailable; fallback path used>",
        )
        fallback_result = {
            "intent": "GENERAL",
            "question_type": "GENERAL_RESEARCH",
            "answer_type": "GENERAL",
            "complexity": "MEDIUM",
            "entities": {},
            "retrieval_hints": [],
            "expanded_queries": [question] if question else []
        }
        self._debug_stage(
            "FALLBACK OBJECT BEFORE validate_result()",
            fallback_result,
        )
        validated_result = self.validate_result(
            fallback_result,
            question
        )
        self._debug_stage(
            "FALLBACK OBJECT AFTER validate_result()",
            validated_result,
        )
        return validated_result
