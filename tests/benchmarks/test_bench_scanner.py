"""CookieRadar benchmarks."""
import pytest
from cookieradar.scanner import is_tracker, TRACKER_DOMAINS


def test_bench_is_tracker(benchmark):
    benchmark(is_tracker, "https://www.googletagmanager.com/gtm.js")


def test_bench_is_tracker_unknown(benchmark):
    benchmark(is_tracker, "https://www.tim.it/page.html")


def test_bench_tracker_domains_lookup(benchmark):
    def lookup():
        return [d for d in TRACKER_DOMAINS if "google" in d]
    benchmark(lookup)
