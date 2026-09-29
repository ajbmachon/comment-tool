"""Static facts about TypeScript source from the TypeScript compiler's own parser (`ts_parse.mjs`).

No type check runs; the compiler module comes from a repository's `node_modules`.
"""

import json
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "ts_parse.mjs"


def typescript_of(repository: Path) -> Path:
    return repository / "node_modules/typescript"


def ts_parse(typescript: Path, path: str, source: str, line: int, scope: str) -> dict:
    """`scope` is "declaration", "module" or "entries"; see `ts_parse.mjs`."""
    request = {"typescript": str(typescript), "file": path, "source": source, "line": line, "scope": scope}
    done = subprocess.run(["node", str(SCRIPT)], input=json.dumps(request), capture_output=True, text=True, check=True)
    return json.loads(done.stdout)
