import json
import sys
import argparse
import io
import logging
import signal
import shutil
import sys
import time
from datetime import datetime
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path

sys.path.append(
    str(
        Path(__file__).resolve().parents[1]
    )
)

from processing.pmc_parser import parse_article
from processing.drug_registry import DrugRegistry
from processing.metadata_enricher import enrich_article
from processing.evidence_classifier import EVIDENCE_CUES
from chunking.section_chunker import create_chunks

XML_FOLDER = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "raw"
    / "xml"
)
MANIFEST_PATH = XML_FOLDER.parents[1] / "manifests" / "index_manifest.json"
QUALITY_REPORT_PATH = XML_FOLDER.parents[1] / "manifests" / "metadata_quality_report.json"
CHECKPOINT_PATH = XML_FOLDER.parents[1] / "manifests" / "index_checkpoint.json"
BUILD_LOG_PATH = XML_FOLDER.parents[1] / "manifests" / "index_build.log"


def _configure_build_logger():
    logger = logging.getLogger("pharma.index_build")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    try:
        BUILD_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(BUILD_LOG_PATH, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        logger.exception("Could not open build log file %s", BUILD_LOG_PATH)
    return logger


def _write_json_atomically(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(path.name + ".tmp")
    temporary_path.write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    temporary_path.replace(path)


def _write_checkpoint(
    last_completed_pmcid,
    articles_processed,
    chunks_indexed,
    articles_attempted,
    failed_articles,
) -> None:
    _write_json_atomically(CHECKPOINT_PATH, {
        "last_completed_pmcid": last_completed_pmcid,
        "articles_processed": articles_processed,
        "chunks_indexed": chunks_indexed,
        "articles_attempted": articles_attempted,
        "failed_articles": failed_articles,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    })


def validate_chunks(chunks):
    errors = []
    seen_ids = set()
    for chunk in chunks:
        chunk_id = chunk.get("chunk_id")
        if not chunk_id or chunk_id in seen_ids:
            errors.append(f"duplicate or missing chunk_id: {chunk_id}")
        seen_ids.add(chunk_id)
        for field in ("pmcid", "section_path", "section_category", "source_type"):
            if not chunk.get(field):
                errors.append(f"{chunk_id}: missing {field}")
        if not chunk.get("text", "").strip():
            errors.append(f"{chunk_id}: empty text")
    return errors


def _build_article_record(xml_file, registry):
    article = parse_article(str(xml_file))
    enriched = enrich_article(article, registry=registry)
    with redirect_stdout(io.StringIO()):
        chunks = create_chunks(enriched)
    return enriched, chunks


def audit_corpus(
    sample_size=20,
    output_path=QUALITY_REPORT_PATH,
    source_dir=XML_FOLDER,
):
    xml_files = sorted(Path(source_dir).glob("*.xml"))
    registry = DrugRegistry()
    article_counts = Counter()
    chunk_counts = Counter()
    evidence_counts = Counter()
    article_type_counts = Counter()
    study_design_counts = Counter()
    year_counts = Counter()
    missing_metadata = Counter()
    failed_articles = []
    duplicate_chunk_ids = []
    seen_chunk_ids = set()
    coverage_labels = {}
    sample = []
    processed_articles = 0
    processed_chunks = 0

    for xml_file in xml_files:
        try:
            article, chunks = _build_article_record(xml_file, registry)
            processed_articles += 1
            processed_chunks += len(chunks)
            drugs = [item["canonical_name"] for item in article.get("drugs", [])]
            evidence_types = article.get("evidence_types", [])
            for drug in drugs:
                article_counts[drug] += 1
                chunk_counts[drug] += len(chunks)
                coverage_labels.setdefault(drug, set()).update(evidence_types)
            for evidence_type in evidence_types:
                evidence_counts[evidence_type] += 1
            article_type_counts[article.get("article_type") or "<missing>"] += 1
            study_design_counts[article.get("study_design") or "<missing>"] += 1
            year_counts[str(article.get("publication_year") or "<missing>")] += 1
            if not drugs:
                missing_metadata["drug"] += 1
            if not article.get("disease"):
                missing_metadata["disease"] += 1
            if not article.get("targets"):
                missing_metadata["targets"] += 1
            if not article.get("publication_year"):
                missing_metadata["publication_year"] += 1
            if not evidence_types:
                missing_metadata["evidence_types"] += 1
            for chunk in chunks:
                chunk_id = chunk.get("chunk_id")
                if chunk_id in seen_chunk_ids:
                    duplicate_chunk_ids.append(chunk_id)
                seen_chunk_ids.add(chunk_id)
            if len(sample) < sample_size:
                invalid_labels = [
                    label for label in evidence_types
                    if label not in EVIDENCE_CUES
                ]
                sample.append({
                    "pmcid": article.get("pmcid"),
                    "title": article.get("title"),
                    "drug": article.get("drug"),
                    "evidence_types": evidence_types,
                    "article_type": article.get("article_type"),
                    "study_design": article.get("study_design"),
                    "classification_valid": not invalid_labels and bool(evidence_types),
                    "invalid_labels": invalid_labels,
                })
        except Exception as exc:
            failed_articles.append({"file": xml_file.name, "error": str(exc)})

    priority_drugs = list(registry.drugs)
    coverage_matrix = {
        drug: {
            evidence_type: evidence_type in coverage_labels.get(drug, set())
            for evidence_type in ("mechanism", "clinical_trial", "safety")
        }
        for drug in priority_drugs
    }
    report = {
        "report_type": "metadata_quality_audit",
        "metadata_version": "1.0",
        "source_xml_files": len(xml_files),
        "articles_processed": processed_articles,
        "chunks_regenerated": processed_chunks,
        "drug_article_counts": dict(article_counts),
        "drug_chunk_counts": dict(chunk_counts),
        "evidence_type_counts": dict(evidence_counts),
        "article_type_counts": dict(article_type_counts),
        "study_design_counts": dict(study_design_counts),
        "publication_year_distribution": dict(year_counts),
        "coverage_matrix_sample": coverage_matrix,
        "missing_metadata": dict(missing_metadata),
        "duplicate_chunk_ids": sorted(set(duplicate_chunk_ids)),
        "failed_articles": failed_articles,
        "classification_sample_size": len(sample),
        "classification_sample_valid": sum(item["classification_valid"] for item in sample),
        "classification_sample": sample,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({
        "articles_processed": processed_articles,
        "chunks_regenerated": processed_chunks,
        "failed_articles": len(failed_articles),
        "classification_sample_valid": report["classification_sample_valid"],
        "report": str(output_path),
    }, indent=2))
    return report


def build_index(source_dir=XML_FOLDER, rebuild=False):
    logger = _configure_build_logger()
    source_dir = Path(source_dir)
    xml_files = sorted(source_dir.glob("*.xml"))
    logger.info("Index build starting: source=%s articles=%d rebuild=%s", source_dir, len(xml_files), rebuild)

    try:
        logger.info("Loading embedding and Chroma modules")
        from embeddings.embedder import embed_chunks
        from vector_store.chroma_store import count_chunks, store_chunks
        registry = DrugRegistry()
    except Exception:
        logger.exception("Index build initialization failed")
        raise

    total_articles = 0
    total_chunks = 0
    articles_attempted = 0
    last_completed_pmcid = None
    failed_articles = []
    drug_counts = Counter()
    evidence_counts = Counter()
    missing_metadata = Counter()
    previous_sigterm_handler = signal.getsignal(signal.SIGTERM)
    previous_sigint_handler = signal.getsignal(signal.SIGINT)

    def handle_termination(signum, frame):
        logger.warning("Received signal %s; stopping after checkpoint", signum)
        raise KeyboardInterrupt(f"Received signal {signum}")

    signal.signal(signal.SIGTERM, handle_termination)
    signal.signal(signal.SIGINT, handle_termination)

    try:
        for article_index, xml_file in enumerate(xml_files, start=1):
            articles_attempted = article_index
            pmcid = xml_file.stem
            stage = "parse"
            article_started = time.perf_counter()
            logger.info("Article %d/%d start: %s", article_index, len(xml_files), xml_file.name)

            try:
                article = parse_article(str(xml_file))

                stage = "metadata_enrichment"
                article = enrich_article(article, registry=registry)

                stage = "chunk_generation"
                chunk_started = time.perf_counter()
                with redirect_stdout(io.StringIO()):
                    chunks = create_chunks(article)
                logger.info(
                    "%s chunk generation complete: chunks=%d elapsed=%.2fs",
                    pmcid,
                    len(chunks),
                    time.perf_counter() - chunk_started,
                )
                validation_errors = validate_chunks(chunks)
                if validation_errors:
                    raise ValueError("; ".join(validation_errors[:10]))

                if not chunks:
                    logger.warning("%s produced no chunks; skipping embedding and Chroma write", pmcid)
                    failed_articles.append({
                        "file": xml_file.name,
                        "stage": "chunk_generation",
                        "error": "no chunks produced",
                    })
                    continue

                stage = "embedding"
                embedding_started = time.perf_counter()
                embedded_chunks = embed_chunks(chunks)
                logger.info(
                    "%s embedding complete: embedded=%d/%d elapsed=%.2fs",
                    pmcid,
                    len(embedded_chunks),
                    len(chunks),
                    time.perf_counter() - embedding_started,
                )
                if not embedded_chunks:
                    raise RuntimeError("embedding produced no usable chunks")

                stage = "chroma_write"
                write_started = time.perf_counter()
                store_chunks(embedded_chunks)
                indexed_chunk_count = len(embedded_chunks)
                logger.info(
                    "%s Chroma write complete: chunks=%d elapsed=%.2fs",
                    pmcid,
                    indexed_chunk_count,
                    time.perf_counter() - write_started,
                )

                total_articles += 1
                total_chunks += indexed_chunk_count
                last_completed_pmcid = pmcid
                for drug in article.get("drugs", []):
                    drug_counts[drug["canonical_name"]] += indexed_chunk_count
                for evidence_type in article.get("evidence_types", []):
                    evidence_counts[evidence_type] += indexed_chunk_count
                if not article.get("drugs"):
                    missing_metadata["articles_without_drug"] += 1
                if not article.get("publication_year"):
                    missing_metadata["missing_publication_year"] += 1

                stage = "checkpoint_write"
                _write_checkpoint(
                    last_completed_pmcid,
                    total_articles,
                    total_chunks,
                    articles_attempted,
                    failed_articles,
                )
                logger.info(
                    "Article %s checkpointed: articles_processed=%d chunks_indexed=%d total_elapsed=%.2fs",
                    pmcid,
                    total_articles,
                    total_chunks,
                    time.perf_counter() - article_started,
                )
            except Exception as exc:
                logger.exception("Article %s failed at stage=%s", pmcid, stage)
                failed_articles.append({
                    "file": xml_file.name,
                    "stage": stage,
                    "error": str(exc),
                })
                _write_checkpoint(
                    last_completed_pmcid,
                    total_articles,
                    total_chunks,
                    articles_attempted,
                    failed_articles,
                )
    except BaseException:
        logger.exception(
            "Index build interrupted or terminated before manifest creation; last_completed_pmcid=%s",
            last_completed_pmcid,
        )
        raise
    finally:
        try:
            _write_checkpoint(
                last_completed_pmcid,
                total_articles,
                total_chunks,
                articles_attempted,
                failed_articles,
            )
            logger.info(
                "Final checkpoint saved: last_completed_pmcid=%s articles=%d chunks=%d",
                last_completed_pmcid,
                total_articles,
                total_chunks,
            )
        except Exception:
            logger.exception("Failed writing final progress checkpoint")
        signal.signal(signal.SIGTERM, previous_sigterm_handler)
        signal.signal(signal.SIGINT, previous_sigint_handler)

    try:
        chroma_count = count_chunks()
        logger.info("Index loop completed: Chroma count=%d", chroma_count)
        manifest = {
            "metadata_version": "1.0",
            "source_dir": str(source_dir),
            "articles_seen": len(xml_files),
            "articles_attempted": articles_attempted,
            "articles_indexed": total_articles,
            "chunks_indexed": total_chunks,
            "chroma_collection_count": chroma_count,
            "last_completed_pmcid": last_completed_pmcid,
            "failed_articles": failed_articles,
            "drug_chunk_counts": dict(drug_counts),
            "evidence_type_chunk_counts": dict(evidence_counts),
            "missing_metadata": dict(missing_metadata),
        }
        _write_json_atomically(MANIFEST_PATH, manifest)
        logger.info("Saved final index manifest: %s", MANIFEST_PATH)
    except Exception:
        logger.exception("Final count or manifest generation failed")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--audit-only",
        action="store_true",
        help="Audit parsing and metadata without embedding or modifying Chroma.",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Back up the existing Chroma directory before rebuilding it.",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=XML_FOLDER,
        help="Directory containing staged PMC XML files.",
    )
    args = parser.parse_args()
    if args.audit_only:
        audit_corpus(source_dir=args.source_dir)
    else:
        if not args.rebuild:
            raise SystemExit("Refusing to build without --rebuild. Run --audit-only first.")
        chroma_dir = Path("data/chromadb")
        if chroma_dir.exists():
            backup_dir = Path("data/backups") / (
                f"chromadb_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            backup_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(chroma_dir), str(backup_dir))
            print(f"Backed up existing Chroma to: {backup_dir}")
        build_index(source_dir=args.source_dir, rebuild=True)