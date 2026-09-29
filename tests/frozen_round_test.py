"""A round's rows count only when they are exactly the registered case ids."""

import json

import pytest

from research.rounds.frozen_round import (
    MANIFEST_LINE,
    FrozenRoundError,
    RunNotCompleteError,
    completed_rows,
    registered_manifest,
    rows_exactly,
    sha256_of,
)
from research.rounds.registered_rounds import Registration

IDS = ["a", "b", "c"]


def written(tmp_path, case_ids: list[str]):
    path = tmp_path / "rows.jsonl"
    path.write_text("".join(json.dumps({"case_id": cid}) + "\n" for cid in case_ids))
    return path


def test_exactly_the_registered_ids_are_accepted(tmp_path):
    assert sorted(rows_exactly(written(tmp_path, ["c", "a", "b"]), IDS)) == IDS


@pytest.mark.parametrize("found", [["a", "b"], ["a", "b", "c", "d"], ["a", "b", "b", "c"]], ids=["partial", "extra", "duplicate"])
def test_a_partial_extra_or_duplicated_file_is_invalid(tmp_path, found):
    with pytest.raises(FrozenRoundError):
        rows_exactly(written(tmp_path, found), IDS)



REGISTRATION = Registration(questions="questions.round5.json", sampler="sample_round6", library_commit="c" * 40, python="3.13",
                            case_ids=("a", "b"))


def registered(tmp_path, **changes) -> None:
    fields = {"case_ids": ["a", "b"], "questions": {"path": "questions.round5.json"}, "sampler": "sample_round6",
              "library_commit": "c" * 40, "python": "3.13", **changes}
    (tmp_path / "manifest.json").write_text(json.dumps(fields))
    (tmp_path / "FROZEN.txt").write_text(f"prose\n{MANIFEST_LINE}{sha256_of(tmp_path / 'manifest.json')}\n")


def test_a_manifest_bound_by_its_frozen_hash_and_the_code_registration_is_accepted(tmp_path):
    registered(tmp_path)

    assert registered_manifest(tmp_path, REGISTRATION).case_ids == ["a", "b"]


def test_a_manifest_edited_after_the_freeze_is_refused(tmp_path):
    registered(tmp_path)
    (tmp_path / "manifest.json").write_text((tmp_path / "manifest.json").read_text().replace('"b"', '"z"'))

    with pytest.raises(FrozenRoundError, match="manifest"):
        registered_manifest(tmp_path, REGISTRATION)


@pytest.mark.parametrize("change", [{"case_ids": ["a"]}, {"questions": {"path": "questions.round4.json"}},
                                    {"sampler": "sample_docs"}, {"library_commit": "d" * 40}, {"python": "3.14"}],
                         ids=["ids", "questions", "sampler", "library", "python"])
def test_a_manifest_that_disagrees_with_the_code_registration_is_refused(tmp_path, change):
    registered(tmp_path, **change)

    with pytest.raises(FrozenRoundError):
        registered_manifest(tmp_path, REGISTRATION)


def test_a_run_that_is_missing_or_still_running_is_not_complete(tmp_path):
    with pytest.raises(RunNotCompleteError):
        completed_rows(tmp_path, "pass.jsonl", IDS)
    written(tmp_path, IDS).rename(tmp_path / "pass.jsonl")
    (tmp_path / "pass.jsonl.partial").write_text("")

    with pytest.raises(RunNotCompleteError):
        completed_rows(tmp_path, "pass.jsonl", IDS)
