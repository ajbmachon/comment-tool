"""Test markers: `local` tests read the local heedvane and analysis-engine checkouts, the round data or
the heedvane-evals checkout, so hosted CI deselects them (`-m "not local"`); run everything locally."""


def pytest_configure(config) -> None:
    config.addinivalue_line("markers", "local: needs local repository checkouts or round data")
