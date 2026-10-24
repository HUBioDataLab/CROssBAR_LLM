"""Scoring functions for benchmark answers.

The structure is Ahmet Oğuzhan's (`reference/metrics.py`), rebuilt for this project's
conventions — pydantic results instead of dicts, and the judge's LLM behind a seam so the
scorers themselves stay import-light and deterministic to test.

Two scorers:

- `overlap_score`: deterministic token/substring intersection. Free (no LLM call). The
  lexical "did the answer say the right words?" floor.
- LLM-as-judge: semantic grading against reference items, paraphrases allowed. The prompts
  and the `JudgeVerdict` schema live here; the model call is the caller's (`run.py` builds a
  `Judge` callable from the configured model, tests inject a fake).
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Literal

from pydantic import BaseModel, Field

from crossbar_llm.litsense_tools.models import TokenUsage

Kind = Literal["factoid", "list"]

#: Bumped whenever the judge prompts or the verdict schema change; recorded in every
#: re-judged result's `run_info.judge_prompt_revision` so verdicts are comparable only
#: within a revision. 2026-10-02: explicit integer 0-5 scale in the list prompt and
#: matched/missed items placed before the scores (llama-3.3-70b scored before matching).
JUDGE_PROMPT_REVISION = "2026-10-02"

#: One (role, content) message, matching `crossbar_llm.litsense_tools.prompts.Message`.
Message = tuple[str, str]

_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "of", "in", "on", "at", "to", "for", "by",
    "with", "from", "is", "are", "was", "were", "be", "been", "this", "that",
    "as", "it", "its", "which", "who", "whom", "what", "where", "when", "why",
    "how", "all", "any", "both", "each", "more", "most", "other", "some",
    "such", "no", "not", "only", "own", "same", "so", "than", "too", "very",
    "can", "will", "may", "could", "should", "would", "have", "has", "had",
})


def _tokenize(s: str) -> set[str]:
    """Lowercase, strip punctuation, drop stopwords + 1-char tokens."""
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s\-]", " ", s)
    return {t for t in s.split() if t and t not in _STOPWORDS and len(t) > 1}


def phrase_in_answer(answer: str, phrase: str) -> bool:
    """A reference phrase counts as "mentioned" if either:

    (1) its lowercased form appears as a substring of the answer, OR
    (2) at least half of its non-stopword tokens appear in the answer.

    The substring check catches multi-word terms cleanly; the token check catches
    reordered or paraphrased mentions.
    """
    if not phrase or not answer:
        return False
    if phrase.lower() in answer.lower():
        return True

    ref_tokens = _tokenize(phrase)
    if not ref_tokens:
        return False
    overlap = ref_tokens & _tokenize(answer)
    return len(overlap) >= max(1, (len(ref_tokens) + 1) // 2)


class OverlapResult(BaseModel):
    """Deterministic score of one generated text against one reference list."""

    hit: bool
    recall: float
    matched_items: list[str] = Field(default_factory=list)
    missed_items: list[str] = Field(default_factory=list)


def overlap_score(generated: str, reference: list[str], *, kind: Kind) -> OverlapResult:
    """Score a generated answer against a list of reference items.

    factoid: hit iff ANY reference item appears in the answer (BioASQ factoid:
        `exact_answer` is one canonical term, possibly with synonyms as alternates —
        any match is a hit).
    list: recall over reference items (BioASQ list / BioHopR / CROssBAR: the reference
        is N independent items; recall = #matched / #total).
    """
    if not reference:
        return OverlapResult(hit=True, recall=1.0)

    matched = [r for r in reference if phrase_in_answer(generated or "", r)]
    missed = [r for r in reference if r not in matched]

    if kind == "factoid":
        return OverlapResult(
            hit=bool(matched), recall=1.0 if matched else 0.0,
            matched_items=matched, missed_items=missed,
        )

    recall = len(matched) / len(reference)
    return OverlapResult(
        hit=recall > 0, recall=round(recall, 3), matched_items=matched, missed_items=missed
    )


# ---------------------------------------------------------------------------
# LLM-as-judge
# ---------------------------------------------------------------------------


class JudgeVerdict(BaseModel):
    """The judge's structured output — same fields as the reference harness.

    Field order is deliberate: the judge enumerates matched/missed items before it
    scores, so the scores follow from the match (smaller judges such as
    llama-3.3-70b scored before matching when `score` came first and contradicted
    their own rationale). The JSON keys are unchanged.
    """

    matched_items: list[str] = Field(
        default_factory=list,
        description="Reference items the answer correctly mentions (paraphrases allowed).",
    )
    missed_items: list[str] = Field(
        default_factory=list,
        description="Reference items the answer fails to mention.",
    )
    score: int = Field(
        ge=0,
        le=5,
        description=(
            "Integer 0-5. 0 = completely wrong / irrelevant; 1-2 = mentions the topic but "
            "misses the answer; 3 = partially correct, includes some of the reference; "
            "4 = mostly correct, paraphrased; 5 = correct and complete."
        ),
    )
    informativeness: int = Field(
        ge=0,
        le=5,
        description=(
            "How explanatory/informative the answer is BEYOND the bare term, judged "
            "independently of correctness: 0 = bare term or empty; 3 = some useful context; "
            "5 = rich, well-contextualised explanation."
        ),
    )
    clarity: int = Field(
        ge=0,
        le=5,
        description=(
            "Clarity and coherence of the presentation, judged independently of "
            "correctness: 0 = incoherent; 3 = readable but loosely organised; 5 = clear "
            "and well-structured."
        ),
    )
    rationale: str = Field(
        default="",
        description="One-sentence justification covering correctness and the quality scores.",
    )


#: The judge seam: async, messages in, verdict + the call's token usage out (the judge's
#: tokens are reported separately from the agent's, so the agent's cost stays comparable
#: with the reference harness). `run.py` builds one from the configured model.
Judge = Callable[[list[Message]], Awaitable[tuple[JudgeVerdict, TokenUsage]]]

_JUDGE_FACTOID_PROMPT = """\
You are an expert biomedical grader. A model produced an answer to a factual question.
Score it against the reference answer.

The reference is a SHORT FACTUAL TERM (sometimes with listed synonyms or alternate
spellings). A score of 5 requires the answer to contain the term or an unambiguous synonym.
Paraphrases are fine — match on meaning, not on exact strings.

Also rate two QUALITY aspects independently of correctness: how informative/explanatory the
answer is, and how clear its reasoning is. A wrong answer may still be informative and
clear; a correct answer may still be bare and terse."""

_JUDGE_LIST_PROMPT = """\
You are an expert biomedical grader. A model produced an answer to a list-style question.
Score it against the reference list.

The reference is a list of N items. A realistic model answer usually covers only a subset —
that is expected. Score proportionally to coverage. Match items on meaning, not on exact
strings (e.g. "type 2 diabetes" matches "T2D", "T2DM", "type-2 diabetes").

Also rate two QUALITY aspects independently of coverage: how informative/explanatory the
answer is, and how clear its reasoning is. Low coverage may still be informative and clear;
high coverage may still be a terse bare list.

Scoring scale — `score`, `informativeness` and `clarity` are each an INTEGER from 0 to 5,
never a fraction and never a 0-1 proportion. `score` is coverage of the reference list:
5 = every reference item covered (paraphrases count), 4 = most, 3 = about half, 2 = a
few, 1 = a single item or only vaguely related content, 0 = nothing from the list.
First list the matched and missed reference items, then score."""


def judge_messages(
    question: str, generated: str, reference: list[str], *, kind: Kind
) -> list[Message]:
    """The full message list for one judge call. Pure."""
    system = _JUDGE_FACTOID_PROMPT if kind == "factoid" else _JUDGE_LIST_PROMPT
    ref_str = "\n".join(f"- {r}" for r in reference)
    user = (
        f"Question:\n{question}\n\n"
        f"Reference (expected answer items):\n{ref_str}\n\n"
        f"Model answer:\n{generated}\n\n"
        "Grade the model answer now."
    )
    return [("system", system), ("human", user)]
