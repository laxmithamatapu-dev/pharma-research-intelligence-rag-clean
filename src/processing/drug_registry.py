# """Registry-backed drug identity and deterministic alias normalization."""

# import json
# import re
# from pathlib import Path
# from typing import Any


# DEFAULT_REGISTRY_PATH = (
#     Path(__file__).resolve().parents[2] / "data" / "registry" / "drugs.yaml"
# )


# class DrugRegistry:
#     def __init__(self, path: str | Path = DEFAULT_REGISTRY_PATH):
#         self.path = Path(path)
#         payload = json.loads(self.path.read_text(encoding="utf-8"))
#         self.version = str(payload.get("registry_version", "unknown"))
#         self.drugs = {
#             item["canonical_name"]: item
#             for item in payload.get("drugs", [])
#             if item.get("canonical_name")
#         }
#         self._aliases = self._build_aliases()

#     def _build_aliases(self) -> dict[str, dict[str, Any]]:
#         aliases = {}
#         for canonical_name, record in self.drugs.items():
#             values = {
#                 canonical_name,
#                 record.get("generic_name", ""),
#                 *record.get("synonyms", []),
#                 *record.get("brand_names", []),
#                 *record.get("development_codes", []),
#             }
#             for value in values:
#                 normalized = str(value).strip().casefold()
#                 if normalized:
#                     aliases[normalized] = {
#                         "canonical_name": canonical_name,
#                         "record": record,
#                         "surface_form": str(value),
#                     }
#         return aliases

#     def get(self, canonical_name: str) -> dict[str, Any] | None:
#         return self.drugs.get(canonical_name)

#     def all_aliases(self) -> list[str]:
#         return sorted(self._aliases, key=len, reverse=True)

#     def lookup(self, surface_form: str) -> dict[str, Any] | None:
#         return self._aliases.get(surface_form.strip().casefold())

#     def find_mentions(self, text: str, source: str) -> list[dict[str, Any]]:
#         mentions = []
#         lowered = text.casefold()
#         for alias in self.all_aliases():
#             pattern = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
#             match = re.search(pattern, lowered)
#             if not match:
#                 continue
#             match_text = text[match.start():match.end()]
#             item = self._aliases[alias]
#             confidence = 1.0 if source == "title" else 0.95 if source == "abstract" else 0.85
#             mentions.append({
#                 "canonical_name": item["canonical_name"],
#                 "surface_form": match_text,
#                 "source": source,
#                 "confidence": confidence,
#                 "role": "unknown",
#             })
#         return mentions

#     def search_query_terms(self, canonical_name: str) -> list[str]:
#         record = self.drugs[canonical_name]
#         values = {
#             record.get("generic_name", canonical_name),
#             *record.get("synonyms", []),
#             *record.get("brand_names", []),
#             *record.get("development_codes", []),
#         }
#         return sorted({value for value in values if value}, key=len, reverse=True)
"""Registry-backed drug identity and deterministic alias normalization."""

# Standard library imports
import json
import re
from pathlib import Path
from typing import Any


# Default path to the registry data file.
# This resolves to:
# <project-root>/data/registry/drugs.yaml
# based on the location of this file.
DEFAULT_REGISTRY_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "registry" / "drugs.yaml"
)


class DrugRegistry:
    """
    A registry wrapper for drug identity data.

    This class loads a JSON payload containing canonical drug information
    and builds a lookup table that maps aliases, brand names, synonyms,
    and development codes back to their canonical drug name.
    """

    def __init__(self, path: str | Path = DEFAULT_REGISTRY_PATH):
        """
        Initialize the registry by loading JSON data from disk.

        Parameters:
            path: File path to the registry JSON file.
        """
        # Store the registry file path.
        self.path = Path(path)

        # Load the JSON registry payload.
        payload = json.loads(self.path.read_text(encoding="utf-8"))

        # Store registry version information.
        # This is helpful for debugging and compatibility checks.
        self.version = str(payload.get("registry_version", "unknown"))

        # Build a dictionary keyed by canonical_name.
        # Each value is the full drug record associated with that canonical name.
        self.drugs = {
            item["canonical_name"]: item
            for item in payload.get("drugs", [])
            if item.get("canonical_name")
        }

        # Precompute alias mappings so lookups are fast and deterministic.
        self._aliases = self._build_aliases()

    def _build_aliases(self) -> dict[str, dict[str, Any]]:
        """
        Build a normalized alias map for all drug names.

        Returns:
            A dict where:
            - key: normalized alias string
            - value: metadata about the canonical drug associated with that alias
        """
        aliases = {}

        # Iterate through all canonical drug records.
        for canonical_name, record in self.drugs.items():
            # Collect all possible alias values for this drug:
            # - canonical name
            # - generic name
            # - synonyms
            # - brand names
            # - development codes
            values = {
                canonical_name,
                record.get("generic_name", ""),
                *record.get("synonyms", []),
                *record.get("brand_names", []),
                *record.get("development_codes", []),
            }

            # Normalize each value and map it to the canonical record.
            for value in values:
                normalized = str(value).strip().casefold()
                if normalized:
                    aliases[normalized] = {
                        "canonical_name": canonical_name,
                        "record": record,
                        "surface_form": str(value),
                    }

        return aliases

    def get(self, canonical_name: str) -> dict[str, Any] | None:
        """
        Fetch a drug record by its canonical name.

        Parameters:
            canonical_name: The canonical drug name as stored in the registry.

        Returns:
            The drug record dictionary or None if it does not exist.
        """
        return self.drugs.get(canonical_name)

    def all_aliases(self) -> list[str]:
        """
        Return all normalized aliases sorted by length descending.

        Sorting by length helps prioritize longer and more specific strings
        when doing pattern-based matching, such as matching full names before
        shorter substrings or acronyms.
        """
        return sorted(self._aliases, key=len, reverse=True)

    def lookup(self, surface_form: str) -> dict[str, Any] | None:
        """
        Look up a drug using a raw surface form such as:
        - "Imbruvica"
        - "ibrutinib"
        - "BTK inhibitor"

        This method normalizes the input by trimming spaces and converting to lowercase.

        Returns:
            A dict containing canonical_name, record, and surface_form
            for the matched alias, or None if no alias matches.
        """
        return self._aliases.get(surface_form.strip().casefold())

    def find_mentions(self, text: str, source: str) -> list[dict[str, Any]]:
        """
        Find drug mentions within a text string and return structured metadata.

        Parameters:
            text: Raw input text to scan.
            source: The source type, such as "title" or "abstract".

        Returns:
            A list of mention dictionaries describing matches.
        """
        mentions = []
        lowered = text.casefold()

        # Check every alias in descending length order.
        for alias in self.all_aliases():
            # Use a regex boundary check so we don't match partial words inside other strings.
            # This avoids false matches like finding "ib" inside unrelated words.
            pattern = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"

            # Search the lowercased text.
            match = re.search(pattern, lowered)
            if not match:
                continue

            # Extract the original text span as it appeared in the source text.
            match_text = text[match.start():match.end()]

            # Get the canonical match data.
            item = self._aliases[alias]

            # Confidence scoring based on source type.
            # Titles are typically more precise than abstracts.
            confidence = (
                1.0 if source == "title"
                else 0.95 if source == "abstract"
                else 0.85
            )

            # Record the mention metadata.
            mentions.append({
                "canonical_name": item["canonical_name"],
                "surface_form": match_text,
                "source": source,
                "confidence": confidence,
                "role": "unknown",
            })

        return mentions

    def search_query_terms(self, canonical_name: str) -> list[str]:
        """
        Build a prioritized list of drug-related search terms for PMC queries.

        This is used to create search terms like:
        - brand names
        - generic names
        - synonyms
        - development codes

        The values are deduplicated and sorted by length descending so
        more specific terms are prioritized over shorter, broader ones.

        Parameters:
            canonical_name: Canonical drug name in the registry.

        Returns:
            List of search terms to use in PubMed/PMC queries.
        """
        # Get the full drug record.
        record = self.drugs[canonical_name]

        # Collect the main identity terms for this drug.
        values = {
            record.get("generic_name", canonical_name),
            *record.get("synonyms", []),
            *record.get("brand_names", []),
            *record.get("development_codes", []),
        }

        # Remove blanks and duplicates, then sort by length descending.
        return sorted({value for value in values if value}, key=len, reverse=True)