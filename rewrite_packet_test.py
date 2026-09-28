"""The static rewrite packet reads signatures from the parser, for Python and TypeScript."""

from pathlib import Path

import pytest

from rewrite_packet import python_signature, ts_signature

PYTHON = '''
def load(path: Path, mode: str = "r", size: int = 0, *, strict: bool = False, **options) -> dict[str, int]:
    """Load the counts."""
    if not path.exists():
        raise FileNotFoundError(path)
    return {}
'''
TYPESCRIPT = """
/** Reads the plan. */
export function readPlan(id: string, limit = 10): Effect.Effect<Plan, PlanMissing, Database> {
  return Effect.fail(new PlanMissing({ id }));
}
"""


def test_a_python_function_signature_comes_from_the_parser():
    signature = python_signature(PYTHON, docstring_line=3, package_modules=[])

    assert signature["name"] == "load"
    assert signature["parameters"] == [{"name": "path", "type": "Path", "default": None},
                                       {"name": "mode", "type": "str", "default": "'r'"},
                                       {"name": "size", "type": "int", "default": "0"},
                                       {"name": "strict", "type": "bool", "default": "False"},
                                       {"name": "**options", "type": None, "default": None}]
    assert (signature["return_type"], signature["raises"]) == ("dict[str, int]", ["FileNotFoundError"])


@pytest.mark.local
def test_a_typescript_function_signature_names_its_effect_failure():
    signature = ts_signature(Path.home() / "Projects/heedvane", "plan.ts", TYPESCRIPT, line=3)

    assert signature["name"] == "readPlan"
    assert [(p["name"], p["type"], p["default"]) for p in signature["parameters"]] == [("id", "string", None), ("limit", None, "10")]
    assert (signature["failure_type"], signature["thrown_or_failed"]) == ("PlanMissing", ["PlanMissing"])


@pytest.mark.local
def test_a_typescript_header_gets_the_module_exports():
    signature = ts_signature(Path.home() / "Projects/heedvane", "plan.ts", TYPESCRIPT, line=2, scope="module")

    assert signature == {"kind": "module", "exports": [{"name": "readPlan", "kind": "FunctionDeclaration"}]}
