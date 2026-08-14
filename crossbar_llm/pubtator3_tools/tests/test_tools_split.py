import re

import pytest

from crossbar_llm.pubtator3_tools.tools import (
    AutocompleteOutput,
    ExportPassagesOutput,
    FindPartnersOutput,
    SearchArticlesOutput,
    pubtator3_autocomplete,
    pubtator3_export_passages,
    pubtator3_find_partners,
    pubtator3_search_articles,
)
from crossbar_llm.pubtator3_tools import client

BASE_URL = client.BASE_URL


def _url_pattern(path: str) -> re.Pattern:
    return re.compile(rf"{re.escape(BASE_URL)}{re.escape(path)}.*")


def test_autocomplete_schema_has_expected_fields():
    assert set(pubtator3_autocomplete.args.keys()) == {"query", "concept", "limit"}


def test_find_partners_schema_has_expected_fields():
    assert set(pubtator3_find_partners.args.keys()) == {"e1_accession", "relation", "e2_type"}


def test_search_articles_schema_has_expected_fields():
    assert set(pubtator3_search_articles.args.keys()) == {"text_query", "page"}


def test_export_passages_schema_has_expected_fields():
    assert set(pubtator3_export_passages.args.keys()) == {"pmids", "full_text"}


async def test_autocomplete_happy_path(httpx_mock, fx):
    httpx_mock.add_response(
        url=_url_pattern("/entity/autocomplete/"),
        json=fx("pubtator3_autocomplete_example"),
    )

    out = await pubtator3_autocomplete.ainvoke({"query": "JAK1", "concept": "gene"})

    assert isinstance(out, AutocompleteOutput)
    assert out.error is None
    assert len(out.candidates) == 5
    assert out.candidates[0].accession.startswith("@GENE_")


async def test_find_partners_happy_path(httpx_mock, fx):
    httpx_mock.add_response(
        url=_url_pattern("/relations"),
        json=fx("pubtator3_relations_example"),
    )

    out = await pubtator3_find_partners.ainvoke(
        {"e1_accession": "@GENE_JAK1", "relation": "negative_correlate", "e2_type": "Chemical"}
    )

    assert isinstance(out, FindPartnersOutput)
    assert out.error is None
    assert len(out.partners) > 0
    assert all(p.publications > 0 for p in out.partners)


async def test_search_articles_happy_path(httpx_mock, fx):
    httpx_mock.add_response(
        url=_url_pattern("/search/"),
        json=fx("pubtator3_search_example"),
    )

    out = await pubtator3_search_articles.ainvoke(
        {"text_query": "relations:negative_correlate|@CHEMICAL_ruxolitinib|@GENE_JAK1"}
    )

    assert isinstance(out, SearchArticlesOutput)
    assert out.error is None
    assert out.total > 0
    assert len(out.hits) > 0
    assert all(h.pmid > 0 for h in out.hits)


async def test_export_passages_happy_path(httpx_mock, fx):
    httpx_mock.add_response(
        url=_url_pattern("/publications/export/biocjson"),
        json=fx("pubtator3_export_example"),
    )

    out = await pubtator3_export_passages.ainvoke({"pmids": [33849366]})

    assert isinstance(out, ExportPassagesOutput)
    assert out.error is None
    assert len(out.documents) > 0
    doc = out.documents[0]
    assert doc.pmid == 33849366
    assert any(p.section == "abstract" for p in doc.passages)


async def test_autocomplete_never_raises_on_persistent_429(httpx_mock, monkeypatch):
    monkeypatch.setattr(client, "RETRY_429_BACKOFF_S", 0.0)
    httpx_mock.add_response(url=_url_pattern("/entity/autocomplete/"), status_code=429)
    httpx_mock.add_response(url=_url_pattern("/entity/autocomplete/"), status_code=429)

    out = await pubtator3_autocomplete.ainvoke({"query": "JAK1"})
    assert out.candidates == []
    assert out.error is not None


async def test_find_partners_never_raises_on_persistent_429(httpx_mock, monkeypatch):
    monkeypatch.setattr(client, "RETRY_429_BACKOFF_S", 0.0)
    httpx_mock.add_response(url=_url_pattern("/relations"), status_code=429)
    httpx_mock.add_response(url=_url_pattern("/relations"), status_code=429)

    out = await pubtator3_find_partners.ainvoke(
        {"e1_accession": "@GENE_JAK1", "relation": "treat", "e2_type": "Disease"}
    )
    assert out.partners == []
    assert out.error is not None


async def test_search_articles_never_raises_on_persistent_429(httpx_mock, monkeypatch):
    monkeypatch.setattr(client, "RETRY_429_BACKOFF_S", 0.0)
    httpx_mock.add_response(url=_url_pattern("/search/"), status_code=429)
    httpx_mock.add_response(url=_url_pattern("/search/"), status_code=429)

    out = await pubtator3_search_articles.ainvoke({"text_query": "anything"})
    assert out.hits == []
    assert out.total == 0
    assert out.error is not None


async def test_export_passages_never_raises_on_persistent_429(httpx_mock, monkeypatch):
    monkeypatch.setattr(client, "RETRY_429_BACKOFF_S", 0.0)
    httpx_mock.add_response(url=_url_pattern("/publications/export/biocjson"), status_code=429)
    httpx_mock.add_response(url=_url_pattern("/publications/export/biocjson"), status_code=429)

    out = await pubtator3_export_passages.ainvoke({"pmids": [12345]})
    assert out.documents == []
    assert out.error is not None


async def test_find_partners_normalizes_relation_alias(httpx_mock, fx):
    httpx_mock.add_response(
        url=_url_pattern("/relations"),
        json=fx("pubtator3_relations_example"),
    )
    # Schema's Literal rejects the alias, so call the coroutine directly.
    out = await pubtator3_find_partners.coroutine(
        e1_accession="@GENE_JAK1",
        relation="negatively_correlate",
        e2_type="Chemical",
    )
    assert out.error is None
    assert len(out.partners) > 0


async def test_export_passages_rejects_empty_pmids():
    with pytest.raises(Exception):
        await pubtator3_export_passages.ainvoke({"pmids": []})


async def test_export_passages_batches_concurrently_above_cap(httpx_mock, fx):
    # EXPORT_PMID_BATCH is 100; 250 PMIDs must split into 3 chunks.
    httpx_mock.add_response(
        url=_url_pattern("/publications/export/biocjson"),
        json=fx("pubtator3_export_example"),
        is_reusable=True,
    )

    pmids = list(range(1, 251))
    out = await pubtator3_export_passages.ainvoke({"pmids": pmids})

    assert out.error is None
    # Fixture has N docs; we should get 3 × N because the same fixture
    # is returned for each of the 3 batches.
    fixture_doc_count = len(fx("pubtator3_export_example")["PubTator3"])
    assert len(out.documents) == 3 * fixture_doc_count

    # Confirm exactly 3 HTTP calls were made and the pmids params chunk correctly.
    requests = httpx_mock.get_requests(url=_url_pattern("/publications/export/biocjson"))
    assert len(requests) == 3
    pmid_chunks = [
        req.url.params["pmids"].split(",") for req in requests
    ]
    assert [len(c) for c in pmid_chunks] == [100, 100, 50]
