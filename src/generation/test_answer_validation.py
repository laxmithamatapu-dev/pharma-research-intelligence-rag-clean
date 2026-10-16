import contextlib
import io
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests

from generation.context_builder import build_context
from generation.generator import QwenGenerator
from evaluation.scoring import parse_context_blocks

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


class AnswerRepairTests(unittest.TestCase):

    def setUp(self):
        self.generator = make_generator()

    def test_invented_author_attribution_is_removed_and_citation_kept(self):
        line = "- **ADA_ab Levels**: According to Huang et al. [E2], ADA_ab levels were higher with LOR."
        repaired = self.generator._strip_author_attributions(line)
        self.assertEqual(repaired, "- **ADA_ab Levels**: In [E2], ADA_ab levels were higher with LOR.")
        self.assertEqual(self.generator.validate_answer(repaired, CONTEXT), [])

    def test_other_author_forms_are_removed(self):
        self.assertEqual(
            self.generator._strip_author_attributions("The study by Huang et al. [E2] also found ERA."),
            "The study [E2] also found ERA.",
        )
        self.assertEqual(
            self.generator._strip_author_attributions("Smith et al. (2021) reported a PFS of 18.2 months [E1]."),
            "The study reported a PFS of 18.2 months [E1].",
        )

    def test_text_without_authors_is_unchanged(self):
        line = "Baseline KL-6 levels predicted liver injury [E1]."
        self.assertEqual(self.generator._strip_author_attributions(line), line)

    def test_only_offending_sentence_is_dropped(self):
        answer = "\n".join([
            "## Key Findings",
            "- Histologic transformation occurred in 4.9% of patients.",
            "- Deteriorating patients were less likely to undergo rebiopsy. Transformation included HGNEC [E1].",
            "## References",
            "[E1]",
        ])
        repaired = self.generator._drop_offending_sentences(answer, CONTEXT)
        self.assertIn("- Histologic transformation occurred in 4.9% of patients.", repaired)
        self.assertIn("- Transformation included HGNEC [E1].", repaired)
        self.assertNotIn("likely", repaired)

    def test_generate_repairs_instead_of_pruning_uncited_content(self):
        raw = "\n".join([
            "## Key Findings",
            "- Histologic transformation occurred in 4.9% of patients.",
            "- Deteriorating patients were less likely to undergo rebiopsy.",
            "- C797S was detected [E1].",
        ])
        response = mock.Mock(status_code=200, text="")
        response.json.return_value = {"message": {"content": raw}}
        with mock.patch("generation.generator.requests.post", return_value=response), \
                contextlib.redirect_stdout(io.StringIO()):
            answer = self.generator.generate("What alterations?", CONTEXT, {})
        self.assertIn("4.9% of patients", answer)
        self.assertIn("C797S was detected [E1].", answer)
        self.assertNotIn("likely", answer)


class StatisticBracketTests(unittest.TestCase):

    def setUp(self):
        self.generator = make_generator()

    def test_statistics_in_brackets_become_parentheses(self):
        answer = self.generator.normalize_answer("hsCRP fell 37.8% [95% CI, -39.7, -35.9] by week 104 [E2].")
        self.assertIn("(95% CI, -39.7, -35.9)", answer)
        self.assertEqual(self.generator.validate_answer(answer, CONTEXT), [])
        self.assertIn("(IQR 0-200)", self.generator.normalize_answer("median 66 AU/mL [IQR 0-200] [E1]"))

    def test_numeric_footnotes_are_still_rejected(self):
        answer = self.generator.normalize_answer("As reported earlier [1] [E1].")
        self.assertIn("non-evidence citation syntax: 1", self.generator.validate_answer(answer, CONTEXT))

    def test_heading_line_content_is_repaired(self):
        answer = "## Outcomes: Effects were likely durable. The PFS was 22 months [E1].\n## References\n[E1]"
        repaired = self.generator._drop_offending_sentences(answer, CONTEXT)
        self.assertIn("## Outcomes: The PFS was 22 months [E1].", repaired)
        self.assertNotIn("likely", repaired)


class OllamaInvocationTests(unittest.TestCase):

    def chat_response(self, content, status=200):
        response = mock.Mock(status_code=status, text="error body")
        response.json.return_value = {
            "message": {"role": "assistant", "content": content},
            "prompt_eval_count": 1200, "eval_count": 150, "done_reason": "stop",
        }
        return response

    def test_generation_uses_chat_api_with_deterministic_options(self):
        generator = make_generator()
        answer = "## Executive Summary\nBaseline KL-6 predicted severe liver injury. [E1]\n"
        with mock.patch("generation.generator.requests.post", return_value=self.chat_response(answer)) as post, \
                contextlib.redirect_stdout(io.StringIO()):
            result = generator.generate("Which biomarker?", CONTEXT, {})
        self.assertTrue(post.call_args.args[0].endswith("/api/chat"))
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], generator.model_name)
        self.assertEqual(payload["options"]["num_ctx"], 8192)
        self.assertEqual(payload["options"]["temperature"], 0)
        self.assertEqual(payload["options"]["seed"], 0)
        self.assertEqual(payload["options"]["num_thread"], generator.options["num_thread"])
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["messages"][0]["role"], "user")
        self.assertIn("Which biomarker?", payload["messages"][0]["content"])
        self.assertEqual(post.call_args.kwargs["timeout"], generator.timeout)
        self.assertIn("[E1]", result)
        self.assertEqual(generator.last_stats["eval_count"], 150)

    def test_generation_timeout_raises_runtime_error(self):
        generator = make_generator()
        with mock.patch("generation.generator.requests.post", side_effect=requests.Timeout("slow")), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                generator.generate("Which biomarker?", CONTEXT, {})

    def test_http_error_raises_runtime_error(self):
        generator = make_generator()
        with mock.patch("generation.generator.requests.post", return_value=self.chat_response("", status=500)), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "Ollama Error"):
                generator.generate("Which biomarker?", CONTEXT, {})


class ContextFormatTests(unittest.TestCase):

    def chunk(self, **extra):
        return {
            "chunk_id": "PMC1_0001", "text": "Finding text.",
            "metadata": {"pmcid": "PMC1", "section_path": "Results", "drug": "osimertinib",
                         "evidence_type": "clinical_trial", "study_design": "not_reported", "publication_year": 2025},
            **extra,
        }

    def test_legacy_chunks_keep_legacy_block_format(self):
        with contextlib.redirect_stdout(io.StringIO()):
            context, evidence_map = build_context(chunks=[self.chunk()])
        self.assertIn("Drug: osimertinib", context)
        self.assertIn("Evidence Type: clinical_trial", context)
        self.assertNotIn("Paper:", context)
        self.assertNotIn("paper_title", evidence_map["E1"])

    def test_paper_first_chunks_carry_paper_identity(self):
        chunk = self.chunk(paper_title="A cohort study", paper_metadata={"study_design": "retrospective_cohort", "publication_year": 2026})
        with contextlib.redirect_stdout(io.StringIO()):
            context, evidence_map = build_context(chunks=[chunk])
        self.assertIn("Paper: A cohort study", context)
        self.assertIn("Study Design: retrospective cohort | Publication Year: 2026", context)
        self.assertNotIn("Evidence Type", context)
        self.assertEqual(evidence_map["E1"]["paper_title"], "A cohort study")
        self.assertEqual(parse_context_blocks(context)["E1"], "Finding text.")


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


class UnloadTests(unittest.TestCase):

    def test_unload_waits_until_model_is_gone(self):
        with contextlib.redirect_stdout(io.StringIO()):
            generator = QwenGenerator()
        post = mock.Mock(return_value=mock.Mock(raise_for_status=mock.Mock()))
        states = iter([True, True, False])
        with mock.patch("generation.generator.requests.post", post), \
                mock.patch.object(QwenGenerator, "_is_loaded", side_effect=lambda: next(states)) as loaded, \
                mock.patch("generation.generator.time.sleep"):
            generator.unload()
        self.assertEqual(post.call_args.kwargs["json"]["keep_alive"], 0)
        self.assertEqual(loaded.call_count, 3)

    def test_unload_times_out_if_model_stays_loaded(self):
        with contextlib.redirect_stdout(io.StringIO()):
            generator = QwenGenerator()
        post = mock.Mock(return_value=mock.Mock(raise_for_status=mock.Mock()))
        with mock.patch("generation.generator.requests.post", post), \
                mock.patch.object(QwenGenerator, "_is_loaded", return_value=True), \
                mock.patch("generation.generator.time.sleep"):
            with self.assertRaises(RuntimeError):
                generator.unload(wait_seconds=0)


class KeepAliveTests(unittest.TestCase):

    def test_numeric_keep_alive_is_sent_as_integer(self):
        self.assertEqual(QwenGenerator._parse_keep_alive("-1"), -1)
        self.assertEqual(QwenGenerator._parse_keep_alive(" 300 "), 300)

    def test_duration_keep_alive_is_unchanged(self):
        self.assertEqual(QwenGenerator._parse_keep_alive("30m"), "30m")


if __name__ == "__main__":
    unittest.main()
