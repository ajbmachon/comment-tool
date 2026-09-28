"""What each scored round was registered with, in code: the question file, the sampler, the library
commit, the Python version and the exact case ids. `frozen_round.verify` refuses a manifest that
disagrees, so an edited manifest cannot change what a run asks or what a score counts."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Registration:
    questions: str
    sampler: str
    library_commit: str
    python: str
    case_ids: tuple[str, ...]


ROUNDS = {
    "round6": Registration(
        questions="questions.round5.json",
        sampler="sample_round6",
        library_commit="1568d3d8bfdf5f038bdc59ed36d8c3a22d3d1f9e",
        python="3.13",
        case_ids=tuple(f"{prefix}{n:02d}" for prefix in ("hv-k", "en-k") for n in range(1, 16)),
    ),
}
