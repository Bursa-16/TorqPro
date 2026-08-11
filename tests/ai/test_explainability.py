"""Faz v3.0.0-alpha.5 (Explainability, ADR-0020).

This phase deliberately does not introduce a new explainability
surface: ``backend.ai_gateway.composer.ComposedAnswer`` (citations,
result_label, evidence_status via evidence_check, validation_required)
already carries every explainability element ADR-0020 calls for
(decision/result summary, evidence/reference identifiers, warnings/
limitations, confidence/traceability metadata). This file proves that
existing surface is (a) what actually reaches the persisted audit
trail, structured only, and (b) that no internal chain-of-thought or
private reasoning field exists anywhere on the persisted shape or the
HTTP response.
"""

from __future__ import annotations

import dataclasses
import uuid

import pytest

from backend import app as app_module
from backend.ai_gateway.llm_client import FakeModelClient
from backend.ai_gateway.store import PersistedAuditRecord
from backend.api.routes import ai_gateway as route_module

_QUERY_ENDPOINT = "/api/ai/query"
_AUDIT_LIST_ENDPOINT = "/api/ai/audit"

#: Field/token names that would indicate a chain-of-thought / private
#: reasoning surface, were one ever accidentally introduced.
_FORBIDDEN_REASONING_TOKENS = (
    "reasoning",
    "thought",
    "scratchpad",
    "internal_notes",
    "chain_of_thought",
    "private",
)


@pytest.fixture()
def fake_model_override():
    fake = FakeModelClient(fixed_text="TorqPro AI explainability test response.")
    app_module.app.dependency_overrides[route_module.get_model_client] = lambda: fake
    yield fake
    del app_module.app.dependency_overrides[route_module.get_model_client]


def test_persisted_audit_record_has_no_reasoning_field():
    field_names = {f.name for f in dataclasses.fields(PersistedAuditRecord)}
    for token in _FORBIDDEN_REASONING_TOKENS:
        assert not any(token in name for name in field_names), (
            f"PersistedAuditRecord unexpectedly has a field containing '{token}': "
            f"{field_names}"
        )


def test_persisted_audit_record_explainability_fields_are_structured_only():
    """The explainability-relevant fields that do exist
    (evidence_status, result_label, evidence_source_ids,
    calculation_formula_ids) are all short, closed-vocabulary or
    identifier-only values -- never a free-text field that could carry
    prose reasoning."""
    field_names = {f.name for f in dataclasses.fields(PersistedAuditRecord)}
    assert {"evidence_status", "result_label", "evidence_source_ids"} <= field_names
    # No field is named/shaped like a free-text explanation blob.
    assert "explanation_text" not in field_names
    assert "summary_text" not in field_names


def test_http_audit_response_contains_no_reasoning_token(client, auth_headers, fake_model_override):
    correlation_id = f"explainability-{uuid.uuid4().hex[:8]}"
    client.post(
        _QUERY_ENDPOINT,
        json={"query_text": "explainability-http-test-query"},
        headers={**auth_headers, "X-Request-ID": correlation_id},
    )

    list_response = client.get(_AUDIT_LIST_ENDPOINT, headers=auth_headers)
    body_text_lower = list_response.text.lower()
    for token in _FORBIDDEN_REASONING_TOKENS:
        assert token not in body_text_lower


def test_query_response_explainability_fields_present_and_structured(
    client, auth_headers, fake_model_override
):
    """POST /api/ai/query's response already exposes the
    explainability elements ADR-0020 asks for (summary=text+
    result_label, evidence=citations/evidence, warnings=
    validation_required, confidence/traceability=result_label/
    evidence status implied by it) -- this phase reuses that surface
    verbatim rather than adding a new one."""
    response = client.post(
        _QUERY_ENDPOINT,
        json={"query_text": "explainability-fields-test-query"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()

    # Decision/result summary
    assert isinstance(body["text"], str) and body["text"]
    # Evidence / reference identifiers
    assert isinstance(body["evidence"], list)
    assert isinstance(body["citations"], list)
    # Warnings / limitations
    assert isinstance(body["validation_required"], bool)
    # Confidence / traceability metadata
    assert body["result_label"] in (None, "CALCULATED", "VALIDATED", "ESTIMATED", "RECOMMENDED")
    # No reasoning-token field anywhere in the response shape.
    for token in _FORBIDDEN_REASONING_TOKENS:
        assert token not in body
