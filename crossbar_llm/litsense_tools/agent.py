"""The agent: the pipeline as a class.

`LitSenseAgent` is the whole public surface — the team's API instantiates it and calls
`answer` (or `run`, for the full pipeline state). It owns graph assembly and the client's
lifecycle; the `client` and `synthesizer` constructor parameters exist as seams: tests hand
in a fake transport and a fake synthesizer, production leaves them None and gets the real
ones. The pipeline itself stays linear by design — no retrieval retry loop, no query
rewriting (CLAUDE.md) — with one sanctioned exception: the supervisor-mandated relevance
gate, whose negative verdict routes straight to END (ADR-008).

The nodes here only orchestrate; `select` and `validate` — the two places correctness
actually lives — remain pure functions in `graph/nodes.py` (invariant 4).
"""

from __future__ import annotations

from types import TracebackType
from typing import Any, Self

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from crossbar_llm.litsense_tools.client import LitSenseClient
from crossbar_llm.litsense_tools.config import Settings
from crossbar_llm.litsense_tools.graph.nodes import (
    FULL_TEXT_SECTION,
    fetch_articles,
    gate_answer,
    pipeline_warnings,
    refine_articles,
    relevance_warning,
    select,
    synthesize,
    validate,
)
from crossbar_llm.litsense_tools.graph.state import PipelineState
from crossbar_llm.litsense_tools.llm import (
    DepthEvaluator,
    RelevanceChecker,
    Synthesizer,
    UsageCollector,
    build_depth_evaluator,
    build_relevance_checker,
    build_synthesizer,
)
from crossbar_llm.litsense_tools.models import Answer, DepthVerdict
from crossbar_llm.litsense_tools.prompts import depth_messages, relevance_messages


class LitSenseAgent:
    """Grounded question answering over the biomedical literature.

    Configure once, ask many questions — every question shares the same client, so the rate
    limiter and the per-pmid cache work across calls. The agent owns the client's lifecycle
    only when it created the client; a caller that passes one in (to share a rate-limit
    budget, or a fake in tests) keeps responsibility for closing it. Use as an async context
    manager, or call `aclose` when done.
    """

    def __init__(
        self,
        config: Settings,
        *,
        client: LitSenseClient | None = None,
        synthesizer: Synthesizer | None = None,
        relevance_checker: RelevanceChecker | None = None,
        depth_evaluator: DepthEvaluator | None = None,
    ) -> None:
        self._config = config
        self._owns_client = client is None
        self._client = client if client is not None else LitSenseClient(config)
        self._synthesizer = (
            synthesizer if synthesizer is not None else build_synthesizer(config)
        )
        # Optional nodes only build their model access when they are on: no gate, no
        # model resolution for it; same for the depth loop (ADR-008, ADR-009).
        self._relevance_checker: RelevanceChecker | None = None
        if config.relevance_gate:
            self._relevance_checker = (
                relevance_checker
                if relevance_checker is not None
                else build_relevance_checker(config)
            )
        self._depth_evaluator: DepthEvaluator | None = None
        if config.full_text:
            self._depth_evaluator = (
                depth_evaluator
                if depth_evaluator is not None
                else build_depth_evaluator(config)
            )
        self._graph = self._build_graph()

    # --- lifecycle ---------------------------------------------------------------------

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # --- public API --------------------------------------------------------------------

    async def answer(self, question: str) -> Answer:
        """Answer one question, grounded in the biomedical literature."""
        state = await self.run(question)
        if state.answer is None:  # pragma: no cover — the linear graph always sets it
            raise RuntimeError("pipeline finished without producing an answer")
        return state.answer

    async def run(self, question: str) -> PipelineState:
        """Run the pipeline once and return the **full final state**, not just the answer.

        This is the inspection surface: everything the pipeline saw and decided — raw hits,
        the selection, the fetched contexts, what failed — comes back for callers that want
        to look inside (notebooks, future evaluation harnesses). `usage` on the returned
        state sums the tokens of every model call the run made (benchmark token cost).
        """
        usage = UsageCollector()
        final = await self._graph.ainvoke(
            PipelineState(question=question), config={"callbacks": [usage]}
        )
        state = PipelineState.model_validate(final)
        state.usage = usage.usage
        return state

    # --- nodes -------------------------------------------------------------------------

    async def _relevance_node(self, state: PipelineState) -> dict[str, Any]:
        assert self._relevance_checker is not None  # node only exists when the gate is on
        verdict = await self._relevance_checker(relevance_messages(state.question))
        update: dict[str, Any] = {"relevance": verdict}
        if not verdict.relevant:
            update["answer"] = gate_answer(verdict)
        return update

    def _route_after_relevance(self, state: PipelineState) -> str:
        assert state.relevance is not None  # the gate node just ran
        return "search" if state.relevance.relevant else END

    async def _search_node(self, state: PipelineState) -> dict[str, Any]:
        return {"hits": await self._client.search_sentences(state.question)}

    def _select_node(self, state: PipelineState) -> dict[str, Any]:
        selection = select(
            state.hits,
            max_articles=self._config.max_articles,
            min_score=self._config.min_score,
        )
        return {"selection": selection}

    async def _fetch_node(self, state: PipelineState) -> dict[str, Any]:
        assert state.selection is not None  # linear graph: select has run
        articles, failed = await fetch_articles(
            state.selection.articles, self._client, section=self._config.section
        )
        return {"articles": articles, "failed_pmids": failed}

    async def _synthesize_node(self, state: PipelineState) -> dict[str, Any]:
        output = await synthesize(
            state.question,
            state.articles,
            self._synthesizer,
            style=self._config.answer_style,
        )
        return {"output": output}

    async def _depth_node(self, state: PipelineState) -> dict[str, Any]:
        """Judge the answer's depth — once. After the refinement pass, the verdict stands."""
        assert self._depth_evaluator is not None and state.output is not None
        if state.refined:
            return {}
        if not state.articles:
            # Nothing was fetched, so there is nothing full text could deepen.
            return {"depth": DepthVerdict(sufficient=True)}
        verdict = await self._depth_evaluator(
            depth_messages(state.question, state.output.text)
        )
        return {"depth": verdict}

    def _route_after_depth(self, state: PipelineState) -> str:
        assert state.depth is not None
        if state.refined or state.depth.sufficient:
            return "validate"
        return "refine"

    async def _refine_node(self, state: PipelineState) -> dict[str, Any]:
        assert state.output is not None
        articles, failed = await refine_articles(
            state.articles,
            cited=set(state.output.citations),
            client=self._client,
            max_chars=self._config.full_text_max_chars,
        )
        return {"articles": articles, "fulltext_failed_pmcids": failed, "refined": True}

    def _route_after_refine(self, state: PipelineState) -> str:
        """Re-synthesize only when refinement actually upgraded something."""
        if any(article.section == FULL_TEXT_SECTION for article in state.articles):
            return "synthesize"
        return "validate"

    def _validate_node(self, state: PipelineState) -> dict[str, Any]:
        assert state.selection is not None and state.output is not None
        low = relevance_warning(state.hits, threshold=self._config.low_relevance_score)
        warnings = ([low] if low is not None else []) + pipeline_warnings(
            state.selection, state.failed_pmids
        )
        if state.fulltext_failed_pmcids:
            warnings.append(
                "full text could not be fetched (answered from abstracts) for: "
                + ", ".join(state.fulltext_failed_pmcids)
            )
        answer = validate(
            state.output,
            fetched_pmids={article.pmid for article in state.articles},
            warnings=warnings,
            articles=state.articles,
        )
        return {"answer": answer}

    def _build_graph(self) -> CompiledStateGraph[PipelineState]:
        """(relevance ⇒) search → select → fetch → synthesize (→ depth ⇄ refine) → validate.

        Two sanctioned departures from the linear pipeline: the ADR-008 gate's exit, and
        the ADR-009 depth loop — at most one refinement pass, enforced by `state.refined`.
        With the gate off and `full_text` off, the graph is fully linear.
        """
        graph: StateGraph[PipelineState] = StateGraph(PipelineState)
        graph.add_node("search", self._search_node)
        graph.add_node("select", self._select_node)
        graph.add_node("fetch", self._fetch_node)
        graph.add_node("synthesize", self._synthesize_node)
        graph.add_node("validate", self._validate_node)
        if self._relevance_checker is not None:
            graph.add_node("relevance", self._relevance_node)
            graph.add_edge(START, "relevance")
            graph.add_conditional_edges(
                "relevance", self._route_after_relevance, {"search": "search", END: END}
            )
        else:
            graph.add_edge(START, "search")
        graph.add_edge("search", "select")
        graph.add_edge("select", "fetch")
        graph.add_edge("fetch", "synthesize")
        if self._depth_evaluator is not None:
            graph.add_node("depth", self._depth_node)
            graph.add_node("refine", self._refine_node)
            graph.add_edge("synthesize", "depth")
            graph.add_conditional_edges(
                "depth", self._route_after_depth, {"refine": "refine", "validate": "validate"}
            )
            graph.add_conditional_edges(
                "refine",
                self._route_after_refine,
                {"synthesize": "synthesize", "validate": "validate"},
            )
        else:
            graph.add_edge("synthesize", "validate")
        graph.add_edge("validate", END)
        return graph.compile()


async def run_pipeline(
    question: str,
    config: Settings,
    *,
    client: LitSenseClient | None = None,
    synthesizer: Synthesizer | None = None,
    relevance_checker: RelevanceChecker | None = None,
    depth_evaluator: DepthEvaluator | None = None,
) -> PipelineState:
    """One-shot convenience wrapper: build an agent, run one question, tear it down."""
    async with LitSenseAgent(
        config,
        client=client,
        synthesizer=synthesizer,
        relevance_checker=relevance_checker,
        depth_evaluator=depth_evaluator,
    ) as agent:
        return await agent.run(question)


async def answer_question(
    question: str,
    config: Settings,
    *,
    client: LitSenseClient | None = None,
    synthesizer: Synthesizer | None = None,
    relevance_checker: RelevanceChecker | None = None,
    depth_evaluator: DepthEvaluator | None = None,
) -> Answer:
    """One-shot convenience wrapper for callers that only want the answer."""
    async with LitSenseAgent(
        config,
        client=client,
        synthesizer=synthesizer,
        relevance_checker=relevance_checker,
        depth_evaluator=depth_evaluator,
    ) as agent:
        return await agent.answer(question)
