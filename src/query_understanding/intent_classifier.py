import json
import subprocess


class IntentClassifier:

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
You are a query understanding system.

Your task is to classify a user question.

Possible intents:

EXPLANATION
    User wants understanding of a concept.

COMPARISON
    User wants comparison between concepts.

ANALYSIS
    User wants insights, interpretation,
    trends or deeper reasoning.

SUMMARY
    User wants a concise overview.

PROCEDURE
    User wants process, workflow,
    methodology or operational steps.

EVIDENCE
    User wants supporting evidence,
    studies, validation or references.

DECISION_SUPPORT
    User wants recommendations,
    options, strategies or choices.

FACT_LOOKUP
    User wants factual information.

GENERAL
    Everything else.

Return ONLY valid JSON.

Format:

{{
  "intent": "...",
  "answer_type": "...",
  "complexity": "low|medium|high"
}}

Question:

{question}
"""

    def classify(
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

            return {
                "intent": "GENERAL",
                "answer_type": "general",
                "complexity": "medium"
            }

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

            return {
                "intent": "GENERAL",
                "answer_type": "general",
                "complexity": "medium"
            }


if __name__ == "__main__":

    classifier = IntentClassifier()

    questions = [

        "What is retrieval augmented generation?",

        "Compare vector search and keyword search.",

        "Provide a summary of this report.",

        "What evidence supports this claim?",

        "What strategy should we use?"
    ]

    for question in questions:

        print("\nQUESTION:")
        print(question)

        print("\nRESULT:")

        print(
            classifier.classify(
                question
            )
        )