import contextlib
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

import requests

SRC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC_ROOT))

from query_understanding.query_understanding import QueryUnderstanding

TIE_QUESTIONS = [
    "What resistance mechanisms emerge after first-line osimertinib?",
    "What mechanisms drive resistance to enzalutamide in prostate cancer?",
    "What resistance alterations were found on rebiopsy after progression on first-line osimertinib in the real-world rebiopsy cohort?",
    "How do abiraterone and enzalutamide compare in efficacy and safety for metastatic prostate cancer?",
    "How do the safety profiles of enzalutamide, apalutamide and darolutamide compare?",
]

CLASSIFY_SCRIPT = """
import contextlib, io, json, sys
sys.path.insert(0, sys.argv[1])
from query_understanding.query_understanding import QueryUnderstanding
questions = json.loads(sys.argv[2])
with contextlib.redirect_stdout(io.StringIO()):
    classifier = QueryUnderstanding()
    results = [classifier._classify_without_llm(question) for question in questions]
print(json.dumps([[result["intent"], result["question_type"], confidence] for result, confidence in results]))
"""


def make_classifier():
    with contextlib.redirect_stdout(io.StringIO()):
        return QueryUnderstanding()


class HashSeedDeterminismTests(unittest.TestCase):

    def test_tied_questions_classify_identically_across_hash_seeds(self):
        outputs = set()
        for seed in range(5):
            result = subprocess.run(
                [sys.executable, "-c", CLASSIFY_SCRIPT, str(SRC_ROOT), json.dumps(TIE_QUESTIONS)],
                capture_output=True,
                text=True,
                env=dict(os.environ, PYTHONHASHSEED=str(seed)),
                check=True,
            )
            outputs.add(result.stdout.strip().splitlines()[-1])
        self.assertEqual(len(outputs), 1, outputs)


class LlmFallbackTests(unittest.TestCase):

    LOW_CONFIDENCE_QUESTION = "Did nephrotic syndrome recur after nivolumab rechallenge?"

    def test_fallback_uses_deterministic_generation_options(self):
        classifier = make_classifier()
        response = mock.Mock(status_code=200)
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "response": json.dumps({
                "intent": "EVIDENCE",
                "question_type": "SAFETY",
                "answer_type": "EVIDENCE_BASED",
                "complexity": "MEDIUM",
                "entities": {"DRUG": ["nivolumab"]},
            })
        }
        with mock.patch("query_understanding.query_understanding.requests.post", return_value=response) as post, \
                contextlib.redirect_stdout(io.StringIO()):
            result = classifier.analyze(self.LOW_CONFIDENCE_QUESTION)
        self.assertEqual(post.call_count, 1)
        self.assertTrue(post.call_args.args[0].endswith("/api/generate"))
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], classifier.model_name)
        self.assertEqual(payload["options"], {"temperature": 0, "seed": 0})
        self.assertFalse(payload["stream"])
        self.assertEqual(post.call_args.kwargs["timeout"], classifier.llm_timeout)
        self.assertEqual(result["question_type"], "SAFETY")
        self.assertIn("nivolumab", result["entities"]["DRUG"])

    def test_fallback_failure_returns_fast_path_result(self):
        classifier = make_classifier()
        with contextlib.redirect_stdout(io.StringIO()):
            expected = classifier.validate_result(
                classifier._classify_without_llm(self.LOW_CONFIDENCE_QUESTION)[0],
                self.LOW_CONFIDENCE_QUESTION,
            )
        with mock.patch(
            "query_understanding.query_understanding.requests.post",
            side_effect=requests.ConnectionError("ollama unavailable"),
        ), contextlib.redirect_stdout(io.StringIO()):
            result = classifier.analyze(self.LOW_CONFIDENCE_QUESTION)
        self.assertEqual(result, expected)

    def test_url_respects_ollama_host(self):
        with mock.patch.dict(os.environ, {"OLLAMA_HOST": "10.0.0.5:11434"}):
            self.assertEqual(QueryUnderstanding._ollama_generate_url(), "http://10.0.0.5:11434/api/generate")
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OLLAMA_HOST", None)
            self.assertEqual(QueryUnderstanding._ollama_generate_url(), "http://127.0.0.1:11434/api/generate")


if __name__ == "__main__":
    unittest.main()
