import math
import re
from collections import Counter, defaultdict
from statistics import median

EVIDENCE_BLOCK_PATTERN = re.compile(r"^\[(E\d+)\]\s*$", re.MULTILINE)
CITATION_PATTERN = re.compile(r"\[(E\d+)\]", re.IGNORECASE)
STRUCTURE_HEADING_PATTERN = re.compile(r"^(##\s+[^:\n]+):", re.MULTILINE)
STRUCTURE_START = "REQUIRED ANSWER STRUCTURE"
STRUCTURE_END = "If a requested section is not established"
ABSTENTION_PHRASE = "not established in the supplied evidence"
VALIDATION_FAILURE_PREFIX = "Generated answer did not pass evidence validation"

PROPOSED_CRITERIA = {
    "level1_fact_recall": 0.8,
    "level2_aspect_coverage_final": 0.6,
    "level2_min_cited_gold_papers": 2,
}


def pmc_of(chunk_id):
    return str(chunk_id).rsplit("_", 1)[0]


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def _first_rank(ordered_ids, predicate):
    return next(
        (index + 1 for index, chunk_id in enumerate(ordered_ids) if predicate(chunk_id)),
        None,
    )


def _best_dense_rank(queries, predicate):
    ranks = [
        _first_rank(query.get("ids") or [], predicate)
        for query in queries
    ]
    ranks = [rank for rank in ranks if rank is not None]
    return min(ranks) if ranks else None


def percentile(values, fraction):
    values = sorted(value for value in values if value is not None)
    if not values:
        return None
    index = max(0, math.ceil(fraction * len(values)) - 1)
    return values[index]


def parse_context_blocks(context):
    matches = list(EVIDENCE_BLOCK_PATTERN.finditer(context or ""))
    blocks = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(context)
        lines = [line for line in context[match.end():end].splitlines() if line.strip()]
        blocks[match.group(1).upper()] = lines[-1].strip() if lines else ""
    return blocks


def expected_headings(prompt):
    if not prompt or STRUCTURE_START not in prompt:
        return []
    section = prompt.split(STRUCTURE_START, 1)[1].split(STRUCTURE_END, 1)[0]
    return [heading.strip() for heading in STRUCTURE_HEADING_PATTERN.findall(section)]


BLOCK_START_PATTERN = re.compile(r"^(?:[-*|]|\d+[.)]\s)")


def answer_units(text):
    units = []
    current = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or BLOCK_START_PATTERN.match(stripped):
            if current:
                units.append(" ".join(current))
            current = []
            if stripped.startswith("#"):
                units.append(stripped)
            elif stripped:
                current = [stripped]
            continue
        current.append(stripped)
    if current:
        units.append(" ".join(current))
    return units


def _lines_matching(text, pattern):
    return [unit for unit in answer_units(text) if pattern.search(unit)]


def _cited_ids(line):
    return {value.upper() for value in CITATION_PATTERN.findall(line)}


def _generation_outcome(record):
    generation = record.get("generation") or {}
    validations = generation.get("validations") or []
    if record.get("abstained"):
        return "abstained"
    if generation.get("skipped"):
        return "skipped"
    if generation.get("error"):
        if generation["error"].startswith(VALIDATION_FAILURE_PREFIX):
            return "fail"
        return "error"
    if not record.get("completed"):
        return "incomplete"
    if validations and not validations[0]["errors"]:
        return "pass_first"
    if validations:
        return "pass_after_prune"
    return "unknown"


def _score_retrieval(record, definition):
    level = definition["level"]
    gold_pmcs = set(definition.get("gold_pmcs", []))
    gold_chunks = {key: int(value) for key, value in definition.get("gold_chunks", {}).items()}
    answer_chunks = {chunk_id for chunk_id, grade in gold_chunks.items() if grade >= 2}
    query_info = (record.get("query_understanding") or {}).get("query_info") or {}
    fast_path = (record.get("query_understanding") or {}).get("fast_path") or {}
    strategy = (record.get("strategy") or {}).get("used") or {}
    rerank = record.get("rerank") or {}
    replay = rerank.get("replay") or {}
    queries = (record.get("retrieval") or {}).get("queries") or []
    pool_ids = [chunk["chunk_id"] for chunk in rerank.get("pool", [])]
    final_ids = [chunk["chunk_id"] for chunk in rerank.get("final", [])]
    ce_order = [chunk["chunk_id"] for chunk in replay.get("order", [])]
    pool_pmcs = {pmc_of(chunk_id) for chunk_id in pool_ids}
    final_pmcs = {pmc_of(chunk_id) for chunk_id in final_ids}
    top_k = rerank.get("top_k")
    max_per_source = replay.get("max_per_source")
    is_gold_paper = lambda chunk_id: pmc_of(chunk_id) in gold_pmcs
    is_answer_chunk = lambda chunk_id: chunk_id in answer_chunks

    ceiling = len(answer_chunks)
    if level == 1 and max_per_source:
        ceiling = min(ceiling, max_per_source)
    if top_k:
        ceiling = min(ceiling, top_k)

    fate = replay.get("fate") or {}
    answer_chunk_loss = Counter(
        fate.get(chunk_id, "unknown")
        for chunk_id in answer_chunks
        if chunk_id in pool_ids and chunk_id not in final_ids
    )
    gold_paper_positions = [index + 1 for index, chunk_id in enumerate(final_ids) if is_gold_paper(chunk_id)]
    answer_positions = [index + 1 for index, chunk_id in enumerate(final_ids) if is_answer_chunk(chunk_id)]

    result = {
        "intent": query_info.get("intent"),
        "question_type": query_info.get("question_type"),
        "fast_path_confidence": fast_path.get("confidence"),
        "llm_fallback": (record.get("query_understanding") or {}).get("llm_fallback"),
        "expanded_queries": len(query_info.get("expanded_queries") or []),
        "retrieval_k": strategy.get("retrieval_k"),
        "top_k": top_k,
        "queries_executed": len(queries),
        "pool_size": len(pool_ids),
        "final_size": len(final_ids),
        "distinct_papers_final": len(final_pmcs),
        "pool_gold_papers": len(gold_pmcs & pool_pmcs),
        "final_gold_papers": len(gold_pmcs & final_pmcs),
        "gold_papers": len(gold_pmcs),
        "dense_best_rank_gold_paper": _best_dense_rank(queries, is_gold_paper) if gold_pmcs else None,
        "dense_best_rank_answer_chunk": _best_dense_rank(queries, is_answer_chunk) if answer_chunks else None,
        "ce_rank_gold_paper": _first_rank(ce_order, is_gold_paper) if gold_pmcs else None,
        "ce_rank_answer_chunk": _first_rank(ce_order, is_answer_chunk) if answer_chunks else None,
        "final_gold_paper_positions": gold_paper_positions,
        "final_answer_chunk_positions": answer_positions,
        "gold_paper_at_1": bool(gold_paper_positions and gold_paper_positions[0] == 1) if gold_pmcs else None,
        "gold_paper_at_2": bool(gold_paper_positions and gold_paper_positions[0] <= 2) if gold_pmcs else None,
        "answer_chunk_at_2": bool(answer_positions and answer_positions[0] <= 2) if answer_chunks else None,
        "answer_chunks_labeled": len(answer_chunks),
        "pool_answer_chunk_recall": _ratio(len(answer_chunks & set(pool_ids)), len(answer_chunks)),
        "final_answer_chunk_recall": _ratio(len(answer_chunks & set(final_ids)), ceiling),
        "labeled_precision_at_final": _ratio(
            sum(1 for chunk_id in final_ids if gold_chunks.get(chunk_id, 0) >= 1),
            len(final_ids),
        ) if gold_chunks else None,
        "answer_chunks_not_in_pool": len(answer_chunks - set(pool_ids)),
        "answer_chunk_loss": dict(answer_chunk_loss),
        "replay_consistent": replay.get("consistent"),
    }

    aspects = definition.get("aspects") or []
    if aspects:
        result["aspect_coverage_pool"] = _ratio(
            sum(1 for aspect in aspects if set(aspect["gold_pmcs"]) & pool_pmcs),
            len(aspects),
        )
        result["aspect_coverage_final"] = _ratio(
            sum(1 for aspect in aspects if set(aspect["gold_pmcs"]) & final_pmcs),
            len(aspects),
        )
        result["normalized_paper_coverage"] = _ratio(
            len(gold_pmcs & final_pmcs),
            min(len(gold_pmcs), top_k or len(gold_pmcs)),
        )
    return result


def _score_context_and_answer(record, definition):
    context = record.get("context") or {}
    blocks = parse_context_blocks(context.get("text"))
    evidence_map = context.get("evidence_map") or {}
    block_chunk = {
        evidence_id: (evidence_map.get(evidence_id) or {}).get("chunk_id")
        for evidence_id in blocks
    }
    source_lengths = context.get("chunk_text_chars") or []
    truncated_blocks = sum(
        1
        for index, text in enumerate(blocks.values())
        if index < len(source_lengths) and source_lengths[index] > len(text)
    )

    answer = record.get("answer") or ""
    generation_calls = [
        call for call in record.get("ollama_calls", [])
        if call.get("stage") == "generation"
    ]
    generation_call = generation_calls[-1] if generation_calls else {}
    raw_output = generation_call.get("stdout") or ""
    gold_pmcs = set(definition.get("gold_pmcs", []))

    facts = []
    for fact in definition.get("facts", []):
        pattern = re.compile(fact["pattern"], re.IGNORECASE)
        evidence_chunks = set(fact.get("evidence_chunks", []))
        evidence_pmcs = {pmc_of(chunk_id) for chunk_id in evidence_chunks} or gold_pmcs
        answer_lines = _lines_matching(answer, pattern)
        cited_chunks = {
            block_chunk.get(evidence_id)
            for line in answer_lines
            for evidence_id in _cited_ids(line)
        } - {None}
        facts.append({
            "id": fact["id"],
            "visible_in_evidence_chunk": any(
                block_chunk.get(evidence_id) in evidence_chunks and pattern.search(text)
                for evidence_id, text in blocks.items()
            ),
            "visible_in_any_block": any(pattern.search(text) for text in blocks.values()),
            "in_raw_output": bool(pattern.search(raw_output)),
            "in_answer": bool(answer_lines),
            "grounded_chunk": bool(cited_chunks & evidence_chunks),
            "grounded_paper": bool({pmc_of(chunk_id) for chunk_id in cited_chunks} & evidence_pmcs),
        })

    cited_ids = _cited_ids(answer)
    cited_chunks = {
        (evidence_map.get(evidence_id) or {}).get("chunk_id")
        for evidence_id in cited_ids
    } - {None}
    cited_papers = {pmc_of(chunk_id) for chunk_id in cited_chunks}
    headings = expected_headings(generation_call.get("prompt"))
    answer_heading_lines = {
        line.strip().casefold()
        for line in answer.splitlines()
        if line.strip().startswith("#")
    }
    absent_terms = [term.casefold() for term in definition.get("absent_terms", [])]
    absent_claims = [
        unit for unit in answer_units(answer)
        if _cited_ids(unit) and any(term in unit.casefold() for term in absent_terms)
    ]
    matched_facts = [fact for fact in facts if fact["in_answer"]]
    raw_lines = [line for line in raw_output.splitlines() if line.strip()]
    answer_lines = [line for line in answer.splitlines() if line.strip()]
    generated = _generation_outcome(record) != "skipped"

    return {
        "context": {
            "chars": context.get("chars"),
            "blocks": len(blocks),
            "truncated_blocks": truncated_blocks,
            "facts_visible": sum(fact["visible_in_evidence_chunk"] for fact in facts),
            "facts_total": len(facts),
        },
        "answer": {
            "outcome": _generation_outcome(record),
            "validation_errors_first": (
                ((record.get("generation") or {}).get("validations") or [{}])[0].get("errors")
            ),
            "raw_nonempty_lines": len(raw_lines),
            "answer_nonempty_lines": len(answer_lines),
            "pruned_lines": max(0, len(raw_lines) - len(answer_lines)) if raw_lines else None,
            "fact_recall": _ratio(len(matched_facts), len(facts)) if generated else None,
            "raw_fact_recall": (
                _ratio(sum(fact["in_raw_output"] for fact in facts), len(facts))
                if generated
                else None
            ),
            "facts_grounded_chunk": sum(fact["grounded_chunk"] for fact in matched_facts),
            "facts_grounded_paper": sum(fact["grounded_paper"] for fact in matched_facts),
            "facts_matched": len(matched_facts),
            "cited_blocks": len(cited_ids),
            "evidence_utilization": _ratio(len(cited_ids), len(blocks)),
            "cited_papers": len(cited_papers),
            "cited_gold_papers": len(cited_papers & gold_pmcs),
            "expected_headings": headings,
            "heading_adherence": _ratio(
                sum(1 for heading in headings if heading.casefold() in answer_heading_lines),
                len(headings),
            ),
            "abstained": record.get("abstained") or ABSTENTION_PHRASE in answer.casefold(),
            "absent_entity_claims": len(absent_claims),
        },
        "facts": facts,
    }


def _score_timing(record):
    query_understanding = record.get("query_understanding") or {}
    retrieval = record.get("retrieval") or {}
    generation_calls = [
        call for call in record.get("ollama_calls", [])
        if call.get("stage") == "generation"
    ]
    generation_call = generation_calls[-1] if generation_calls else {}
    stats = generation_call.get("stats") or {}
    app_metrics = record.get("app_metrics") or {}
    return {
        "query_understanding_seconds": query_understanding.get("seconds"),
        "query_understanding_llm_seconds": sum(
            call.get("wall_seconds") or 0
            for call in record.get("ollama_calls", [])
            if call.get("stage") == "query_understanding"
        ),
        "embed_seconds": retrieval.get("embed_seconds"),
        "chroma_seconds": retrieval.get("chroma_seconds"),
        "rerank_seconds": (record.get("rerank") or {}).get("seconds"),
        "context_seconds": (record.get("context") or {}).get("seconds"),
        "generation_seconds": (record.get("generation") or {}).get("seconds"),
        "app_total_seconds": app_metrics.get("total"),
        "wall_seconds": record.get("wall_seconds"),
        "prompt_chars": generation_call.get("prompt_chars"),
        "prompt_tokens": stats.get("prompt_eval_count"),
        "answer_tokens": stats.get("eval_count"),
        "prefill_seconds": stats.get("prompt_eval_duration_seconds"),
        "prefill_tokens_per_second": stats.get("prompt_eval_rate_tokens_per_second"),
        "decode_seconds": stats.get("eval_duration_seconds"),
        "decode_tokens_per_second": stats.get("eval_rate_tokens_per_second"),
        "load_seconds": stats.get("load_duration_seconds"),
        "ollama_total_seconds": stats.get("total_duration_seconds"),
        "ollama_rss_kb": generation_call.get("ollama_rss_kb"),
        "harness_peak_rss_kb": record.get("harness_peak_rss_kb"),
    }


def _evaluate(definition, retrieval, scored):
    level = definition["level"]
    answer = scored["answer"]
    control = bool(definition.get("control"))
    if control:
        retrieval_pass = None
    elif level == 1:
        retrieval_pass = (
            retrieval["answer_chunk_at_2"]
            if retrieval["answer_chunks_labeled"]
            else retrieval["gold_paper_at_2"]
        )
    else:
        retrieval_pass = (
            (retrieval.get("aspect_coverage_final") or 0)
            >= PROPOSED_CRITERIA["level2_aspect_coverage_final"]
        )

    outcome = answer["outcome"]
    if outcome == "skipped":
        return {"retrieval_pass": retrieval_pass, "answer_pass": None, "pass": retrieval_pass}

    generation_ok = outcome in {"pass_first", "pass_after_prune", "abstained"}
    if control:
        answer_pass = outcome == "abstained" or answer["absent_entity_claims"] == 0
    elif level == 1:
        recall = answer["fact_recall"]
        answer_pass = (
            generation_ok
            and (recall is None or recall >= PROPOSED_CRITERIA["level1_fact_recall"])
            and answer["facts_grounded_paper"] == answer["facts_matched"]
        )
    else:
        answer_pass = (
            generation_ok
            and answer["cited_gold_papers"] >= PROPOSED_CRITERIA["level2_min_cited_gold_papers"]
        )
    overall = answer_pass if control else bool(retrieval_pass and answer_pass)
    return {"retrieval_pass": retrieval_pass, "answer_pass": answer_pass, "pass": overall}


def score_record(record, definition):
    retrieval = _score_retrieval(record, definition)
    scored = _score_context_and_answer(record, definition)
    return {
        "id": record["id"],
        "level": definition["level"],
        "category": definition.get("category"),
        "control": bool(definition.get("control")),
        "review_status": definition.get("review_status"),
        "repeat": record["repeat"],
        "retrieval": retrieval,
        "context": scored["context"],
        "answer": scored["answer"],
        "facts": scored["facts"],
        "timing": _score_timing(record),
        "evaluation": _evaluate(definition, retrieval, scored),
        "manual_review": None,
    }


def _summary_stats(values):
    values = [value for value in values if value is not None]
    if not values:
        return None
    return {
        "n": len(values),
        "median": median(values),
        "p90": percentile(values, 0.9),
        "min": min(values),
        "max": max(values),
    }


def score_run(records, definitions):
    definitions_by_id = {definition["id"]: definition for definition in definitions}
    scores = [
        score_record(record, definitions_by_id[record["id"]])
        for record in records
        if not record.get("warmup") and record["id"] in definitions_by_id
    ]

    by_question = defaultdict(list)
    for score in scores:
        by_question[score["id"]].append(score)

    questions = {}
    for question_id, runs in by_question.items():
        passes = [run["evaluation"]["pass"] for run in runs]
        decided = [value for value in passes if value is not None]
        questions[question_id] = {
            "level": runs[0]["level"],
            "control": runs[0]["control"],
            "runs": len(runs),
            "passes": sum(1 for value in decided if value),
            "majority_pass": (
                sum(1 for value in decided if value) >= len(runs) // 2 + 1
                if decided
                else None
            ),
            "intents": sorted({run["retrieval"]["intent"] for run in runs if run["retrieval"]["intent"]}),
            "outcomes": dict(Counter(run["answer"]["outcome"] for run in runs)),
        }

    levels = {}
    for level in sorted({score["level"] for score in scores}):
        level_scores = [score for score in scores if score["level"] == level]
        level_questions = {key: value for key, value in questions.items() if value["level"] == level}
        loss = Counter()
        for score in level_scores:
            loss.update(score["retrieval"]["answer_chunk_loss"])
            loss["not_in_pool"] += score["retrieval"]["answer_chunks_not_in_pool"]
        levels[str(level)] = {
            "questions": len(level_questions),
            "questions_majority_pass": sum(1 for value in level_questions.values() if value["majority_pass"]),
            "runs": len(level_scores),
            "outcomes": dict(Counter(score["answer"]["outcome"] for score in level_scores)),
            "answer_chunk_loss": dict(loss),
            "retrieval_pass_rate": _ratio(
                sum(1 for score in level_scores if score["evaluation"]["retrieval_pass"]),
                sum(1 for score in level_scores if score["evaluation"]["retrieval_pass"] is not None),
            ),
            "fact_recall": _summary_stats([score["answer"]["fact_recall"] for score in level_scores]),
            "aspect_coverage_final": _summary_stats(
                [score["retrieval"].get("aspect_coverage_final") for score in level_scores]
            ),
            "pool_size": _summary_stats([score["retrieval"]["pool_size"] for score in level_scores]),
            "rerank_seconds": _summary_stats([score["timing"]["rerank_seconds"] for score in level_scores]),
            "generation_seconds": _summary_stats([score["timing"]["generation_seconds"] for score in level_scores]),
            "app_total_seconds": _summary_stats([score["timing"]["app_total_seconds"] for score in level_scores]),
            "prompt_tokens": _summary_stats([score["timing"]["prompt_tokens"] for score in level_scores]),
            "answer_tokens": _summary_stats([score["timing"]["answer_tokens"] for score in level_scores]),
            "prefill_tokens_per_second": _summary_stats(
                [score["timing"]["prefill_tokens_per_second"] for score in level_scores]
            ),
            "decode_tokens_per_second": _summary_stats(
                [score["timing"]["decode_tokens_per_second"] for score in level_scores]
            ),
        }

    return {
        "criteria": PROPOSED_CRITERIA,
        "runs": scores,
        "questions": questions,
        "levels": levels,
    }
