"""Static facts about TypeScript source from the TypeScript compiler's own parser (`ts_parse.mjs`).

Reference scopes use its binder/TypeChecker on the supplied file; no emit, type diagnostics or
import/library loading runs. The compiler module comes from a repository's `node_modules`.
"""

import json
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "ts_parse.mjs"


def typescript_of(repository: Path) -> Path:
    return repository / "node_modules/typescript"


def ts_parse(typescript: Path, path: str, source: str, line: int, scope: str, *, end_line: int | None = None) -> dict:
    """`scope` is "declaration", "module", "entries", "conditions" or "parameters"; see `ts_parse.mjs`."""
    request = {"typescript": str(typescript), "file": path, "source": source, "line": line, "scope": scope,
               "end_line": end_line}
    done = subprocess.run(["node", str(SCRIPT)], input=json.dumps(request), capture_output=True, text=True, check=True)
    return json.loads(done.stdout)
