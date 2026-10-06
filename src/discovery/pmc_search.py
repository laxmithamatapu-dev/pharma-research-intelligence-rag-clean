
import requests
import time

# Try importing the DrugRegistry from the project package structure.
# This supports both app layouts:
# - processing.drug_registry
# - src.processing.drug_registry
try:
    from processing.drug_registry import DrugRegistry
except ModuleNotFoundError:
    from src.processing.drug_registry import DrugRegistry


# Base URL for NCBI Entrez E-utilities API.
# This is the endpoint used for PubMed Central searches and metadata retrieval.
BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# Custom HTTP headers for API requests.
# A User-Agent string is useful to identify the client and helps avoid some API restrictions.
REQUEST_HEADERS = {
    "User-Agent": "PharmaResearchIntelligence/1.0 (PMC corpus acquisition)"
}

# Discovery profiles define how the script searches PMC for different research angles.
# Each profile contains a query pattern that includes a drug search term group ({terms})
# and additional clinical/biomedical keywords such as mechanism, trial, safety, biomarker, etc.
DISCOVERY_PROFILES = {
    "indication": '({terms}) AND (indication[Title/Abstract] OR treatment[Title/Abstract] OR approved[Title/Abstract])',
    "mechanism": '({terms}) AND (mechanism[Title/Abstract] OR "mechanism of action"[Title/Abstract] OR binding[Title/Abstract] OR inhibition[Title/Abstract] OR pharmacodynamics[Title/Abstract])',
    "clinical_trial": '({terms}) AND ("clinical trial"[Publication Type] OR randomized[Title/Abstract] OR "phase I"[Title/Abstract] OR "phase II"[Title/Abstract] OR "phase III"[Title/Abstract])',
    "safety": '({terms}) AND (safety[Title/Abstract] OR toxicity[Title/Abstract] OR "adverse event"[Title/Abstract] OR tolerability[Title/Abstract])',
    "biomarker": '({terms}) AND (biomarker*[Title/Abstract] OR predictive[Title/Abstract] OR prognostic[Title/Abstract] OR mutation*[Title/Abstract] OR expression[Title/Abstract])',
    "resistance": '({terms}) AND (resistance[Title/Abstract] OR progression[Title/Abstract] OR "acquired mutation"[Title/Abstract] OR transformation[Title/Abstract] OR bypass[Title/Abstract])',
    "comparison": '({terms}) AND (comparison[Title/Abstract] OR comparative[Title/Abstract] OR versus[Title/Abstract] OR "standard of care"[Title/Abstract])',
    "combination_strategy": '({terms}) AND (combination[Title/Abstract] OR synergistic[Title/Abstract] OR sequencing[Title/Abstract] OR "in combination with"[Title/Abstract])',
    "review": '({terms}) AND (review[Publication Type] OR "systematic review"[Title/Abstract] OR "meta-analysis"[Title/Abstract])',
    "real_world_evidence": '({terms}) AND (retrospective[Title/Abstract] OR observational[Title/Abstract] OR registry[Title/Abstract] OR "real-world"[Title/Abstract] OR claims[Title/Abstract])',
}


def build_profile_query(
    canonical_drug: str,
    profile: str,
    registry: DrugRegistry | None = None,
) -> str:
    """
    Build a PubMed Central search query for a specific evidence profile.

    Parameters:
        canonical_drug: The canonical or normalized name of the drug.
        profile: One of the keys in DISCOVERY_PROFILES.
        registry: Optional DrugRegistry instance for generating drug-specific search terms.

    Returns:
        A formatted PMC query string.
    """
    # Use injected registry or create a default one if none was supplied.
    registry = registry or DrugRegistry()

    # Validate that the requested profile exists.
    if profile not in DISCOVERY_PROFILES:
        raise ValueError(f"Unknown PMC discovery profile: {profile}")

    # Retrieve the list of keyword variants for the drug.
    # Example: ["erlotinib", "EGFR inhibitor", "TKI"]
    # Then convert each into a title/abstract search term.
    terms = " OR ".join(
        f'"{term}"[Title/Abstract]'
        for term in registry.search_query_terms(canonical_drug)
    )

    # Pull the template for the selected research profile and insert the terms.
    template = DISCOVERY_PROFILES[profile]
    return template.format(terms=terms)


def build_discovery_profiles(
    canonical_drug: str,
    profiles: list[str] | None = None,
    registry: DrugRegistry | None = None,
) -> dict[str, str]:
    """
    Build a dictionary of all evidence-profile queries for a drug.

    Parameters:
        canonical_drug: Drug name.
        profiles: Optional subset of profiles to generate.
        registry: Optional DrugRegistry instance.

    Returns:
        Dictionary mapping profile name -> query string.
    """
    # If no list is provided, use all available discovery profiles.
    profiles = profiles or list(DISCOVERY_PROFILES)

    # Build query for each requested profile.
    return {
        profile: build_profile_query(canonical_drug, profile, registry)
        for profile in profiles
    }


def search_drug_profiles(
    canonical_drug: str,
    profiles: list[str] | None = None,
    max_results: int = 50,
    registry: DrugRegistry | None = None,
) -> list[dict]:
    """
    Search PMC using multiple evidence-driven discovery profiles and return unique matches.

    Parameters:
        canonical_drug: The canonical drug name.
        profiles: Optional subset of discovery profiles.
        max_results: Number of results to fetch from each profile.
        registry: Optional DrugRegistry instance.

    Returns:
        A list of result dictionaries containing article info and profile metadata.
    """
    # Create a registry if none is supplied.
    registry = registry or DrugRegistry()

    # Store results in a list.
    results = []

    # Deduplicate across profiles using a set.
    seen = set()

    # Loop through each profile and its generated query.
    for profile, query in build_discovery_profiles(canonical_drug, profiles, registry).items():
        # Search PMC for the current query.
        # The rank is the position of this article within that profile search result set.
        for rank, pmcid in enumerate(search_pmc(query, max_results), start=1):
            # Skip duplicates across profiles.
            if pmcid in seen:
                continue

            # Remember this PMCID so we don't see it again.
            seen.add(pmcid)

            # Save structured metadata for each unique hit.
            results.append({
                "pmcid": pmcid,
                "canonical_drug": canonical_drug,
                "discovery_profile": profile,
                "query": query,
                "search_rank": rank,
            })

    return results


# NCBI E-utilities API documentation:
# https://www.ncbi.nlm.nih.gov/books/NBK25499/
# This API is used for searching PMC, retrieving metadata, and obtaining article details.
def search_pmc(
    query: str,
    max_results: int = 50
) -> list[str]:
    """
    Search PubMed Central (PMC) using Entrez ESearch and return a list of PMC IDs.

    Parameters:
        query: The query string to send to PMC.
        max_results: Maximum number of results to fetch.

    Returns:
        A list of PMC IDs in the format "PMC########".
    """
    # Helpful debug output for script usage.
    print("\nSearching PMC...")
    print(f"Query: {query}")

    # PMC search endpoint.
    url = f"{BASE_URL}/esearch.fcgi"

    # Parameters for the ESearch API call.
    params = {
        "db": "pmc",
        "term": query,
        "retmode": "json",
        "retmax": max_results
    }

    # Make a request with retry support for 429 rate limit responses.
    response = None
    for attempt in range(4):
        response = requests.get(
            url,
            params=params,
            headers=REQUEST_HEADERS,
            timeout=30,
        )

        # If the response is not a rate-limit error, stop retrying.
        if response.status_code != 429:
            break

        # If we hit 429 and are out of retry attempts, raise the error.
        if attempt == 3:
            response.raise_for_status()

        # Retry after header may specify how long to wait.
        retry_after = response.headers.get("Retry-After")

        # If Retry-After is missing, use exponential backoff.
        delay = float(retry_after) if retry_after else 2 ** attempt
        time.sleep(delay)

    # Raise an exception if the final response is an HTTP error.
    response.raise_for_status()

    # Parse JSON response.
    data = response.json()

    # ESearch returns an "esearchresult" object containing "idlist".
    ids = data["esearchresult"].get("idlist", [])

    # Convert numeric PMC IDs to full PMC IDs like "PMC1234567".
    return [
        f"PMC{article_id}"
        for article_id in ids
    ]


def get_pmc_metadata(
    pmcid: str
) -> dict:
    """
    Retrieve metadata for a single PMC article.

    Parameters:
        pmcid: PMC article ID, e.g. "PMC1234567"

    Returns:
        Dictionary with article metadata: pmcid, title, journal, publication_date, source
    """
    # Remove the "PMC" prefix to get the numeric article ID used by the API.
    numeric_id = pmcid.replace("PMC", "")

    # Use the ESummary endpoint to read article metadata.
    url = f"{BASE_URL}/esummary.fcgi"

    params = {
        "db": "pmc",
        "id": numeric_id,
        "retmode": "json"
    }

    # Fetch metadata.
    response = requests.get(
        url,
        params=params,
        timeout=30
    )

    # If the HTTP request fails, raise an exception.
    response.raise_for_status()

    # Parse the JSON response.
    data = response.json()

    # Get the article record for this PMCID.
    article = data["result"][numeric_id]

    # Return a clean dictionary with the most useful fields.
    return {
        "pmcid": pmcid,
        "title": article.get("title"),
        "journal": article.get("fulljournalname"),
        "publication_date": article.get("pubdate"),
        "source": article.get("source")
    }