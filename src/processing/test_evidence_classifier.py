import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from processing.evidence_classifier import infer_study_design


def design(title, abstract=""):
    return infer_study_design({"title": title, "abstract": abstract, "article_type": "research-article"})


class StudyDesignTests(unittest.TestCase):

    def test_phase_iii_is_not_labeled_phase_i(self):
        self.assertEqual(design("Final analysis of the randomized phase III CheckMate 9ER trial"), "randomized_phase_III")
        self.assertEqual(design("A randomized phase 3 study"), "randomized_phase_III")
        self.assertEqual(design("OPTIM: a randomized phase II trial"), "randomized_phase_II")
        self.assertEqual(design("A randomized phase I dose-escalation study"), "randomized_phase_I")

    def test_randomized_without_phase_is_not_phase_i(self):
        self.assertEqual(design("A randomized, double-blind, placebo-controlled trial"), "randomized_trial")
        self.assertEqual(design("A randomised controlled trial"), "randomized_trial")

    def test_phase_without_randomization_is_not_randomized(self):
        self.assertEqual(design("A single-arm phase II study"), "single_arm")

    def test_reviews_of_randomized_trials_are_reviews(self):
        self.assertEqual(design("A systematic review of randomised trials"), "systematic_review")
        self.assertEqual(design("Efficacy of T-DXd: a meta-analysis of randomized trials"), "meta_analysis")

    def test_prefix_matching_is_preserved(self):
        self.assertEqual(design("Outcomes", "We retrospectively analyzed 80 patients"), "retrospective_cohort")
        self.assertEqual(design("Mechanism study", "Experiments in three cell lines"), "in_vitro")

    def test_no_cue_is_not_reported(self):
        self.assertEqual(design("Osimertinib resistance mechanisms"), "not_reported")


if __name__ == "__main__":
    unittest.main()
