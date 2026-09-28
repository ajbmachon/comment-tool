"""The rewrite job a "rewrite" classification carries, built by code from the parser with no model.

The tool only classifies; the calling agent or another system writes the new comment (Andre,
28.09.2026). For each doc comment the rules send to "rewrite", the job holds what that writer needs
and nothing else: the declaration's signature (name, parameters with types and defaults, return
type, the failure or thrown types, decorators or heritage), the documented code, the old comment,
and the answers that led to "rewrite", in plain words. A module-level doc (a file header or module
docstring) gets the module's exported or public names, and a package's modules, instead of one
declaration. Python is read with `ast`; TypeScript with the TypeScript compiler's parser from the
repository's own `node_modules` (`ts_parse.mjs`), with no type check. `sweep.py` attaches the job to
each decided rewrite; `main` rebuilds the jobs of stored rounds.
usage: uv run python rewrite_packet.py <cases.jsonl> <pass.jsonl> <out.jsonl> [per repository]
"""

import ast
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import compose
from comment_review import CommentCase
from sample_round4 import REPOSITORIES
from ts_parse import ts_parse, typescript_of


def git_source(repository: Path, commit: str, path: str) -> str:
    return subprocess.run(["git", "show", f"{commit}:{path}"], cwd=repository, capture_output=True, text=True,
                          check=True).stdout


def ts_signature(repository: Path, path: str, source: str, line: int, scope: str = "declaration") -> dict:
    return ts_parse(typescript_of(repository), path, source, line, scope)


def python_signature(source: str, docstring_line: int, package_modules: list[str]) -> dict:
    """The signature of the module, class or function whose docstring starts on `docstring_line`."""
    tree = ast.parse(source)
    owner = next((node for node in ast.walk(tree) if _docstring_line(node) == docstring_line), None)
    if owner is None:
        return {"kind": "none"}
    if isinstance(owner, ast.Module):
        return {"kind": "module", "public_names": _public_names(owner), "package_modules": package_modules}
    if isinstance(owner, ast.ClassDef):
        return {"kind": "class", "name": owner.name, "bases": [ast.unparse(base) for base in owner.bases],
                "decorators": [ast.unparse(d) for d in owner.decorator_list], "fields": _fields(owner),
                "methods": [node.name for node in owner.body if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)],
                "raises": _raised(owner)}
    return {"kind": "async function" if isinstance(owner, ast.AsyncFunctionDef) else "function", "name": owner.name,
            "decorators": [ast.unparse(d) for d in owner.decorator_list], "parameters": _parameters(owner.args),
            "return_type": ast.unparse(owner.returns) if owner.returns else None, "raises": _raised(owner)}


def _docstring_line(node: ast.AST) -> int | None:
    body = getattr(node, "body", None)
    if not isinstance(body, list) or not body or not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
        return None
    first = body[0]
    is_text = isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str)
    return first.lineno if is_text else None


def _parameters(args: ast.arguments) -> list[dict]:
    positional = [*args.posonlyargs, *args.args]
    defaults = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)
    listed = [_parameter(arg, default) for arg, default in zip(positional, defaults, strict=True)]
    if args.vararg:
        listed.append(_parameter(args.vararg, None, "*"))
    listed += [_parameter(arg, default) for arg, default in zip(args.kwonlyargs, args.kw_defaults, strict=True)]
    if args.kwarg:
        listed.append(_parameter(args.kwarg, None, "**"))
    return listed


def _parameter(arg: ast.arg, default: ast.expr | None, star: str = "") -> dict:
    return {"name": star + arg.arg, "type": ast.unparse(arg.annotation) if arg.annotation else None,
            "default": ast.unparse(default) if default is not None else None}


def _raised(node: ast.AST) -> list[str]:
    raised = []
    for child in ast.walk(node):
        if isinstance(child, ast.Raise):
            exc = child.exc
            raised.append("re-raise" if exc is None else ast.unparse(exc.func if isinstance(exc, ast.Call) else exc))
    return list(dict.fromkeys(raised))


def _fields(owner: ast.ClassDef) -> list[dict]:
    return [{"name": ast.unparse(node.target), "type": ast.unparse(node.annotation)}
            for node in owner.body if isinstance(node, ast.AnnAssign)]


def _public_names(module: ast.Module) -> list[str]:
    named = (node for node in module.body if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef))
    return [node.name for node in named if not node.name.startswith("_")]


def signature_at(repository: Path, commit: str, path: str, comment_line: int, documented_line: int,
                 doc_kind: str) -> dict:
    """The parser's signature of what the comment starting on `comment_line` documents."""
    source = git_source(repository, commit, path)
    if path.endswith(".py"):
        return python_signature(source, comment_line, _package_modules(repository, commit, path))
    scope = "module" if doc_kind == "header" else "declaration"
    return ts_signature(repository, path, source, documented_line, scope)


def _package_modules(repository: Path, commit: str, path: str) -> list[str]:
    """For a package's `__init__.py`, the modules and subpackages it holds; empty for other files."""
    if not path.endswith("__init__.py"):
        return []
    folder = path.rsplit("/", 1)[0] + "/"
    listed = subprocess.run(["git", "ls-tree", "--name-only", commit, folder], cwd=repository, capture_output=True,
                            text=True, check=True).stdout.splitlines()
    return [entry.removeprefix(folder) for entry in listed if not entry.endswith(("__init__.py", "_test.py", "conftest.py"))]


def rewrite_job(repository: Path, commit: str, case: CommentCase, doc_kind: str, documented: dict,
                probabilities: dict) -> dict:
    """What the writer gets: signature, documented code (`lines` and `code`), old comment, and why it
    goes to rewrite in plain words."""
    signature = signature_at(repository, commit, case.file, case.first_line, documented["lines"][0], doc_kind)
    return {
        "doc_kind": doc_kind,
        "old_comment": case.text,
        "why_rewrite": compose.rewrite_reasons(probabilities, case.facts),
        "signature": signature,
        "documented_code": None if signature["kind"] == "module" else documented,
    }


def rewrite_packet(case: dict, row: dict) -> dict:
    """A stored round's rewrite job, with where it came from."""
    provenance = case["provenance"]
    comment = CommentCase(provenance["path"], *provenance["comment_lines"], case["state"]["comment"]["text"],
                          case["state"]["code"]["language"], case["code_facts"])
    documented = {"lines": provenance["code_after_lines"], "code": case["state"]["code"]["after_comment"]}
    repository = REPOSITORIES[provenance["repository"]][0]
    return {"case_id": case["case_id"], "location": f"{provenance['path']}:{provenance['comment_lines'][0]}",
            "commit": provenance["commit"], **rewrite_job(repository, provenance["commit"], comment, case["kind"], documented, row["probabilities"])}


def main() -> None:
    cases_path, passes_path, out_path = map(Path, sys.argv[1:4])
    per_repository = int(sys.argv[4]) if len(sys.argv) > 4 else 5
    cases = {case["case_id"]: case for case in map(json.loads, cases_path.read_text().splitlines())}
    rows = [json.loads(line) for line in passes_path.read_text().splitlines()]
    rewrites = [row for row in rows if row["action"] == "rewrite" and "escalate" not in row]
    taken = Counter()
    packets = []
    for row in rewrites:
        case = cases[row["case_id"]]
        repository = case["provenance"]["repository"]
        if taken[repository] < per_repository:
            taken[repository] += 1
            packets.append(rewrite_packet(case, row))
    out_path.write_text("".join(json.dumps(packet) + "\n" for packet in packets))
    print(f"{len(packets)} rewrite packets from {len(rows)} reviewed doc comments")


if __name__ == "__main__":
    main()
