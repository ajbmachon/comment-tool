"""Sol's list labels are read by entry index, never by response order."""

import pytest

from list_sol_labels import parse


def test_list_labels_must_answer_every_entry_by_its_index_in_order():
    answered = '{"A": {"label": "true"}, "entries": [{"index": 0, "label": "true"}, {"index": 1, "label": "false"}]}'
    reordered = '{"A": {"label": "true"}, "entries": [{"index": 1, "label": "false"}, {"index": 0, "label": "true"}]}'

    assert [e["label"] for e in parse(answered, 2)["entries"]] == ["true", "false"]
    with pytest.raises(ValueError):
        parse(reordered, 2)
