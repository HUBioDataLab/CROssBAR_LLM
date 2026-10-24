"""The deterministic overlap scorer — the benchmark's always-on metric.

Pure functions, so these pin exact behaviour: the substring path, the half-tokens path,
and the factoid/list difference. The LLM-judge side is prompts + a schema; there is nothing
deterministic to test there beyond message assembly.
"""

from __future__ import annotations

from litsense.metrics import judge_messages, overlap_score, phrase_in_answer


def test_a_multiword_phrase_matches_as_a_substring() -> None:
    answer = "Risk rises with interstitial lung disease."
    assert phrase_in_answer(answer, "interstitial lung disease")


def test_half_of_the_content_tokens_is_enough() -> None:
    # "PI3K/AKT/mTOR signaling" tokenizes to {pi3k, akt, mtor, signaling}; 2/4 present.
    assert phrase_in_answer("PI3K and AKT activity increased.", "PI3K/AKT/mTOR signaling")


def test_fewer_than_half_of_the_tokens_is_not_a_match() -> None:
    assert not phrase_in_answer("Signaling was altered.", "PI3K/AKT/mTOR signaling pathway")


def test_stopwords_and_case_do_not_produce_matches() -> None:
    assert not phrase_in_answer("The and of which", "the of and")
    assert not phrase_in_answer("", "HLA-C")
    assert not phrase_in_answer("HLA-C", "")


def test_factoid_hits_on_any_synonym() -> None:
    result = overlap_score("The answer is donepezil.", ["donepezil", "Aricept"], kind="factoid")
    assert result.hit is True and result.recall == 1.0
    assert result.matched_items == ["donepezil"] and result.missed_items == ["Aricept"]


def test_factoid_misses_when_no_synonym_appears() -> None:
    result = overlap_score("The answer is memantine.", ["donepezil", "Aricept"], kind="factoid")
    assert result.hit is False and result.recall == 0.0


def test_list_recall_is_matched_over_total() -> None:
    result = overlap_score(
        "IL23R and IL12B are established; CARD14 is rarer.",
        ["IL23R", "IL12B", "CARD14", "HLA-C"],
        kind="list",
    )
    assert result.hit is True and result.recall == 0.75
    assert result.missed_items == ["HLA-C"]


def test_an_empty_reference_scores_as_a_free_hit() -> None:
    result = overlap_score("anything", [], kind="list")
    assert result.hit is True and result.recall == 1.0


def test_judge_messages_carry_question_reference_and_answer() -> None:
    messages = judge_messages("Q?", "generated text", ["item-a", "item-b"], kind="list")
    assert messages[0][0] == "system" and "list-style" in messages[0][1]
    user = messages[1][1]
    assert "Q?" in user and "generated text" in user and "- item-a" in user and "- item-b" in user
