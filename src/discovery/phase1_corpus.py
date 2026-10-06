
"""Phase 2 drug-centric PMC acquisition and coverage reporting."""

import argparse
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

# Build drug-specific PMC queries and execute them against NCBI E-utilities.
from discovery.pmc_search import build_profile_query, search_pmc, DISCOVERY_PROFILES

# Download full-text XML from the PMC OAI-PMH service.
from ingestion.pmc_oai import get_article_xml

# Retrieve article summary metadata from NCBI E-utilities.
from discovery.pmc_search import get_pmc_metadata

# Load the local registry of canonical drug names and aliases.
from processing.drug_registry import DrugRegistry


# The project root is calculated relative to this Python file.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Where this script stages downloaded article XML and metadata.
STAGING_ROOT = PROJECT_ROOT / "data" / "staging" / "phase1"

# Default location for the acquisition report JSON file.
REPORT_PATH = PROJECT_ROOT / "data" / "manifests" / "phase1_acquisition_report.json"


# Drugs included in this acquisition run.
# Each name must match a canonical name in the drug registry.
PRIORITY_DRUGS = (
    "osimertinib",
    "pembrolizumab",
    "trastuzumab",
    "imatinib",
    "adalimumab",
    "semaglutide",
    "nivolumab",
    "enzalutamide",
)

# These profiles are considered essential for minimum coverage reporting.
REQUIRED_COVERAGE = ("mechanism", "clinical_trial", "safety")

# Default maximum number of search results to request for each drug/profile pair.
DEFAULT_RESULTS_PER_PROFILE = 20

# Approximate chunk count per article, based on an earlier corpus audit.
# This is used for estimates only; actual chunking happens later during indexing.
AUDITED_CHUNKS_PER_ARTICLE = 1961 / 75


def _query_plan(registry: DrugRegistry, results_per_profile: int) -> list[dict]:
    """Create one PMC search task for every drug and discovery profile."""
    plan = []

    # Pair every priority drug with every configured evidence profile.
    for drug in PRIORITY_DRUGS:
        for profile in DISCOVERY_PROFILES:
            plan.append({
                "drug": drug,
                "profile": profile,

                # Build the PMC query using the drug's registry terms and
                # the keyword template for this evidence profile.
                "query": build_profile_query(drug, profile, registry),

                # Remember the result limit so discover() can use it.
                "requested_results": results_per_profile,
            })

    return plan


def discover(plan: list[dict]) -> tuple[list[dict], dict]:
    """
    Execute all planned searches and combine hits by PMCID.

    Each article is stored once, even if multiple drugs or profiles found it.
    The associated drugs, profiles, and individual search hits are retained.
    """
    # Keyed by PMCID. This lets results from different searches merge into
    # the same article record.
    records = {}

    # Count search hits per profile. These are raw counts, so the same article
    # can contribute more than once if multiple queries find it.
    profile_counts = Counter()

    # Count hits by both drug and profile. This counter is currently collected
    # during discovery but is not included in the returned statistics.
    drug_profile_counts = Counter()

    # Search errors are recorded rather than stopping the entire discovery run.
    search_failures = []

    # Execute the plan in order and display progress.
    for index, item in enumerate(plan, start=1):
        print(f"[{index}/{len(plan)}] {item['drug']} / {item['profile']}")

        # Query PMC for this particular drug/profile combination.
        try:
            pmcids = search_pmc(item["query"], item["requested_results"])
        except Exception as exc:
            # Keep the query details alongside the error for diagnosis.
            search_failures.append({
                **item,
                "error": str(exc),
            })
            continue

        # Pause between successful search calls to reduce request frequency.
        time.sleep(0.34)

        # Update raw result counts.
        profile_counts[item["profile"]] += len(pmcids)
        drug_profile_counts[(item["drug"], item["profile"])] += len(pmcids)

        # Add each result to the PMCID-keyed collection.
        for rank, pmcid in enumerate(pmcids, start=1):
            # Create the article record the first time this PMCID is seen.
            # setdefault() returns the existing record on later appearances.
            record = records.setdefault(pmcid, {
                "pmcid": pmcid,
                "drugs": set(),
                "profiles": set(),
                "search_hits": [],
            })

            # Record which drug/profile search discovered this article.
            record["drugs"].add(item["drug"])
            record["profiles"].add(item["profile"])
            record["search_hits"].append({
                "drug": item["drug"],
                "profile": item["profile"],
                "rank": rank,
            })

    # Convert sets to sorted lists so the records can be serialized as JSON.
    normalized = []
    for record in records.values():
        normalized.append({
            "pmcid": record["pmcid"],
            "drugs": sorted(record["drugs"]),
            "profiles": sorted(record["profiles"]),
            "search_hits": record["search_hits"],
        })

    # Return deduplicated article records plus summary statistics.
    return normalized, {
        "profile_result_counts": dict(profile_counts),
        "search_failures": search_failures,

        # Sum of all search results before deduplication.
        "raw_search_hits": sum(profile_counts.values()),
    }


def build_report(
    plan: list[dict],
    records: list[dict],
    search_stats: dict,
    results_per_profile: int,
) -> dict:
    """Build the acquisition and evidence-profile coverage report."""
    article_counts = Counter()

    # Maps each drug to the set of profiles that found at least one article.
    profile_coverage = defaultdict(set)

    # Maps each drug to the set of article IDs found for it.
    # This is collected here but not used elsewhere in the current report.
    drug_article_ids = defaultdict(set)

    # Count articles and determine profile coverage for each drug.
    for record in records:
        for drug in record["drugs"]:
            drug_article_ids[drug].add(record["pmcid"])
            article_counts[drug] += 1
            profile_coverage[drug].update(record["profiles"])

    # Estimate chunks per drug using the previously measured average.
    # These are estimates; the real chunk count is known after indexing.
    expected_chunks = {
        drug: round(article_counts[drug] * AUDITED_CHUNKS_PER_ARTICLE)
        for drug in PRIORITY_DRUGS
    }

    # For every drug, mark each profile as covered if at least one article
    # was found for that drug through that profile.
    coverage_matrix = {
        drug: {
            profile: profile in profile_coverage.get(drug, set())
            for profile in DISCOVERY_PROFILES
        }
        for drug in PRIORITY_DRUGS
    }

    # Build the same coverage matrix for only the required profiles.
    required_matrix = {
        drug: {
            profile: profile in profile_coverage.get(drug, set())
            for profile in REQUIRED_COVERAGE
        }
        for drug in PRIORITY_DRUGS
    }

    # Return all acquisition counts, coverage information, and article records.
    return {
        "report_type": "phase1_drug_centric_acquisition",
        "registry_version": "1.0",
        "priority_drugs": list(PRIORITY_DRUGS),
        "profiles": list(DISCOVERY_PROFILES),
        "results_per_profile": results_per_profile,
        "planned_searches": len(plan),
        "raw_search_hits": search_stats["raw_search_hits"],
        "unique_pmc_articles": len(records),
        "expected_article_counts": dict(article_counts),
        "expected_chunk_counts": expected_chunks,

        # This total sums the per-drug estimates. It can count an article more
        # than once if the same article is associated with multiple drugs.
        "expected_total_chunks": sum(expected_chunks.values()),

        # This estimates chunks based on unique articles, counting each
        # deduplicated article once.
        "estimated_unique_chunks": round(len(records) * AUDITED_CHUNKS_PER_ARTICLE),

        # Clarifies why the per-drug estimate may exceed the unique estimate.
        "expected_total_chunks_note": "Per-drug counts may overlap for multi-drug articles.",
        "audited_chunks_per_article_estimate": AUDITED_CHUNKS_PER_ARTICLE,
        "drug_coverage_matrix": coverage_matrix,
        "required_coverage_matrix": required_matrix,

        # List only drugs that are missing at least one required profile.
        "missing_required_coverage": {
            drug: [
                profile for profile, present in required_matrix[drug].items()
                if not present
            ]
            for drug in PRIORITY_DRUGS
            if not all(required_matrix[drug].values())
        },
        "profile_result_counts": search_stats["profile_result_counts"],
        "search_failures": search_stats["search_failures"],
        "records": records,

        # The report initially says files have not been downloaded.
        # stage_records() updates this when --download is used.
        "staging": {
            "root": str(STAGING_ROOT),
            "status": "not_downloaded",
        },
    }


def stage_records(
    records: list[dict],
    report: dict,
    report_path: Path | None = None,
) -> dict:
    """
    Download XML and metadata for each discovered PMCID.

    Existing complete staged files are skipped. Failed downloads are recorded
    in the report rather than stopping the rest of the staging run.
    """
    # Keep XML and metadata in separate subdirectories.
    xml_dir = STAGING_ROOT / "xml"
    metadata_dir = STAGING_ROOT / "metadata"

    # Create the directories if they do not already exist.
    xml_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    failures = []
    staged = 0
    skipped = 0

    # Process each unique article record.
    for index, record in enumerate(records, start=1):
        pmcid = record["pmcid"]

        # Use the PMCID to create matching XML and metadata file names.
        xml_path = xml_dir / f"{pmcid}.xml"
        metadata_path = metadata_dir / f"{pmcid}.json"

        # If both files exist and XML is nonempty, treat the article as already
        # staged and avoid downloading it again.
        if (
            xml_path.exists()
            and metadata_path.exists()
            and xml_path.stat().st_size > 0
        ):
            skipped += 1
            continue

        print(f"Staging [{index}/{len(records)}] {pmcid}")

        try:
            # Download the article's full XML from PMC.
            xml_text = get_article_xml(pmcid)

            # Retrieve its summary metadata from NCBI.
            metadata = get_pmc_metadata(pmcid)

            # Add information about which searches discovered the article.
            metadata.update({
                "discovery_drugs": record["drugs"],
                "discovery_profiles": record["profiles"],
                "search_hits": record["search_hits"],
            })

            # Save the raw article XML.
            xml_path.write_text(xml_text, encoding="utf-8")

            # Save metadata as readable JSON. ensure_ascii=False preserves
            # non-ASCII characters in titles and other metadata.
            metadata_path.write_text(
                json.dumps(metadata, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            staged += 1

            # Pause after a successful article download to moderate requests.
            time.sleep(0.34)

        except Exception as exc:
            # Record the failed PMCID and continue with the next article.
            failures.append({"pmcid": pmcid, "error": str(exc)})

            # Save progress after a failure if the caller supplied a report path.
            if report_path:
                report["staging"] = {
                    "root": str(STAGING_ROOT),
                    "status": "in_progress",
                    "articles_staged": staged + skipped,
                    "staging_failures": failures,
                }
                report_path.write_text(
                    json.dumps(report, indent=2),
                    encoding="utf-8",
                )

    # Record final staging totals. "completed" means the loop finished;
    # staging_failures indicates whether some articles failed.
    report["staging"] = {
        "root": str(STAGING_ROOT),
        "status": "completed",
        "articles_staged": staged + skipped,
        "newly_downloaded": staged,
        "already_staged": skipped,
        "staging_failures": failures,
    }

    return report


def main() -> None:
    """Parse command-line options and run discovery, reporting, and staging."""
    parser = argparse.ArgumentParser(
        description="Build Phase 1 PMC acquisition report."
    )

    # Limit how many results are requested for each drug/profile query.
    parser.add_argument(
        "--results-per-profile",
        type=int,
        default=DEFAULT_RESULTS_PER_PROFILE,
    )

    # Choose where to save the final report.
    parser.add_argument(
        "--output",
        type=Path,
        default=REPORT_PATH,
    )

    # If supplied, download XML and metadata after searching PMC.
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download and stage discovered XML after producing the acquisition plan.",
    )

    # Load an existing report's records and stage them without re-running searches.
    parser.add_argument(
        "--resume-report",
        type=Path,
        help="Resume staging from an existing acquisition report without searching PMC again.",
    )

    # Read command-line arguments.
    args = parser.parse_args()

    if args.resume_report:
        # Resume mode: load prior discovery results from the supplied report.
        report = json.loads(
            args.resume_report.read_text(encoding="utf-8")
        )
        records = report["records"]

    else:
        # New discovery mode: load the drug registry and build all queries.
        registry = DrugRegistry()
        plan = _query_plan(registry, args.results_per_profile)

        # Search PMC and combine results by unique PMCID.
        records, search_stats = discover(plan)

        # Summarize search results and evidence-profile coverage.
        report = build_report(
            plan,
            records,
            search_stats,
            args.results_per_profile,
        )

    if args.download:
        # Download XML and metadata for discovered records and update the report.
        report = stage_records(records, report, args.output)

    # Ensure the output directory exists before writing the report.
    args.output.parent.mkdir(parents=True, exist_ok=True)

    # Save the final acquisition report as formatted JSON.
    args.output.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    # Print a concise summary to the terminal.
    print(json.dumps({
        "unique_pmc_articles": report["unique_pmc_articles"],
        "expected_total_chunks": report["expected_total_chunks"],
        "missing_required_coverage": report["missing_required_coverage"],
        "downloaded": args.download,
        "report": str(args.output),
    }, indent=2))


# Run the command-line workflow only when this file is executed directly.
if __name__ == "__main__":
    main()