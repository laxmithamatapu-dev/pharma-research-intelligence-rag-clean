import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.append(
    str(
        Path(__file__).resolve().parent / "src"
    )
)

from query_understanding.query_understanding import (
    QueryUnderstanding
)

from retrieval.retrieval_strategy import (
    StrategyManager,
    plan_for
)

from retrieval.retriever import (
    retrieve_chunks,
    retrieve_evidence
)

RETRIEVAL_MODES = ("legacy", "paper_first")

RETRIEVAL_MODE = os.environ.get("RETRIEVAL_MODE", "paper_first")

ABSTENTION_ANSWER = (
    "## Answer\n"
    "Not established in the supplied evidence. No indexed paper is relevant enough to answer this question."
)

from generation.context_builder import (
    build_context
)

from generation.generator import (
    QwenGenerator
)


def save_debug_run(
    question,
    query_info,
    strategy,
    chunks,
    evidence_map,
    answer,
    metrics,
    error=None,
    telemetry=None,
):
    debug_dir = Path(__file__).resolve().parent / "debug_runs"
    debug_dir.mkdir(parents=True, exist_ok=True)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    artifact_path = debug_dir / f"run_{run_id}.json"
    artifact = {
        "question": question,
        "retrieval_mode": RETRIEVAL_MODE,
        "query_info": query_info,
        "strategy": str(strategy),
        "chunks": [
            {
                "chunk_id": chunk.get("chunk_id"),
                "rerank_score": chunk.get("rerank_score"),
                "paper_title": chunk.get("paper_title"),
                "metadata": chunk.get("metadata", {}),
                "text": chunk.get("text", ""),
            }
            for chunk in chunks
        ],
        "evidence_map": evidence_map,
        "answer": answer,
        "error": error,
        "telemetry": telemetry or {},
        "metrics_seconds": metrics,
    }

    with artifact_path.open("w", encoding="utf-8") as artifact_file:
        json.dump(artifact, artifact_file, indent=2, ensure_ascii=False, default=str)

    return artifact_path


class Pipeline:
    """Question in, grounded answer out; shared by the CLI and the HTTP service."""

    def __init__(self, mode: str = RETRIEVAL_MODE):
        if mode not in RETRIEVAL_MODES:
            raise SystemExit(
                f"RETRIEVAL_MODE must be one of {', '.join(RETRIEVAL_MODES)}; got {mode!r}"
            )
        self.mode = mode
        self.generator = QwenGenerator()
        self.query_understanding = QueryUnderstanding()
        self.strategy_manager = StrategyManager()

    def warm_up(self):
        """Load the generation model into memory before the first question."""
        return self.generator.warm_up()

    def answer(self, question: str) -> dict:
        total_start = time.perf_counter()
        metrics = {}
        telemetry = {}
        query_info = strategy = None
        chunks, evidence_map, answer, error = [], {}, None, None
        abstained = False

        try:
            start = time.perf_counter()
            query_info = self.query_understanding.analyze(question)
            metrics["query_understanding"] = time.perf_counter() - start

            if self.mode == "paper_first":
                strategy = plan_for(query_info)
            else:
                strategy = self.strategy_manager.get_strategy(
                    {"intent": query_info.get("intent", "GENERAL")}
                )

            start = time.perf_counter()
            if self.mode == "paper_first":
                evidence = retrieve_evidence(
                    question=question,
                    query_info=query_info,
                    plan=strategy,
                )
                chunks = evidence.chunks
                abstained = evidence.abstained
                telemetry["retrieval"] = evidence.telemetry
            else:
                chunks = retrieve_chunks(
                    question=question,
                    query_info=query_info,
                    strategy=strategy,
                )
            metrics["retrieval"] = time.perf_counter() - start

            start = time.perf_counter()
            context, evidence_map = build_context(chunks=chunks)
            metrics["context_builder"] = time.perf_counter() - start

            start = time.perf_counter()
            if abstained:
                answer = ABSTENTION_ANSWER
            else:
                answer = self.generator.generate(
                    question=question,
                    context=context,
                    query_info=query_info,
                )
                telemetry["generation"] = dict(self.generator.last_stats)
            metrics["generation"] = time.perf_counter() - start
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"

        metrics["total"] = time.perf_counter() - total_start
        result = {
            "question": question,
            "answer": answer,
            "abstained": abstained,
            "error": error,
            "references": [
                {
                    "evidence_id": evidence_id,
                    "pmcid": data.get("pmcid"),
                    "chunk_id": data.get("chunk_id"),
                    "section_path": data.get("section_path"),
                    "paper_title": data.get("paper_title"),
                }
                for evidence_id, data in evidence_map.items()
            ],
            "metrics_seconds": metrics,
            "telemetry": telemetry,
            "retrieval_mode": self.mode,
        }
        try:
            result["artifact"] = str(save_debug_run(
                question=question,
                query_info=query_info,
                strategy=strategy,
                chunks=chunks,
                evidence_map=evidence_map,
                answer=answer,
                metrics=metrics,
                error=error,
                telemetry=telemetry,
            ))
        except (OSError, TypeError, ValueError) as exc:
            result["artifact_error"] = str(exc)
        return result


def main():

    pipeline = Pipeline()

    print("\n" + "=" * 80)
    print("PHARMA RESEARCH INTELLIGENCE ASSISTANT")
    print("=" * 80)
    print(f"Retrieval mode: {pipeline.mode}")

    while True:

        print(
            "\nEnter your question "
            "(type 'exit' to quit):"
        )

        question = input("> ").strip()

        if question.lower() in [
            "exit",
            "quit",
            "q"
        ]:

            print(
                "\nThank you for using "
                "Pharma Research Intelligence Assistant."
            )

            break

        if not question:

            print(
                "\nPlease enter a valid question."
            )

            continue

        result = pipeline.answer(question)

        print("\nPIPELINE METRICS")
        print("=" * 80)
        for stage, elapsed in result["metrics_seconds"].items():
            print(f"{stage.replace('_', ' ').title()}: {elapsed:.2f}s")

        if result["error"]:
            print(f"\nError: {result['error']}")
        else:
            print("\n" + "=" * 80)
            print("ANSWER")
            print("=" * 80)
            print(result["answer"])

            print("\n" + "=" * 80)
            print("REFERENCES")
            print("=" * 80)
            for reference in result["references"]:
                print(
                    f"{reference['evidence_id']}: "
                    f"{reference['chunk_id']} | "
                    f"{reference['pmcid']} | "
                    f"{reference['paper_title'] or reference['section_path']}"
                )

        if result.get("artifact"):
            print(f"\nDebug artifact: {result['artifact']}")


if __name__ == "__main__":
    main()
