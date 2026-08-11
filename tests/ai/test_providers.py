"""Faz v3.0.0-alpha.5 (Provider Abstraction, ADR-0020).

Covers ``backend.ai_gateway.providers.registry``/``deterministic``, and
the additive ``model_identifier``/``is_available()`` capability hooks
on ``backend.ai_gateway.llm_client.AIModelClient`` itself.
"""

from __future__ import annotations

import pytest

from backend.ai_gateway.exceptions import AIGatewayConfigurationError, ProviderNotFoundError
from backend.ai_gateway.llm_client import (
    AIModelClient,
    FakeModelClient,
    ModelResponse,
    PromptContext,
)
from backend.ai_gateway.providers.deterministic import DeterministicModelClient
from backend.ai_gateway.providers.registry import (
    ProviderInfo,
    ProviderRegistry,
    build_default_registry,
)


# --------------------------------------------------------------- interface contract


def test_provider_not_found_error_is_a_configuration_error():
    """ADR-0020: an unknown provider is a caller/wiring mistake, the
    same *kind* of failure as any other AIGatewayConfigurationError --
    not a new, unrelated exception branch."""
    assert issubclass(ProviderNotFoundError, AIGatewayConfigurationError)


def test_ai_model_client_default_model_identifier_mirrors_name():
    """Every pre-existing client (FakeModelClient here) gets a working
    ``model_identifier`` for free via the base class default, without
    needing to override it."""
    client = FakeModelClient()
    assert client.model_identifier == client.name


def test_ai_model_client_default_is_available_is_true():
    client = FakeModelClient()
    assert client.is_available() is True


def test_deterministic_client_is_an_ai_model_client():
    assert isinstance(DeterministicModelClient(), AIModelClient)


def test_deterministic_client_makes_no_network_call_and_is_always_available():
    client = DeterministicModelClient()
    assert client.is_available() is True
    context = PromptContext(query_text="torque nedir", language="tr")
    response = client.complete(context)
    assert isinstance(response, ModelResponse)
    assert response.model_name == "deterministic"
    assert response.text  # non-empty, fixed text -- never fabricated per-query


def test_deterministic_client_is_deterministic_across_calls():
    client = DeterministicModelClient()
    first = client.complete(PromptContext(query_text="a", language="tr"))
    second = client.complete(PromptContext(query_text="completely different query", language="en"))
    assert first.text == second.text


# --------------------------------------------------------------------- registry


def test_registry_register_and_get_round_trip():
    registry = ProviderRegistry()
    client = FakeModelClient()
    registry.register(client)

    assert registry.get(client.name) is client


def test_registry_unknown_provider_raises_provider_not_found_error():
    registry = ProviderRegistry()
    with pytest.raises(ProviderNotFoundError):
        registry.get("does-not-exist")


def test_registry_list_providers_returns_provider_info_sorted_by_name():
    registry = ProviderRegistry()
    registry.register(FakeModelClient())  # name="fake-test-client"
    registry.register(DeterministicModelClient())  # name="deterministic"

    infos = registry.list_providers()
    assert all(isinstance(info, ProviderInfo) for info in infos)
    names = [info.name for info in infos]
    assert names == sorted(names)


def test_registry_list_providers_never_exposes_the_live_client_instance():
    """ProviderInfo is a read-only descriptor -- a caller with only the
    listing cannot reach into it and call complete()."""
    registry = ProviderRegistry()
    registry.register(DeterministicModelClient())
    info = registry.list_providers()[0]
    assert not hasattr(info, "complete")
    assert not hasattr(info, "client")


def test_build_default_registry_registers_only_deterministic_provider():
    """ADR-0020 scope limit: no networked provider (OpenAI/Claude/
    Ollama) is registered in this phase."""
    registry = build_default_registry()
    infos = registry.list_providers()
    assert [info.name for info in infos] == ["deterministic"]
    assert infos[0].available is True


def test_build_default_registry_deterministic_provider_is_selectable():
    registry = build_default_registry()
    client = registry.get("deterministic")
    assert isinstance(client, DeterministicModelClient)
