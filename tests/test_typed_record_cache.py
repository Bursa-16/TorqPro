"""Faz 2.4.2A tests: BaseLibrary.typed_records() validation cache.

Covers the per-instance typed-record cache added to
``backend.library.registry.BaseLibrary`` (Faz 2.4.2A): validation
call counting (via monkeypatch, no timing-based assertions),
invalidation on ``replace_records``, no cross-instance leakage,
immutability of the cached/returned collection, and that the raising
behaviour of ``typed_records()`` is unchanged.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.library import registry as registry_module
from backend.library.models import BoltRecord, ConfidenceLevel
from backend.library.registry import BaseLibrary, LibraryMetadata


def _bolt_metadata(**overrides):
    defaults = dict(
        name="Bolt Library",
        organization="TorqPro",
        status="draft",
        supported_units=("mm", "N", "MPa"),
    )
    defaults.update(overrides)
    return LibraryMetadata(**defaults)


def _counting_parse_typed_records(monkeypatch):
    """Wrap the real ``parse_typed_records`` with a call counter,
    patched at the import site ``registry.py`` actually calls through
    (``registry_module.models_module.parse_typed_records``)."""
    calls = {"count": 0}
    real = registry_module.models_module.parse_typed_records

    def _wrapped(library_key, records):
        calls["count"] += 1
        return real(library_key, records)

    monkeypatch.setattr(registry_module.models_module, "parse_typed_records", _wrapped)
    return calls


# ---------------------------------------------------------------------
# 1: first call validates
# ---------------------------------------------------------------------


def test_first_call_validates():
    lib = BaseLibrary(metadata=_bolt_metadata())
    lib.replace_records([{"id": "BOLT-1", "designation": "M8", "confidence": 1}])
    typed = lib.typed_records()
    assert len(typed) == 1
    assert isinstance(typed[0], BoltRecord)


# ---------------------------------------------------------------------
# 2: second call does not re-validate the same records
# ---------------------------------------------------------------------


def test_second_call_does_not_revalidate(monkeypatch):
    calls = _counting_parse_typed_records(monkeypatch)
    lib = BaseLibrary(metadata=_bolt_metadata())
    lib.replace_records([{"id": "BOLT-1", "designation": "M8"}])

    first = lib.typed_records()
    second = lib.typed_records()

    assert calls["count"] == 1
    assert first is second  # same cached tuple object, not just equal


def test_typed_records_returns_a_tuple():
    lib = BaseLibrary(metadata=_bolt_metadata())
    lib.replace_records([{"id": "BOLT-1", "designation": "M8"}])
    assert isinstance(lib.typed_records(), tuple)


# ---------------------------------------------------------------------
# 3: reload (replace_records) refreshes the cache
# ---------------------------------------------------------------------


def test_replace_records_invalidates_cache(monkeypatch):
    calls = _counting_parse_typed_records(monkeypatch)
    lib = BaseLibrary(metadata=_bolt_metadata())
    lib.replace_records([{"id": "BOLT-1", "designation": "M8"}])
    lib.typed_records()
    assert calls["count"] == 1

    lib.replace_records([{"id": "BOLT-2", "designation": "M10"}])
    lib.typed_records()
    assert calls["count"] == 2


# ---------------------------------------------------------------------
# 4: new records after mutation -> new typed models, old ones gone
# ---------------------------------------------------------------------


def test_new_records_produce_new_typed_models_not_stale_cache():
    lib = BaseLibrary(metadata=_bolt_metadata())
    lib.replace_records([{"id": "BOLT-1", "designation": "M8"}])
    first = lib.typed_records()
    assert first[0].designation == "M8"

    lib.replace_records([{"id": "BOLT-2", "designation": "M10"}])
    second = lib.typed_records()
    assert second[0].designation == "M10"
    assert first[0].designation == "M8"  # old tuple/object untouched


# ---------------------------------------------------------------------
# 5: no cross-instance leakage
# ---------------------------------------------------------------------


def test_cache_does_not_leak_between_instances():
    lib_a = BaseLibrary(metadata=_bolt_metadata())
    lib_a.replace_records([{"id": "BOLT-A", "designation": "M8"}])
    lib_b = BaseLibrary(metadata=_bolt_metadata())
    lib_b.replace_records([{"id": "BOLT-B", "designation": "M10"}])

    typed_a = lib_a.typed_records()
    typed_b = lib_b.typed_records()

    assert typed_a[0].designation == "M8"
    assert typed_b[0].designation == "M10"
    assert typed_a is not typed_b


# ---------------------------------------------------------------------
# 6: external mutation of the returned collection cannot corrupt cache
# ---------------------------------------------------------------------


def test_returned_tuple_is_immutable():
    lib = BaseLibrary(metadata=_bolt_metadata())
    lib.replace_records([{"id": "BOLT-1", "designation": "M8"}])
    typed = lib.typed_records()
    with pytest.raises(TypeError):
        typed[0] = "corrupted"  # type: ignore[index]
    with pytest.raises(AttributeError):
        typed.append("corrupted")  # type: ignore[attr-defined]


def test_external_records_list_mutation_does_not_affect_cache():
    lib = BaseLibrary(metadata=_bolt_metadata())
    raw = [{"id": "BOLT-1", "designation": "M8"}]
    lib.replace_records(raw)
    raw.append({"id": "BOLT-2", "designation": "M10"})  # mutate caller's own list
    typed = lib.typed_records()
    assert len(typed) == 1  # unaffected -- replace_records() copied raw


# ---------------------------------------------------------------------
# 7: empty record set caches correctly
# ---------------------------------------------------------------------


def test_empty_record_set_is_cached_correctly(monkeypatch):
    calls = _counting_parse_typed_records(monkeypatch)
    lib = BaseLibrary(metadata=_bolt_metadata())
    lib.replace_records([])
    first = lib.typed_records()
    second = lib.typed_records()
    assert first == ()
    assert first is second
    assert calls["count"] == 1


# ---------------------------------------------------------------------
# 8: validation exception behaviour is unchanged
# ---------------------------------------------------------------------


def test_typed_records_still_raises_on_invalid_record():
    lib = BaseLibrary(
        metadata=LibraryMetadata(name="Thread Library", organization="TorqPro")
    )
    lib.replace_records([{"id": "no-designation"}])
    with pytest.raises(ValidationError):
        lib.typed_records()


def test_typed_records_raising_does_not_poison_cache_for_next_valid_call():
    lib = BaseLibrary(
        metadata=LibraryMetadata(name="Thread Library", organization="TorqPro")
    )
    lib.replace_records([{"id": "no-designation"}])
    with pytest.raises(ValidationError):
        lib.typed_records()

    lib.replace_records([{"id": "T1", "designation": "M8"}])
    typed = lib.typed_records()  # must succeed, not raise a stale error
    assert len(typed) == 1


# ---------------------------------------------------------------------
# 9: find_schema_violations behaviour is unchanged (non-raising,
# bypasses the cache by design -- see registry.py docstring)
# ---------------------------------------------------------------------


def test_find_schema_violations_still_reports_without_raising():
    lib = BaseLibrary(
        metadata=LibraryMetadata(name="Thread Library", organization="TorqPro")
    )
    lib.replace_records([{"id": "no-designation"}])
    violations = lib.find_schema_violations()
    assert violations != []


def test_confidence_level_still_parsed_through_cache():
    lib = BaseLibrary(metadata=_bolt_metadata())
    lib.replace_records([{"id": "BOLT-1", "designation": "M8", "confidence": 1}])
    typed = lib.typed_records()
    assert typed[0].confidence is ConfidenceLevel.G1
