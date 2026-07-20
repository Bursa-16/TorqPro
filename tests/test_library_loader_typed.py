"""Faz 2.4.0 tests: loader.py load_typed().

Uses a temporary JSON source file so no existing data/*.json file is
read or depended upon (no real record migration in this phase).
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from backend.library import loader
from backend.library.models import ThreadRecord
from backend.library.registry import BaseLibrary, LibraryMetadata


def _thread_library() -> BaseLibrary:
    return BaseLibrary(
        metadata=LibraryMetadata(name="Thread Library", organization="TorqPro")
    )


def test_load_typed_parses_valid_records(tmp_path):
    source = tmp_path / "threads.json"
    source.write_text(
        json.dumps({"records": [{"id": "T1", "designation": "M8"}]}),
        encoding="utf-8",
    )
    lib = _thread_library()
    lib.attach_source(str(source))

    typed = loader.load_typed(lib, using=loader.LibraryLoader())

    assert len(typed) == 1
    assert isinstance(typed[0], ThreadRecord)
    assert typed[0].designation == "M8"
    # load_typed must not mutate the library's own record store.
    assert lib.records == []


def test_load_typed_raises_on_invalid_record(tmp_path):
    source = tmp_path / "threads.json"
    source.write_text(
        json.dumps({"records": [{"id": "no-designation"}]}), encoding="utf-8"
    )
    lib = _thread_library()
    lib.attach_source(str(source))

    with pytest.raises(ValidationError):
        loader.load_typed(lib, using=loader.LibraryLoader())


def test_load_typed_without_source_raises_value_error():
    lib = _thread_library()
    with pytest.raises(ValueError):
        loader.load_typed(lib, using=loader.LibraryLoader())
