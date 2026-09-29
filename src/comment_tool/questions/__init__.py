"""The frozen question files, packaged with the tool so a checkout at one commit asks one question set."""

from pathlib import Path

QUESTIONS_DIR = Path(__file__).resolve().parent


def path(name: str) -> Path:
    """The packaged question file `name`, e.g. `questions.round5.json`."""
    return QUESTIONS_DIR / name
