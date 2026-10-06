import json
import re
import subprocess
import time
from typing import Any


NON_EVIDENCE_CITATION_PATTERN = re.compile(
    r"\b(?:doi|pmid|pmcid)\b|"
    r"\b[A-Z][A-Za-z'-]+\s+et\s+al\.?|"
    r"\b[A-Z][A-Za-z'-]+(?:\s+et\s+al\.?)?\s*\(\s*\d{4}[a-z]?\s*\)|"
    r"\(\s*[A-Z][^()]{1,80},\s*\d{4}\s*\)",
    flags=re.IGNORECASE,
)


class QwenGenerator:

    FORBIDDEN_PHRASES = (
        "not directly cited",
        "while not explicitly reported",
        "it may be",
        "may suggest",
        "possibly",
        "likely",
    )

    ANSWER_SECTIONS = {
        "MECHANISM": (
            "## Molecular Target",
            "Identify the molecular target only when the evidence supports it.",
            "## Mechanism of Action",
            "Explain the supported molecular or cellular mechanism.",
            "## Biological Effect",
            "Describe downstream biological effects reported in the evidence.",
            "## Clinical Significance",
            "Explain the supported clinical relevance and note evidence limitations.",
        ),
        "CLINICAL_TRIAL": (
            "## Trial Name",
            "Name the trial when it is explicitly identified in the evidence.",
            "## Study Design",
            "Summarize phase, randomization, comparator, arms, and follow-up when reported.",
            "## Population",
            "Describe the enrolled population and relevant eligibility characteristics.",
            "## Outcomes",
            "Report the stated endpoints and results, preserving units and comparison groups.",
            "## Clinical Significance",
            "Interpret the results conservatively and include material limitations.",
        ),
        "COMPARISON": (
            "## Similarities",
            "Summarize evidence-supported similarities among the drugs or treatments asked about.",
            "## Differences",
            "Compare distinguishing properties and reported outcomes; do not imply a head-to-head "
            "comparison unless the evidence reports one.",
            "## Mechanism",
            "Compare mechanisms only where supported by the supplied evidence.",
            "## Indications",
            "Compare reported indications and populations; identify differences in evidence coverage.",
            "## Safety",
            "Compare reported safety findings without treating rates from different studies as "
            "directly comparable.",
            "## Evidence Base",
            "Describe the study types, designs, and limitations represented in the evidence.",
        ),
        "DRUG_OVERVIEW": (
            "## Drug Class",
            "State the drug class when supported by the evidence.",
            "## Mechanism",
            "Summarize the supported mechanism and target.",
            "## Major Indications",
            "List indications supported by the supplied evidence.",
            "## Key Clinical Evidence",
            "Summarize the most relevant trials or other clinical evidence, including design and "
            "reported outcomes where available.",
            "## Safety Considerations",
            "Summarize safety findings and qualify them by study population and evidence source.",
        ),
    }

    def __init__(
        self,
        model_name: str = "qwen2.5:7b"
    ):
        self.model_name = model_name

        print(
            f"\nUsing Ollama model: "
            f"{self.model_name}"
        )

    def build_prompt(
        self,
        question: str,
        context: str,
        query_info: dict[str, Any] | None = None,
    ) -> str:
        query_info = query_info or {}
        question_type = str(query_info.get("question_type", "")).strip().upper()
        intent = str(query_info.get("intent", "")).strip().upper()
        print(f"\nDEBUG GENERATOR question_type received: {question_type!r}")

        # Prefer an explicit comparison intent because query classifiers may
        # label comparison questions with a broad question_type such as "DRUG".
        if intent == "COMPARISON" or question_type in {
            "COMPARISON",
            "COMPARATIVE_EFFECTIVENESS",
        }:
            prompt_profile = "COMPARISON"
        elif question_type in {"MECHANISM", "MOA"}:
            prompt_profile = "MECHANISM"
        elif question_type in {"CLINICAL_TRIAL", "TRIAL"}:
            prompt_profile = "CLINICAL_TRIAL"
        elif question_type in {"DRUG", "DRUG_OVERVIEW", "OVERVIEW"}:
            prompt_profile = "DRUG_OVERVIEW"
        else:
            prompt_profile = ""

        print(f"DEBUG GENERATOR prompt_profile chosen: {prompt_profile!r}")

        # Keep a general answer structure for question types without a
        # specialized template, while allowing older callers to omit query_info.
        sections = self.ANSWER_SECTIONS.get(
            prompt_profile,
            (
                "## Executive Summary",
                "Answer the question directly using the most relevant supplied evidence.",
                "## Key Findings",
                "Organize findings under concise, question-relevant subheadings.",
                "## Evidence Limitations",
                "State important gaps, conflicts, or limitations in the supplied evidence.",
            ),
        )
        section_instructions = "\n".join(
            f"{sections[index]}: {sections[index + 1]}"
            for index in range(0, len(sections), 2)
        )
        query_interpretation = json.dumps(
            {
                key: query_info.get(key)
                for key in (
                    "intent",
                    "question_type",
                    "answer_type",
                    "complexity",
                    "entities",
                    "retrieval_hints",
                )
                if query_info.get(key) is not None
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )

        return f"""
You are a pharmaceutical research intelligence assistant. Answer the question
using only the available evidence. Synthesize and compare findings relevant to
the question, including mechanisms, resistance, biomarkers, clinical trials,
and safety when applicable. Consider all evidence blocks, distinguish reported
results from interpretation, and preserve conflicts and limitations. Do not
invent facts or provide patient-specific medical advice.

QUESTION INTERPRETATION
Use this query analysis to tailor the answer structure and emphasis. It is
guidance about the question, not evidence for factual claims:
{query_interpretation}

REQUIRED ANSWER STRUCTURE
Use these headings in this order and address each one:
{section_instructions}
If a requested section is not established by the supplied evidence, state:
"Not established in the supplied evidence." Do not fill gaps from memory.
For comparisons, distinguish direct head-to-head evidence from indirect
comparisons across different studies. Do not imply that unmatched populations,
endpoints, or study designs are directly comparable.

CITATION AND OUTPUT RULES
- Cite every factual sentence with one or more supplied evidence IDs.
- Use only citations in the exact form [E1] [E2], immediately after the claim.
- Do not use author/year, DOI, PMID, PMCID, footnote, or other references.
- Treat the drug, evidence type, study design, publication year, and section
  labels in each evidence block as metadata to help interpret and compare the
  associated text. Metadata is not a substitute for evidence in the text.
- Finish with ## References listing only evidence IDs used.
- Be complete but concise. Use one claim per bullet or sentence.

AVAILABLE EVIDENCE

{context}

QUESTION

{question}

ANSWER:
"""

    @staticmethod
    def _expand_evidence_ids(value: str) -> str:
        parts = re.split(r"\s*[,;]\s*", value.strip())
        expanded = []

        for part in parts:
            range_match = re.fullmatch(
                r"E(\d+)\s*-\s*E?(\d+)",
                part,
                flags=re.IGNORECASE,
            )
            if range_match:
                start, end = map(int, range_match.groups())
                if end < start or end - start > 100:
                    return value
                expanded.extend(
                    f"[E{number}]"
                    for number in range(start, end + 1)
                )
                continue

            evidence_match = re.fullmatch(
                r"E\d+",
                part,
                flags=re.IGNORECASE,
            )
            if not evidence_match:
                return value
            expanded.append(f"[{part.upper()}]")

        return " ".join(expanded)

    @classmethod
    def normalize_answer(cls, answer: str) -> str:
        """Normalize terminal artifacts and evidence citation variants."""
        cursor_edit = re.compile(
            r"([^\n]*?)\x1b\[(\d+)D\x1b\[K([^\n]*)"
        )
        while match := cursor_edit.search(answer):
            prefix, cursor_left, replacement = match.groups()
            prefix = prefix[:max(0, len(prefix) - int(cursor_left))]
            answer = (
                answer[:match.start()]
                + prefix
                + replacement
                + answer[match.end():]
            )

        answer = re.sub(
            r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))",
            "",
            answer,
        )
        answer = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", answer)

        evidence_list = r"E\d+(?:(?:\s*[,;]\s*|\s*-\s*)E?\d+)*"

        def normalize_group(match: re.Match) -> str:
            return cls._expand_evidence_ids(match.group(1))

        answer = re.sub(
            rf"\[\s*({evidence_list})\s*\]",
            normalize_group,
            answer,
            flags=re.IGNORECASE,
        )
        answer = re.sub(
            rf"\(\s*({evidence_list})\s*\)",
            normalize_group,
            answer,
            flags=re.IGNORECASE,
        )

        normalized_lines = []
        in_references = False
        for line in answer.splitlines():
            if re.match(r"^\s*##\s+References\s*$", line, re.IGNORECASE):
                in_references = True

            citation_only = re.fullmatch(
                r"\s*(?:\[E\d+\]\s*)+\s*",
                line,
                flags=re.IGNORECASE,
            )
            if citation_only and normalized_lines and not in_references:
                normalized_lines[-1] = (
                    normalized_lines[-1].rstrip()
                    + " "
                    + line.strip()
                )
            else:
                normalized_lines.append(line)

        return "\n".join(normalized_lines).strip()

    @staticmethod
    def _available_evidence_ids(context: str) -> set[str]:
        return set(
            re.findall(
                r"\[(E\d+)\]",
                context,
                flags=re.IGNORECASE,
            )
        )

    def validate_answer(
        self,
        answer: str,
        context: str,
    ) -> list[str]:
        errors = []
        available_ids = {
            evidence_id.upper()
            for evidence_id in self._available_evidence_ids(context)
        }
        cited_ids = set(
            re.findall(
                r"\[(E\d+)\]",
                answer,
                flags=re.IGNORECASE,
            )
        )
        cited_ids = {evidence_id.upper() for evidence_id in cited_ids}

        invalid_ids = cited_ids.difference(available_ids)
        if invalid_ids:
            errors.append(
                "invalid evidence IDs: "
                + ", ".join(sorted(invalid_ids))
            )

        bracketed_references = re.findall(
            r"\[([^\]]+)\]",
            answer,
        )
        invalid_reference_formats = [
            reference
            for reference in bracketed_references
            if not re.fullmatch(r"E\d+", reference.strip(), re.IGNORECASE)
        ]
        if invalid_reference_formats:
            errors.append(
                "non-evidence citation syntax: "
                + ", ".join(invalid_reference_formats[:5])
            )

        bare_evidence_ids = re.findall(
            r"(?<![A-Za-z0-9\[])E\d+(?![A-Za-z0-9\]])",
            answer,
            flags=re.IGNORECASE,
        )
        if bare_evidence_ids:
            errors.append(
                "bare evidence IDs must use [E#] format: "
                + ", ".join(sorted(set(bare_evidence_ids)))
            )

        if NON_EVIDENCE_CITATION_PATTERN.search(answer):
            errors.append("author, year, DOI, PMID, or PMCID citation detected")

        lowered_answer = answer.lower()
        for phrase in self.FORBIDDEN_PHRASES:
            if phrase in lowered_answer:
                errors.append(f"forbidden phrase detected: {phrase}")

        return list(dict.fromkeys(errors))

    def _retain_cited_claims(
        self,
        answer: str,
        context: str,
    ) -> str:
        """Keep whole lines containing evidence IDs supplied in context."""
        available_ids = {
            evidence_id.upper()
            for evidence_id in self._available_evidence_ids(context)
        }
        retained = []
        used_ids = set()
        in_references = False

        for line in answer.splitlines():
            if line.strip().casefold() == "## references":
                in_references = True
                continue
            if in_references:
                continue
            if not line.strip():
                if retained and retained[-1] != "":
                    retained.append("")
                continue
            if line.lstrip().startswith("#"):
                retained.append(line)
                continue

            citations = {
                evidence_id.upper()
                for evidence_id in re.findall(
                    r"\[(E\d+)\]",
                    line,
                    flags=re.IGNORECASE,
                )
            }
            if not citations or not citations.issubset(available_ids):
                continue

            retained.append(line)
            used_ids.update(citations)

        while retained and not retained[-1]:
            retained.pop()

        if used_ids:
            retained.extend([
                "",
                "## References",
                *[
                    f"- [{evidence_id}]"
                    for evidence_id in sorted(
                        used_ids,
                        key=lambda value: int(value[1:]),
                    )
                ],
            ])

        return "\n".join(retained).strip()

    def generate(
        self,
        question: str,
        context: str,
        query_info: dict[str, Any] | None = None,
    ) -> str:

        prompt = self.build_prompt(
            question,
            context,
            query_info,
        )

        print(
            f"\nPrompt Length: "
            f"{len(prompt)} characters"
        )

        start = time.time()

        result = subprocess.run(
            [
                "ollama",
                "run",
                self.model_name
            ],
            input=prompt,
            text=True,
            capture_output=True
        )

        print(
            f"\nOllama Call Time: "
            f"{time.time() - start:.2f} seconds"
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Ollama Error:\n"
                f"{result.stderr}"
            )

        answer = self.normalize_answer(result.stdout)
        validation_errors = self.validate_answer(answer, context)

        if validation_errors:
            answer = self._retain_cited_claims(answer, context)
            answer = self.normalize_answer(answer)
            validation_errors = self.validate_answer(answer, context)

        if validation_errors or not answer:
            raise ValueError(
                "Generated answer did not pass evidence validation: "
                + ("; ".join(validation_errors) or "no cited claims remained")
            )

        return answer