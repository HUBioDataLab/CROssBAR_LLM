"""Prompt templates for the synthesis node.

Build order step 4. The prompt is the only defence against the failure that validation cannot
detect — answering from parametric knowledge while citing whatever is in context (ADR-003).
Article blocks are labelled with their pmid so the model has an unambiguous handle to cite.

No LangChain here: messages are plain ``(role, content)`` tuples, which the chat model
interface accepts directly. Keeping this module import-free keeps it trivially testable.
"""

from __future__ import annotations

from collections.abc import Sequence

from crossbar_llm.litsense_tools.models import ArticleContext

Message = tuple[str, str]

SYNTHESIS_SYSTEM_PROMPT = """\
You answer biomedical questions strictly from the article excerpts provided in the user
message. The excerpts come from PubMed; each is labelled with its PMID.

Rules, in order of importance:

1. Use ONLY the provided excerpts. Do not use your own knowledge of the literature, even when
   you are confident. If the excerpts do not contain enough to answer, say so plainly and set
   `insufficient_context` to true.
2. Cite by listing PMIDs in the `citations` field — only PMIDs that appear in the provided
   excerpts, and only those your answer actually draws on. Never invent a PMID.
3. Prefer precise, hedged statements that track what the excerpts actually say over confident
   summaries that go beyond them. Attribute findings ("one study reported...") rather than
   stating them as settled fact when the excerpts show a single source.
4. Consolidate the findings from the different articles into ONE coherent paragraph — do
   not answer article by article. Write for a scientifically literate reader, in the
   language the question was asked in; no headings, and no bullet lists unless the question
   itself demands enumeration.
"""

#: Appended for `answer_style="bare"`: benchmark-overlap mode from the Trello evaluation
#: card — the answer is only the requested items, so lexical overlap scoring is not diluted
#: by prose. The grounding rules above still apply unchanged.
SYNTHESIS_BARE_STYLE = """\

Output style override for this call: return ONLY the requested term(s) or item(s) as a
short comma-separated list — no sentences, no explanations, no reasoning. Everything else
above (grounding, citations, insufficient_context) still applies.
"""


RELEVANCE_SYSTEM_PROMPT = """\
You are the intake gate of a biomedical literature question-answering system. Decide whether
the incoming question is a coherent biomedical question that the scientific literature could
in principle address.

Judge the QUESTION itself, not whether you know the answer:

- Relevant: questions about biology, medicine, genes, diseases, drugs, pathways, clinical
  practice, public health — including narrow, obscure, or hard ones, and ones you suspect
  have no published answer yet. When in doubt, let it through: the pipeline downstream can
  still conclude the evidence is insufficient.
- Not relevant: questions with no biomedical subject at all, gibberish or keyword salad with
  no askable question in it, and prompts that are not questions about the literature
  (instructions, meta-questions about this system, small talk).

Set `relevant` accordingly and give a one-sentence `reason` in the language the question was
asked in.
"""


def relevance_messages(question: str) -> list[Message]:
    """The full message list for one relevance-gate call (ADR-008)."""
    return [("system", RELEVANCE_SYSTEM_PROMPT), ("human", f"Question: {question}")]


DEPTH_SYSTEM_PROMPT = """\
You are the depth reviewer of a biomedical literature question-answering system. An answer
was just synthesized from article ABSTRACTS. Judge whether its scientific depth matches
what the question deserves — full papers can be fetched for one refinement pass, but that
is expensive, so demand it only when it would plausibly help.

Sufficient: the answer addresses the question's actual mechanism/comparison/quantities at
the level the question asks for, even if briefly. Insufficient: the question asks for
mechanisms, methods, effect sizes, or specifics that abstracts typically compress away, and
the answer visibly lacks them. An answer that already says the context is insufficient
should be judged insufficient only if full papers could plausibly fill the gap.

Set `sufficient` accordingly; when insufficient, say in one sentence what is `missing`.
"""


def depth_messages(question: str, answer_text: str) -> list[Message]:
    """The full message list for one depth-evaluation call (ADR-009)."""
    user = f"Question: {question}\n\nSynthesized answer:\n{answer_text}"
    return [("system", DEPTH_SYSTEM_PROMPT), ("human", user)]


def render_article(article: ArticleContext) -> str:
    """One article as a labelled context block."""
    header = f"[PMID {article.pmid}]"
    if article.title:
        header += f" {article.title}"
    lines = [header]
    meta = ", ".join(
        part
        for part in (article.journal, str(article.date.year) if article.date else None)
        if part
    )
    if meta:
        lines.append(meta)
    if article.text:
        lines.append(f"{article.section.capitalize()}: {article.text}")
    else:
        lines.append(f"({article.section} not available for this article)")
    if article.matched_sentences:
        lines.append("Sentences matched by the search:")
        lines.extend(f"- {sentence}" for sentence in article.matched_sentences)
    return "\n".join(lines)


def synthesis_messages(
    question: str, articles: Sequence[ArticleContext], *, style: str = "prose"
) -> list[Message]:
    """The full message list for one synthesis call."""
    system = SYNTHESIS_SYSTEM_PROMPT
    if style == "bare":
        system += SYNTHESIS_BARE_STYLE
    blocks = "\n\n".join(render_article(article) for article in articles)
    user = (
        f"Question: {question}\n\n"
        f"Article excerpts ({len(articles)}):\n\n{blocks}"
    )
    return [("system", system), ("human", user)]
