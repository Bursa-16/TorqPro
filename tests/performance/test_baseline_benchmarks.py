"""v3.0.0-rc.1 Performance & Reliability -- P1: performance baseline /
benchmark infrastructure.

**Not part of the normal `pytest -q` run.** Every test in this module
is skipped at collection time unless ``TORQPRO_RUN_PERFORMANCE_TESTS``
is set, so the full suite's runtime is unaffected (this file is still
collected -- the skip itself costs a fraction of a millisecond per
test, nothing close to "slowing down" the suite). To actually run the
benchmark:

    TORQPRO_RUN_PERFORMANCE_TESTS=1 pytest tests/performance/ -v -s

Each test measures one critical path (see ``tests/performance/bench_utils.py``
for the measurement harness) and asserts only:

1. zero request errors across the sample (a *correctness* floor, not
   a latency threshold), and
2. the benchmark itself produced a non-trivial sample (n matches the
   configured count).

No absolute millisecond pass/fail threshold is used anywhere in this
file -- Stage 0 found no previously-validated latency target for this
repository, and this sandbox's own speed is not a reliable stand-in
for one. Results (p50/p95/p99/mean/throughput per path) are printed
and also written to ``tests/performance/baseline_results.json`` as a
*this-run's-own* reference point for future informational comparison,
never a checked-in cross-machine target.

Critical paths covered (see the rc.1 Stage 0 / Performance &
Reliability scope for the full rationale of each):

* POST /api/calculations
* GET /api/projects (list) + GET /api/projects/{id}/traceability
* GET /api/projects/{id}/release-package
* POST /api/ai/torque-recommendation (Torque Recommendation Engine)
* POST /api/ai/engineering-reasoning (Engineering Reasoning Engine)
* POST /api/ai/query (AI gateway path -- production default provider
  is always-unavailable, per v3.0.0-alpha.4/alpha.5; 503 is therefore
  the *expected*, not erroneous, response here and is treated as
  benchmark "success" alongside 200)
* GET /api/question-bank/stats (Question Bank / knowledge retrieval)
* GET /api/admin/audit (audit-log read path; every POST in this file
  also exercises the audit-log *write* path as a side effect of the
  action it performs)
* GET /api/health, GET /health/ready (health/readiness)
"""

from __future__ import annotations

import os
import uuid

import pytest

from tests.performance.bench_utils import load_baseline, measure, save_baseline

pytestmark = pytest.mark.skipif(
    not os.environ.get("TORQPRO_RUN_PERFORMANCE_TESTS"),
    reason="Performance benchmarks are opt-in -- set TORQPRO_RUN_PERFORMANCE_TESTS=1 to run.",
)

_N_SAMPLES = 40

_SEGMENT = {"length_mm": 20, "modulus_mpa": 210000, "area_mm2": 200}

# Reused verbatim from tests/torque_recommendation/test_beta1_http_route.py
# and tests/ai/reasoning/test_http_route_reasoning.py -- a known-good,
# already-proven payload, not invented for this file.
_TORQUE_PAYLOAD = {
    "diameter_mm": 10,
    "pitch_mm": 1.5,
    "rp02_mpa": 900,
    "target_yield_ratio": 0.5,
    "max_utilization_ratio": 0.9,
    "mu_thread_nom": 0.12,
    "mu_bearing_nom": 0.10,
    "effective_bearing_diameter_mm": 14,
    "bolt_segments": [_SEGMENT],
    "joint_segments": [_SEGMENT],
    "minimum_required_clamp_load_n": 1000,
    "external_axial_load_n": 500,
    "fail_threshold": 0.95,
    "warn_threshold": 0.80,
}

# Reused verbatim from tests/test_faz_2_8_7_joint_analysis.py's
# NOMINAL_KWARGS.
_JOINT_ANALYSIS_PAYLOAD = {
    "diameter_mm": 10.0,
    "pitch_mm": 1.5,
    "rp02_mpa": 900.0,
    "target_yield_ratio": 0.8,
    "max_utilization_ratio": 0.9,
    "mu_thread_nom": 0.12,
    "mu_bearing_nom": 0.12,
    "effective_bearing_diameter_mm": 14.0,
    "bolt_segments": [_SEGMENT],
    "joint_segments": [_SEGMENT],
    "external_axial_load_n": 5000.0,
    "minimum_required_clamp_load_n": 8000.0,
    "applied_torque_nm": 45.0,
    "fail_threshold": 1.0,
    "warn_threshold": 0.9,
}


@pytest.fixture(scope="module")
def bench_user(client, auth_headers):
    """One dedicated user + one project + a handful of calculations,
    created once for the whole module so every benchmark test reads
    the same warm, realistic dataset instead of each starting from
    zero (list/traceability/release-package endpoints are far more
    representative of real usage against a project that already has
    several calculations, not exactly one). Logs in directly (rather
    than via the function-scoped ``login_as`` fixture, which cannot be
    requested from a module-scoped fixture) using the same
    ``client.post("/api/login", ...)`` call ``login_as`` itself wraps."""
    username = f"bench_{uuid.uuid4().hex[:8]}"
    password = "BenchTest1"
    r = client.post(
        "/api/admin/users",
        headers=auth_headers,
        json={"username": username, "display_name": "Benchmark User", "password": password, "role": "engineer"},
    )
    assert r.status_code == 200, r.text
    r = client.post("/api/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    headers = {"Authorization": "Bearer " + r.json()["token"]}

    r = client.post("/api/projects", headers=headers, json={"name": "Benchmark Project"})
    assert r.status_code == 200, r.text
    project_id = r.json()["id"]

    for _ in range(10):
        r = client.post(
            "/api/calculations",
            headers=headers,
            json={"thread": "M10", "torque_nm": 45.0, "standard": "VDI2230", "project_id": project_id},
        )
        assert r.status_code == 200, r.text

    return {"headers": headers, "project_id": project_id}


_results: dict = {}


def _record(label: str, result) -> None:
    _results[label] = result.to_dict()
    print(f"\n[bench] {label}: {result}")


def test_benchmark_health(client):
    result = measure(lambda: client.get("/api/health").status_code == 200, n=_N_SAMPLES)
    _record("GET /api/health", result)
    assert result.errors == 0
    assert result.n == _N_SAMPLES


def test_benchmark_health_ready(client):
    result = measure(lambda: client.get("/health/ready").status_code == 200, n=_N_SAMPLES)
    _record("GET /health/ready", result)
    assert result.errors == 0
    assert result.n == _N_SAMPLES


def test_benchmark_create_calculation(client, bench_user):
    headers = bench_user["headers"]
    result = measure(
        lambda: client.post(
            "/api/calculations",
            headers=headers,
            json={"thread": "M10", "torque_nm": 45.0, "standard": "VDI2230"},
        ).status_code
        == 200,
        n=_N_SAMPLES,
    )
    _record("POST /api/calculations", result)
    assert result.errors == 0
    assert result.n == _N_SAMPLES


def test_benchmark_list_projects(client, bench_user):
    headers = bench_user["headers"]
    result = measure(lambda: client.get("/api/projects", headers=headers).status_code == 200, n=_N_SAMPLES)
    _record("GET /api/projects", result)
    assert result.errors == 0
    assert result.n == _N_SAMPLES


def test_benchmark_project_traceability(client, bench_user):
    headers, project_id = bench_user["headers"], bench_user["project_id"]
    result = measure(
        lambda: client.get(f"/api/projects/{project_id}/traceability", headers=headers).status_code == 200,
        n=_N_SAMPLES,
    )
    _record("GET /api/projects/{id}/traceability", result)
    assert result.errors == 0
    assert result.n == _N_SAMPLES


def test_benchmark_project_release_package(client, bench_user):
    headers, project_id = bench_user["headers"], bench_user["project_id"]
    result = measure(
        lambda: client.get(f"/api/projects/{project_id}/release-package", headers=headers).status_code == 200,
        n=_N_SAMPLES,
    )
    _record("GET /api/projects/{id}/release-package", result)
    assert result.errors == 0
    assert result.n == _N_SAMPLES


def test_benchmark_joint_analysis(client, bench_user):
    headers = bench_user["headers"]
    result = measure(
        lambda: client.post(
            "/api/engineering/joint-analysis", headers=headers, json=_JOINT_ANALYSIS_PAYLOAD
        ).status_code
        == 200,
        n=_N_SAMPLES,
    )
    _record("POST /api/engineering/joint-analysis", result)
    assert result.errors == 0
    assert result.n == _N_SAMPLES


def test_benchmark_torque_recommendation(client, bench_user):
    headers = bench_user["headers"]
    result = measure(
        lambda: client.post(
            "/api/ai/torque-recommendation", headers=headers, json=_TORQUE_PAYLOAD
        ).status_code
        == 200,
        n=_N_SAMPLES,
    )
    _record("POST /api/ai/torque-recommendation", result)
    assert result.errors == 0
    assert result.n == _N_SAMPLES


def test_benchmark_engineering_reasoning(client, bench_user):
    headers = bench_user["headers"]
    r = client.post("/api/ai/torque-recommendation", headers=headers, json=_TORQUE_PAYLOAD)
    assert r.status_code == 200, r.text
    trace_id = r.json()["trace_id"]

    result = measure(
        lambda: client.post(
            "/api/ai/engineering-reasoning", headers=headers, json={"trace_id": trace_id}
        ).status_code
        == 200,
        n=_N_SAMPLES,
    )
    _record("POST /api/ai/engineering-reasoning", result)
    assert result.errors == 0
    assert result.n == _N_SAMPLES


def test_benchmark_ai_query_gateway_path(client, bench_user):
    """Production's default AI provider is always-unavailable (see
    v3.0.0-alpha.4/alpha.5) -- 503 is the correct, expected response
    here, not a benchmark error. This still exercises the full gateway
    path (permission check, context building, provider-unavailable
    handling, audit write)."""
    headers = bench_user["headers"]
    result = measure(
        lambda: client.post(
            "/api/ai/query", headers=headers, json={"query_text": "benchmark query"}
        ).status_code
        in (200, 503),
        n=_N_SAMPLES,
    )
    _record("POST /api/ai/query", result)
    assert result.errors == 0
    assert result.n == _N_SAMPLES


def test_benchmark_question_bank_stats(client, bench_user):
    headers = bench_user["headers"]
    result = measure(lambda: client.get("/api/question-bank/stats", headers=headers).status_code == 200, n=_N_SAMPLES)
    _record("GET /api/question-bank/stats", result)
    assert result.errors == 0
    assert result.n == _N_SAMPLES


def test_benchmark_admin_audit_read(client, auth_headers):
    result = measure(lambda: client.get("/api/admin/audit", headers=auth_headers).status_code == 200, n=_N_SAMPLES)
    _record("GET /api/admin/audit", result)
    assert result.errors == 0
    assert result.n == _N_SAMPLES


def test_zzz_save_baseline_results():
    """Runs last alphabetically within this module -- persists every
    result recorded by the tests above in this session. Not a
    correctness assertion; only fails if nothing was recorded at all
    (which would mean the module-scoped fixtures/tests above never
    ran, itself a real problem worth surfacing)."""
    assert _results, "no benchmark results were recorded"
    previous = load_baseline()
    save_baseline(_results)
    if previous:
        print("\n[bench] Comparison against this repo's previous local baseline run "
              "(informational only, not a pass/fail gate):")
        for label, current in _results.items():
            prior = previous.get(label)
            if prior:
                print(f"  {label}: p50 {prior['p50_ms']}ms -> {current['p50_ms']}ms, "
                      f"p95 {prior['p95_ms']}ms -> {current['p95_ms']}ms")
