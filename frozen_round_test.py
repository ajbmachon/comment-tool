"""A round's rows count only when they are exactly the registered case ids."""

import json

import pytest

from frozen_round import FrozenRoundError, rows_exactly

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

