"""The repositories the tool may read comments from, at the commits the rounds sampled.

Classifying runs against other repositories is refused: every Jev exchange is journaled, so only
our own repositories may be classified.
"""

import re
from pathlib import Path

REPOSITORIES = {
    "heedvane": (Path.home() / "Projects/heedvane", "39d8a3dcf6e9d744c329d7c18c8a3d46b8246590", "hv-h",
                 re.compile(r"^apps/.*\.(ts|tsx)$"),
                 re.compile(r"^apps/web/src/lib/|\.test\.|\.spec\.|test-support|generated|\.d\.ts$|__tests__|/e2e/")),
    "analysis-engine": (Path.home() / "Projects/analysis-engine", "65ce1972665975d20bb09f3638a6155f6fb3f9b9", "en-h",
                        re.compile(r"^enginepy/.*\.py$"), re.compile(r"_test\.py$|/tests?/|generated|conftest\.py$")),
}
