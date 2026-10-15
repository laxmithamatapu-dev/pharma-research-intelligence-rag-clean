import contextlib
import io
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from generation.generator import QwenGenerator

CONTEXT = "[E1]\n\nDrug: nivolumab\n\nKL-6 text\n\n[E2]\n\nDrug: nivolumab\n\nmore text"


def make_generator():
    with contextlib.redirect_stdout(io.StringIO()):
        return QwenGenerator()


class ForbiddenPhraseTests(unittest.TestCase):

    def setUp(self):
        self.generator = make_generator()

    def errors_for(self, text):
        return [
            error for error in self.generator.validate_answer(text, CONTEXT)
            if error.startswith("forbidden phrase")
        ]

    def test_unlikely_is_not_treated_as_likely(self):
        self.assertEqual(self.errors_for("Recurrence was unlikely in this cohort. [E1]"), [])

    def test_impossibly_is_not_treated_as_possibly(self):
        self.assertEqual(self.errors_for("An impossibly small sample was excluded. [E1]"), [])

    def test_standalone_forbidden_words_are_still_detected(self):
        self.assertEqual(
            self.errors_for("This is likely related to KL-6. [E1]"),
            ["forbidden phrase detected: likely"],
        )
        self.assertEqual(
            self.errors_for("It may be a class effect. [E2]"),
            ["forbidden phrase detected: it may be"],
        )


class PruningTests(unittest.TestCase):

    def setUp(self):
        self.generator = make_generator()

    def test_abstention_statement_survives_pruning(self):
        answer = "\n".join([
            "## Molecular Target",
            "Not established in the supplied evidence.",
            "",
            "## Clinical Significance",
            "- Not established in the supplied evidence",
            "Baseline KL-6 predicted severe liver injury. [E1]",
            "An uncited claim that must be removed.",
        ])
        pruned = self.generator._retain_cited_claims(answer, CONTEXT)
        self.assertIn("Not established in the supplied evidence.", pruned)
        self.assertIn("- Not established in the supplied evidence", pruned)
        self.assertIn("Baseline KL-6 predicted severe liver injury. [E1]", pruned)
        self.assertNotIn("uncited claim", pruned)

    def test_abstention_followed_by_claims_is_not_exempt(self):
        line = "Not established in the supplied evidence. Other biomarkers were not studied."
        pruned = self.generator._retain_cited_claims(f"## Limits\n{line}", CONTEXT)
        self.assertNotIn(line, pruned)


class OllamaInvocationTests(unittest.TestCase):

    def test_generation_disables_word_wrapping(self):
        generator = make_generator()
        completed = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="## Executive Summary\nBaseline KL-6 predicted severe liver injury. [E1]\n",
            stderr="",
        )
        with mock.patch("generation.generator.subprocess.run", return_value=completed) as run, \
                contextlib.redirect_stdout(io.StringIO()):
            generator.generate("Which biomarker?", CONTEXT, {})
        command = run.call_args.args[0]
        self.assertEqual(command[:2], ["ollama", "run"])
        self.assertIn("--nowordwrap", command)
        self.assertEqual(command[-1], generator.model_name)
        self.assertEqual(run.call_args.kwargs["timeout"], generator.timeout)

    def test_generation_timeout_raises_runtime_error(self):
        generator = make_generator()
        with mock.patch(
            "generation.generator.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="ollama", timeout=generator.timeout),
        ), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                generator.generate("Which biomarker?", CONTEXT, {})


class IndexPathTests(unittest.TestCase):

    def test_chroma_path_is_absolute_and_independent_of_working_directory(self):
        result = subprocess.run(
            [
                sys.executable, "-c",
                "import sys; sys.path.insert(0, sys.argv[1]); "
                "from vector_store.chroma_store import CHROMA_PATH, collection; "
                "print(CHROMA_PATH); print(collection.count())",
                str(Path(__file__).resolve().parents[1]),
            ],
            capture_output=True,
            text=True,
            cwd="/tmp",
            check=True,
        )
        path, count = result.stdout.strip().splitlines()[-2:]
        expected = Path(__file__).resolve().parents[2] / "data" / "chromadb"
        self.assertEqual(Path(path), expected)
        self.assertGreater(int(count), 0)


if __name__ == "__main__":
    unittest.main()
