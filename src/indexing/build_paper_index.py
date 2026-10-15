import argparse
import contextlib
import io
import json
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.append(
    str(
        Path(__file__).resolve().parents[1]
    )
)

from processing.drug_registry import DrugRegistry
from processing.metadata_enricher import enrich_article
from processing.pmc_parser import parse_article

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SOURCE_DIR = DATA_DIR / "staging" / "phase1" / "xml"
MANIFEST_PATH = DATA_DIR / "manifests" / "paper_index_manifest.json"
METADATA_VERSION = "1.0"


def indexed_paper_counts(collection):
    metadatas = collection.get(include=["metadatas"])["metadatas"]
    return Counter(metadata.get("pmcid") for metadata in metadatas if metadata.get("pmcid"))


def paper_document(title, abstract):
    title = (title or "").strip()
    abstract = " ".join((abstract or "").split())
    if title and abstract:
        return f"{title}. {abstract}"
    return title or abstract


def collect_paper_records(source_dir=SOURCE_DIR, passage_counts=None):
    registry = DrugRegistry()
    records = []
    failures = []
    for pmcid in sorted(passage_counts):
        xml_path = Path(source_dir) / f"{pmcid}.xml"
        try:
            article = enrich_article(parse_article(str(xml_path)), registry=registry)
        except Exception as exc:
            failures.append({"pmcid": pmcid, "error": str(exc)})
            continue
        title = article.get("title") or ""
        abstract = " ".join((article.get("abstract") or "").split())
        records.append({
            "pmcid": pmcid,
            "title": title,
            "abstract": abstract,
            "document": paper_document(title, abstract),
            "metadata": {
                "pmcid": pmcid,
                "title": title,
                "publication_year": article.get("publication_year") or "",
                "journal": article.get("journal") or "",
                "article_type": article.get("article_type") or "",
                "study_design": article.get("study_design") or "",
                "drugs": [item["canonical_name"] for item in article.get("drugs", [])],
                "n_passages": passage_counts[pmcid],
                "has_abstract": bool(abstract),
                "abstract_words": len(abstract.split()),
                "metadata_version": METADATA_VERSION,
            },
        })
    return records, failures


def build_paper_index(source_dir=SOURCE_DIR, pooling="mean", distance="l2", batch_size=16):
    from embeddings.embedder import embed_papers
    from vector_store.chroma_store import collection, reset_papers_collection, store_papers

    started = time.perf_counter()
    passage_counts = indexed_paper_counts(collection)
    records, failures = collect_paper_records(source_dir, passage_counts)
    embeddings = embed_papers(
        [(record["title"], record["abstract"]) for record in records],
        pooling=pooling,
        batch_size=batch_size,
    )
    for record, embedding in zip(records, embeddings):
        record["embedding"] = embedding.tolist()
        record["metadata"]["pooling"] = pooling

    reset_papers_collection(distance)
    count = 0
    for start in range(0, len(records), 256):
        count = store_papers(records[start:start + 256], distance)

    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_dir": str(source_dir),
        "pooling": pooling,
        "distance": distance,
        "papers_in_passage_index": len(passage_counts),
        "papers_indexed": count,
        "papers_without_abstract": sum(1 for record in records if not record["abstract"]),
        "failures": failures,
        "seconds": time.perf_counter() - started,
        "metadata_version": METADATA_VERSION,
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the paper-level (title + abstract) collection.")
    parser.add_argument("--source-dir", type=Path, default=SOURCE_DIR)
    parser.add_argument("--pooling", choices=("mean", "cls"), default="mean")
    parser.add_argument("--distance", choices=("l2", "ip", "cosine"), default="l2")
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()
    with contextlib.redirect_stdout(io.StringIO()):
        manifest = build_paper_index(args.source_dir, args.pooling, args.distance, args.batch_size)
    print(json.dumps(manifest, indent=2))
