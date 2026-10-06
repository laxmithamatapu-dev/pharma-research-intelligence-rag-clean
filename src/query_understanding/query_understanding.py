import json
import re
import subprocess
import unicodedata
from typing import Dict, List, Any

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

    @staticmethod
    def _debug_stage(stage: str, value: Any) -> None:
        print(f"\nDEBUG {stage}:")
        if isinstance(value, str):
            print(value)
        else:
            print(json.dumps(value, indent=2, ensure_ascii=False, default=str))

    def __init__(
        self,
        model_name: str = "qwen2.5:1.5b",
        registry: DrugRegistry | None = None,
    ):
        self.model_name = model_name
        self.registry = registry or DrugRegistry()

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
                queries.append(f"{drug_name} biomarker evidence")
            elif question_type == "RESISTANCE":
                queries.append(f"{drug_name} resistance evidence")

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

        def return_fallback() -> Dict[str, Any]:
            final_result = self.fallback(question)
            self._debug_stage(
                "FINAL VALUE RETURNED BY analyze() (fallback)",
                final_result,
            )
            return final_result

        if not question:
            return return_fallback()

        prompt = self.build_prompt(
            question
        )

        print(
            f"\nQuery Prompt Length: "
            f"{len(prompt)} chars"
        )

        try:
            result = subprocess.run(
                [
                    "ollama",
                    "run",
                    self.model_name
                ],
                input=prompt,
                text=True,
                capture_output=True,
                check=False
            )
        except OSError as error:
            print(
                f"\nQuery Understanding Error: {error}"
            )
            return return_fallback()

        self._debug_stage("RAW OLLAMA OUTPUT", result.stdout)
        if result.returncode != 0:

            print(
                "\nQuery Understanding Error:"
            )

            print(
                result.stderr
            )

            return return_fallback()

        response = result.stdout.strip()

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