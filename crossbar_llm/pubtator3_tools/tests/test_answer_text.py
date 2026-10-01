"""The synthesizer's answer must be prose, never a Python repr of content blocks."""
from langchain_core.messages import AIMessage

from crossbar_llm.pubtator3_tools.structured_output import _answer_text


def test_plain_string_content_is_returned_unchanged():
    assert _answer_text(AIMessage(content="EGFR drives proliferation.")) == (
        "EGFR drives proliferation."
    )


def test_content_blocks_are_joined_as_text_not_repr():
    # Anthropic with reasoning, and some Gemini setups, return a list of blocks.
    msg = AIMessage(content=[
        {"type": "text", "text": "EGFR drives proliferation"},
        {"type": "text", "text": " [PMID:123]."},
    ])

    assert _answer_text(msg) == "EGFR drives proliferation [PMID:123]."


def test_reasoning_blocks_never_reach_the_answer():
    msg = AIMessage(content=[
        {"type": "thinking", "thinking": "private chain of thought", "signature": "x"},
        {"type": "reasoning", "reasoning": "more private reasoning"},
        {"type": "text", "text": "EGFR drives proliferation."},
    ])

    answer = _answer_text(msg)

    assert answer == "EGFR drives proliferation."
    assert "private" not in answer


def test_bare_string_blocks_are_kept():
    assert _answer_text(AIMessage(content=["EGFR ", "drives proliferation."])) == (
        "EGFR drives proliferation."
    )
