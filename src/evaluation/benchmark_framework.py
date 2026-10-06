"""Evaluate retrieval completeness, answer grounding, and concept coverage.

This module is intentionally separate from the production pipeline. It runs the
same five benchmark questions through Chroma, the current reranker, context
building, and optionally Qwen generation, then writes machine-readable metrics.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT / "src"))

from embeddings.embedder import embed_query
from generation.context_builder import build_context
from generation.generator import QwenGenerator
from retrieval.reranker import rerank_chunks
from vector_store.chroma_store import collection


RETRIEVAL_K = 50
TOP_K = 8
OUTPUT_PATH = PROJECT_ROOT / "evaluation_outputs" / "benchmark_report.json"


BENCHMARKS = [
    {
        "name": "MOA",
        "question": "What is the mechanism of action of osimertinib in EGFR-mutant NSCLC?",
        "queries": [
            "mechanism of action osimertinib EGFR-mutant NSCLC",
            "osimertinib EGFR inhibition mechanism",
            "EGFR TKI mechanism osimertinib",
        ],
        "expected_concepts": {
            "osimertinib",
            "EGFR",
            "activating EGFR mutations",
            "covalent irreversible inhibition",
            "wild-type EGFR selectivity",
            "T790M",
        },
    },
    {
        "name": "RESISTANCE",
        "question": "What resistance mechanisms emerge after first-line osimertinib?",
        "queries": [
            "resistance mechanisms after first-line osimertinib",
            "EGFR mutations osimertinib resistance",
            "MET amplification osimertinib resistance",
            "histologic transformation osimertinib",
        ],
        "expected_concepts": {
            "C797S",
            "L718Q",
            "MET amplification",
            "HER2 amplification",
            "KRAS or BRAF alterations",
            "PIK3CA alterations",
            "gene fusions",
            "histologic transformation",
        },
    },
    {
        "name": "BIOMARKER",
        "question": "Which biomarkers predict response or resistance to EGFR-targeted therapy in NSCLC?",
        "queries": [
            "biomarkers response resistance EGFR targeted therapy NSCLC",
            "EGFR mutation biomarkers osimertinib response",
            "biomarkers acquired resistance EGFR TKI",
        ],
        "expected_concepts": {
            "EGFR mutations",
            "exon 19 deletion",
            "L858R",
            "T790M",
            "C797S",
            "MET amplification",
            "PD-L1",
        },
    },
    {
        "name": "CLINICAL_TRIAL",
        "question": "What clinical trial evidence supports osimertinib for EGFR-mutant NSCLC?",
        "queries": [
            "clinical trial evidence osimertinib EGFR-mutant NSCLC",
            "osimertinib randomized trial efficacy",
            "osimertinib clinical outcomes EGFR NSCLC",
        ],
        "expected_concepts": {
            "FLAURA",
            "randomized phase III trial",
            "first-line treatment",
            "progression-free survival",
            "overall survival",
            "EGFR-mutant NSCLC",
        },
    },
    {
        "name": "SAFETY",
        "question": "What safety concerns and adverse events are associated with osimertinib?",
        "queries": [
            "safety adverse events osimertinib",
            "osimertinib toxicity clinical safety NSCLC",
            "osimertinib cardiac pulmonary adverse events",
        ],
        "expected_concepts": {
            "diarrhea",
            "rash",
            "paronychia",
            "interstitial lung disease",
            "QT prolongation",
            "cardiotoxicity",
            "left ventricular ejection fraction",
        },
    },
]


CONCEPT_PATTERNS = {
    "osimertinib": r"\bosimertinib\b",
    "EGFR": r"\begfr\b",
    "activating EGFR mutations": r"activating egfr mutations?|common activating mutations?",
    "covalent irreversible inhibition": r"covalent(?:ly)?|irreversible(?:ly)?",
    "wild-type EGFR selectivity": r"wild[- ]type egfr|selective over wild[- ]type",
    "T790M": r"\bt790m\b",
    "C797S": r"\bc797s\b",
    "L718Q": r"\bl718q\b",
    "MET amplification": r"met amplification|amplification of met",
    "HER2 amplification": r"her2 amplification|erbb2 amplification",
    "KRAS or BRAF alterations": r"kras|braf",
    "PIK3CA alterations": r"pik3ca",
    "gene fusions": r"gene fusion|alk fusion|ret fusion|nrg1 fusion",
    "histologic transformation": r"histologic transformation|histological transformation|small[- ]cell transformation|lineage plasticity",
    "EGFR mutations": r"egfr mutations?|egfr-mutant",
    "exon 19 deletion": r"exon 19 deletion|ex19del",
    "L858R": r"\bl858r\b",
    "PD-L1": r"pd[- ]l1",
    "FLAURA": r"\bflaura\b",
    "randomized phase III trial": r"randomi[sz]ed(?: phase iii)?|phase iii trial",
    "first-line treatment": r"first[- ]line",
    "progression-free survival": r"progression[- ]free survival|pfs",
    "overall survival": r"overall survival|\bmos\b",
    "EGFR-mutant NSCLC": r"egfr[- ]mutant nsclc|nsclc with egfr",
    "diarrhea": r"\bdiarrhea\b",
    "rash": r"\brash\b|acneiform dermatitis",
    "paronychia": r"\bparonychia\b",
    "interstitial lung disease": r"interstitial lung disease|pneumonitis",
    "QT prolongation": r"qt prolongation|qt interval",
    "cardiotoxicity": r"cardiotox|heart failure|arrhythmia",
    "left ventricular ejection fraction": r"left ventricular ejection fraction|lvef",
}


def _query_plan(benchmark: dict[str, Any]) -> list[str]:
    return list(dict.fromkeys([benchmark["question"], *benchmark["queries"]]))


def _retrieve_candidates(queries: list[str]) -> tuple[list[dict], dict[str, Any]]:
    merged: dict[str, dict] = {}
    raw_count = 0
    search_times = []

    for query in queries:
        started = time.perf_counter()
        embedding = embed_query(query).tolist()
        results = collection.query(
            query_embeddings=[embedding],
            n_results=RETRIEVAL_K,
        )
        search_times.append(time.perf_counter() - started)

        ids = results.get("ids", [[]])[0] if results.get("ids") else []
        documents = results.get("documents", [[]])[0] if results.get("documents") else []
        metadatas = results.get("metadatas", [[]])[0] if results.get("metadatas") else []
        raw_count += len(ids)

        for index, chunk_id in enumerate(ids):
            if not chunk_id or index >= len(documents) or not documents[index]:
                continue

            metadata = (
                metadatas[index]
                if index < len(metadatas) and isinstance(metadatas[index], dict)
                else {}
            )
            merged.setdefault(
                chunk_id,
                {
                    "chunk_id": chunk_id,
                    "text": documents[index],
                    "pmcid": metadata.get("pmcid"),
                    "section_path": metadata.get("section_path"),
                    "metadata": metadata,
                },
            )

    return list(merged.values()), {
        "search_count": len(queries),
        "raw_candidates": raw_count,
        "unique_candidates": len(merged),
        "retrieval_seconds": round(sum(search_times), 4),
        "mean_search_seconds": round(sum(search_times) / len(search_times), 4),
    }


def _extract_concepts(answer: str) -> set[str]:
    answer_text = answer.lower()
    return {
        concept
        for concept, pattern in CONCEPT_PATTERNS.items()
        if re.search(pattern, answer_text, flags=re.IGNORECASE)
    }


def _citation_metrics(answer: str, evidence_map: dict[str, dict]) -> dict[str, Any]:
    cited_ids = set(re.findall(r"\[(E\d+)\]", answer))
    valid_ids = cited_ids.intersection(evidence_map)
    invalid_ids = cited_ids.difference(evidence_map)
    evidence_count = len(evidence_map)

    return {
        "cited_evidence_ids": sorted(cited_ids),
        "valid_evidence_ids": sorted(valid_ids),
        "invalid_evidence_ids": sorted(invalid_ids),
        "citation_precision": round(
            len(valid_ids) / len(cited_ids),
            4,
        ) if cited_ids else 0.0,
        "evidence_block_coverage": round(
            len(valid_ids) / evidence_count,
            4,
        ) if evidence_count else 0.0,
    }


def _quality_metrics(
    answer: str,
    expected_concepts: set[str],
    citation_metrics: dict[str, Any],
) -> dict[str, Any]:
    extracted = _extract_concepts(answer)
    present = extracted.intersection(expected_concepts)
    missing = expected_concepts.difference(extracted)

    concept_recall = (
        len(present) / len(expected_concepts)
        if expected_concepts
        else 0.0
    )
    grounding_score = (
        0.5 * citation_metrics["citation_precision"]
        + 0.5 * citation_metrics["evidence_block_coverage"]
    )

    return {
        "extracted_concepts": sorted(extracted),
        "expected_concepts": sorted(expected_concepts),
        "matched_concepts": sorted(present),
        "missing_concepts": sorted(missing),
        "concept_recall": round(concept_recall, 4),
        "grounding_score": round(grounding_score, 4),
        "answer_quality_score": round(
            0.6 * concept_recall + 0.4 * grounding_score,
            4,
        ),
    }


def evaluate_benchmark(
    generate_answers: bool = True,
    output_path: Path = OUTPUT_PATH,
) -> dict[str, Any]:
    generator = QwenGenerator() if generate_answers else None
    report = {
        "configuration": {
            "retrieval_k": RETRIEVAL_K,
            "top_k": TOP_K,
            "answer_generation": generate_answers,
        },
        "benchmarks": [],
    }

    for benchmark in BENCHMARKS:
        question_started = time.perf_counter()
        queries = _query_plan(benchmark)
        candidates, retrieval_stats = _retrieve_candidates(queries)

        rerank_started = time.perf_counter()
        final_chunks = rerank_chunks(
            query=benchmark["question"],
            chunks=candidates,
            top_k=TOP_K,
            diversity_boost=True,
            question_type=benchmark["name"],
        )
        rerank_seconds = time.perf_counter() - rerank_started

        context_started = time.perf_counter()
        context, evidence_map = build_context(final_chunks)
        context_seconds = time.perf_counter() - context_started

        result = {
            "name": benchmark["name"],
            "question": benchmark["question"],
            "queries": queries,
            "retrieval": retrieval_stats,
            "reranking": {
                "final_chunk_count": len(final_chunks),
                "final_chunk_ids": [chunk["chunk_id"] for chunk in final_chunks],
                "rerank_seconds": round(rerank_seconds, 4),
                "evidence_types": sorted({
                    evidence_type
                    for chunk in final_chunks
                    for evidence_type in chunk.get("evidence_types", [])
                }),
            },
            "context": {
                "evidence_block_count": len(evidence_map),
                "context_characters": len(context),
                "context_seconds": round(context_seconds, 4),
            },
        }

        if generator is not None:
            generation_started = time.perf_counter()
            answer = generator.generate(
                question=benchmark["question"],
                context=context,
            )
            generation_seconds = time.perf_counter() - generation_started
            citations = _citation_metrics(answer, evidence_map)
            quality = _quality_metrics(
                answer,
                benchmark["expected_concepts"],
                citations,
            )
            result["answer"] = answer
            result["generation_seconds"] = round(generation_seconds, 4)
            result["citations"] = citations
            result["quality"] = quality
        else:
            result["answer"] = None
            result["quality"] = {
                "expected_concepts": sorted(benchmark["expected_concepts"])
            }

        result["total_seconds"] = round(
            time.perf_counter() - question_started,
            4,
        )
        report["benchmarks"].append(result)

        print(
            f"{benchmark['name']}: "
            f"unique={retrieval_stats['unique_candidates']} "
            f"final={len(final_chunks)} "
            f"total={result['total_seconds']:.2f}s"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    print(f"Saved benchmark report: {output_path}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate the five-question pharma RAG benchmark."
    )
    parser.add_argument(
        "--skip-generation",
        action="store_true",
        help="Measure retrieval and concept expectations without calling Qwen.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_PATH,
        help="Path for the JSON report.",
    )
    args = parser.parse_args()
    evaluate_benchmark(
        generate_answers=not args.skip_generation,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
