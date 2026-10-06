import json
import subprocess


class QueryExpander:

    def __init__(
        self,
        model_name: str = "qwen2.5:7b"
    ):
        self.model_name = model_name

    def build_prompt(
        self,
        question: str,
        intent: dict,
        entities: dict
    ) -> str:

        return f"""
You are a query expansion system.

Your goal is to improve retrieval quality.

Given:

1. Original user question
2. Question intent
3. Extracted entities

Generate:

- Related concepts
- Alternative terminology
- Synonyms
- Supporting concepts
- Broader and narrower search topics

Requirements:

1. Do NOT answer the question.
2. Do NOT explain.
3. Do NOT generate paragraphs.
4. Return JSON only.
5. Keep concepts concise.
6. Generate concepts that improve search recall.

Output format:

{{
    "expanded_queries": [
        "...",
        "...",
        "..."
    ]
}}

Question:

{question}

Intent:

{json.dumps(intent, indent=2)}

Entities:

{json.dumps(entities, indent=2)}
"""

    def expand(
        self,
        question: str,
        intent: dict,
        entities: dict
    ) -> dict:

        prompt = self.build_prompt(
            question=question,
            intent=intent,
            entities=entities
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
                "expanded_queries": [
                    question
                ]
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
                "expanded_queries": [
                    question
                ]
            }


if __name__ == "__main__":

    expander = QueryExpander()

    question = (
        "Compare osimertinib "
        "and amivantamab."
    )

    intent = {
        "intent": "COMPARISON",
        "answer_type": "comparison",
        "complexity": "medium"
    }

    entities = {
        "entities": {
            "DRUG": [
                "osimertinib",
                "amivantamab"
            ]
        }
    }

    result = expander.expand(
        question=question,
        intent=intent,
        entities=entities
    )

    print(
        json.dumps(
            result,
            indent=4
        )
    )