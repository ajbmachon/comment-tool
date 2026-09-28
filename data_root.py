"""Where the round data lives: packets, answers, journals, labels and frozen records.

The code lives in this repository; the data stays in the handoff folder it was measured in, so frozen
records keep their paths. `COMMENT_TOOL_DATA` points elsewhere when set.
"""

import os
from pathlib import Path

DATA = Path(os.environ.get("COMMENT_TOOL_DATA", Path.home() / ".claude/handoffs/effect-2026-09-25/comment-tool"))
