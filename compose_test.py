"""Behaviour of readout A for doc comments: never removed, rewritten instead (Andre, 28.09.2026 04:52 CEST)."""

import itertools

import compose

NO = 0.05
YES = 0.95
QUESTIONS = ("code_is_hard_to_follow", "explains_how_or_why", *compose.OTHER_VALUES, *compose.STALE_PARTS,
             "is_noise", "name_would_replace", "only_restates_code", "has_time_reference")


def answers(**yes: float) -> dict:
    return {question: yes.get(question, NO) for question in QUESTIONS}


def facts(doc_comment: bool) -> dict:
    return {"dates": [], "ticket_refs": [], "unowned_todo": False, "commented_out_code": False,
            "doc_comment": doc_comment}


def test_remove_leading_answers_rewrite_a_doc_comment():
    noise = answers(is_noise=YES)

    assert compose.readout_a(noise, facts(doc_comment=False)) == "remove"
    assert compose.readout_a(noise, facts(doc_comment=True)) == "rewrite"


def test_a_doc_comment_describing_its_code_is_kept():
    restates = answers(only_restates_code=YES)

    assert compose.readout_a(restates, facts(doc_comment=False)) == "remove"
    assert compose.readout_a(restates, facts(doc_comment=True)) == "keep"


def test_a_doc_comment_that_restates_and_only_labels_is_rewritten():
    label = answers(only_restates_code=YES, is_noise=YES)

    assert compose.readout_a(label, facts(doc_comment=True)) == "rewrite"


def test_restating_is_not_on_the_escalation_path_of_a_doc_comment():
    unsure_restates = answers(only_restates_code=0.5)

    assert compose.escalation_reasons(unsure_restates, facts(doc_comment=False)) == ["problem 0.50"]
    assert compose.escalation_reasons(unsure_restates, facts(doc_comment=True)) == []


def test_a_better_name_does_not_replace_a_doc_comment():
    renamable = answers(name_would_replace=YES)

    assert compose.readout_a(renamable, facts(doc_comment=False)) == "refactor_instead"
    assert compose.readout_a(renamable, facts(doc_comment=True)) == "rewrite"


def test_stale_and_keep_are_unchanged_for_a_doc_comment():
    stale = answers(**{part: YES for part in compose.STALE_PARTS})
    valuable = answers(states_hidden_rule=YES)

    assert compose.readout_a(stale, facts(doc_comment=True)) == "fix_stale"
    assert compose.readout_a(valuable, facts(doc_comment=True)) == "keep"


def test_escalation_is_unchanged_for_a_doc_comment():
    unsure = answers(is_noise=0.5)

    assert compose.escalation_reasons(unsure, facts(doc_comment=True)) == ["is_noise 0.50"]


def test_a_doubtful_label_is_one_escalation_reason_for_a_doc_comment():
    doubtful_label = answers(is_noise=0.45)

    assert compose.escalation_reasons(doubtful_label, facts(doc_comment=True)) == ["is_noise 0.45"]


STALE_IN_DOUBT = {"names_specific_detail": YES, "code_shows_same_detail": 0.45, "code_differs_from_comment": YES}


def test_a_search_can_settle_a_stale_doubt_about_a_detail_the_shown_code_lacks():
    assert compose.search_could_settle(answers(**STALE_IN_DOUBT))


def test_a_search_opens_on_the_whole_band_while_the_detail_is_not_surely_shown():
    doubtfully_shown = answers(**{**STALE_IN_DOUBT, "code_shows_same_detail": 0.55})

    assert compose.search_could_settle(doubtfully_shown)


def test_no_search_when_the_shown_code_surely_holds_the_detail():
    shown = answers(**{**STALE_IN_DOUBT, "code_shows_same_detail": 0.65, "code_differs_from_comment": 0.45})

    assert not compose.search_could_settle(shown)


def test_a_named_detail_the_shown_code_lacks_is_recorded_as_not_checked():
    not_shown = answers(names_specific_detail=YES, code_shows_same_detail=0.11)

    assert compose.stale_check(not_shown) == compose.NOT_CHECKABLE
    assert compose.stale_check(answers(**STALE_IN_DOUBT)) == compose.NOT_CHECKABLE
    assert compose.stale_check(answers(names_specific_detail=YES, code_shows_same_detail=YES)) is None
    assert compose.stale_check(answers()) is None


def test_no_search_when_the_comment_names_no_detail():
    unnamed = answers(**{**STALE_IN_DOUBT, "names_specific_detail": 0.45})

    assert not compose.search_could_settle(unnamed)


def test_no_search_for_a_doubt_that_is_not_about_staleness():
    history_doubt = answers(has_time_reference=0.45, states_hidden_rule=YES)

    assert not compose.search_could_settle(history_doubt)


def doc_facts(**overrides) -> dict:
    return {**facts(doc_comment=True), **overrides}


def test_a_rewrite_names_the_answers_that_led_to_it():
    assert compose.rewrite_reasons(answers(is_noise=YES), doc_facts()) == ["only a title or label (is_noise 0.95)"]
    assert compose.rewrite_reasons(answers(name_would_replace=YES), doc_facts()) == [
        "a better name would say it all (name_would_replace 0.95)"]
    assert compose.rewrite_reasons(answers(states_hidden_rule=YES, has_time_reference=YES), doc_facts()) == [
        "tells history (has_time_reference 0.95)"]
    assert compose.rewrite_reasons(answers(), doc_facts(dates=["2026-08-06"], unowned_todo=True)) == [
        "names a date or ticket (2026-08-06)", "a TODO without an owner"]


def test_a_comment_that_is_not_rewritten_has_no_rewrite_reasons():
    assert compose.rewrite_reasons(answers(states_hidden_rule=YES), doc_facts()) == []


def test_a_stale_verdict_below_the_bar_goes_to_the_calling_agent():
    differs_below_bar = answers(names_specific_detail=YES, code_shows_same_detail=YES, code_differs_from_comment=0.71)

    assert compose.readout_a(differs_below_bar, facts(doc_comment=False)) == "fix_stale"
    assert compose.escalation_reasons(differs_below_bar, facts(doc_comment=False)) == [
        "fix stale below bar: code_differs_from_comment 0.71"]


def test_a_stale_verdict_at_the_bar_decides_alone():
    differs_at_bar = answers(names_specific_detail=YES, code_shows_same_detail=YES,
                             code_differs_from_comment=compose.STALE_DECIDES_AT)

    assert compose.escalation_reasons(differs_at_bar, facts(doc_comment=False)) == []


def test_no_answers_or_facts_ever_delete_a_doc_comment_and_some_delete_an_inline_one():
    grid = [answers(**dict(zip(QUESTIONS, values, strict=True))) for values in itertools.product((NO, YES), repeat=len(QUESTIONS))]
    fact_sets = [{**facts(doc_comment=False), "dates": dates, "unowned_todo": todo} for dates in ([], ["2026-08-27"]) for todo in (False, True)]

    inline = {compose.readout_a(p, f) for p in grid for f in fact_sets}
    docs = {compose.readout_a(p, {**f, "doc_comment": True}) for p in grid for f in fact_sets}

    assert "remove" in inline
    assert docs.isdisjoint(compose.REWRITTEN_NOT_REMOVED)
