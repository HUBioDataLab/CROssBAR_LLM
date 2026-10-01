"""Partner discovery must give every partner a share of the exported papers.

Each partner's search returns a relevance-ranked page of hits, and export keeps
only the first `max_documents` PMIDs. Appending pages one after another let the
first partner's page fill every export slot, so the answer only covered that
partner. PMIDs are taken from each page in turn instead.
"""
from types import SimpleNamespace

import pytest

from crossbar_llm.pubtator3_tools import nodes
from crossbar_llm.pubtator3_tools.client import RelatedEntity, SearchHit
from crossbar_llm.pubtator3_tools.tools import SearchArticlesOutput

PAGES = {
    "relations:inhibit|@CHEMICAL_A|@GENE_JAK1": [101, 102, 103, 104, 105, 106, 107, 108, 109, 110],
    "relations:inhibit|@CHEMICAL_B|@GENE_JAK1": [201, 202, 203, 101],
    "relations:inhibit|@CHEMICAL_C|@GENE_JAK1": [301, 302],
}


@pytest.fixture
def fake_search(monkeypatch):
    async def ainvoke(args):
        pmids = PAGES[args["text_query"]]
        return SearchArticlesOutput(
            hits=[SearchHit(pmid=p, title=f"paper {p}") for p in pmids],
            total=len(pmids),
        )

    monkeypatch.setattr(nodes, "pubtator3_search_articles", SimpleNamespace(ainvoke=ainvoke))


def _partner_state():
    return {
        "question_type": "relation_partner_discovery",
        "partners": [
            RelatedEntity(type="inhibit", source=source, target="@GENE_JAK1", publications=1)
            for source in ("@CHEMICAL_A", "@CHEMICAL_B", "@CHEMICAL_C")
        ],
        "warnings": [],
    }


async def test_pmids_are_taken_from_each_partner_in_turn(fake_search):
    out = await nodes.search_node(_partner_state())

    # The first seven — what export keeps by default — cover all three partners.
    assert out["pmids"][:7] == [101, 201, 301, 102, 202, 302, 103]


async def test_interleaving_keeps_every_pmid_once(fake_search):
    out = await nodes.search_node(_partner_state())

    expected = {p for page in PAGES.values() for p in page}
    assert len(out["pmids"]) == len(expected)
    assert set(out["pmids"]) == expected
    assert out["total_articles"] == 16
