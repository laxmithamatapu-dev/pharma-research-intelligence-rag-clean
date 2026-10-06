import xml.etree.ElementTree as ET


def _clean_text(element) -> str:
    if element is None:
        return ""
    return " ".join(
        part.strip()
        for part in element.itertext()
        if part and part.strip()
    )


def _publication_year(root):
    candidates = []
    priority = {
        "epub": 0,
        "ppub": 1,
        "": 2,
        "collection": 3,
    }
    for element in root.iter():
        if not element.tag.endswith("pub-date"):
            continue
        year = next(
            (
                (child.text or "").strip()
                for child in element
                if child.tag.endswith("year")
            ),
            "",
        )
        if year.isdigit() and len(year) == 4:
            pub_type = element.attrib.get("pub-type", "").casefold()
            candidates.append((priority.get(pub_type, 4), int(year)))
    return min(candidates)[1] if candidates else None


def parse_section(sec):
    """
    Recursively parse a JATS <sec> element.
    """

    section_title = None

    for child in sec:

        if child.tag.endswith("title"):

            section_title = _clean_text(child)

            break

    section = {
        "title": section_title,
        "text": "",
        "subsections": []
    }

    text_parts = []

    for child in sec:

        # Skip the title itself
        if child.tag.endswith("title"):
            continue

        # Nested subsection
        elif child.tag.endswith("sec"):

            subsection = parse_section(child)

            section["subsections"].append(
                subsection
            )

        else:

            content = _clean_text(child)

            if content:
                text_parts.append(
                    content
                )

    section["text"] = " ".join(
        text_parts
    )

    return section


def parse_article(xml_path):

    tree = ET.parse(xml_path)
    root = tree.getroot()

    title = None
    abstract = None
    journal = None

    pmcid = None
    pmid = None
    doi = None
    article_type = root.attrib.get("article-type")
    keywords = []
    subjects = []

    # ----------------------------
    # Metadata
    # ----------------------------

    for element in root.iter():

        if element.tag.endswith("article-title"):

            if title is None:

                title = _clean_text(element)

        elif element.tag.endswith("abstract"):

            if abstract is None:

                abstract = _clean_text(element)

        elif element.tag.endswith("journal-title"):

            if journal is None:

                journal = _clean_text(element)

        elif element.tag.endswith("article-id"):

            id_type = element.attrib.get(
                "pub-id-type"
            )

            if id_type == "pmcid":
                pmcid = (element.text or "").strip()

            elif id_type == "pmid":
                pmid = (element.text or "").strip()

            elif id_type == "doi":
                doi = (element.text or "").strip()

        elif element.tag.endswith("kwd"):
            value = _clean_text(element)
            if value:
                keywords.append(value)

        elif element.tag.endswith("subject"):
            value = _clean_text(element)
            if value:
                subjects.append(value)

    # ----------------------------
    # Authors
    # ----------------------------

    authors = []

    for contrib in root.iter():

        if (
            contrib.tag.endswith("contrib")
            and contrib.attrib.get(
                "contrib-type"
            ) == "author"
        ):

            surname = None
            given = None

            for child in contrib.iter():

                if child.tag.endswith(
                    "surname"
                ):

                    surname = child.text

                elif child.tag.endswith(
                    "given-names"
                ):

                    given = child.text

            if surname and given:

                authors.append(
                    f"{given} {surname}"
                )

    # ----------------------------
    # Hierarchical Sections
    # ----------------------------

    sections = []

    body = None

    for element in root.iter():

        if element.tag.endswith("body"):

            body = element
            break

    if body:

        for child in body:

            if child.tag.endswith("sec"):

                sections.append(
                    parse_section(child)
                )

    return {

        "pmcid": pmcid,

        "pmid": pmid,

        "doi": doi,

        "title": title,

        "journal": journal,

        "abstract": abstract,

        "authors": authors,

        "publication_year": _publication_year(root),

        "article_type": article_type,

        "keywords": list(dict.fromkeys(keywords)),

        "subjects": list(dict.fromkeys(subjects)),

        "sections": sections
    }