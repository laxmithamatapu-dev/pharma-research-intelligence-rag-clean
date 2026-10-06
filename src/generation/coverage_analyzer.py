import subprocess


class CoverageAnalyzer:

    def __init__(
        self,
        model_name: str = "qwen2.5:7b"
    ):
        self.model_name = model_name

    def build_prompt(
        self,
        question: str,
        chunks
    ) -> str:

        evidence_blocks = []

        for idx, chunk in enumerate(
            chunks,
            start=1
        ):

            section = (
                chunk["metadata"].get(
                    "section_path",
                    "Unknown"
                )
            )

            text = chunk["text"]

            evidence_blocks.append(
                f"""
Chunk {idx}

Section:
{section}

Content:
{text}
"""
            )

        return f"""
You are an information extraction system.

Question:
{question}

Review ALL evidence.

Extract ALL entities relevant to answering the question.

Return ONLY lists.

Categories:

Mutations:
- ...

Amplifications:
- ...

Gene Fusions:
- ...

Biomarkers:
- ...

Pathways:
- ...

Therapies:
- ...

Clinical Findings:
- ...

Do not summarize.
Do not explain.
Do not write paragraphs.
Do not provide interpretation.

Only extract findings.

Examples of findings:

- mutations
- biomarkers
- amplifications
- gene fusions
- pathways
- therapies
- clinical outcomes
- resistance mechanisms
- transformations
- treatment strategies
- key observations

Requirements:

1. Review ALL chunks.
2. Extract every unique finding.
3. Remove duplicates.
4. Do NOT explain findings.
5. Do NOT write paragraphs.
6. Do NOT summarize documents.
7. Produce a finding inventory.
8. Focus on information relevant to the question.

Output format:

IMPORTANT FINDINGS

- finding 1
- finding 2
- finding 3

Evidence:

{"".join(evidence_blocks)}
"""

    def analyze(
        self,
        question: str,
        chunks
    ) -> dict:

        prompt = self.build_prompt(
            question=question,
            chunks=chunks
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
                "coverage_summary": ""
            }

        response = (
            result.stdout.strip()
        )

        print("\n" + "=" * 80)
        print("RAW COVERAGE RESPONSE")
        print("=" * 80)
        print(response)

        return {
            "coverage_summary": response
        }