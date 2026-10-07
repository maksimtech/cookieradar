"""The benchmarks need the CodSpeed runner, and only codspeed.yml installs it.

That is deliberate — the suite must not need a benchmark runner to check
correctness — but `pytest`, as the README says to run it, ended with three
`fixture 'benchmark' not found` errors that said nothing about the code. Without
the runner they are skipped and say why; codspeed.yml runs them as before.
"""
import pytest


def pytest_collection_modifyitems(config, items):
    if config.pluginmanager.hasplugin("codspeed"):
        return
    skip = pytest.mark.skip(reason="the CodSpeed runner is not installed: codspeed.yml runs the benchmarks")
    for item in items:
        if "benchmark" in getattr(item, "fixturenames", ()):
            item.add_marker(skip)
