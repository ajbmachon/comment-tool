"""Test markers: `local` tests read the local heedvane and analysis-engine checkouts, the round data or
the heedvane-evals checkout, so hosted CI deselects them (`-m "not local"`); run everything locally."""

from pathlib import Path

import pytest


@pytest.fixture
def script_repository(tmp_path):
    """A real isolated source repository using the installed compiler, without copying its runtime."""
    compiler = tmp_path / "node_modules/typescript"
    compiler.parent.mkdir()
    compiler.symlink_to(Path.home() / "Projects/heedvane/node_modules/typescript", target_is_directory=True)
    return tmp_path


def pytest_configure(config) -> None:
    config.addinivalue_line("markers", "local: needs local repository checkouts or round data")
