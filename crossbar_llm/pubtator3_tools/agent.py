"""LangGraph orchestrator for PubTator3 literature evidence.

This module defines `build_graph`, which wires the standalone nodes from
`agents.nodes` together with three inline LLM-bound nodes (router,
synthesizer, depth evaluator) that close over the chat model and prompts.

Pydantic schemas live in `agents.schemas`; token-usage helpers live in
`agents.usage`. The names are re-exported here for backwards compatibility
with code that imported them from this module directly.
"""
from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    MessagesPlaceholder,
    SystemMessagePromptTemplate,
)
from langgraph.graph import END, StateGraph

from crossbar_llm.pubtator3_tools.structured_output import (
    _ainvoke_structured_with_json_fallback,
    _extract_json_object,
    _message_content_to_text,
)
from crossbar_llm.pubtator3_tools.nodes import (
    _add_warning,
    export_node,
    partner_discovery_node,
    resolve_node,
    search_node,
)
from crossbar_llm.pubtator3_tools.prompts import (
    DEPTH_EVAL_SYSTEM_PROMPT,
    ROUTER_SYSTEM_PROMPT,
    SYNTHESIZE_SYSTEM_PROMPT,
)
from crossbar_llm.pubtator3_tools.schemas import (
    DepthEvaluation,
    EntityMention,
    EvaluatorFn,
    PubTator3State,
    QuestionType,
    RouterDecision,
    RouterFn,
    StructuredModel,
    SynthesizerFn,
)
from crossbar_llm.pubtator3_tools.usage import (
    _flatten_usage,
    ainvoke_with_usage_capture,
    ainvoke_with_usage_logging,
)


async def _always_sufficient_evaluator(_state: PubTator3State) -> DepthEvaluation:
    """Default no-op evaluator: declares every answer sufficient and skips the
    refinement loop. Used when no chat_model and no explicit evaluator are
    supplied (test seam) so the existing test path stays single-pass."""
    return DepthEvaluation(sufficient=True, missing=None, rationale="no-op evaluator")


def build_graph(
    *,
    chat_model: BaseChatModel | None = None,
    router: RouterFn | None = None,
    synthesizer: SynthesizerFn | None = None,
    evaluator: EvaluatorFn | None = None,
    max_partners: int = 5,
    max_documents: int = 7,
    abstracts_only: bool = False,
):
    """Compile the PubTator3 LangGraph.

    Pass `chat_model` for production. Pass `router`/`synthesizer`/`evaluator`
    directly to bypass the LLM (test seam). `evaluator` is optional; when
    neither it nor `chat_model` is given, the no-op default treats every
    answer as sufficient and the refinement loop never fires.

    `abstracts_only` is a deployment-level switch that forces title + abstract
    retrieval regardless of what the router or depth evaluator decide. With it
    enabled, the router's `full_text` / `sections` choices are clamped to
    False / None and the depth evaluator's full-text refinement path is
    short-circuited (no second pass). Use it when you want predictable token
    cost and don't need PMC body text.
    """
    if (router is None or synthesizer is None) and chat_model is None:
        raise ValueError(
            "build_graph requires either chat_model, or both router and synthesizer."
        )
    if evaluator is None and chat_model is None:
        evaluator = _always_sufficient_evaluator

    async def router_node(state: PubTator3State) -> dict:
        warnings = list(state.get("warnings", []))
        try:
            if router is not None:
                decision = await router(state["question"])
            else:
                prompt = ChatPromptTemplate.from_messages([
                    SystemMessagePromptTemplate.from_template(ROUTER_SYSTEM_PROMPT),
                    MessagesPlaceholder("chat_history", optional=True),
                    HumanMessagePromptTemplate.from_template("User question: {question}"),
                ])
                decision, used_json_fallback = await _ainvoke_structured_with_json_fallback(
                    chat_model=chat_model,
                    prompt=prompt,
                    schema=RouterDecision,
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
            # Provider-side schema validation (e.g. invented relation value)
            # would otherwise crash the run. Degrade to keyword_search so the
            # user still gets papers.
            warnings.append(f"router failed ({type(e).__name__}); fell back to keyword_search.")
            decision = RouterDecision(
                question_type="keyword_search",
                keyword_query=state["question"],
                rationale=f"router error fallback: {e}",
            )
        return {
            "question_type": decision.question_type,
            "mentions": decision.mentions,
            "relation": decision.relation,
            "e2_type": decision.e2_type,
            "keyword_query": decision.keyword_query,
            "full_text": False if abstracts_only else decision.full_text,
            "sections": None if abstracts_only else decision.sections,
            "rationale": decision.rationale,
            "warnings": warnings,
        }

    async def _partner_discovery(state):
        return await partner_discovery_node(state, max_partners=max_partners)

    async def _export(state):
        return await export_node(state, max_documents=max_documents)

    async def synthesize_node(state: PubTator3State) -> dict:
        if synthesizer is not None:
            answer = await synthesizer(state)
        else:
            ctx_lines: list[str] = []
            for p in state.get("passages", []):
                ctx_lines.append(f"[PMID:{p.pmid}] ({p.section}) {p.text}")
            for r in state.get("document_relations", []):
                ctx_lines.append(
                    f"[PMID:{r.pmid}] relation={r.type} "
                    f"{r.role1_accession or '?'}->{r.role2_accession or '?'} "
                    f"score={r.score:.2f}"
                )
            evidence = "\n".join(ctx_lines) if ctx_lines else "(no passages found)"

            # Full-text requested but only title/abstract sections came back
            # means none of the retrieved papers are PMC Open Access. Surface
            # that caveat so the synthesizer mentions it instead of pretending
            # the answer is full-text-backed.
            full_text_requested = bool(state.get("full_text", False))
            body_sections_present = any(
                p.section not in ("title", "abstract")
                for p in state.get("passages") or []
            )
            availability_note = ""
            if full_text_requested and state.get("passages") and not body_sections_present:
                availability_note = (
                    "\n\nNOTE: full paper body text was requested but none of "
                    "the retrieved PMIDs are PMC Open Access — only titles "
                    "and abstracts are available. End your paragraph with an "
                    "explicit caveat that full-text body was unavailable for "
                    "these papers and the answer is derived from abstracts only."
                )

            prompt = ChatPromptTemplate.from_messages([
                SystemMessagePromptTemplate.from_template(SYNTHESIZE_SYSTEM_PROMPT),
                MessagesPlaceholder("chat_history", optional=True),
                HumanMessagePromptTemplate.from_template(
                    "User question:\n{question}\n\nEvidence:\n{evidence}{availability_note}\n\n"
                    "Write the final answer."
                ),
            ])
            chain = prompt | chat_model
            msg = await chain.ainvoke({
                "question": state["question"],
                "evidence": evidence,
                "availability_note": availability_note,
                "chat_history": state.get("chat_history", []),
            })
            answer = msg.content if isinstance(msg.content, str) else str(msg.content)
        return {"final_answer": answer}

    async def evaluate_depth_node(state: PubTator3State) -> dict:
        # Short-circuit cases — no escalation lever to pull. Each path tags
        # `depth_skip_reason` so downstream tooling (benchmark printer, API
        # response) can distinguish "the LLM said sufficient" from "we skipped
        # the LLM because escalation was impossible / disabled".
        if abstracts_only:
            return {"depth_sufficient": True, "depth_skip_reason": "abstracts_only enabled"}
        if not state.get("final_answer") or not state.get("passages"):
            return {"depth_sufficient": True, "depth_skip_reason": "no answer or no passages"}
        if state.get("refinement_attempted"):
            return {"depth_sufficient": True, "depth_skip_reason": "refinement already attempted"}
        full_text_already = bool(state.get("full_text"))
        current_sections = state.get("sections") or None
        if full_text_already and current_sections is None:
            return {
                "depth_sufficient": True,
                "depth_skip_reason": "already at max depth (full_text + no section filter)",
            }

        warnings = list(state.get("warnings", []))
        current_sections_str = (
            ", ".join(current_sections) if current_sections else "(none — abstracts only so far)"
        )
        try:
            if evaluator is not None:
                verdict = await evaluator(state)
            else:
                prompt = ChatPromptTemplate.from_messages([
                    SystemMessagePromptTemplate.from_template(DEPTH_EVAL_SYSTEM_PROMPT),
                    HumanMessagePromptTemplate.from_template(
                        "User question:\n{question}\n\n"
                        "Generated answer:\n{answer}\n\n"
                        "Retrieval context so far:\n"
                        "- full_text: {full_text}\n"
                        "- current body sections: {current_sections}"
                    ),
                ])
                verdict, used_json_fallback = await _ainvoke_structured_with_json_fallback(
                    chat_model=chat_model,
                    prompt=prompt,
                    schema=DepthEvaluation,
                    values={
                        "question": state["question"],
                        "answer": state["final_answer"],
                        "full_text": full_text_already,
                        "current_sections": current_sections_str,
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
            return {
                "depth_sufficient": True,
                "depth_missing": None,
                "warnings": warnings,
            }

        # Insufficient — refine. Escalation strategy:
        #   1. If we haven't pulled full text yet, flip full_text=True and
        #      honour suggested_sections (or pull everything when unset).
        #   2. If full text is already on but sections is set, UNION the
        #      evaluator's suggested sections with the current set; if the
        #      evaluator gave nothing new, fall back to pulling every body
        #      section (sections=None).
        suggested = verdict.suggested_sections or []
        if not full_text_already:
            next_sections = list(suggested) if suggested else None
            next_full_text = True
        else:
            merged = list(dict.fromkeys([*(current_sections or []), *suggested]))
            # If the union added nothing, drop the filter to pull every section.
            next_sections = merged if suggested and merged != (current_sections or []) else None
            next_full_text = True

        sections_msg = (
            f"sections={next_sections}" if next_sections is not None else "sections=ALL"
        )
        warnings.append(
            f"depth check flagged shallow answer: "
            f"{verdict.missing or 'no specific gap reported'}; "
            f"re-fetching with full_text={next_full_text}, {sections_msg}."
        )
        return {
            "depth_sufficient": False,
            "depth_missing": verdict.missing,
            "full_text": next_full_text,
            "sections": next_sections,
            "refinement_attempted": True,
            "warnings": warnings,
        }

    def _post_evaluate_route(state: PubTator3State) -> str:
        if state.get("depth_sufficient", True):
            return "end"
        if not state.get("refinement_attempted"):
            # Safety net: evaluate_depth_node should have set this, but
            # bail out anyway so we never loop without the cap in place.
            return "end"
        return "refine"

    g = StateGraph(PubTator3State)
    g.add_node("router", router_node)
    g.add_node("resolve", resolve_node)
    g.add_node("partner_discovery", _partner_discovery)
    g.add_node("search", search_node)
    g.add_node("export", _export)
    g.add_node("synthesize", synthesize_node)
    g.add_node("evaluate_depth", evaluate_depth_node)

    g.set_entry_point("router")
    g.add_conditional_edges(
        "router",
        lambda s: s["question_type"],
        {
            "out_of_scope": END,
            "single_node": "resolve",
            "relation_known_pair": "resolve",
            "relation_partner_discovery": "resolve",
            "keyword_search": "search",
        },
    )
    g.add_conditional_edges(
        "resolve",
        lambda s: s["question_type"],
        {
            "single_node": "search",
            "relation_known_pair": "search",
            "relation_partner_discovery": "partner_discovery",
        },
    )
    g.add_edge("partner_discovery", "search")
    g.add_edge("search", "export")
    g.add_edge("export", "synthesize")
    g.add_edge("synthesize", "evaluate_depth")
    g.add_conditional_edges(
        "evaluate_depth",
        _post_evaluate_route,
        {"end": END, "refine": "export"},
    )

    return g.compile()


__all__ = [
    # Re-exported schemas (backwards compat with old imports).
    "QuestionType",
    "StructuredModel",
    "EntityMention",
    "RouterDecision",
    "DepthEvaluation",
    "PubTator3State",
    "RouterFn",
    "SynthesizerFn",
    "EvaluatorFn",
    # Re-exported nodes (backwards compat).
    "resolve_node",
    "partner_discovery_node",
    "search_node",
    "export_node",
    "_add_warning",
    "_message_content_to_text",
    "_extract_json_object",
    "_ainvoke_structured_with_json_fallback",
    # Re-exported usage helpers (backwards compat).
    "_flatten_usage",
    "ainvoke_with_usage_capture",
    "ainvoke_with_usage_logging",
    # Core builder + default evaluator.
    "build_graph",
    "_always_sufficient_evaluator",
]
