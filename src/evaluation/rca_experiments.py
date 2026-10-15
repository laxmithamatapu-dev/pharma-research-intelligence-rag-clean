import argparse
import contextlib
import glob
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
QUESTIONS_PATH = Path(__file__).resolve().parent / "benchmark_questions.json"
STAGING_DIR = PROJECT_ROOT / "data" / "staging" / "phase1"
K_GRID = (20, 30, 60, 100, 200, 500)
CAPTION_PATTERN = re.compile(r"\b(?:FIGURE|Figure|Fig\.|TABLE|Table)\s*\d")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")

QUERY_VARIANTS = {
    "L1-01": {
        "entity": "trastuzumab deruxtecan permanent discontinuation reasons metastatic breast cancer real-world cohort",
        "oracle": "the primary reason for T-DXd discontinuation was progressive disease (82.8%); other reasons included adverse events (14.0%)",
    },
    "L1-02": {
        "entity": "baseline serum biomarker severe immune-related liver injury nivolumab ipilimumab cutoff",
        "oracle": "baseline serum KL-6 ROC curve AUC 0.755; optimal cutoff 418 U/mL by Youden index predicting severe irAE liver injury",
    },
    "L1-03": {
        "entity": "first-line afatinib versus osimertinib EGFR-mutant NSCLC response rate progression-free survival overall survival 3-year follow-up",
        "oracle": "objective response rates were 66.0% with osimertinib and 60.5% with afatinib; median PFS 18.2 vs 13.5 months; median OS 37.0 vs 40.5 months",
    },
    "L1-04": {
        "entity": "semaglutide 2.4 mg ad libitum energy intake placebo weeks 20 40 60",
        "oracle": "semaglutide-treated participants reduced ad libitum energy intake at lunch by 367 kcal, 317 kcal and 200 kcal at weeks 20, 40 and 60 relative to placebo",
    },
    "L1-06": {
        "entity": "EGFR adjusted variant allele frequency progression-free survival first-line osimertinib",
        "oracle": "aVAF < 50% was not associated with PFS (HR 1.13); aVAF > 100% was not associated with PFS (HR 0.60)",
    },
    "L1-07": {
        "entity": "myeloperoxidase osimertinib-induced cardiotoxicity molecular mechanism",
        "oracle": "osimertinib increased myocardial MPO expression and reduced AMPK/PI3K/Akt/eNOS phosphorylation; an MPO inhibitor partially reversed this effect",
    },
    "L1-09": {
        "entity": "SPEN alterations biomarker androgen receptor pathway inhibitor resistance metastatic prostate cancer",
        "oracle": "SPEN-mutated mCRPC had shorter time to next treatment (HR 2.57) and shorter overall survival in the MSK-IMPACT cohort (25.4 vs 64.7 months)",
    },
    "L1-10": {
        "entity": "acquired EML4-ALK fusion BRAF V600G after osimertinib lung adenocarcinoma treatment",
        "oracle": "ALK immunohistochemistry confirmed the acquired ALK rearrangement; PD-L1 tumor proportion score was 40%",
    },
    "L1-11": {
        "entity": "osimertinib duration before squamous transformation EGFR-mutant lung adenocarcinoma case report",
        "oracle": "osimertinib was discontinued after squamous transformation; about 39 months to first progression and 52 months of total osimertinib treatment",
    },
    "L1-13": {
        "entity": "Yifeixiaoji decoction osimertinib randomized trial primary outcome sample size",
        "oracle": "sample size was calculated on the primary outcome progression-free survival with target hazard ratio 0.66, requiring about 176 PFS events, based on FLAURA median PFS 18.9 months",
    },
    "L1-14": {
        "entity": "CheckMate 9ER final analysis nivolumab cabozantinib sunitinib objective response rate duration of response",
        "oracle": "ORR was 55.7% with NIVO+CABO versus 27.4% with SUN; median duration of response 22.0 versus 15.2 months",
    },
    "L1-15": {
        "entity": "KEYNOTE-671 Japanese participants perioperative pembrolizumab nodal downstaging residual viable tumor",
        "oracle": "nodal downstaging in 39% of the pembrolizumab arm and 21% of the placebo arm; median residual viable tumor 33% versus 52%",
    },
}


def section_bucket(path):
    head = re.sub(r"^[\d.\s]+", "", (path or "").split(">")[0].strip().lower())
    for key, name in (
        ("introduction", "introduction"), ("background", "introduction"),
        ("discussion", "discussion"), ("conclusion", "discussion"),
        ("result", "results"), ("method", "methods"), ("material", "methods"),
        ("case", "case"),
    ):
        if head.startswith(key) or key in head[:25]:
            return name
    return "other"


def collapse(text):
    return " ".join((text or "").split())


class Corpus:

    def __init__(self, collection, embedder):
        everything = collection.get(include=["embeddings", "documents", "metadatas"])
        self.ids = everything["ids"]
        self.documents = everything["documents"]
        self.metadatas = everything["metadatas"]
        self.matrix = np.asarray(everything["embeddings"], dtype="float32")
        self.index = {chunk_id: position for position, chunk_id in enumerate(self.ids)}
        self.embedder = embedder
        self._query_cache = {}

    def query_vector(self, text):
        if text not in self._query_cache:
            self._query_cache[text] = np.asarray(self.embedder.embed_query(text), dtype="float32")
        return self._query_cache[text]

    def distances(self, query_text):
        vector = self.query_vector(query_text)
        return ((self.matrix - vector) ** 2).sum(axis=1)

    def rank_of(self, distances, chunk_id):
        return int((distances < distances[self.index[chunk_id]]).sum()) + 1

    def rank_of_distance(self, distances, value, exclude):
        mask = np.ones(len(distances), dtype=bool)
        mask[self.index[exclude]] = False
        return int((distances[mask] < value).sum()) + 1

    def paper_rank(self, distances, pmcid):
        order = np.argsort(distances)
        for position, row in enumerate(order, start=1):
            if self.ids[row].rsplit("_", 1)[0] == pmcid:
                return position
        return None

    def top_sections(self, distances, k):
        return Counter(
            section_bucket(self.metadatas[row].get("section_path"))
            for row in np.argsort(distances)[:k]
        )


def load_seed_records(seed):
    runs = sorted(glob.glob(str(PROJECT_ROOT / "benchmark_runs" / f"*_retrieval_seed{seed}")))
    if not runs:
        raise SystemExit(f"No retrieval-only run for seed {seed}")
    return {
        json.loads(Path(path).read_text())["id"]: json.loads(Path(path).read_text())
        for path in glob.glob(f"{runs[-1]}/records/*.json")
    }


def answer_chunks(definition):
    return [chunk_id for chunk_id, grade in definition.get("gold_chunks", {}).items() if grade >= 2]


def experiment_e5(definitions, corpus, embedder):
    from chunking.section_chunker import create_chunks
    from processing.drug_registry import DrugRegistry
    from processing.metadata_enricher import enrich_article
    from processing.pmc_parser import parse_article

    registry = DrugRegistry()
    papers = sorted({
        pmcid
        for definition in definitions
        if definition["level"] == 1
        for pmcid in definition.get("gold_pmcs", [])
    })
    results = {}
    for pmcid in papers:
        article = enrich_article(parse_article(str(STAGING_DIR / "xml" / f"{pmcid}.xml")), registry=registry)
        with contextlib.redirect_stdout(io.StringIO()):
            chunks = create_chunks(article)
        rebuilt = {chunk["chunk_id"]: chunk["text"] for chunk in chunks}
        stored = {chunk_id for chunk_id in corpus.ids if chunk_id.rsplit("_", 1)[0] == pmcid}
        text_mismatch = [
            chunk_id for chunk_id in sorted(set(rebuilt) & stored)
            if collapse(rebuilt[chunk_id]) != collapse(corpus.documents[corpus.index[chunk_id]])
        ]
        cosines = []
        max_abs = 0.0
        for chunk_id in sorted(set(rebuilt) & stored):
            fresh = np.asarray(embedder.embed_document(rebuilt[chunk_id].strip()), dtype="float32")
            saved = corpus.matrix[corpus.index[chunk_id]]
            cosines.append(float(fresh @ saved / (np.linalg.norm(fresh) * np.linalg.norm(saved))))
            max_abs = max(max_abs, float(np.abs(fresh - saved).max()))
        results[pmcid] = {
            "rebuilt_chunks": len(rebuilt),
            "stored_chunks": len(stored),
            "missing_in_index": sorted(set(rebuilt) - stored),
            "extra_in_index": sorted(stored - set(rebuilt)),
            "text_mismatch": text_mismatch,
            "min_cosine": min(cosines) if cosines else None,
            "max_abs_component_diff": max_abs,
        }
    return results


def lost_answer_chunks(definitions, records):
    lost = []
    for definition in definitions:
        if definition["level"] != 1 or definition.get("control"):
            continue
        record = records[definition["id"]]
        final = {chunk["chunk_id"] for chunk in record["rerank"]["final"]}
        pool = {chunk["chunk_id"] for chunk in record["rerank"]["pool"]}
        for chunk_id in answer_chunks(definition):
            if chunk_id in final:
                continue
            lost.append({
                "id": definition["id"],
                "chunk": chunk_id,
                "loss": "not_retrieved" if chunk_id not in pool else "in_pool_not_delivered",
                "retrieval_k": record["strategy"]["used"]["retrieval_k"],
                "question": definition["question"],
            })
    return lost


def experiment_e3(lost, corpus):
    rows = []
    sections = {name: Counter() for name in ("original", "entity", "oracle")}
    seen_questions = set()
    for item in lost:
        variants = QUERY_VARIANTS.get(item["id"])
        if not variants:
            continue
        queries = {"original": item["question"], **variants}
        ranks = {}
        for name, text in queries.items():
            distances = corpus.distances(text)
            ranks[name] = corpus.rank_of(distances, item["chunk"])
            if item["id"] not in seen_questions:
                sections[name].update(corpus.top_sections(distances, 60))
        seen_questions.add(item["id"])
        rows.append({**item, "ranks": ranks})
    return {"rows": rows, "top60_sections": {name: dict(counter) for name, counter in sections.items()}}


def _fact_window(text, patterns):
    sentences = SENTENCE_SPLIT.split(collapse(text))
    hits = [
        index for index, sentence in enumerate(sentences)
        if any(pattern.search(sentence) for pattern in patterns)
    ]
    if not hits:
        return None
    start, end = max(0, min(hits) - 1), min(len(sentences), max(hits) + 2)
    return " ".join(sentences[start:end])


def _without_captions(text):
    sentences = SENTENCE_SPLIT.split(collapse(text))
    kept = [sentence for sentence in sentences if not CAPTION_PATTERN.search(sentence)]
    return " ".join(kept)


def _embed_pair(embedder, title, text):
    import torch

    inputs = embedder.article_tokenizer(
        [[title, text]],
        return_tensors="pt",
        truncation=True,
        max_length=512,
        padding=True,
    )
    with torch.no_grad():
        outputs = embedder.article_model(**inputs)
        embedding = embedder.mean_pooling(outputs.last_hidden_state, inputs["attention_mask"])
    return embedding.squeeze().cpu().numpy()


def _first_tokens(embedder, text, limit):
    ids = embedder.article_tokenizer(text, add_special_tokens=False, truncation=False)["input_ids"][:limit]
    return embedder.article_tokenizer.decode(ids)


def experiment_e1(lost, definitions, corpus, embedder):
    by_id = {definition["id"]: definition for definition in definitions}
    titles = {}
    rows = []
    for item in lost:
        definition = by_id[item["id"]]
        pmcid = item["chunk"].rsplit("_", 1)[0]
        if pmcid not in titles:
            metadata_path = STAGING_DIR / "metadata" / f"{pmcid}.json"
            titles[pmcid] = json.loads(metadata_path.read_text()).get("title", "") if metadata_path.exists() else ""
        text = corpus.documents[corpus.index[item["chunk"]]]
        patterns = [
            re.compile(fact["pattern"], re.IGNORECASE)
            for fact in definition["facts"]
            if item["chunk"] in fact["evidence_chunks"]
        ]
        distances = corpus.distances(item["question"])
        query = corpus.query_vector(item["question"])
        cutoff = float(np.sort(distances)[item["retrieval_k"] - 1])
        variants = {
            "recomputed": embedder.embed_document(text.strip()),
            "title_pair": _embed_pair(embedder, titles[pmcid], text),
            "no_captions": embedder.embed_document(_without_captions(text)),
            "first_256_tokens": embedder.embed_document(_first_tokens(embedder, text, 254)),
        }
        window = _fact_window(text, patterns)
        if window:
            variants["fact_window"] = embedder.embed_document(window)
        ranks = {"stored": corpus.rank_of(distances, item["chunk"])}
        for name, vector in variants.items():
            value = float(((np.asarray(vector, dtype="float32") - query) ** 2).sum())
            ranks[name] = corpus.rank_of_distance(distances, value, item["chunk"])
        rows.append({
            **item,
            "cutoff_rank": item["retrieval_k"],
            "caption_sentences_removed": len(SENTENCE_SPLIT.split(collapse(text))) - len(SENTENCE_SPLIT.split(_without_captions(text))),
            "fact_window_words": len(window.split()) if window else None,
            "ranks": ranks,
        })
    return rows


def experiment_e4(definitions, records, corpus):
    chunk_rows = []
    paper_rows = []
    for definition in definitions:
        if definition.get("control"):
            continue
        record = records[definition["id"]]
        executed = [query["text"] for query in record["retrieval"]["queries"]]
        distance_sets = [corpus.distances(text) for text in executed]
        for chunk_id in answer_chunks(definition):
            chunk_rows.append({
                "id": definition["id"],
                "chunk": chunk_id,
                "retrieval_k": record["strategy"]["used"]["retrieval_k"],
                "best_rank": min(corpus.rank_of(distances, chunk_id) for distances in distance_sets),
            })
        for pmcid in definition.get("gold_pmcs", []):
            paper_rows.append({
                "id": definition["id"],
                "level": definition["level"],
                "pmcid": pmcid,
                "retrieval_k": record["strategy"]["used"]["retrieval_k"],
                "best_rank": min(corpus.paper_rank(distances, pmcid) for distances in distance_sets),
            })

    def curve(rows):
        return {
            str(k): sum(1 for row in rows if row["best_rank"] <= k) / len(rows)
            for k in K_GRID
        } if rows else {}

    return {
        "answer_chunk_recall_at_k": curve(chunk_rows),
        "l1_paper_recall_at_k": curve([row for row in paper_rows if row["level"] == 1]),
        "l2_paper_recall_at_k": curve([row for row in paper_rows if row["level"] == 2]),
        "answer_chunks": chunk_rows,
        "papers": paper_rows,
    }


def experiment_e6(definitions, collection, seeds):
    rows = []
    for seed in seeds:
        records = load_seed_records(seed)
        for definition in definitions:
            if definition["level"] != 1 or definition.get("control"):
                continue
            record = records[definition["id"]]
            replay = record["rerank"]["replay"]
            order = replay["order"]
            top_k = record["rerank"]["top_k"]
            final = [chunk["chunk_id"] for chunk in record["rerank"]["final"]]
            patterns = [re.compile(fact["pattern"], re.IGNORECASE) for fact in definition["facts"]]
            for chunk_id in answer_chunks(definition):
                if chunk_id not in {item["chunk_id"] for item in order}:
                    continue
                pmcid = chunk_id.rsplit("_", 1)[0]
                same_paper = [item for item in order if item["chunk_id"].startswith(pmcid + "_")]
                within_rank = next(index + 1 for index, item in enumerate(same_paper) if item["chunk_id"] == chunk_id)
                above = same_paper[:within_rank - 1]
                holders = [item["chunk_id"] for item in same_paper if item["chunk_id"] in final]
                holder_texts = collection.get(ids=holders, include=["documents"])["documents"] if holders else []
                facts_in_holders = sum(
                    1 for pattern in patterns
                    if any(pattern.search(collapse(text)[:1200]) for text in holder_texts)
                )
                counterfactual = {}
                for cap in (2, 3, 4):
                    counts, selected = Counter(), []
                    for item in order:
                        if len(selected) >= top_k:
                            break
                        source = item.get("pmcid") or "unknown"
                        if counts[source] >= cap:
                            continue
                        selected.append(item["chunk_id"])
                        counts[source] += 1
                    counterfactual[str(cap)] = chunk_id in selected
                rows.append({
                    "seed": seed,
                    "id": definition["id"],
                    "chunk": chunk_id,
                    "delivered": chunk_id in final,
                    "within_paper_rank": within_rank,
                    "sections_above": [section_bucket(item["section_path"]) for item in above],
                    "holders": holders,
                    "facts_in_holders": facts_in_holders,
                    "facts_total": len(patterns),
                    "delivered_with_cap": counterfactual,
                })
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only retrieval root-cause experiments E1, E3, E4, E5, E6.")
    parser.add_argument("--seeds", default="0,1,2,3,4")
    args = parser.parse_args(argv)

    os.chdir(PROJECT_ROOT)
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    with contextlib.redirect_stdout(io.StringIO()):
        import embeddings.embedder as embedder
        from vector_store.chroma_store import collection

    definitions = json.loads(QUESTIONS_PATH.read_text())["questions"]
    seeds = [value.strip() for value in args.seeds.split(",") if value.strip()]
    records = load_seed_records(seeds[0])
    corpus = Corpus(collection, embedder)
    lost = lost_answer_chunks(definitions, records)

    output = {"seed_for_e1_e3_e4": seeds[0], "lost_answer_chunks": lost}
    print("[rca] E5 index integrity", file=sys.stderr, flush=True)
    output["e5"] = experiment_e5(definitions, corpus, embedder)
    print("[rca] E3 query variants", file=sys.stderr, flush=True)
    output["e3"] = experiment_e3(lost, corpus)
    print("[rca] E1 chunk perturbations", file=sys.stderr, flush=True)
    output["e1"] = experiment_e1(lost, definitions, corpus, embedder)
    print("[rca] E4 recall@k", file=sys.stderr, flush=True)
    output["e4"] = experiment_e4(definitions, records, corpus)
    print("[rca] E6 within-paper reranking", file=sys.stderr, flush=True)
    output["e6"] = experiment_e6(definitions, collection, seeds)

    run_dir = PROJECT_ROOT / "benchmark_runs" / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_rca"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "rca_results.json").write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(run_dir / "rca_results.json")


if __name__ == "__main__":
    main()
