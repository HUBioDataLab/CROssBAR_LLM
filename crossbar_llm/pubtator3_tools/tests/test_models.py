"""Pydantic round-trip tests against recorded API fixtures.

These don't touch the network. They prove that the models defined in
`crossbar_llm.pubtator3_tools.client` correctly parse what the real
PubTator3 API returns — independent of the rest of the pipeline.
"""
from crossbar_llm.pubtator3_tools.client import (
    EntityCandidate,
    RelatedEntity,
    SearchHit,
    _clean_snippet,
    _parse_document,
)


def test_autocomplete_round_trip(fx):
    raw = fx("pubtator3_autocomplete_example")
    candidates = [EntityCandidate(**item) for item in raw]

    assert len(candidates) == 5
    assert all(c.accession.startswith("@GENE_") for c in candidates)
    assert candidates[0].name == "JAK1"
    assert candidates[0].biotype == "gene"
    assert candidates[0].db == "ncbi_gene"


def test_relations_round_trip(fx):
    raw = fx("pubtator3_relations_example")
    related = [RelatedEntity(**item) for item in raw]

    assert len(related) > 0
    assert all(r.publications > 0 for r in related)
    assert all(r.type == "negative_correlate" for r in related)
    assert related[0].source == "@CHEMICAL_ruxolitinib"
    assert related[0].target == "@GENE_JAK1"

    # API returns results sorted by publication count descending.
    counts = [r.publications for r in related]
    assert counts == sorted(counts, reverse=True)


def test_search_round_trip_strips_markup(fx):
    raw = fx("pubtator3_search_example")
    hits = [SearchHit(**item) for item in raw["results"]]

    assert len(hits) > 0
    h = hits[0]
    assert h.pmid == 33849366
    assert isinstance(h.score, float)

    # text_hl preserved as-is for debugging; snippet is cleaned.
    assert h.text_hl is not None
    assert "@<m>" in h.text_hl  # raw markup present in source
    assert h.snippet is not None
    assert "@<m>" not in h.snippet
    assert "@@@" not in h.snippet


def test_export_round_trip(fx):
    raw = fx("pubtator3_export_example")
    docs = [_parse_document(d) for d in raw["PubTator3"]]

    assert len(docs) > 0
    doc = docs[0]
    assert doc.pmid == 33849366
    assert doc.title.startswith("Investigating")

    # Both title and abstract sections present.
    sections = {p.section for p in doc.passages}
    assert {"title", "abstract"}.issubset(sections)

    # BioREx scores parse as floats and carry their PMID.
    assert len(doc.relations) > 0
    rel = doc.relations[0]
    assert isinstance(rel.score, float)
    assert 0.0 <= rel.score <= 1.0
    assert rel.pmid == doc.pmid

    # Database identifiers are surfaced for CROssBAR-KG joins. At least one
    # of the document's relations must have non-null identifiers on both sides
    # — that's the field the KG keys on (MESH:Dxxxxxx for chemicals/diseases,
    # bare NCBI Gene ID for genes).
    assert any(
        r.role1_identifier and r.role2_identifier for r in doc.relations
    )

    # Annotations were filtered: every survivor has a valid accession.
    abstract_passage = next(p for p in doc.passages if p.section == "abstract")
    assert all(a.accession is not None for a in abstract_passage.annotations)


def test_clean_snippet_strips_both_highlight_forms():
    """The regex must handle both highlighted (@<m>...</m>) and
    annotated-only entities in the same string."""
    raw = (
        "Atomic Simulation of @<m>GENE_JAK1</m> @GENE_395681 @@@JAK1@@@ "
        "and @GENE_JAK2 @GENE_16452 @@@JAK2@@@ "
        "with @<m>CHEMICAL_ruxolitinib</m> @CHEMICAL_MESH:C540383 @@@Ruxolitinib@@@"
    )
    cleaned = _clean_snippet(raw)

    assert cleaned is not None
    assert "JAK1" in cleaned
    assert "JAK2" in cleaned
    assert "Ruxolitinib" in cleaned
    assert "@<m>" not in cleaned
    assert "@@@" not in cleaned


def test_clean_snippet_handles_none():
    assert _clean_snippet(None) is None
    assert _clean_snippet("") == ""


def test_full_text_parser_uses_section_type_and_drops_boilerplate():
    """Full-text docs put the semantic section in `infons.section_type`
    (not `infons.type`, which is just a formatting hint). Boilerplate
    sections like COMP_INT and SUPPL must be dropped at parse time."""
    raw_doc = {
        "pmid": "99999999",
        "passages": [
            {
                "infons": {"type": "title"},
                "offset": 0,
                "text": "A fake paper title for testing.",
                "annotations": [],
            },
            {
                "infons": {"section_type": "INTRO", "type": "paragraph"},
                "offset": 100,
                "text": "Introductory body content with real science.",
                "annotations": [],
            },
            {
                "infons": {"section_type": "METHODS", "type": "paragraph"},
                "offset": 500,
                "text": "Methods body content.",
                "annotations": [],
            },
            {
                "infons": {"section_type": "RESULTS", "type": "paragraph"},
                "offset": 1500,
                "text": "Results body content.",
                "annotations": [],
            },
            {
                "infons": {"section_type": "COMP_INT", "type": "paragraph"},
                "offset": 5000,
                "text": "No potential conflict of interest was reported by the author(s).",
                "annotations": [],
            },
            {
                "infons": {"section_type": "ACK_FUND", "type": "paragraph"},
                "offset": 5100,
                "text": "This work was funded by NIH grant ...",
                "annotations": [],
            },
            {
                "infons": {"section_type": "SUPPL", "type": "title_1"},
                "offset": 5200,
                "text": "Supplementary material",
                "annotations": [],
            },
            {
                "infons": {"section_type": "REF", "type": "paragraph"},
                "offset": 5400,
                "text": "1. Smith J et al. 2020. ...",
                "annotations": [],
            },
        ],
        "relations": [],
    }

    doc = _parse_document(raw_doc)

    sections = [p.section for p in doc.passages]

    # title (from `type`) plus the three content body sections survive.
    assert sections == ["title", "INTRO", "METHODS", "RESULTS"]

    # No boilerplate leaked through.
    skipped = {"COMP_INT", "ACK_FUND", "SUPPL", "REF"}
    assert not (set(sections) & skipped)

    # Body sections are labeled by section_type, not by the formatting `type`.
    assert "paragraph" not in sections
    assert "title_1" not in sections


# --- one bad record must not discard the batch -----------------------------
# PubTator3 is an evolving service: a new concept type or relation type is a
# routine upstream change. Parsing every record in one comprehension meant a
# single unfamiliar value raised for the whole response, and the tool wrapper
# turned that into an empty result — one new relation type discarded all 352
# partners of a query.

def test_parse_items_skips_only_the_bad_record():
    from crossbar_llm.pubtator3_tools.client import SearchHit, _parse_items

    raw = [
        {"pmid": 1, "title": "Good one"},
        {"pmid": 2},                      # missing required `title`
        {"pmid": 3, "title": "Good two"},
    ]
    hits = _parse_items(raw, lambda i: SearchHit(**i), what="test")
    assert [h.pmid for h in hits] == [1, 3]


def test_parse_items_tolerates_non_list_response():
    from crossbar_llm.pubtator3_tools.client import SearchHit, _parse_items

    # An error envelope instead of a list must yield [], not raise.
    assert _parse_items({"error": "busy"}, lambda i: SearchHit(**i), what="test") == []
    assert _parse_items(None, lambda i: SearchHit(**i), what="test") == []


def test_unknown_biotype_is_kept_not_dropped():
    """An unfamiliar concept type still carries a usable accession/name, so the
    record is kept rather than discarded."""
    from crossbar_llm.pubtator3_tools.client import EntityCandidate

    c = EntityCandidate(
        _id="@PROTEINDOMAIN_X", name="X", biotype="proteindomain",
        db_id="1", db="ncbi_gene",
    )
    assert c.accession == "@PROTEINDOMAIN_X"
    assert c.biotype == "proteindomain"


def test_unknown_relation_type_is_kept_not_dropped():
    from crossbar_llm.pubtator3_tools.client import RelatedEntity

    r = RelatedEntity(type="coexpress", source="@GENE_A", target="@GENE_B", publications=3)
    assert r.type == "coexpress"
