import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

SRC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC_ROOT))

from query_understanding.query_understanding import QueryUnderstanding
from retrieval.retrieval_strategy import PLAN_SHAPES, plan_for

with contextlib.redirect_stdout(io.StringIO()):
    from retrieval import reranker


class ScopeRuleTests(unittest.TestCase):

    def scope(self, question, intent="FACT_LOOKUP", question_type="GENERAL_RESEARCH"):
        return QueryUnderstanding._detect_scope(question, intent, question_type)

    def test_definite_study_references_are_single_study(self):
        for question in (
            "In the real-world cohort of patients who discontinued treatment, what were the reasons?",
            "How quickly did semaglutide lower hsCRP in the SELECT trial?",
            "What alterations were found in the lung adenocarcinoma patient who developed resistance?",
            "How long was treatment given in the case report?",
        ):
            self.assertEqual(self.scope(question), "single_study", question)

    def test_trial_identifiers_are_single_study(self):
        self.assertEqual(self.scope("In Japanese participants of KEYNOTE-671, what happened?"), "single_study")
        self.assertEqual(self.scope("What did the final analysis of CheckMate 9ER report?"), "single_study")
        self.assertEqual(self.scope("Results of NCT01234567?"), "single_study")

    def test_gene_and_receptor_names_are_not_trial_identifiers(self):
        for question in (
            "How does HER2-targeted therapy work?",
            "What is the role of PD-1 blockade?",
            "Does GLP-1 agonism reduce weight?",
        ):
            self.assertEqual(self.scope(question), "unspecified", question)

    def test_comparison_without_study_reference(self):
        self.assertEqual(
            self.scope("How do abiraterone and enzalutamide compare?", intent="COMPARISON"),
            "comparison",
        )

    def test_study_reference_takes_precedence_over_comparison(self):
        self.assertEqual(
            self.scope("In the final analysis of CheckMate 9ER, how did arms compare?", intent="COMPARISON"),
            "single_study",
        )

    def test_general_synthesis_questions_are_unspecified(self):
        self.assertEqual(self.scope("What mechanisms drive resistance to enzalutamide in prostate cancer?"), "unspecified")


class PlanTests(unittest.TestCase):

    def test_scope_selects_shape(self):
        self.assertEqual(plan_for({"scope": "single_study"}).allocation, PLAN_SHAPES["depth"])
        self.assertEqual(plan_for({"scope": "comparison"}).shape, "adaptive")
        self.assertEqual(plan_for({"scope": "unspecified"}).shape, "adaptive")
        self.assertEqual(plan_for({"scope": "unspecified"}).adaptive_margin, 2.0)
        self.assertEqual(plan_for({"scope": "unspecified"}, unspecified_shape="breadth").allocation, PLAN_SHAPES["breadth"])

    def test_adaptive_plan_carries_margin(self):
        plan = plan_for({"scope": "unspecified"}, unspecified_shape="adaptive", adaptive_margin=1.5)
        self.assertEqual(plan.shape, "adaptive")
        self.assertEqual(plan.adaptive_margin, 1.5)
        self.assertIsNone(plan_for({"scope": "single_study"}, unspecified_shape="adaptive", adaptive_margin=1.5).adaptive_margin)

    def test_unknown_shape_is_rejected(self):
        with self.assertRaises(ValueError):
            plan_for({"scope": "unspecified"}, unspecified_shape="wide")


class PassageSelectionTests(unittest.TestCase):

    def passages(self, pmcid, count):
        return [
            {"chunk_id": f"{pmcid}_{index:04d}", "pmcid": pmcid, "text": f"{pmcid} passage {index} text",
             "metadata": {"pmcid": pmcid, "section_path": "Results"}}
            for index in range(1, count + 1)
        ]

    def test_quota_per_paper_and_paper_order(self):
        papers = [("PMC1", self.passages("PMC1", 5), 3), ("PMC2", self.passages("PMC2", 4), 1)]
        scores = {f"PMC1 passage {i} text": float(i) for i in range(1, 6)}
        scores.update({f"PMC2 passage {i} text": 10.0 + i for i in range(1, 5)})
        with mock.patch.object(reranker.reranker, "predict", side_effect=lambda pairs: [scores[text] for _, text in pairs]):
            selected = reranker.select_passages_by_paper("question", papers)
        self.assertEqual([p["chunk_id"] for p in selected], ["PMC1_0005", "PMC1_0004", "PMC1_0003", "PMC2_0004"])
        self.assertEqual([p["paper_rank"] for p in selected], [1, 1, 1, 2])
        self.assertEqual([p["rank_in_paper"] for p in selected], [1, 2, 3, 1])

    def test_duplicate_text_is_removed(self):
        duplicate = self.passages("PMC1", 2)
        duplicate[1]["text"] = duplicate[0]["text"]
        with mock.patch.object(reranker.reranker, "predict", side_effect=lambda pairs: [1.0 for _ in pairs]):
            selected = reranker.select_passages_by_paper("question", [("PMC1", duplicate, 2)])
        self.assertEqual(len(selected), 1)

    def test_no_candidates_returns_empty(self):
        self.assertEqual(reranker.select_passages_by_paper("question", [("PMC1", [], 3)]), [])


if __name__ == "__main__":
    unittest.main()
