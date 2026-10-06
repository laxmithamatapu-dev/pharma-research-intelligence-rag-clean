from pathlib import Path
import json

RAW_DIR = Path("data/raw/xml")
METADATA_DIR = Path("data/metadata")


def save_article(
    pmcid: str,
    xml_text: str,
    metadata: dict
):
    RAW_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    METADATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    xml_path = RAW_DIR / f"{pmcid}.xml"

    with open(
        xml_path,
        "w",
        encoding="utf-8"
    ) as file:
        file.write(xml_text)

    metadata_path = (
        METADATA_DIR /
        f"{pmcid}.json"
    )

    with open(
        metadata_path,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            metadata,
            file,
            indent=2,
            ensure_ascii=False
        )

    print(f"Saved XML: {xml_path}")
    print(f"Saved metadata: {metadata_path}")