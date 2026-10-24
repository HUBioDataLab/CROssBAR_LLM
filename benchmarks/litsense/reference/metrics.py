"""Scoring functions for benchmark answers.

Two scorers:

- `overlap_score`: deterministic, token/substring intersection. Free
  (no LLM call). Good for the lexical "did the model say the right
  words?" floor.

- `llm_judge`: one extra LLM call per question. Semantic grading
  against reference items, paraphrases allowed. Catches correct
  answers that overlap_score under-rates.
"""
from __future__ import annotations

import re
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
)
from pydantic import BaseModel, Field


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


def _phrase_in_answer(answer: str, phrase: str) -> bool:
    """A reference phrase counts as 'mentioned' if either:
      (1) its lowercased form appears as a substring of the answer, OR
      (2) at least half of its non-stopword tokens appear in the answer.
    The substring check catches multi-word terms cleanly; the token check
    catches reordered or paraphrased mentions.
    """
    if not phrase or not answer:
        return False
    answer_lower = answer.lower()
    if phrase.lower() in answer_lower:
        return True

    ref_tokens = _tokenize(phrase)
    if not ref_tokens:
        return False
    answer_tokens = _tokenize(answer)
    overlap = ref_tokens & answer_tokens
    return len(overlap) >= max(1, (len(ref_tokens) + 1) // 2)


def overlap_score(
    generated: str,
    reference: list[str],
    kind: Literal["factoid", "list"],
) -> dict:
    """Score a generated answer against a list of reference items.

    factoid: hit iff ANY reference item appears in the answer (BioASQ
        factoid: exact_answer is a single canonical term, possibly with
        synonyms listed as alternates — any match is a hit).
    list: recall over reference items (BioASQ list / BioHopR: the reference
        is N independent items; recall = #matched / #total).
    """
    if not reference:
        return {"hit": True, "recall": 1.0, "matched": [], "missed": []}

    matched = [r for r in reference if _phrase_in_answer(generated or "", r)]
    missed = [r for r in reference if r not in matched]

    if kind == "factoid":
        return {
            "hit": len(matched) > 0,
            "recall": 1.0 if matched else 0.0,
            "matched": matched,
            "missed": missed,
        }

    recall = len(matched) / len(reference)
    return {
        "hit": recall > 0,
        "recall": round(recall, 3),
        "matched": matched,
        "missed": missed,
    }


# ---------------------------------------------------------------------------
# LLM-as-judge
# ---------------------------------------------------------------------------

class JudgeVerdict(BaseModel):
    score: int = Field(
        ...,
        ge=0,
        le=5,
        description=(
            "0 = completely wrong / irrelevant; "
            "1-2 = mentions the topic but misses the answer; "
            "3 = partially correct, includes some of the reference; "
            "4 = mostly correct, paraphrased; "
            "5 = correct and complete."
        ),
    )
    matched_items: list[str] = Field(
        default_factory=list,
        description="Reference items the answer correctly mentions (paraphrases allowed).",
    )
    missed_items: list[str] = Field(
        default_factory=list,
        description="Reference items the answer fails to mention.",
    )
    informativeness: int = Field(
        ...,
        ge=0,
        le=5,
        description=(
            "How explanatory/informative the answer is BEYOND the bare term, "
            "judged independently of correctness: 0 = bare term or empty; "
            "3 = some useful context (mechanism, role, caveats); "
            "5 = rich, well-contextualised explanation with relevant supporting "
            "detail. A wrong answer can still be informative; a correct answer "
            "can still be bare."
        ),
    )
    clarity: int = Field(
        ...,
        ge=0,
        le=5,
        description=(
            "Clarity and coherence of the reasoning/presentation, judged "
            "independently of correctness: 0 = incoherent or contradictory; "
            "3 = readable but loosely organised; 5 = clear, well-structured, "
            "easy to follow."
        ),
    )
    rationale: str = Field(
        "",
        description="One-sentence justification covering correctness and the two quality scores.",
    )


_JUDGE_FACTOID_PROMPT = """\
You are an expert biomedical grader. A model produced an answer to a factual question. Score it against the reference answer.

The reference is a SHORT FACTUAL TERM (sometimes with listed synonyms or alternate spellings). A score of 5 requires the answer to contain the term or an unambiguous synonym. Paraphrases are fine — match on meaning, not on exact strings.

Also rate two QUALITY aspects independently of correctness: how informative/explanatory the answer is, and how clear its reasoning is. A wrong answer may still be informative and clear; a correct answer may still be bare and terse.

Output:
- score: integer 0-5 (correctness)
- matched_items: which reference items the answer mentions (paraphrasing OK)
- missed_items: which reference items the answer fails to mention
- informativeness: integer 0-5 (depth of explanation beyond the bare term)
- clarity: integer 0-5 (clarity/coherence of the reasoning)
- rationale: one sentence covering correctness and the two quality scores"""


_JUDGE_LIST_PROMPT = """\
You are an expert biomedical grader. A model produced an answer to a list-style question. Score it against the reference list.

The reference is a list of N items. A realistic model answer usually covers only a subset — that is expected. Score proportionally to coverage. Match items on meaning, not on exact strings (e.g. "type 2 diabetes" matches "T2D", "T2DM", "type-2 diabetes").

Also rate two QUALITY aspects independently of coverage: how informative/explanatory the answer is, and how clear its reasoning is. Low coverage may still be informative and clear; high coverage may still be a terse bare list.

Output:
- score: integer 0-5 (coverage: 0=none matched, 5=most or all matched)
- matched_items: which reference items appear in the answer (paraphrasing OK)
- missed_items: which reference items are missing
- informativeness: integer 0-5 (depth of explanation beyond the bare list)
- clarity: integer 0-5 (clarity/coherence of the reasoning)
- rationale: one sentence covering coverage and the two quality scores"""


async def llm_judge(
    question: str,
    generated: str,
    reference: list[str],
    chat_model: BaseChatModel,
    kind: Literal["factoid", "list"],
) -> JudgeVerdict:
    """One LLM call: grade `generated` against `reference` for `question`.

    Uses `with_structured_output(JudgeVerdict)` so the verdict is type-safe
    and the score is constrained to 0-5 at the provider boundary.
    """
    system = _JUDGE_FACTOID_PROMPT if kind == "factoid" else _JUDGE_LIST_PROMPT
    ref_str = "\n".join(f"- {r}" for r in reference)

    prompt = ChatPromptTemplate.from_messages([
        SystemMessagePromptTemplate.from_template(system),
        HumanMessagePromptTemplate.from_template(
            "Question:\n{question}\n\n"
            "Reference (expected answer items):\n{reference}\n\n"
            "Model answer:\n{generated}\n\n"
            "Grade the model answer now."
        ),
    ])
    chain = prompt | chat_model.with_structured_output(JudgeVerdict)
    return await chain.ainvoke({
        "question": question,
        "reference": ref_str,
        "generated": generated,
    })
