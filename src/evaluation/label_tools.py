import argparse
import json
import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QUESTIONS_PATH = Path(__file__).resolve().parent / "benchmark_questions.json"
CONTEXT_TRUNCATION_CHARS = 1200
VALID_LEVELS = {1, 2}
VALID_STATUSES = {"draft", "verified"}


def _collection():
    os.chdir(PROJECT_ROOT)
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    from vector_store.chroma_store import collection

    return collection


def _collapse(text):
    return " ".join((text or "").split())


def _chunks_for_paper(collection, pmcid):
    result = collection.get(where={"pmcid": pmcid}, include=["documents", "metadatas"])
    rows = sorted(
        zip(result["ids"], result["documents"], result["metadatas"]),
        key=lambda row: row[0],
    )
    return rows


def _documents_by_id(collection, chunk_ids):
    if not chunk_ids:
        return {}
    result = collection.get(ids=list(chunk_ids), include=["documents"])
    return dict(zip(result["ids"], result["documents"]))


def command_list(args):
    collection = _collection()
    rows = _chunks_for_paper(collection, args.pmcid)
    if not rows:
        print(f"No indexed chunks for {args.pmcid}")
        return 1
    for chunk_id, document, metadata in rows:
        text = _collapse(document)
        print(
            f"{chunk_id} | {len(text.split()):>3} w | {len(text):>4} ch | "
            f"{metadata.get('section_category', '')} | {metadata.get('section_path', '')}"
        )
    return 0


def command_show(args):
    collection = _collection()
    documents = _documents_by_id(collection, args.chunk_ids)
    for chunk_id in args.chunk_ids:
        if chunk_id not in documents:
            print(f"===== {chunk_id}: not found")
            continue
        text = _collapse(documents[chunk_id])
        print(f"===== {chunk_id} ({len(text)} chars; Qwen sees first {CONTEXT_TRUNCATION_CHARS})")
        print(text[:CONTEXT_TRUNCATION_CHARS])
        if len(text) > CONTEXT_TRUNCATION_CHARS:
            print(f"----- [cut at {CONTEXT_TRUNCATION_CHARS}; not visible to Qwen] -----")
            print(text[CONTEXT_TRUNCATION_CHARS:])
    return 0


def command_find(args):
    collection = _collection()
    pattern = re.compile(args.pattern, re.IGNORECASE)
    found = False
    for chunk_id, document, metadata in _chunks_for_paper(collection, args.pmcid):
        text = _collapse(document)
        for match in pattern.finditer(text):
            found = True
            visible = "visible" if match.start() < CONTEXT_TRUNCATION_CHARS else "CUT"
            start = max(0, match.start() - 60)
            snippet = text[start:match.end() + 60]
            print(f"{chunk_id} @ {match.start():>4} [{visible}] {metadata.get('section_path', '')}")
            print(f"    …{snippet}…")
    if not found:
        print("No matches.")
    return 0


def command_validate(args):
    collection = _collection()
    payload = json.loads(args.questions.read_text(encoding="utf-8"))
    questions = payload.get("questions", [])
    errors = []
    warnings = []
    seen_ids = set()

    all_chunk_ids = {
        chunk_id
        for question in questions
        for chunk_id in (
            list(question.get("gold_chunks", {}))
            + [chunk for fact in question.get("facts", []) for chunk in fact.get("evidence_chunks", [])]
        )
    }
    documents = _documents_by_id(collection, all_chunk_ids)

    for question in questions:
        question_id = question.get("id", "<missing id>")
        prefix = f"{question_id}:"
        if question_id in seen_ids:
            errors.append(f"{prefix} duplicate id")
        seen_ids.add(question_id)
        if question.get("level") not in VALID_LEVELS:
            errors.append(f"{prefix} level must be 1 or 2")
        if question.get("review_status") not in VALID_STATUSES:
            errors.append(f"{prefix} review_status must be draft or verified")
        if not question.get("question"):
            errors.append(f"{prefix} empty question")

        gold_pmcs = set(question.get("gold_pmcs", []))
        for pmcid in sorted(gold_pmcs):
            if not collection.get(where={"pmcid": pmcid}, limit=1)["ids"]:
                errors.append(f"{prefix} gold paper {pmcid} not indexed")

        for chunk_id, grade in question.get("gold_chunks", {}).items():
            if chunk_id not in documents:
                errors.append(f"{prefix} gold chunk {chunk_id} not indexed")
            if grade not in (0, 1, 2):
                errors.append(f"{prefix} gold chunk {chunk_id} grade must be 0, 1 or 2")
            if chunk_id.rsplit("_", 1)[0] not in gold_pmcs:
                errors.append(f"{prefix} gold chunk {chunk_id} is not from a gold paper")

        for fact in question.get("facts", []):
            fact_prefix = f"{prefix} fact {fact.get('id')}:"
            try:
                pattern = re.compile(fact["pattern"], re.IGNORECASE)
            except (KeyError, re.error) as exc:
                errors.append(f"{fact_prefix} invalid pattern ({exc})")
                continue
            evidence = fact.get("evidence_chunks", [])
            if not evidence:
                warnings.append(f"{fact_prefix} no evidence_chunks")
            matches = []
            for chunk_id in evidence:
                if chunk_id not in question.get("gold_chunks", {}):
                    errors.append(f"{fact_prefix} evidence chunk {chunk_id} missing from gold_chunks")
                match = pattern.search(_collapse(documents.get(chunk_id, "")))
                if match:
                    matches.append((chunk_id, match.start()))
            if evidence and not matches:
                errors.append(f"{fact_prefix} pattern matches none of its evidence chunks")
            elif matches and all(offset >= CONTEXT_TRUNCATION_CHARS for _, offset in matches):
                warnings.append(
                    f"{fact_prefix} only beyond char {CONTEXT_TRUNCATION_CHARS} in "
                    + ", ".join(f"{chunk_id}@{offset}" for chunk_id, offset in matches)
                )

        for aspect in question.get("aspects", []):
            missing = set(aspect.get("gold_pmcs", [])) - gold_pmcs
            if missing:
                errors.append(f"{prefix} aspect {aspect.get('id')} uses non-gold papers {sorted(missing)}")

        if question.get("control") and (gold_pmcs or question.get("gold_chunks")):
            errors.append(f"{prefix} control question must not have gold evidence")
        if question.get("control") and not question.get("absent_terms"):
            warnings.append(f"{prefix} control question has no absent_terms")
        if not question.get("control") and not gold_pmcs:
            errors.append(f"{prefix} no gold_pmcs")
        if question.get("level") == 1 and not question.get("control") and not question.get("gold_chunks"):
            warnings.append(f"{prefix} no gold_chunks labeled")
        if question.get("level") == 2 and not question.get("aspects"):
            warnings.append(f"{prefix} no aspects defined")

    for message in errors:
        print(f"ERROR   {message}")
    for message in warnings:
        print(f"WARNING {message}")
    statuses = {}
    for question in questions:
        statuses[question.get("review_status")] = statuses.get(question.get("review_status"), 0) + 1
    print(
        f"\n{len(questions)} questions; status {statuses}; "
        f"{len(errors)} errors; {len(warnings)} warnings"
    )
    return 1 if errors else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Gold-labeling utilities for benchmark questions.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List indexed chunks of a paper.")
    list_parser.add_argument("pmcid")
    list_parser.set_defaults(handler=command_list)

    show_parser = subparsers.add_parser("show", help="Show chunk text and the truncation point.")
    show_parser.add_argument("chunk_ids", nargs="+")
    show_parser.set_defaults(handler=command_show)

    find_parser = subparsers.add_parser("find", help="Find a regex in a paper's chunks.")
    find_parser.add_argument("pmcid")
    find_parser.add_argument("pattern")
    find_parser.set_defaults(handler=command_find)

    validate_parser = subparsers.add_parser("validate", help="Validate the question definitions file.")
    validate_parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS_PATH)
    validate_parser.set_defaults(handler=command_validate)

    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
