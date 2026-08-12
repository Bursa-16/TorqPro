"""Reusable benchmark measurement harness for rc.1 Performance &
Reliability tests.

Not a pytest plugin, not a new dependency -- a small, self-contained
module used by ``tests/performance/*`` to produce a reproducible
p50/p95/p99/throughput summary for a callable, and to persist those
summaries to a JSON baseline file for future runs to compare against
(informationally; see ``tests/performance/test_baseline_benchmarks.py``
for how comparisons are used -- always as a soft warning, never a hard
pass/fail threshold, since absolute latency is sandbox/machine
dependent and no such threshold has ever been validated for this
repository, per the rc.1 Performance & Reliability scope).
"""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path
from typing import Callable, List

BASELINE_FILE = Path(__file__).resolve().parent / "baseline_results.json"


def measure(fn: Callable[[], object], n: int, warmup: int = 2) -> "BenchmarkResult":
    """Call ``fn()`` ``n`` times (after ``warmup`` untimed calls) and
    return a :class:`BenchmarkResult`. ``fn`` must return a truthy
    "success" indicator or raise -- callers decide what "success"
    means for their endpoint (usually: response.status_code < 400).
    """
    for _ in range(warmup):
        fn()

    samples: List[float] = []
    errors = 0
    for _ in range(n):
        start = time.perf_counter()
        try:
            ok = fn()
        except Exception:
            ok = False
        elapsed = time.perf_counter() - start
        samples.append(elapsed)
        if not ok:
            errors += 1

    return BenchmarkResult(samples=samples, errors=errors)


class BenchmarkResult:
    def __init__(self, samples: List[float], errors: int):
        self.samples = sorted(samples)
        self.errors = errors
        self.n = len(samples)
        self.total_seconds = sum(samples)

    @staticmethod
    def _percentile(sorted_samples: List[float], pct: float) -> float:
        if not sorted_samples:
            return 0.0
        k = (len(sorted_samples) - 1) * pct
        f = int(k)
        c = min(f + 1, len(sorted_samples) - 1)
        if f == c:
            return sorted_samples[f]
        return sorted_samples[f] + (sorted_samples[c] - sorted_samples[f]) * (k - f)

    @property
    def mean_ms(self) -> float:
        return statistics.mean(self.samples) * 1000 if self.samples else 0.0

    @property
    def p50_ms(self) -> float:
        return self._percentile(self.samples, 0.50) * 1000

    @property
    def p95_ms(self) -> float:
        return self._percentile(self.samples, 0.95) * 1000

    @property
    def p99_ms(self) -> float:
        return self._percentile(self.samples, 0.99) * 1000

    @property
    def throughput_rps(self) -> float:
        return self.n / self.total_seconds if self.total_seconds > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "n": self.n,
            "errors": self.errors,
            "mean_ms": round(self.mean_ms, 3),
            "p50_ms": round(self.p50_ms, 3),
            "p95_ms": round(self.p95_ms, 3),
            "p99_ms": round(self.p99_ms, 3),
            "throughput_rps": round(self.throughput_rps, 2),
        }

    def __repr__(self) -> str:
        d = self.to_dict()
        return (
            f"n={d['n']} errors={d['errors']} mean={d['mean_ms']}ms "
            f"p50={d['p50_ms']}ms p95={d['p95_ms']}ms p99={d['p99_ms']}ms "
            f"throughput={d['throughput_rps']}req/s"
        )


def load_baseline() -> dict:
    if not BASELINE_FILE.exists():
        return {}
    try:
        return json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_baseline(results: dict) -> None:
    """Persist a ``{path_label: BenchmarkResult.to_dict()}`` mapping.
    Called explicitly by the benchmark test run (see
    ``test_baseline_benchmarks.py``'s module-level fixture), never by
    the normal ``pytest -q`` suite -- this file records this
    session's/sandbox's own numbers for future informational
    comparison, not a checked-in cross-machine target.
    """
    BASELINE_FILE.write_text(
        json.dumps(results, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8"
    )
