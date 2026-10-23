"""Citations in a Paperclip answer: how papers are labelled for the model, and
how the answer's inline citations become the run's reference list.

The model cites each paper by a stable identifier label (`[PMID:12345678]`,
falling back to PMCID, DOI, then the Paperclip document id) rather than by its
position in the search results. Positions leaked retrieval order into the
answer: a reply that used only the third, fifth and sixth papers read
"[3, 5, 6]". The answer carries no reference section of its own;
`resolve_answer_citations` builds the reference list from what the answer
actually cites, so the text and the list cannot disagree.
"""
from __future__ import annotations

import re
from collections.abc import Sequence

from crossbar_llm.paperclip_tools.nodes import format_line_anchor
from crossbar_llm.paperclip_tools.schemas import (
    Citation,
    PaperclipCitedSource,
    PaperContext,
)

# A heading line that opens a reference list: "References:", "**References**",
# "## Sources" and the like. It must start a line and end there or at a colon,
# so prose that merely begins with the word ("References to IL-17 ...") stays.
_REFERENCE_SECTION = re.compile(
    r"\n[ \t]*(?:#{1,6}[ \t]*)?(?:\*\*|__)?[ \t]*(?:references|sources|bibliography)"
    r"[ \t]*(?:\*\*|__)?[ \t]*(?::|(?=\n|$))",
    re.IGNORECASE,
)
_ID_TOKEN = re.compile(r"\b(PMID|PMCID|DOI|Paperclip)[ \t]*:[ \t]*([^\s,;\]]+)", re.IGNORECASE)
_PMCID = re.compile(r"PMC\d+", re.IGNORECASE)
_LINE_SPEC = re.compile(r"L?(\d+)(?:\s*-\s*L?(\d+))?", re.IGNORECASE)
_BODY_LINE = re.compile(r"^\s*L(\d+):", re.MULTILINE)
# A model asking for a 10,000-line range is not pointing at evidence.
_MAX_ANCHOR_SPAN = 200


def strip_reference_section(answer: str) -> str:
    """The answer without a trailing reference list the model added anyway."""
    match = _REFERENCE_SECTION.search(answer)
    if match is None:
        return answer
    head = answer[: match.start()].rstrip()
    # A reply that is nothing but a reference list is left alone rather than
    # emptied; there is no answer to keep.
    return head or answer


def _pmcid(citation: Citation) -> str | None:
    if citation.pmcid:
        value = citation.pmcid.strip().upper()
        return value if value.startswith("PMC") else f"PMC{value}"
    return citation.doc_id.upper() if _PMCID.fullmatch(citation.doc_id) else None


def _doi(value: str) -> str:
    value = value.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if value.lower().startswith(prefix):
            value = value[len(prefix):]
    return value


def _normalize(prefix: str, value: str) -> str | None:
    """A comparable `PREFIX:value` key, or None for something that is no id."""
    prefix = prefix.upper()
    value = value.rstrip(".")
    # A DOI may hold balanced parentheses, e.g. 10.1016/S0140-6736(20)30183-5,
    # but a closing one it never opened belongs to the surrounding prose.
    while value.endswith(")") and value.count(")") > value.count("("):
        value = value[:-1].rstrip(".")
    if not value:
        return None
    if prefix == "PMID":
        return f"PMID:{value}" if value.isdigit() else None
    if prefix == "PMCID":
        value = value.upper()
        value = value if value.startswith("PMC") else f"PMC{value}"
        return f"PMCID:{value}" if _PMCID.fullmatch(value) else None
    if prefix == "DOI":
        return f"DOI:{_doi(value).lower()}"
    return f"PAPERCLIP:{value.lower()}"


def _key(label: str) -> str | None:
    prefix, _, value = label.partition(":")
    return _normalize(prefix, value)


def _candidate_labels(citation: Citation) -> list[str]:
    """Labels a paper could be cited by, best first. Malformed ids are skipped,
    so a bad PMID in the metadata falls through to the next identifier rather
    than producing a label no citation could ever match."""
    labels = []
    if citation.pmid:
        labels.append(f"PMID:{citation.pmid.strip()}")
    if pmcid := _pmcid(citation):
        labels.append(f"PMCID:{pmcid}")
    if citation.doi:
        labels.append(f"DOI:{_doi(citation.doi)}")
    labels.append(f"Paperclip:{citation.doc_id}")
    return [label for label in labels if _key(label) is not None]


def source_labels(citations: Sequence[Citation]) -> dict[str, str]:
    """The label each paper is cited by, keyed by doc id.

    Prefers the PMID, then the PMCID, then the DOI, then the Paperclip doc id.
    Labels are unique: a paper whose PMID another paper already uses (the same
    article found in two corpora) falls back to its next identifier.
    """
    labels: dict[str, str] = {}
    used: set[str | None] = set()
    for citation in citations:
        candidates = _candidate_labels(citation)
        label = next((c for c in candidates if _key(c) not in used), candidates[-1])
        used.add(_key(label))
        labels[citation.doc_id] = label
    return labels


def cited_keys(answer: str) -> list[str]:
    """Normalized identifiers the answer cites, in order of first citation."""
    keys: list[str] = []
    for prefix, value in _ID_TOKEN.findall(answer):
        key = _normalize(prefix, value)
        if key is not None and key not in keys:
            keys.append(key)
    return keys


def _line_numbers(spec: str) -> list[int]:
    numbers: list[int] = []
    for start, end in _LINE_SPEC.findall(spec):
        first, last = int(start), int(end or start)
        if last < first or last - first > _MAX_ANCHOR_SPAN:
            continue
        numbers.extend(range(first, last + 1))
    return numbers


def _anchored_url(url: str, spec: str | None, body: str | None) -> str:
    """`url` with a `#L...` anchor for the lines the model named, if they hold up.

    Only line numbers actually shown in that paper's evidence are kept, and only
    Paperclip citation URLs without an anchor get one: a map extraction's URL
    already carries the lines Paperclip itself pinned.
    """
    if not spec or not body or "#" in url or "citations.gxl.ai" not in url:
        return url
    shown = {int(n) for n in _BODY_LINE.findall(body)}
    lines = [n for n in _line_numbers(spec) if n in shown]
    anchor = format_line_anchor(lines)
    return f"{url}#{anchor}" if anchor else url


def resolve_answer_citations(
    answer: str,
    citations: Sequence[Citation],
    *,
    documents: Sequence[PaperContext] = (),
    cited: Sequence[PaperclipCitedSource] | None = None,
) -> tuple[str, list[Citation], list[str]]:
    """The answer without a reference section, the papers it cites, and warnings.

    The reference list follows the answer's inline citations, in the order they
    first appear, numbered from 1. `cited` (the model's own list) only fills in
    when the answer has no inline citations at all, and supplies line anchors.
    Identifiers that match no retrieved paper are left out and reported.
    """
    answer = strip_reference_section(answer)
    by_key: dict[str, Citation] = {}
    for citation in citations:
        for label in _candidate_labels(citation):
            key = _key(label)
            if key is not None:
                by_key.setdefault(key, citation)

    keys = cited_keys(answer)
    if not keys and cited:
        keys = [k for item in cited if (k := _key(item.source.strip("[] "))) is not None]

    ordered: list[Citation] = []
    seen: set[str] = set()
    unknown: list[str] = []
    for key in keys:
        citation = by_key.get(key)
        if citation is None:
            unknown.append(key)
        elif citation.doc_id not in seen:
            seen.add(citation.doc_id)
            ordered.append(citation)

    line_specs: dict[str, str] = {}
    for item in cited or ():
        key = _key(item.source.strip("[] "))
        if item.lines and key in by_key:
            line_specs.setdefault(by_key[key].doc_id, item.lines)
    bodies = {doc.doc_id: doc.body for doc in documents}

    resolved = [
        citation.model_copy(
            update={
                "ref_num": number,
                "url": _anchored_url(
                    citation.url,
                    line_specs.get(citation.doc_id),
                    bodies.get(citation.doc_id),
                ),
            }
        )
        for number, citation in enumerate(ordered, start=1)
    ]
    warnings = []
    if unknown:
        warnings.append(
            "synthesize: the answer cited "
            + ", ".join(unknown)
            + (", which is" if len(unknown) == 1 else ", which are")
            + " not among the retrieved papers; left out of the citations."
        )
    return answer, resolved, warnings


__all__ = [
    "cited_keys",
    "resolve_answer_citations",
    "source_labels",
    "strip_reference_section",
]
