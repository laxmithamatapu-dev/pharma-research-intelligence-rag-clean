import argparse
import contextlib
import glob
import io
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
QUESTIONS_PATH = Path(__file__).resolve().parent / "benchmark_questions.json"
METADATA_DIR = PROJECT_ROOT / "data" / "staging" / "phase1" / "metadata"
MEDCPT_CROSS_ENCODER = "ncbi/MedCPT-Cross-Encoder"
CAPS = (2, 3, 4, None)
WINDOW_WORDS = 128
WINDOW_STRIDE = 64


def prepare_imports():
    os.chdir(PROJECT_ROOT)
    for path in (PROJECT_ROOT, PROJECT_ROOT / "src"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))


def load_records(run_dir):
    return {
        json.loads(Path(path).read_text())["id"]: json.loads(Path(path).read_text())
        for path in glob.glob(f"{run_dir}/records/*.json")
    }


def load_titles():
    return {
        path.stem: json.loads(path.read_text(encoding="utf-8")).get("title") or ""
        for path in METADATA_DIR.glob("*.json")
    }


def windows(text):
    words = text.split()
    if len(words) <= WINDOW_WORDS:
        return [" ".join(words)]
    starts = range(0, max(1, len(words) - WINDOW_WORDS + WINDOW_STRIDE), WINDOW_STRIDE)
    return [" ".join(words[start:start + WINDOW_WORDS]) for start in starts]


class Scorers:

    def __init__(self, titles):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        with contextlib.redirect_stdout(io.StringIO()):
            from retrieval import reranker
        self.torch = torch
        self.reranker = reranker
        self.minilm = reranker.reranker
        self.medcpt_tokenizer = AutoTokenizer.from_pretrained(MEDCPT_CROSS_ENCODER)
        self.medcpt_model = AutoModelForSequenceClassification.from_pretrained(MEDCPT_CROSS_ENCODER)
        self.medcpt_model.eval()
        self.titles = titles
        self.seconds = Counter()
        self.pairs = Counter()

    def _medcpt(self, query, texts):
        scores = []
        with self.torch.no_grad():
            for start in range(0, len(texts), 16):
                encoded = self.medcpt_tokenizer(
                    [[query, text] for text in texts[start:start + 16]],
                    truncation=True,
                    padding=True,
                    return_tensors="pt",
                    max_length=512,
                )
                scores.extend(self.medcpt_model(**encoded).logits.squeeze(dim=1).tolist())
        return scores

    def score(self, name, query, chunks):
        started = time.perf_counter()
        if name == "minilm":
            scores = [float(value) for value in self.minilm.predict([(query, chunk["text"]) for chunk in chunks])]
            self.pairs[name] += len(chunks)
        elif name == "minilm_window":
            spans = [windows(chunk["text"]) for chunk in chunks]
            flat = [(query, span) for group in spans for span in group]
            flat_scores = [float(value) for value in self.minilm.predict(flat)]
            scores, cursor = [], 0
            for group in spans:
                scores.append(max(flat_scores[cursor:cursor + len(group)]))
                cursor += len(group)
            self.pairs[name] += len(flat)
        elif name == "medcpt":
            scores = self._medcpt(query, [chunk["text"] for chunk in chunks])
            self.pairs[name] += len(chunks)
        elif name == "medcpt_title":
            scores = self._medcpt(query, [
                f"{self.titles.get(chunk['pmcid'], '')}. {chunk['text']}" for chunk in chunks
            ])
            self.pairs[name] += len(chunks)
        else:
            raise ValueError(name)
        self.seconds[name] += time.perf_counter() - started
        return scores


def combine(scores, chunks, query, question_type, reranker, mode):
    if mode == "raw":
        return list(scores)
    resolved = reranker._resolve_question_type(query, question_type)
    low, high = min(scores), max(scores)
    span = high - low
    return [
        ((score - low) / span if span else 0.5) + reranker._question_type_bonus(chunk, resolved)
        for score, chunk in zip(scores, chunks)
    ]


def select(chunks, combined, top_k, cap):
    order = sorted(range(len(chunks)), key=lambda index: combined[index], reverse=True)
    seen, kept = set(), []
    for index in order:
        signature = chunks[index]["text"].lower().strip()[:300]
        if signature in seen:
            continue
        seen.add(signature)
        kept.append(index)
    counts, final = Counter(), []
    for index in kept:
        source = str(chunks[index]["pmcid"] or "unknown")
        if cap is not None and counts[source] >= cap:
            continue
        final.append(index)
        counts[source] += 1
        if len(final) >= top_k:
            break
    return [chunks[index] for index in final], kept


def evaluate(definition, final_chunks, build_context, parse_context_blocks):
    gold_pmcs = set(definition.get("gold_pmcs", []))
    with contextlib.redirect_stdout(io.StringIO()):
        context, evidence_map = build_context(chunks=final_chunks)
    blocks = parse_context_blocks(context)
    gold_text = [
        text for evidence_id, text in blocks.items()
        if evidence_map[evidence_id]["chunk_id"].rsplit("_", 1)[0] in gold_pmcs
    ]
    final_ids = [chunk["chunk_id"] for chunk in final_chunks]
    final_pmcs = {chunk_id.rsplit("_", 1)[0] for chunk_id in final_ids}
    answer = [chunk_id for chunk_id, grade in definition.get("gold_chunks", {}).items() if grade >= 2]
    aspects = definition.get("aspects") or []
    return {
        "final": final_ids,
        "answer_delivered": sum(1 for chunk_id in answer if chunk_id in final_ids),
        "facts_visible": sum(
            1 for fact in definition.get("facts", [])
            if any(re.search(fact["pattern"], text, re.IGNORECASE) for text in gold_text)
        ),
        "gold_paper_delivered": bool(gold_pmcs & final_pmcs),
        "gold_papers_delivered": len(gold_pmcs & final_pmcs),
        "aspect_coverage": (
            sum(1 for aspect in aspects if set(aspect["gold_pmcs"]) & final_pmcs) / len(aspects)
            if aspects else None
        ),
        "distinct_papers": len(final_pmcs),
        "context_chars": len(context),
    }


def section_bucket(path):
    from evaluation.rca_experiments import section_bucket as bucket

    return bucket(path)


def rank_percentiles(values):
    order = np.argsort(np.argsort(values))
    return order / max(1, len(values) - 1)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline passage-selection study on stored candidate pools.")
    parser.add_argument("run_dir", help="Retrieval-only run whose records provide the candidate pools.")
    args = parser.parse_args(argv)

    prepare_imports()
    with contextlib.redirect_stdout(io.StringIO()):
        from generation.context_builder import build_context
        from vector_store.chroma_store import collection
    from evaluation.scoring import parse_context_blocks

    definitions = {d["id"]: d for d in json.loads(QUESTIONS_PATH.read_text())["questions"]}
    records = load_records(args.run_dir)
    titles = load_titles()
    scorers = Scorers(titles)
    scorer_names = ("minilm", "minilm_window", "medcpt", "medcpt_title")

    pools, scores = {}, defaultdict(dict)
    for question_id, record in sorted(records.items()):
        ids = [chunk["chunk_id"] for chunk in record["rerank"]["pool"]]
        got = collection.get(ids=ids, include=["documents", "metadatas"])
        by_id = {
            chunk_id: {"chunk_id": chunk_id, "text": text, "metadata": metadata,
                       "pmcid": metadata.get("pmcid"), "section_path": metadata.get("section_path")}
            for chunk_id, text, metadata in zip(got["ids"], got["documents"], got["metadatas"])
        }
        pools[question_id] = [by_id[chunk_id] for chunk_id in ids]
        for name in scorer_names:
            scores[question_id][name] = scorers.score(name, record["question"], pools[question_id])
        print(f"[study] scored {question_id} ({len(ids)} candidates)", file=sys.stderr, flush=True)

    configs = {}
    consistency = []
    for name in scorer_names:
        for mode in ("production", "raw"):
            for cap in CAPS:
                key = f"{name}|{mode}|cap{cap or 'none'}"
                per_question = {}
                for question_id, record in records.items():
                    chunks = pools[question_id]
                    combined = combine(scores[question_id][name], chunks, record["question"],
                                       record["rerank"]["question_type"], scorers.reranker, mode)
                    final, _ = select(chunks, combined, record["rerank"]["top_k"], cap)
                    per_question[question_id] = evaluate(definitions[question_id], final, build_context, parse_context_blocks)
                    if key == "minilm|production|cap2":
                        consistency.append(
                            per_question[question_id]["final"] == [c["chunk_id"] for c in record["rerank"]["final"]]
                        )
                configs[key] = per_question

    def summarize(per_question):
        l1 = [q for q, d in definitions.items() if d["level"] == 1 and not d.get("control")]
        l2 = [q for q, d in definitions.items() if d["level"] == 2]
        return {
            "l1_answer_delivered": sum(per_question[q]["answer_delivered"] for q in l1),
            "l1_facts_visible": sum(per_question[q]["facts_visible"] for q in l1),
            "l1_gold_paper_delivered": sum(1 for q in l1 if per_question[q]["gold_paper_delivered"]),
            "l1_questions_all_facts": sum(
                1 for q in l1 if per_question[q]["facts_visible"] == len(definitions[q]["facts"])
            ),
            "l1_questions_zero_facts": sum(1 for q in l1 if per_question[q]["facts_visible"] == 0),
            "l2_gold_papers_delivered": sum(per_question[q]["gold_papers_delivered"] for q in l2),
            "l2_aspect_coverage": float(np.mean([per_question[q]["aspect_coverage"] for q in l2])),
            "l2_distinct_papers": float(np.mean([per_question[q]["distinct_papers"] for q in l2])),
            "mean_context_chars": float(np.mean([v["context_chars"] for v in per_question.values()])),
        }

    l1_ids = [q for q, d in definitions.items() if d["level"] == 1 and not d.get("control")]
    answer_total = sum(len([c for c, g in definitions[q]["gold_chunks"].items() if g >= 2]) for q in l1_ids)
    answer_pooled = sum(
        1 for q in l1_ids for c, g in definitions[q]["gold_chunks"].items()
        if g >= 2 and c in {chunk["chunk_id"] for chunk in pools[q]}
    )
    facts_total = sum(len(definitions[q]["facts"]) for q in l1_ids)
    facts_ceiling = 0
    for q in l1_ids:
        gold = set(definitions[q]["gold_pmcs"])
        texts = [" ".join(c["text"].split())[:1200] for c in pools[q] if c["pmcid"] in gold]
        facts_ceiling += sum(
            1 for fact in definitions[q]["facts"]
            if any(re.search(fact["pattern"], text, re.IGNORECASE) for text in texts)
        )

    within = []
    for q in l1_ids:
        definition = definitions[q]
        gold = definition["gold_pmcs"][0]
        answer = {c for c, g in definition["gold_chunks"].items() if g >= 2}
        indices = [i for i, c in enumerate(pools[q]) if c["pmcid"] == gold]
        if not indices:
            continue
        row = {"id": q, "paper_chunks_in_pool": len(indices), "answer_in_pool": sorted(answer & {pools[q][i]["chunk_id"] for i in indices})}
        for name in scorer_names:
            order = sorted(indices, key=lambda i: scores[q][name][i], reverse=True)
            ranked_ids = [pools[q][i]["chunk_id"] for i in order]
            row[name] = {
                "answer_rank_in_paper": min((ranked_ids.index(c) + 1 for c in answer if c in ranked_ids), default=None),
                "top_sections": [section_bucket(pools[q][i]["section_path"]) for i in order[:3]],
            }
        within.append(row)

    full_paper = []
    for q in l1_ids:
        definition = definitions[q]
        gold = definition["gold_pmcs"][0]
        answer = {c for c, g in definition["gold_chunks"].items() if g >= 2}
        got = collection.get(where={"pmcid": gold}, include=["documents", "metadatas"])
        chunks = [
            {"chunk_id": i, "text": t, "metadata": m, "pmcid": m.get("pmcid"), "section_path": m.get("section_path")}
            for i, t, m in zip(got["ids"], got["documents"], got["metadatas"])
        ]
        row = {"id": q, "paper_chunks": len(chunks)}
        for name in ("minilm", "medcpt", "minilm_window"):
            values = scorers.score(name, records[q]["question"], chunks)
            ranked = [chunks[i]["chunk_id"] for i in np.argsort(values)[::-1]]
            row[name] = min((ranked.index(c) + 1 for c in answer), default=None)
        full_paper.append(row)

    section_percentiles = {name: defaultdict(list) for name in scorer_names}
    numeric_correlation = {name: [] for name in scorer_names}
    for q, chunks in pools.items():
        if len(chunks) < 5:
            continue
        sections = [section_bucket(c["section_path"]) for c in chunks]
        density = np.array([len(re.findall(r"\d+(?:\.\d+)?", c["text"])) / max(1, len(c["text"].split())) for c in chunks])
        for name in scorer_names:
            pct = rank_percentiles(np.array(scores[q][name]))
            for section, value in zip(sections, pct):
                section_percentiles[name][section].append(float(value))
            numeric_correlation[name].append(float(np.corrcoef(rank_percentiles(density), pct)[0, 1]))

    output = {
        "run_dir": args.run_dir,
        "consistency_minilm_production_cap2": f"{sum(consistency)}/{len(consistency)}",
        "ceilings": {
            "l1_answer_chunks_total": answer_total,
            "l1_answer_chunks_in_pool": answer_pooled,
            "l1_facts_total": facts_total,
            "l1_facts_present_in_pooled_gold_text": facts_ceiling,
        },
        "summary": {key: summarize(value) for key, value in configs.items()},
        "within_paper": within,
        "full_paper_answer_rank": full_paper,
        "section_mean_percentile": {
            name: {section: float(np.mean(values)) for section, values in by_section.items()}
            for name, by_section in section_percentiles.items()
        },
        "numeric_density_rank_correlation": {name: float(np.mean(values)) for name, values in numeric_correlation.items()},
        "seconds_per_pair": {name: scorers.seconds[name] / max(1, scorers.pairs[name]) for name in scorer_names},
        "seconds_per_candidate": {
            name: scorers.seconds[name] / max(1, sum(len(p) for p in pools.values()) + (sum(r["paper_chunks"] for r in full_paper) if name != "medcpt_title" else 0))
            for name in scorer_names
        },
        "per_question": configs,
    }
    out_dir = Path(args.run_dir)
    (out_dir / "passage_selection_study.json").write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(out_dir / "passage_selection_study.json")


if __name__ == "__main__":
    main()
