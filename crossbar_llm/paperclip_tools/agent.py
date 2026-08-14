"""LangGraph orchestrator for Paperclip literature evidence.

`build_graph` wires the standalone data-plumbing nodes from `paperclip_nodes`
(which call the Paperclip MCP adapter) together with three inline LLM-bound nodes
(router, synthesizer, depth evaluator) that close over the chat model and
prompts. It mirrors PubTator3's `build_graph` shape and its injectable seams so
the two tools share one external contract:

    question (+ shared state) in -> {final_answer, citations, warnings, usage} out

The Paperclip module is architecturally asymmetric with PubTator3 (a thin
MCP-adapter subgraph vs. a hand-built REST subgraph); that is deliberate — the
shared contract is what the top-level graph depends on, not the internals.
"""
from __future__ import annotations

import re

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    MessagesPlaceholder,
    SystemMessagePromptTemplate,
)
from langgraph.graph import END, StateGraph

# Reuse PubTator3's provider-agnostic structured-output helper (function-calling
# first, plain-JSON fallback) rather than re-deriving it.
from crossbar_llm.paperclip_tools.structured_output import (
    _ainvoke_structured_with_json_fallback,
)
from crossbar_llm.paperclip_tools.nodes import (
    _add_warning,
    assemble_context_node,
    filter_node,
    search_node,
    sql_node,
)
from crossbar_llm.paperclip_tools.prompts import (
    PAPERCLIP_DEPTH_EVAL_SYSTEM_PROMPT,
    PAPERCLIP_ROUTER_SYSTEM_PROMPT,
    PAPERCLIP_SQL_SYNTHESIZE_SYSTEM_PROMPT,
    PAPERCLIP_SYNTHESIZE_SYSTEM_PROMPT,
)
from crossbar_llm.paperclip_tools.schemas import (
    PaperclipDepthEvaluation,
    PaperclipEvaluatorFn,
    PaperclipRouterDecision,
    PaperclipRouterFn,
    PaperclipState,
    PaperclipSynthesizerFn,
)
from crossbar_llm.paperclip_tools.adapter import (
    PaperclipAdapterProtocol,
    PaperclipAdapter,
)


async def _always_sufficient_evaluator(_state: PaperclipState) -> PaperclipDepthEvaluation:
    """Default no-op evaluator: declares every answer sufficient and skips the
    refinement loop. Used when no chat_model and no explicit evaluator are given
    (test seam) so the default path stays single-pass."""
    return PaperclipDepthEvaluation(sufficient=True, missing=None, rationale="no-op evaluator")


def _format_documents(state: PaperclipState) -> str:
    """Render the assembled papers into the numbered evidence block the
    synthesizer reads. Reference numbers align with `state['citations']`.

    Includes the citation URL explicitly: the synthesis prompt's mandatory
    References format ends every entry with `— <url>`, so the model needs
    the real value here rather than being left to guess or omit it — a real
    gap this used to have (URL was in `state['citations']` but never
    actually surfaced in the text the model reads)."""
    docs = state.get("documents") or []
    citations = {c.doc_id: c for c in (state.get("citations") or [])}
    if not docs:
        return "(no papers found)"
    blocks: list[str] = []
    for doc in docs:
        cit = citations.get(doc.doc_id)
        ref = cit.ref_num if cit else "?"
        url = cit.url if cit else ""
        meta = doc.meta
        header = (
            f"[{ref}] {meta.title}\n"
            f"    Authors: {meta.authors or 'n/a'}\n"
            f"    Journal: {meta.journal or 'n/a'} ({meta.pub_year or 'n/a'})  "
            f"doi:{meta.doi or 'n/a'}  pmid:{meta.pmid or 'n/a'}\n"
            f"    URL: {url or 'n/a'}\n"
            f"    Abstract: {meta.abstract or '(no abstract)'}"
        )
        if doc.body:
            header += f"\n    Evidence (full text / map extraction):\n{doc.body}"
        blocks.append(header)
    return "\n\n".join(blocks)


def _format_sql_result(state: PaperclipState) -> str:
    """Render the SQL query + result table for `PAPERCLIP_SQL_SYNTHESIZE_SYSTEM_PROMPT`.

    Caps what's shown to the LLM at 50 rows — `sql`'s own 200-row server cap
    is already generous for an aggregate query; this is just a token-budget
    guard for the rare case a query legitimately returns close to that cap.
    """
    query = state.get("sql_query") or ""
    columns = state.get("sql_columns") or []
    rows = state.get("sql_rows") or []
    header = f"Query:\n{query}\n\n"
    if not rows:
        return header + "(No rows returned.)"
    col_line = " | ".join(columns)
    lines = [col_line, "-" * len(col_line)]
    for row in rows[:50]:
        lines.append(" | ".join(str(row.get(c, "")) for c in columns))
    table = "\n".join(lines)
    more = f"\n... and {len(rows) - 50} more rows" if len(rows) > 50 else ""
    plural = "s" if len(rows) != 1 else ""
    return f"{header}Results ({len(rows)} row{plural}):\n{table}{more}"


def _is_sql_success(state: PaperclipState) -> bool:
    return state.get("question_type") == "sql_aggregate" and not state.get("sql_error")


_RULE_CHARS = re.escape("-=_*#~")
_DEGENERATE_RUN_RES = (
    # Rule characters repeat legitimately: a markdown table's alignment row is
    # routinely 30+ dashes and trimming one stops the table rendering, so these
    # only count as degenerate far past any real formatting.
    re.compile(rf"([{_RULE_CHARS}])\1{{199,}}"),
    re.compile(rf"([^\w\s{_RULE_CHARS}])\1{{29,}}"),
)


def _collapse_degenerate_runs(text: str) -> tuple[str, int]:
    """Cut back pathological punctuation repetition in a model's answer.

    Models occasionally lock into emitting one character for thousands of
    tokens, typically at the tail of a numbered reference list. The prose
    before the run is intact, so the run is trimmed rather than the answer
    discarded, and a recovery after the run is preserved. Thirty clears any
    real use of repeated punctuation (`...`, `???`) while still catching the
    shortest run we have observed, which was 41.
    """
    total = 0
    for pattern in _DEGENERATE_RUN_RES:
        text, n = pattern.subn(lambda m: m.group(1) * 3, text)
        total += n
    return text, total


def build_graph(
    *,
    chat_model: BaseChatModel | None = None,
    router: PaperclipRouterFn | None = None,
    synthesizer: PaperclipSynthesizerFn | None = None,
    evaluator: PaperclipEvaluatorFn | None = None,
    adapter: PaperclipAdapterProtocol | None = None,
    max_documents: int = 7,
    content_max_lines: int | None = None,
    abstracts_only: bool = True,
    use_map: bool = True,
    use_filter: bool = False,
):
    """Compile the Paperclip LangGraph.

    Pass `chat_model` for production. Pass `router`/`synthesizer`/`evaluator`
    directly to bypass the LLM (test seam). Pass `adapter` to inject a fake
    Paperclip MCP adapter (the single MCP seam); defaults to a live
    `PaperclipAdapter`. `evaluator` is optional; when neither it nor
    `chat_model` is given, the no-op default treats every answer as sufficient
    and the refinement loop never fires.

    `abstracts_only` forces title+abstract retrieval regardless of the router's
    `full_text` choice and short-circuits the depth-refinement pass — use it for
    predictable token cost.

    `use_map` (ON by default) runs Paperclip's `map` over the search results: it
    reads each paper's FULL TEXT server-side and extracts an answer to the
    question per paper, used as the evidence body. This boosts recall on detail
    questions without pulling whole bodies through our tokens (it costs Paperclip
    tokens + latency instead). Independent of `abstracts_only`; set it False to
    synthesize from abstracts only.

    `use_filter` (OFF by default) runs Paperclip's `filter` on the search hits
    before `assemble`, trimming to server-judged relevant papers. REST-only and
    best-effort (see `PaperclipAdapter.filter`/`filter_node`) — any failure or
    unavailability reverts to the unfiltered hits rather than failing the run.
    """
    if (router is None or synthesizer is None) and chat_model is None:
        raise ValueError(
            "build_graph requires either chat_model, or both router and synthesizer."
        )
    if evaluator is None and chat_model is None:
        evaluator = _always_sufficient_evaluator
    if adapter is None:
        adapter = PaperclipAdapter()

    async def router_node(state: PaperclipState) -> dict:
        warnings = list(state.get("warnings", []))
        try:
            if router is not None:
                decision = await router(state["question"])
            else:
                prompt = ChatPromptTemplate.from_messages([
                    SystemMessagePromptTemplate.from_template(PAPERCLIP_ROUTER_SYSTEM_PROMPT),
                    MessagesPlaceholder("chat_history", optional=True),
                    HumanMessagePromptTemplate.from_template("User question: {question}"),
                ])
                decision, used_json_fallback = await _ainvoke_structured_with_json_fallback(
                    chat_model=chat_model,
                    prompt=prompt,
                    schema=PaperclipRouterDecision,
                    values={
                        "question": state["question"],
                        "chat_history": state.get("chat_history", []),
                    },
                    json_instruction=(
                        "The previous instruction defines the exact routing schema. "
                        "Return ONLY a valid JSON object for that schema. Do not use "
                        "Markdown, prose, tool calls, or extra keys."
                    ),
                )
                if used_json_fallback:
                    warnings.append(
                        "router structured-output unavailable; used JSON fallback."
                    )
        except Exception as e:
            # Degrade to keyword_search rather than crash the run.
            warnings.append(
                f"router failed ({type(e).__name__}); fell back to keyword_search."
            )
            decision = PaperclipRouterDecision(
                question_type="keyword_search",
                source="pmc",
                search_query=state["question"],
                map_question=state["question"],
                rationale=f"router error fallback: {e}",
            )
        return {
            "question_type": decision.question_type,
            "source": decision.source,
            "search_query": decision.search_query,
            "analogical_query": decision.analogical_query,
            "map_question": decision.map_question,
            "sql_query": decision.sql_query,
            "full_text": False if abstracts_only else decision.full_text,
            "sections": None if abstracts_only else decision.sections,
            "year": decision.year,
            "rationale": decision.rationale,
            "warnings": warnings,
        }

    async def _search(state):
        return await search_node(
            state, adapter=adapter, max_documents=max_documents, use_filter=use_filter
        )

    async def _sql(state):
        return await sql_node(state, adapter=adapter)

    async def _filter(state):
        return await filter_node(state, adapter=adapter, use_filter=use_filter)

    async def _assemble(state):
        return await assemble_context_node(
            state,
            adapter=adapter,
            max_documents=max_documents,
            content_max_lines=content_max_lines,
            use_map=use_map,
        )

    async def synthesize_node(state: PaperclipState) -> dict:
        if synthesizer is not None:
            answer = await synthesizer(state)
        else:
            if _is_sql_success(state):
                evidence = _format_sql_result(state)
                system_prompt = PAPERCLIP_SQL_SYNTHESIZE_SYSTEM_PROMPT
            else:
                evidence = _format_documents(state)
                system_prompt = PAPERCLIP_SYNTHESIZE_SYSTEM_PROMPT
            prompt = ChatPromptTemplate.from_messages([
                SystemMessagePromptTemplate.from_template(system_prompt),
                MessagesPlaceholder("chat_history", optional=True),
                HumanMessagePromptTemplate.from_template(
                    "User question:\n{question}\n\nEvidence:\n{evidence}\n\n"
                    "Write the final answer."
                ),
            ])
            chain = prompt | chat_model
            msg = await chain.ainvoke({
                "question": state["question"],
                "evidence": evidence,
                "chat_history": state.get("chat_history", []),
            })
            answer = msg.content if isinstance(msg.content, str) else str(msg.content)
        answer, degenerate_runs = _collapse_degenerate_runs(answer)
        if degenerate_runs:
            return {
                "final_answer": answer,
                "warnings": _add_warning(
                    state,
                    f"synthesize: trimmed {degenerate_runs} degenerate character "
                    "run(s) from the model's answer",
                ),
            }
        return {"final_answer": answer}

    async def evaluate_depth_node(state: PaperclipState) -> dict:
        # Short-circuit cases — no escalation lever to pull.
        if _is_sql_success(state):
            return {
                "depth_sufficient": True,
                "depth_skip_reason": "sql_aggregate has no full-text escalation lever",
            }
        if abstracts_only:
            return {"depth_sufficient": True, "depth_skip_reason": "abstracts_only enabled"}
        if not state.get("final_answer") or not state.get("documents"):
            return {"depth_sufficient": True, "depth_skip_reason": "no answer or no documents"}
        if state.get("refinement_attempted"):
            return {"depth_sufficient": True, "depth_skip_reason": "refinement already attempted"}
        if state.get("full_text"):
            return {"depth_sufficient": True, "depth_skip_reason": "already at full-text depth"}

        warnings = list(state.get("warnings", []))
        try:
            if evaluator is not None:
                verdict = await evaluator(state)
            else:
                prompt = ChatPromptTemplate.from_messages([
                    SystemMessagePromptTemplate.from_template(PAPERCLIP_DEPTH_EVAL_SYSTEM_PROMPT),
                    HumanMessagePromptTemplate.from_template(
                        "User question:\n{question}\n\n"
                        "Generated answer (abstracts-only):\n{answer}"
                    ),
                ])
                verdict, used_json_fallback = await _ainvoke_structured_with_json_fallback(
                    chat_model=chat_model,
                    prompt=prompt,
                    schema=PaperclipDepthEvaluation,
                    values={
                        "question": state["question"],
                        "answer": state["final_answer"],
                    },
                    json_instruction=(
                        "Return ONLY a valid JSON object for the depth-evaluation "
                        "schema. Do not use Markdown, prose, tool calls, or extra keys."
                    ),
                )
                if used_json_fallback:
                    warnings.append(
                        "depth evaluator structured-output unavailable; used JSON fallback."
                    )
        except Exception as e:
            warnings.append(
                f"depth evaluator failed ({type(e).__name__}); accepting answer as-is."
            )
            return {
                "depth_sufficient": True,
                "depth_skip_reason": f"evaluator error ({type(e).__name__}: {e})",
                "warnings": warnings,
            }

        if verdict.sufficient:
            return {"depth_sufficient": True, "depth_missing": None, "warnings": warnings}

        warnings.append(
            f"depth check flagged shallow answer: "
            f"{verdict.missing or 'no specific gap reported'}; "
            f"re-fetching with full text."
        )
        return {
            "depth_sufficient": False,
            "depth_missing": verdict.missing,
            "full_text": True,
            "refinement_attempted": True,
            "warnings": warnings,
        }

    def _post_evaluate_route(state: PaperclipState) -> str:
        if state.get("depth_sufficient", True):
            return "end"
        if not state.get("refinement_attempted"):
            return "end"  # safety net — never loop without the cap
        return "refine"

    g = StateGraph(PaperclipState)
    g.add_node("router", router_node)
    g.add_node("search", _search)
    g.add_node("sql", _sql)
    g.add_node("filter", _filter)
    g.add_node("assemble", _assemble)
    g.add_node("synthesize", synthesize_node)
    g.add_node("evaluate_depth", evaluate_depth_node)

    g.set_entry_point("router")
    g.add_conditional_edges(
        "router",
        lambda s: s["question_type"],
        {
            "out_of_scope": END,
            "keyword_search": "search",
            "list_breadth": "search",
            "full_text_depth": "search",
            "analogical_search": "search",
            "sql_aggregate": "sql",
        },
    )
    # sql_node never fails the run: on a bad/timed-out query it sets
    # sql_error and leaves hits/search_id unset, so this falls through to
    # the normal search path using the router's search_query fallback —
    # same shape as search_node's own zero-result fallback.
    g.add_conditional_edges(
        "sql",
        lambda s: "search" if s.get("sql_error") else "synthesize",
        {"search": "search", "synthesize": "synthesize"},
    )
    g.add_edge("search", "filter")
    g.add_edge("filter", "assemble")
    g.add_edge("assemble", "synthesize")
    g.add_edge("synthesize", "evaluate_depth")
    g.add_conditional_edges(
        "evaluate_depth",
        _post_evaluate_route,
        {"end": END, "refine": "assemble"},
    )

    return g.compile()


__all__ = [
    "build_graph",
    "_always_sufficient_evaluator",
    "_format_documents",
    "_format_sql_result",
]
