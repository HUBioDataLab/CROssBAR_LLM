"""The wired pipeline, end to end on a fake transport and a fake synthesizer.

What is worth testing here is not each node again — it is that the pipeline stays standing
when parts of it degrade: a fetch that fails, a citation that was never fetched, a hit with no
pmid. A degraded answer is fine; a silent one is not.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import httpx

from crossbar_llm.litsense_tools import LitSenseAgent, Settings, answer_question, run_pipeline
from crossbar_llm.litsense_tools.client import LitSenseClient
from crossbar_llm.litsense_tools.graph.nodes import GATE_WARNING, NO_CONTEXT_ANSWER
from crossbar_llm.litsense_tools.llm import (
    DRY_RUN_TEXT,
    build_dry_run_relevance_checker,
    build_dry_run_synthesizer,
)
from crossbar_llm.litsense_tools.models import DepthVerdict, RelevanceVerdict, SynthesisOutput
from crossbar_llm.litsense_tools.prompts import Message

MISSING_BODY = {"detail": "Can not retrieve publications : Publication not found"}


def hit(
    pmid: int | None,
    score: float,
    text: str,
    annotations: list[str] | None = None,
    pmcid: str | None = None,
) -> dict[str, Any]:
    return {
        "pmid": pmid,
        "pmcid": pmcid,
        "text": text,
        "score": score,
        "section": "abstract",
        "annotations": annotations,
    }


def publication(pmid: int, title: str, abstract: str) -> dict[str, Any]:
    return {
        "pmid": pmid,
        "passages": [
            {"infons": {"type": "title"}, "offset": 0, "text": title},
            {"infons": {"type": "abstract"}, "offset": 1, "text": abstract},
        ],
    }


class FakeApi:
    """Routes search, publication and full-text requests the way the live APIs answer them."""

    def __init__(
        self,
        hits: list[dict[str, Any]],
        publications: dict[int, dict[str, Any]],
        full_texts: dict[str, str] | None = None,
    ) -> None:
        self.hits = hits
        self.publications = publications
        self.full_texts = full_texts or {}  # pmcid -> narrative body text
        self.requests: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.requests.append(path)
        if path.endswith("/api/sentences/"):
            return httpx.Response(200, json=self.hits)
        if "/BioC_json/" in path:
            pmcid = path.split("/BioC_json/")[1].split("/")[0]
            if pmcid not in self.full_texts:
                # The live service's "no result": 200 with an HTML error page.
                return httpx.Response(
                    200, text="[Error] : No result", headers={"content-type": "text/html"}
                )
            wrapper = [{"documents": [{"passages": [
                {"infons": {"section_type": "RESULTS"}, "text": self.full_texts[pmcid]},
            ]}]}]
            return httpx.Response(200, json=wrapper)
        pmid = int(path.rsplit("/", 1)[-1])
        if pmid in self.publications:
            return httpx.Response(200, json=self.publications[pmid])
        return httpx.Response(500, json=MISSING_BODY)

    @property
    def fulltext_requests(self) -> list[str]:
        return [p for p in self.requests if "/BioC_json/" in p]


class FakeSynthesizer:
    def __init__(self, output: SynthesisOutput) -> None:
        self.output = output
        self.calls: list[list[Message]] = []

    async def __call__(self, messages: Sequence[Message]) -> SynthesisOutput:
        self.calls.append(list(messages))
        return self.output


class FakeRelevanceChecker:
    def __init__(self, verdict: RelevanceVerdict) -> None:
        self.verdict = verdict
        self.calls: list[list[Message]] = []

    async def __call__(self, messages: Sequence[Message]) -> RelevanceVerdict:
        self.calls.append(list(messages))
        return self.verdict


class FakeDepthEvaluator:
    def __init__(self, verdict: DepthVerdict) -> None:
        self.verdict = verdict
        self.calls: list[list[Message]] = []

    async def __call__(self, messages: Sequence[Message]) -> DepthVerdict:
        self.calls.append(list(messages))
        return self.verdict


def settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "model": "test:model",
        "requests_per_second": 10_000.0,
        "max_retries": 0,
        "max_articles": 10,
        # Off by default here so the pre-gate tests exercise the linear graph unchanged;
        # the gate tests below turn it on and inject a fake checker.
        "relevance_gate": False,
    }
    return Settings(**{**defaults, **overrides})  # type: ignore[arg-type]


def client_for(api: FakeApi, config: Settings) -> LitSenseClient:
    return LitSenseClient(config, transport=httpx.MockTransport(api))


async def run(
    api: FakeApi, output: SynthesisOutput, config: Settings | None = None
) -> tuple[Any, FakeSynthesizer]:
    config = config or settings()
    synthesizer = FakeSynthesizer(output)
    async with client_for(api, config) as client:
        answer = await answer_question(
            "What does TP53 do?", config, client=client, synthesizer=synthesizer
        )
    return answer, synthesizer


async def test_happy_path_answers_with_validated_citations() -> None:
    api = FakeApi(
        hits=[hit(101, 0.9, "s1"), hit(102, 0.8, "s2"), hit(101, 0.7, "s3")],
        publications={
            101: publication(101, "T101", "A101"),
            102: publication(102, "T102", "A102"),
        },
    )
    answer, synthesizer = await run(api, SynthesisOutput(text="grounded", citations=[101]))

    assert answer.text == "grounded"
    assert answer.citations == [101]
    assert answer.warnings == []
    # the model saw both articles, ranked, with their matched sentences
    user_message = synthesizer.calls[0][1][1]
    assert user_message.index("[PMID 101]") < user_message.index("[PMID 102]")
    assert "- s1" in user_message and "- s3" in user_message
    assert "A101" in user_message


async def test_a_hallucinated_citation_is_dropped_with_a_warning() -> None:
    api = FakeApi(hits=[hit(101, 0.9, "s1")], publications={101: publication(101, "T", "A")})
    answer, _ = await run(api, SynthesisOutput(text="a", citations=[101, 424242]))
    assert answer.citations == [101]
    assert any("424242" in warning for warning in answer.warnings)


async def test_an_unresolvable_pmid_drops_the_article_not_the_pipeline() -> None:
    api = FakeApi(
        hits=[hit(101, 0.9, "s1"), hit(666, 0.8, "s2")],
        publications={101: publication(101, "T", "A")},
    )
    answer, synthesizer = await run(api, SynthesisOutput(text="a", citations=[101]))
    assert answer.citations == [101]
    assert any("666" in warning for warning in answer.warnings)
    assert "[PMID 666]" not in synthesizer.calls[0][1][1]


async def test_every_fetch_failing_yields_the_insufficient_answer_without_an_llm_call() -> None:
    api = FakeApi(hits=[hit(666, 0.9, "s")], publications={})
    answer, synthesizer = await run(api, SynthesisOutput(text="never"))
    assert synthesizer.calls == []
    assert answer.text == NO_CONTEXT_ANSWER
    assert answer.insufficient_context is True
    assert answer.citations == []
    assert any("666" in warning for warning in answer.warnings)


async def test_hits_without_pmid_are_reported_in_the_answer_warnings() -> None:
    api = FakeApi(
        hits=[hit(None, 0.95, "pmc-only"), hit(101, 0.9, "s1")],
        publications={101: publication(101, "T", "A")},
    )
    answer, _ = await run(api, SynthesisOutput(text="a", citations=[101]))
    assert any("no pmid" in warning for warning in answer.warnings)


async def test_max_articles_bounds_the_fetch_fan_out() -> None:
    api = FakeApi(
        hits=[hit(100 + i, 0.9 - i / 100, f"s{i}") for i in range(5)],
        publications={100 + i: publication(100 + i, f"T{i}", f"A{i}") for i in range(5)},
    )
    config = settings(max_articles=2)
    answer, synthesizer = await run(api, SynthesisOutput(text="a", citations=[100, 101]), config)
    user_message = synthesizer.calls[0][1][1]
    assert "[PMID 100]" in user_message and "[PMID 101]" in user_message
    assert "[PMID 102]" not in user_message
    assert answer.citations == [100, 101]


async def test_a_uniformly_weak_search_flags_the_answer_as_low_relevance() -> None:
    """ADR-007: the nonsense-query signature (full page, low ceiling) must not pass silently."""
    api = FakeApi(
        hits=[hit(101, 0.54, "weak"), hit(102, 0.5, "weaker")],
        publications={101: publication(101, "T", "A"), 102: publication(102, "T2", "A2")},
    )
    answer, _ = await run(api, SynthesisOutput(text="a", citations=[101]))
    assert any("relevance is low" in warning for warning in answer.warnings)
    assert answer.citations == [101]  # advisory: the pipeline still ran to completion


async def test_run_pipeline_exposes_the_intermediate_state() -> None:
    """The inspection surface: hits, selection and contexts survive into the final state."""
    api = FakeApi(
        hits=[hit(101, 0.9, "s1"), hit(102, 0.8, "s2")],
        publications={101: publication(101, "T101", "A101"), 102: publication(102, "T2", "A2")},
    )
    config = settings()
    async with client_for(api, config) as client:
        state = await run_pipeline(
            "q", config, client=client, synthesizer=FakeSynthesizer(SynthesisOutput(text="a"))
        )
    assert [h.pmid for h in state.hits] == [101, 102]
    assert state.selection is not None and state.selection.pmids == [101, 102]
    assert [a.text for a in state.articles] == ["A101", "A2"]
    assert state.answer is not None and state.answer.text == "a"


async def test_a_dry_run_consults_no_model_and_still_fetches_for_real() -> None:
    """The team-LLM seam: retrieval runs end to end while synthesis stays unconnected."""
    api = FakeApi(hits=[hit(101, 0.9, "s1")], publications={101: publication(101, "T", "A")})
    config = settings()
    async with client_for(api, config) as client:
        state = await run_pipeline(
            "q", config, client=client, synthesizer=build_dry_run_synthesizer()
        )
    assert [a.pmid for a in state.articles] == [101]
    assert state.answer is not None
    assert state.answer.text == DRY_RUN_TEXT
    assert state.answer.citations == []


async def test_one_agent_answers_many_questions_over_a_shared_client() -> None:
    """The class surface: construct once, ask repeatedly; the client persists across calls."""
    api = FakeApi(hits=[hit(101, 0.9, "s1")], publications={101: publication(101, "T", "A")})
    config = settings()
    synthesizer = FakeSynthesizer(SynthesisOutput(text="a", citations=[101]))
    async with (
        client_for(api, config) as client,
        LitSenseAgent(config, client=client, synthesizer=synthesizer) as agent,
    ):
        first = await agent.answer("q1")
        second = await agent.answer("q2")
    assert first.citations == second.citations == [101]
    assert len(synthesizer.calls) == 2


async def test_a_caller_owned_client_survives_the_agent_closing() -> None:
    """A client passed in stays the caller's responsibility — the agent must not close it."""
    api = FakeApi(hits=[hit(101, 0.9, "s1")], publications={101: publication(101, "T", "A")})
    config = settings()
    client = client_for(api, config)
    async with LitSenseAgent(
        config, client=client, synthesizer=FakeSynthesizer(SynthesisOutput(text="a"))
    ) as agent:
        await agent.answer("q")
    assert await client.search_sentences("still open")  # would raise on a closed client
    await client.aclose()


async def test_entity_ids_flow_from_annotations_into_the_answer() -> None:
    """Trello: return entity ids. PubTator annotations on the hits end up on the answer."""
    api = FakeApi(
        hits=[
            hit(101, 0.9, "TP53 mutations", annotations=["0|4|gene|7157"]),
            hit(102, 0.8, "in cancer", annotations=["3|6|disease|MESH:D009369", "0|4|gene|7157"]),
        ],
        publications={101: publication(101, "T1", "A1"), 102: publication(102, "T2", "A2")},
    )
    answer, _ = await run(api, SynthesisOutput(text="a", citations=[101, 102]))
    assert [(e.type, e.id) for e in answer.entities] == [
        ("gene", "7157"),
        ("disease", "MESH:D009369"),
    ]


# --- relevance gate (ADR-008) ----------------------------------------------------------


async def test_a_rejected_question_ends_before_any_retrieval() -> None:
    """Negative verdict: no HTTP request leaves, no model is consulted, the answer explains."""
    api = FakeApi(hits=[hit(101, 0.9, "s1")], publications={101: publication(101, "T", "A")})
    config = settings(relevance_gate=True)
    checker = FakeRelevanceChecker(
        RelevanceVerdict(relevant=False, reason="Not a biomedical question.")
    )
    synthesizer = FakeSynthesizer(SynthesisOutput(text="never"))
    async with (
        client_for(api, config) as client,
        LitSenseAgent(
            config, client=client, synthesizer=synthesizer, relevance_checker=checker
        ) as agent,
    ):
        state = await agent.run("What is the best pizza topping?")

    assert api.requests == []
    assert synthesizer.calls == []
    assert state.hits == [] and state.selection is None
    assert state.relevance is not None and state.relevance.relevant is False
    assert state.answer is not None
    assert state.answer.insufficient_context is True
    assert state.answer.citations == []
    assert "Not a biomedical question." in state.answer.text
    assert GATE_WARNING in state.answer.warnings


async def test_an_accepted_question_runs_the_pipeline_unchanged() -> None:
    api = FakeApi(hits=[hit(101, 0.9, "s1")], publications={101: publication(101, "T", "A")})
    config = settings(relevance_gate=True)
    checker = FakeRelevanceChecker(RelevanceVerdict(relevant=True))
    synthesizer = FakeSynthesizer(SynthesisOutput(text="grounded", citations=[101]))
    async with (
        client_for(api, config) as client,
        LitSenseAgent(
            config, client=client, synthesizer=synthesizer, relevance_checker=checker
        ) as agent,
    ):
        answer = await agent.answer("What does TP53 do?")

    assert [call[1][1] for call in checker.calls]  # the gate saw the question
    assert "What does TP53 do?" in checker.calls[0][1][1]
    assert answer.text == "grounded" and answer.citations == [101]
    assert GATE_WARNING not in answer.warnings


async def test_a_disabled_gate_never_consults_the_checker() -> None:
    api = FakeApi(hits=[hit(101, 0.9, "s1")], publications={101: publication(101, "T", "A")})
    config = settings(relevance_gate=False)
    checker = FakeRelevanceChecker(RelevanceVerdict(relevant=False, reason="would reject"))
    synthesizer = FakeSynthesizer(SynthesisOutput(text="a", citations=[101]))
    async with (
        client_for(api, config) as client,
        LitSenseAgent(
            config, client=client, synthesizer=synthesizer, relevance_checker=checker
        ) as agent,
    ):
        answer = await agent.answer("q")

    assert checker.calls == []
    assert answer.citations == [101]


async def test_the_dry_run_checker_lets_everything_through() -> None:
    api = FakeApi(hits=[hit(101, 0.9, "s1")], publications={101: publication(101, "T", "A")})
    config = settings(relevance_gate=True)
    async with client_for(api, config) as client:
        state = await run_pipeline(
            "q",
            config,
            client=client,
            synthesizer=build_dry_run_synthesizer(),
            relevance_checker=build_dry_run_relevance_checker(),
        )
    assert state.relevance is not None and state.relevance.relevant is True
    assert [a.pmid for a in state.articles] == [101]
    assert state.answer is not None and state.answer.text == DRY_RUN_TEXT


# --- full-text depth refinement (ADR-009) ----------------------------------------------


async def full_text_run(
    api: FakeApi, depth: FakeDepthEvaluator, output: SynthesisOutput
) -> tuple[Any, FakeSynthesizer, FakeDepthEvaluator]:
    config = settings(full_text=True)
    synthesizer = FakeSynthesizer(output)
    async with (
        client_for(api, config) as client,
        LitSenseAgent(
            config, client=client, synthesizer=synthesizer, depth_evaluator=depth
        ) as agent,
    ):
        state = await agent.run("What is the mechanism?")
    return state, synthesizer, depth


async def test_an_insufficient_verdict_refetches_full_text_and_resynthesizes() -> None:
    api = FakeApi(
        hits=[hit(101, 0.9, "s1", pmcid="PMC101")],
        publications={101: publication(101, "T", "A-abstract")},
        full_texts={"PMC101": "Full mechanistic detail from the paper body."},
    )
    depth = FakeDepthEvaluator(DepthVerdict(sufficient=False, missing="mechanism"))
    state, synthesizer, depth = await full_text_run(
        api, depth, SynthesisOutput(text="shallow", citations=[101])
    )

    assert len(synthesizer.calls) == 2  # abstracts pass, then full-text pass
    assert "A-abstract" in synthesizer.calls[0][1][1]
    assert "Full mechanistic detail" in synthesizer.calls[1][1][1]
    assert len(depth.calls) == 1  # the verdict stands after refinement — no second call
    assert state.refined is True
    assert state.articles[0].section == "full_text"
    assert state.answer is not None and state.answer.citations == [101]


async def test_a_sufficient_verdict_skips_refinement_entirely() -> None:
    api = FakeApi(
        hits=[hit(101, 0.9, "s1", pmcid="PMC101")],
        publications={101: publication(101, "T", "A")},
        full_texts={"PMC101": "never fetched"},
    )
    depth = FakeDepthEvaluator(DepthVerdict(sufficient=True))
    state, synthesizer, _ = await full_text_run(
        api, depth, SynthesisOutput(text="deep enough", citations=[101])
    )
    assert len(synthesizer.calls) == 1
    assert api.fulltext_requests == []
    assert state.refined is False


async def test_a_failed_full_text_fetch_keeps_the_abstract_and_warns() -> None:
    api = FakeApi(
        hits=[hit(101, 0.9, "s1", pmcid="PMC101")],
        publications={101: publication(101, "T", "A")},
        full_texts={},  # the service has nothing: 200 + HTML error
    )
    depth = FakeDepthEvaluator(DepthVerdict(sufficient=False, missing="depth"))
    state, synthesizer, _ = await full_text_run(
        api, depth, SynthesisOutput(text="shallow", citations=[101])
    )
    assert len(synthesizer.calls) == 1  # nothing upgraded, so no re-synthesis
    assert state.refined is True
    assert state.fulltext_failed_pmcids == ["PMC101"]
    assert state.answer is not None
    assert any("PMC101" in warning for warning in state.answer.warnings)


async def test_with_full_text_off_the_depth_evaluator_is_never_consulted() -> None:
    api = FakeApi(hits=[hit(101, 0.9, "s1")], publications={101: publication(101, "T", "A")})
    config = settings()  # full_text defaults to False
    depth = FakeDepthEvaluator(DepthVerdict(sufficient=False))
    synthesizer = FakeSynthesizer(SynthesisOutput(text="a", citations=[101]))
    async with (
        client_for(api, config) as client,
        LitSenseAgent(
            config, client=client, synthesizer=synthesizer, depth_evaluator=depth
        ) as agent,
    ):
        await agent.answer("q")
    assert depth.calls == []


async def test_refinement_targets_only_the_cited_articles() -> None:
    api = FakeApi(
        hits=[hit(101, 0.9, "s1", pmcid="PMC101"), hit(102, 0.8, "s2", pmcid="PMC102")],
        publications={101: publication(101, "T1", "A1"), 102: publication(102, "T2", "A2")},
        full_texts={"PMC101": "body-101", "PMC102": "body-102"},
    )
    depth = FakeDepthEvaluator(DepthVerdict(sufficient=False))
    state, _, _ = await full_text_run(api, depth, SynthesisOutput(text="x", citations=[101]))
    assert [p.split("/BioC_json/")[1].split("/")[0] for p in api.fulltext_requests] == ["PMC101"]
    assert [a.section for a in state.articles] == ["full_text", "abstract"]


async def test_the_search_payload_round_trips_the_state() -> None:
    """The state is pydantic throughout; nothing decays to raw dicts on the way."""
    api = FakeApi(hits=[hit(101, 0.9, "s1")], publications={101: publication(101, "T", "A")})
    config = settings()
    synthesizer = FakeSynthesizer(SynthesisOutput(text=json.dumps({"ok": True})))
    async with client_for(api, config) as client:
        answer = await answer_question("q", config, client=client, synthesizer=synthesizer)
    assert json.loads(answer.text) == {"ok": True}


# --- token usage (benchmark cost capture) -----------------------------------------------


async def test_run_sums_the_token_usage_of_every_model_call_inside_the_graph() -> None:
    """A synthesizer and a gate built on a real LangChain chat model report their usage
    through the run's callback — without the seams knowing anything about tokens."""
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.messages.ai import UsageMetadata

    model = FakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="gate",
                usage_metadata=UsageMetadata(
                    input_tokens=10, output_tokens=2, total_tokens=12
                ),
            ),
            AIMessage(
                content="synth",
                usage_metadata=UsageMetadata(
                    input_tokens=100,
                    output_tokens=30,
                    total_tokens=130,
                    output_token_details={"reasoning": 5},
                    input_token_details={"cache_read": 8},
                ),
            ),
        ]
    )

    async def check(messages: Sequence[Message]) -> RelevanceVerdict:
        await model.ainvoke(list(messages))
        return RelevanceVerdict(relevant=True, reason="ok")

    async def synthesize(messages: Sequence[Message]) -> SynthesisOutput:
        reply = await model.ainvoke(list(messages))
        return SynthesisOutput(text=str(reply.content), citations=[101])

    api = FakeApi(hits=[hit(101, 0.9, "s1")], publications={101: publication(101, "T", "A")})
    config = settings(relevance_gate=True)
    async with client_for(api, config) as client:
        state = await run_pipeline(
            "Q?", config, client=client, synthesizer=synthesize, relevance_checker=check
        )

    assert state.usage.model_dump() == {
        "input": 110, "output": 32, "reasoning": 5, "cache_read": 8, "total": 142, "calls": 2
    }


async def test_a_model_free_run_reports_zero_usage() -> None:
    api = FakeApi(hits=[hit(101, 0.9, "s1")], publications={101: publication(101, "T", "A")})
    config = settings()
    async with client_for(api, config) as client:
        state = await run_pipeline(
            "Q?", config, client=client, synthesizer=build_dry_run_synthesizer()
        )
    assert state.usage.total == 0
