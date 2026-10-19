"""Citations in a PubTator3 answer: the PMIDs it cites become the run's
reference list, instead of a `References:` section written into the text.

The answer cites papers inline as `[PMID:12345678]`. `resolve_answer_pmids`
takes the PMIDs in the order the answer first cites them, so the reference
list and the text cannot disagree. Kept separate from Paperclip's equivalent:
the two tool packages do not import each other.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

# A heading line that opens a reference list: "References:", "**References**",
# "## Sources" and the like. It must start a line and end there or at a colon,
# so prose that merely begins with the word ("References to IL-17 ...") stays.
_REFERENCE_SECTION = re.compile(
    r"\n[ \t]*(?:#{1,6}[ \t]*)?(?:\*\*|__)?[ \t]*(?:references|sources|bibliography)"
    r"[ \t]*(?:\*\*|__)?[ \t]*(?::|(?=\n|$))",
    re.IGNORECASE,
)
_PMID = re.compile(r"\bPMID[ \t]*:[ \t]*(\d+)", re.IGNORECASE)


def strip_reference_section(answer: str) -> str:
    """The answer without a trailing reference list the model added anyway."""
    match = _REFERENCE_SECTION.search(answer)
    if match is None:
        return answer
    head = answer[: match.start()].rstrip()
    # A reply that is nothing but a reference list is left alone rather than
    # emptied; there is no answer to keep.
    return head or answer


def cited_pmids(answer: str) -> list[str]:
    """PMIDs the answer cites inline, in order of first citation."""
    return list(dict.fromkeys(_PMID.findall(answer)))


def resolve_answer_pmids(
    answer: str,
    evidence_pmids: Iterable[int | str],
    *,
    cited: Sequence[str] | None = None,
) -> tuple[str, list[str], list[str]]:
    """The answer without a reference section, the PMIDs it cites, and warnings.

    `cited` (the model's own list) only fills in when the answer has no inline
    PMIDs at all. PMIDs that were not in the evidence are left out and reported.
    """
    answer = strip_reference_section(answer)
    known = {str(pmid) for pmid in evidence_pmids}
    pmids = cited_pmids(answer)
    if not pmids and cited:
        pmids = list(dict.fromkeys(
            match.group(1) if (match := _PMID.search(item)) else item.strip()
            for item in cited
        ))
    unknown = [pmid for pmid in pmids if pmid not in known]
    warnings = []
    if unknown:
        listed = ", ".join(f"PMID:{pmid}" for pmid in unknown)
        verb = "is" if len(unknown) == 1 else "are"
        warnings.append(
            f"synthesize: the answer cited {listed}, which {verb} not in the "
            "retrieved evidence; left out of the citations."
        )
    return answer, [pmid for pmid in pmids if pmid in known], warnings


__all__ = ["cited_pmids", "resolve_answer_pmids", "strip_reference_section"]
