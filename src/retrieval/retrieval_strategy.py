from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalStrategy:
    retrieval_k: int
    top_k: int
    diversity_boost: bool
    evidence_depth: str


PLAN_SHAPES = {
    "depth": (4, 4),
    "breadth": (1, 1, 1, 1, 1, 1, 1, 1),
    "hedged": (4, 1, 1, 1, 1),
    "comparison": (2, 2, 1, 1, 1, 1),
}

SCOPE_SHAPES = {
    "single_study": "depth",
}

DEFAULT_ADAPTIVE_MARGIN = 2.0


@dataclass(frozen=True)
class RetrievalPlan:
    """Paper-first evidence budget: passages to take from each ranked paper."""

    scope: str
    shape: str
    allocation: tuple
    paper_candidates: int = 30
    passage_candidates: int = 60
    passages_considered_per_paper: int = 20
    adaptive_margin: float | None = None

    @property
    def max_passages(self) -> int:
        return sum(self.allocation)


def plan_for(
    query_info: dict | None,
    unspecified_shape: str = "adaptive",
    adaptive_margin: float | None = DEFAULT_ADAPTIVE_MARGIN,
) -> RetrievalPlan:
    scope = (query_info or {}).get("scope") or "unspecified"
    shape = SCOPE_SHAPES.get(scope, unspecified_shape)
    if shape not in PLAN_SHAPES and shape != "adaptive":
        raise ValueError(f"Unknown plan shape: {shape}")
    return RetrievalPlan(
        scope=scope,
        shape=shape,
        allocation=PLAN_SHAPES.get(shape, PLAN_SHAPES["breadth"]),
        adaptive_margin=adaptive_margin if shape == "adaptive" else None,
    )


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
