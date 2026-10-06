import json
import subprocess


ENTITY_TYPES = [
    "DRUG",
    "GENE",
    "BIOMARKER",
    "DISEASE",
    "THERAPY",
    "TRIAL",
    "COMPANY",
    "DOCUMENT",
    "REGULATORY_ENTITY",
    "OTHER"
]


class EntityExtractor:

    def __init__(
        self,
        model_name: str = "qwen2.5:7b"
    ):
        self.model_name = model_name

    def build_prompt(
        self,
        question: str
    ) -> str:

        return f"""
You are an entity extraction system.

Extract all important entities from the user question.

Classify entities using ONLY the following
entity types:

{chr(10).join(ENTITY_TYPES)}

Definitions:

DRUG
    Medication, compound, molecule,
    therapeutic product.

GENE
    Gene names and genetic markers.

BIOMARKER
    Biomarkers, mutations,
    amplifications, fusions,
    variants.

DISEASE
    Diseases,
    conditions,
    disorders.

THERAPY
    Treatment approaches,
    regimens,
    interventions.

TRIAL
    Clinical studies,
    programs,
    trials.

COMPANY
    Organizations,
    companies,
    institutions.

DOCUMENT
    Reports,
    publications,
    study documents,
    submissions.

REGULATORY_ENTITY
    FDA,
    EMA,
    PMDA,
    health authorities,
    regulatory programs.

OTHER
    Important entities
    not fitting above categories.

Return JSON only.

Format:

{{
    "entities": {{
        "DRUG": [],
        "GENE": [],
        "BIOMARKER": [],
        "DISEASE": [],
        "THERAPY": [],
        "TRIAL": [],
        "COMPANY": [],
        "DOCUMENT": [],
        "REGULATORY_ENTITY": [],
        "OTHER": []
    }}
}}

Question:

{question}
"""

    def extract(
        self,
        question: str
    ) -> dict:

        prompt = self.build_prompt(
            question
        )

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

        if result.returncode != 0:

            return self.empty_response()

        response = result.stdout.strip()

        try:

            start = response.find("{")
            end = response.rfind("}")

            json_text = response[
                start:end + 1
            ]

            return json.loads(
                json_text
            )

        except Exception:

            return self.empty_response()

    def empty_response(
        self
    ) -> dict:

        return {
            "entities": {
                "DRUG": [],
                "GENE": [],
                "BIOMARKER": [],
                "DISEASE": [],
                "THERAPY": [],
                "TRIAL": [],
                "COMPANY": [],
                "DOCUMENT": [],
                "REGULATORY_ENTITY": [],
                "OTHER": []
            }
        }


if __name__ == "__main__":

    extractor = EntityExtractor()

    questions = [

        "Compare osimertinib and amivantamab.",

        "What evidence supports MARIPOSA-2?",

        "What is the role of MET amplification in NSCLC?",

        "Summarize Roche oncology strategy.",

        "Analyze Study ABC-123 findings.",

        "What is FDA guidance for companion diagnostics?"
    ]

    for question in questions:

        print("\nQUESTION:")
        print(question)

        result = extractor.extract(
            question
        )

        print("\nENTITIES:")

        print(
            json.dumps(
                result,
                indent=4
            )
        )