"""The round-6 draw must be exactly the registered pull requests, repositories and case ids."""

import pytest

from registered_rounds import ROUNDS
from sample_round6 import PULL_REQUESTS, SampleError, require_registered_draw


def drawn(pull_requests=PULL_REQUESTS) -> list[dict]:
    ids = iter(ROUNDS["round6"].case_ids)
    return [{"case_id": next(ids), "pull_request": number, "provenance": {"repository": name, "commit": merge, "path": f"f{n}.py",
                                                                          "comment_lines": [n, n]}}
            for name, number, merge in pull_requests for n in range(1, 6)]


def test_the_registered_draw_is_accepted():
    require_registered_draw(drawn())


def test_a_draw_from_another_pull_request_with_the_same_counts_is_refused():
    swapped = [PULL_REQUESTS[0], ("heedvane", 9999, "0" * 40), *PULL_REQUESTS[2:]]

    with pytest.raises(SampleError):
        require_registered_draw(drawn(swapped))
