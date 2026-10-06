import requests
import time

OAI_PMH_URL = "https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/"
REQUEST_HEADERS = {
    "User-Agent": "PharmaResearchIntelligence/1.0 (PMC corpus ingestion)"
}


def get_article_xml(pmcid: str) -> str:

    numeric_id = pmcid.replace("PMC", "")

    params = {
        "verb": "GetRecord",
        "identifier": f"oai:pubmedcentral.nih.gov:{numeric_id}",
        "metadataPrefix": "pmc"
    }

    last_error = None
    for attempt in range(3):
        try:
            response = requests.get(
                OAI_PMH_URL,
                params=params,
                headers=REQUEST_HEADERS,
                timeout=30,
            )
            response.raise_for_status()
            return response.text
        except requests.RequestException as error:
            last_error = error
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)

    raise last_error