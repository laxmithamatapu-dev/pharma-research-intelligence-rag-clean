from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalStrategy:
    retrieval_k: int
    top_k: int
    diversity_boost: bool
    evidence_depth: str


class StrategyManager:
    """Return the retrieval settings tuned to the inferred intent."""

    def __init__(self):
        self.default_strategy = RetrievalStrategy(
            retrieval_k=30,
            top_k=5,
            diversity_boost=False,
            evidence_depth="medium",
        )

        self.intent_map = {
            "COMPARISON": RetrievalStrategy(
                retrieval_k=60,
                top_k=8,
                diversity_boost=True,
                evidence_depth="high",
            ),
            "ANALYSIS": RetrievalStrategy(
                retrieval_k=50,
                top_k=8,
                diversity_boost=True,
                evidence_depth="high",
            ),
            "EVIDENCE": RetrievalStrategy(
                retrieval_k=50,
                top_k=6,
                diversity_boost=True,
                evidence_depth="high",
            ),
            "SUMMARY": RetrievalStrategy(
                retrieval_k=40,
                top_k=6,
                diversity_boost=True,
                evidence_depth="medium",
            ),
            "PROCEDURE": RetrievalStrategy(
                retrieval_k=30,
                top_k=5,
                diversity_boost=False,
                evidence_depth="focused",
            ),
            "DECISION_SUPPORT": RetrievalStrategy(
                retrieval_k=50,
                top_k=8,
                diversity_boost=True,
                evidence_depth="high",
            ),
            "EXPLANATION": RetrievalStrategy(
                retrieval_k=30,
                top_k=5,
                diversity_boost=False,
                evidence_depth="focused",
            ),
            "FACT_LOOKUP": RetrievalStrategy(
                retrieval_k=20,
                top_k=3,
                diversity_boost=False,
                evidence_depth="minimal",
            ),
        }

    @staticmethod
    def _normalize_intent(intent_value) -> str:
        if isinstance(intent_value, str):
            return intent_value.strip().upper()
        return "GENERAL"

    def get_strategy(self, intent_info: dict | str | None) -> RetrievalStrategy:
        if isinstance(intent_info, str):
            intent = self._normalize_intent(intent_info)
        elif isinstance(intent_info, dict):
            intent = self._normalize_intent(intent_info.get("intent", "GENERAL"))
        else:
            intent = "GENERAL"

        return self.intent_map.get(intent, self.default_strategy)


if __name__ == "__main__":
    manager = StrategyManager()
    test_intents = [
        {"intent": "COMPARISON"},
        {"intent": "analysis"},
        {"intent": "EVIDENCE"},
        {"intent": "summary"},
        {"intent": "FACT_LOOKUP"},
        {"intent": "GENERAL"},
    ]

    for intent in test_intents:
        strategy = manager.get_strategy(intent)
        print("\nIntent:")
        print(intent)
        print("\nStrategy:")
        print(strategy)
