"""Standalone LangGraph node functions for the PubTator3 pipeline.

Each node is a plain coroutine that takes the current `PubTator3State` and
returns a partial state dict to merge. The LLM-bound nodes (router,
synthesize, evaluate_depth) live inside `build_graph` because they close
over the chat model and prompts — every node here is pure data plumbing
around the four PubTator3 tools.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate

from crossbar_llm.pubtator3_tools.structured_output import (
    _ainvoke_structured_with_json_fallback,
)
from crossbar_llm.pubtator3_tools.schemas import (
    EntityMention,
    PubTator3State,
    StructuredModel,
)
from crossbar_llm.pubtator3_tools.tools import (
    pubtator3_autocomplete,
    pubtator3_export_passages,
    pubtator3_find_partners,
    pubtator3_search_articles,
)
from crossbar_llm.pubtator3_tools.client import (
    ABSTRACT_ONLY_SECTIONS,
    DocumentRelation,
    EntityCandidate,
    Passage,
)


def _add_warning(state: PubTator3State, msg: str) -> list[str]:
    return [*state.get("warnings", []), msg]


def _is_confident_match(candidate: EntityCandidate) -> bool:
    """Whether PubTator3 matched the query to this candidate with confidence.

    The autocomplete `match` field reports HOW the query matched:
        'Matched on name <m>BTK</m>'
        'Matched on synonyms <m>LY450139</m>'
        'Multiple matches'
    A name or synonym match means PubTator3 found the query in its entity
    dictionary. 'Multiple matches' is its low-confidence fuzzy/token fallback
    and is the dominant source of wrong resolutions (e.g. 'histone H3' ->
    @GENE_HTR12, 'Fibrodysplasia Ossificans Progressiva' -> Myositis
    Ossificans). We trust only name/synonym matches; anything else is left
    unresolved so the entity falls through to the keyword-search fallback.
    """
    lowered = (candidate.match or "").lower()
    return lowered.startswith("matched on name") or lowered.startswith(
        "matched on synonym"
    )


async def resolve_node(state: PubTator3State) -> dict:
    mentions = state.get("mentions") or []
    if not mentions:
        return {"resolved": {}, "unresolved": []}

    async def _one(m: EntityMention):
        out = await pubtator3_autocomplete.ainvoke(
            {"query": m.text, "concept": m.suggested_type, "limit": 5}
        )
        return m.text, out

    results = await asyncio.gather(*(_one(m) for m in mentions))

    resolved: dict[str, EntityCandidate] = {}
    unresolved: list[str] = []
    warnings = list(state.get("warnings", []))

    for text, out in results:
        if out.error:
            warnings.append(f"autocomplete failed for '{text}': {out.error}")
            unresolved.append(text)
            continue
        if not out.candidates:
            unresolved.append(text)
            continue

        # Trust only name/synonym matches — PubTator3 ranks those above its
        # fuzzy 'Multiple matches' fallback, so the first confident candidate
        # is the right pick. If none are confident, leave the entity
        # unresolved rather than inject a fuzzy (often wrong) accession into a
        # structured query; downstream keyword-search fallback handles it.
        confident = [c for c in out.candidates if _is_confident_match(c)]
        if not confident:
            unresolved.append(text)
            warnings.append(
                f"'{text}' had no confident PubTator3 name/synonym match "
                f"(best candidate '{out.candidates[0].accession}' was a fuzzy "
                f"'Multiple matches' hit); left unresolved for keyword fallback."
            )
            continue

        resolved[text] = confident[0]
        if len(confident) > 1:
            warnings.append(
                f"'{text}' was ambiguous ({len(confident)} confident candidates); "
                f"picked '{confident[0].accession}'."
            )

    return {"resolved": resolved, "unresolved": unresolved, "warnings": warnings}


async def partner_discovery_node(
    state: PubTator3State, *, max_partners: int = 5
) -> dict:
    mentions = state.get("mentions") or []
    resolved = state.get("resolved") or {}
    if not mentions:
        return {"partners": [], "warnings": _add_warning(state, "No mentions to anchor partner discovery.")}

    anchor = resolved.get(mentions[0].text)
    if not anchor:
        return {
            "partners": [],
            "warnings": _add_warning(
                state, f"Could not resolve anchor entity '{mentions[0].text}'."
            ),
        }

    relation = state.get("relation")
    e2_type = state.get("e2_type")
    if not relation or not e2_type:
        return {
            "partners": [],
            "warnings": _add_warning(
                state, "partner_discovery requires both `relation` and `e2_type`."
            ),
        }

    out = await pubtator3_find_partners.ainvoke(
        {"e1_accession": anchor.accession, "relation": relation, "e2_type": e2_type}
    )
    if out.error:
        return {
            "partners": [],
            "warnings": _add_warning(state, f"find_partners failed: {out.error}"),
        }

    partners = out.partners[:max_partners]
    if not partners:
        return {
            "partners": [],
            "warnings": _add_warning(
                state,
                f"No '{relation}' partners of type '{e2_type}' found for "
                f"{anchor.accession}.",
            ),
        }
    return {"partners": partners}


async def search_node(state: PubTator3State) -> dict:
    qtype = state.get("question_type")
    mentions = state.get("mentions") or []
    resolved = state.get("resolved") or {}

    queries: list[str] = []
    warnings = list(state.get("warnings", []))

    if qtype == "relation_partner_discovery":
        for partner in state.get("partners") or []:
            queries.append(f"relations:{partner.type}|{partner.source}|{partner.target}")
    elif qtype == "relation_known_pair":
        relation = state.get("relation")
        if len(mentions) < 2 or not relation:
            warnings.append("relation_known_pair needs two mentions plus a relation.")
        else:
            e1 = resolved.get(mentions[0].text)
            e2 = resolved.get(mentions[1].text)
            if e1 and e2:
                queries.append(f"relations:{relation}|{e1.accession}|{e2.accession}")
            else:
                # One or both entities failed to resolve (often because the
                # mention is a generic descriptor like 'antidote' that isn't
                # a PubTator3 entity). Fall back to a keyword query built
                # from whatever resolved + the unresolved mention surface form.
                fallback_terms: list[str] = []
                for m, ent in ((mentions[0], e1), (mentions[1], e2)):
                    fallback_terms.append(ent.name if ent else m.text)
                if relation:
                    fallback_terms.append(relation)
                fallback_query = " ".join(fallback_terms)
                queries.append(fallback_query)
                warnings.append(
                    "known-pair entity resolution incomplete; fell back to "
                    f"keyword query: {fallback_query!r}."
                )
    elif qtype == "single_node":
        if mentions:
            entity = resolved.get(mentions[0].text)
            if entity:
                queries.append(entity.accession)
            else:
                warnings.append(
                    f"Could not resolve '{mentions[0].text}' for single-node search."
                )
    elif qtype == "keyword_search":
        kq = (state.get("keyword_query") or "").strip()
        if kq:
            queries.append(kq)
        else:
            warnings.append("keyword_search needs a non-empty keyword_query.")

    async def _one(q: str):
        return q, await pubtator3_search_articles.ainvoke({"text_query": q})

    seen: set[int] = set()
    pmids: list[int] = []
    total = 0

    if queries:
        results = await asyncio.gather(*(_one(q) for q in queries))
        for q, out in results:
            if out.error:
                warnings.append(f"search failed for '{q}': {out.error}")
                continue
            total += out.total
            for hit in out.hits:
                if hit.pmid not in seen:
                    seen.add(hit.pmid)
                    pmids.append(hit.pmid)

    # Zero-results fallback. Structured PubTator3 queries (relations:|...|...,
    # bare accession) often return nothing even when the literature clearly
    # discusses the topic — BioREx may have tagged the relation under a
    # different vocabulary value, or the entity pair isn't co-mentioned in
    # PubTator3's graph. The router already emits `keyword_query` for every
    # in-scope route precisely as a contingency for this case; we simply
    # re-run search with it as a free-text query (the same code path the
    # keyword_search route uses). If the router didn't fill `keyword_query`
    # (e.g. router error fallback set only question_type), use the user's
    # question verbatim as the catastrophic-failure tier.
    if not pmids and qtype in ("relation_partner_discovery", "relation_known_pair", "single_node"):
        fallback_query = (state.get("keyword_query") or "").strip() or (state.get("question") or "").strip()
        if fallback_query and fallback_query not in queries:
            warnings.append(
                f"structured query returned 0 PMIDs; falling back to "
                f"keyword search: {fallback_query!r}."
            )
            queries.append(fallback_query)
            fb_out = await pubtator3_search_articles.ainvoke({"text_query": fallback_query})
            if fb_out.error:
                warnings.append(f"fallback search failed: {fb_out.error}")
            else:
                total += fb_out.total
                for hit in fb_out.hits:
                    if hit.pmid not in seen:
                        seen.add(hit.pmid)
                        pmids.append(hit.pmid)

    if not pmids:
        warnings.append("No articles found for the constructed query.")

    return {
        "queries_used": queries,
        "pmids": pmids,
        "total_articles": total,
        "warnings": warnings,
    }


async def export_node(state: PubTator3State, *, max_documents: int = 10) -> dict:
    pmids = state.get("pmids") or []
    if not pmids:
        return {
            "documents": [],
            "passages": [],
            "document_relations": [],
        }

    full_text = bool(state.get("full_text", False))

    # PubTator3 /publications/export/biocjson caps at 50 docs per request.
    export_count = min(max_documents, 50)
    pmids_for_export = pmids[:export_count]

    out = await pubtator3_export_passages.ainvoke(
        {"pmids": pmids_for_export, "full_text": full_text}
    )

    warnings = list(state.get("warnings", []))
    if out.error:
        warnings.append(f"export failed: {out.error}")
        return {
            "documents": [],
            "passages": [],
            "document_relations": [],
            "warnings": warnings,
        }

    docs = out.documents
    returned = {d.pmid for d in docs}
    missing = [p for p in pmids_for_export if p not in returned]
    if missing:
        warnings.append(
            f"{len(missing)} PMIDs were not returned by the export endpoint."
        )

    section_filter = state.get("sections") or None
    allowed_body: set[str] | None = set(section_filter) if section_filter else None

    all_passages: list[Passage] = []
    all_doc_relations: list[DocumentRelation] = []
    for d in docs:
        if full_text:
            if allowed_body is None:
                all_passages.extend(d.passages)
            else:
                # Always keep title + abstract; restrict body to the requested set.
                all_passages.extend(
                    p for p in d.passages
                    if p.section in ABSTRACT_ONLY_SECTIONS or p.section in allowed_body
                )
        else:
            # PubTator3 occasionally returns body sections even when full=false
            # was requested (review articles especially). Enforce abstract mode locally.
            all_passages.extend(
                p for p in d.passages if p.section in ABSTRACT_ONLY_SECTIONS
            )
        all_doc_relations.extend(d.relations)

    return {
        "documents": docs,
        "passages": all_passages,
        "document_relations": all_doc_relations,
        "warnings": warnings,
    }


__all__ = [
    "_add_warning",
    "_message_content_to_text",
    "_extract_json_object",
    "_ainvoke_structured_with_json_fallback",
    "_is_confident_match",
    "resolve_node",
    "partner_discovery_node",
    "search_node",
    "export_node",
]
