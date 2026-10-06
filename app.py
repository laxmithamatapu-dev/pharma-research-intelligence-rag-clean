import json
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
    StrategyManager
)

from retrieval.retriever import (
    retrieve_chunks
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
):
    debug_dir = Path(__file__).resolve().parent / "debug_runs"
    debug_dir.mkdir(parents=True, exist_ok=True)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    artifact_path = debug_dir / f"run_{run_id}.json"
    artifact = {
        "question": question,
        "query_info": query_info,
        "strategy": str(strategy),
        "chunks": [
            {
                "chunk_id": chunk.get("chunk_id"),
                "rerank_score": chunk.get("rerank_score"),
                "metadata": chunk.get("metadata", {}),
                "text": chunk.get("text", ""),
            }
            for chunk in chunks
        ],
        "evidence_map": evidence_map,
        "answer": answer,
        "metrics_seconds": metrics,
    }

    with artifact_path.open("w", encoding="utf-8") as artifact_file:
        json.dump(artifact, artifact_file, indent=2, ensure_ascii=False, default=str)

    return artifact_path


def main():

    print("\n" + "=" * 80)
    print("PHARMA RESEARCH INTELLIGENCE ASSISTANT")
    print("=" * 80)

    generator = QwenGenerator()

    query_understanding = (
        QueryUnderstanding()
    )

    strategy_manager = (
        StrategyManager()
    )

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
        try:

            total_start = time.perf_counter()
            metrics = {}

            # ==========================
            # QUERY UNDERSTANDING
            # ==========================

            print("\nUnderstanding question...")

            start = time.perf_counter()

            query_info = (
                query_understanding.analyze(
                    question
                )
            )
            print("\nDEBUG APP query_info:")
            print(query_info)

            metrics["query_understanding"] = time.perf_counter() - start

            print("\n" + "=" * 80)
            print("QUERY UNDERSTANDING")
            print("=" * 80)

            print(
                json.dumps(
                    query_info,
                    indent=4
                )
            )

            intent_info = {
                "intent":
                    query_info.get(
                        "intent",
                        "GENERAL"
                    )
            }

            expanded_queries = (
                query_info.get(
                    "expanded_queries",
                    []
                )
            )

            strategy = (
                strategy_manager.get_strategy(
                    intent_info
                )
            )

            print("\n" + "=" * 80)
            print("RETRIEVAL STRATEGY")
            print("=" * 80)

            print(strategy)

            # ==========================
            # RETRIEVAL
            # ==========================

            print("\nRetrieving evidence...")

            start = time.perf_counter()

            chunks = retrieve_chunks(
                question=question,
                query_info=query_info,
                strategy=strategy,
            )
            metrics["retrieval"] = time.perf_counter() - start

            print("\n" + "=" * 80)
            print("FINAL CHUNKS SENT TO QWEN")
            print("=" * 80)

            for i, chunk in enumerate(
                chunks,
                start=1
            ):
                metadata = chunk.get("metadata", {}) or {}

                print(
                    f"{i}. "
                    f"{chunk['chunk_id']} | "
                    f"Score={chunk.get('rerank_score', 0.0):.4f} | "
                    f"{metadata.get('section_path', '')}"
                )

            print("\nTOP CHUNK PREVIEW")
            for i, chunk in enumerate(chunks[:5], start=1):
                print("-" * 80)
                print(chunk.get("chunk_id", "Unknown chunk"))
                print((chunk.get("text", "") or "")[:500])

            print(
                f"\nRetrieved "
                f"{len(chunks)} chunks"
            )

            # ==========================
            # CONTEXT BUILDING
            # ==========================

            start = time.perf_counter()

            context, evidence_map = (
                build_context(
                    chunks=chunks
                )
            )

            metrics["context_builder"] = time.perf_counter() - start

            print(
                f"\nContext Length: "
                f"{len(context)} characters"
            )

            # ==========================
            # GENERATION
            # ==========================

            print("\nGenerating answer...")

            start = time.perf_counter()

            answer = (
                generator.generate(
                    question=question,
                    context=context,
                    query_info=query_info,
                )
            )

            metrics["generation"] = time.perf_counter() - start

            # ==========================
            # TOTAL TIME
            # ==========================

            metrics["total"] = time.perf_counter() - total_start
            print("\nPIPELINE METRICS")
            print("=" * 80)
            for stage, elapsed in metrics.items():
                print(f"{stage.replace('_', ' ').title()}: {elapsed:.2f}s")

            print("\n" + "=" * 80)
            print("ANSWER")
            print("=" * 80)

            print(answer)

            print("\n" + "=" * 80)
            print("REFERENCES")
            print("=" * 80)

            for (
                evidence_id,
                data
            ) in evidence_map.items():

                print(
                    f"{evidence_id}: "
                    f"{data['chunk_id']} | "
                    f"{data['pmcid']} | "
                    f"{data['section_path']}"
                )

            try:
                artifact_path = save_debug_run(
                    question=question,
                    query_info=query_info,
                    strategy=strategy,
                    chunks=chunks,
                    evidence_map=evidence_map,
                    answer=answer,
                    metrics=metrics,
                )
                print(f"\nDebug artifact: {artifact_path}")
            except (OSError, TypeError, ValueError) as exc:
                print(f"\nUnable to save debug artifact: {exc}")

        except Exception as exc:

            print(
                f"\nError: {str(exc)}"
            )
if __name__ == "__main__":
    main()