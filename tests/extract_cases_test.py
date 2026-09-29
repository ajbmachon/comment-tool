"""Commented-out code is decided by code alone, so prose must never read as code."""

from comment_tool.core.extract_cases import is_commented_out_code


def test_typescript_prose_that_starts_with_a_keyword_is_not_code():
    for prose in ("for custom agents", "if the plan is missing, fall back to the default", "return the cached value",
                  "export the report before the run ends", "while the lock is held", "import happens once per run"):
        assert not is_commented_out_code([prose], "//"), prose


def test_typescript_statements_are_code():
    for code in ("for (const row of rows) {", "if (done) return;", "return cached;", "const limit = 3;",
                 'import { plan } from "./plan";', "await flush(queue);", "logger.debug(event)"):
        assert is_commented_out_code([code], "//"), code
