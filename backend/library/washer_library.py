"""TorqPro Engineering Library - washer library (Phase 1.3 infrastructure).

Metadata-only definition for washers: inner/outer diameter, thickness,
hardness and type. No records are migrated from the existing washer
hardness/bearing-pressure dataset in this phase.

Faz 2.8.5 investigation note (registry metadata synchronisation):
``WASHER_LIBRARY.metadata`` below still declares ``version="0.1"``,
``status="draft"``, ``record_count=0`` -- unchanged since Phase 1.3.
This is **not** washer-specific staleness: every one of the other
eight domain shells in this package (``bolt_library.py``,
``nut_library.py``, ``thread_library.py``, ``friction_condition_library.py``,
etc.) declares the identical Phase 1.3 placeholder, including shells
whose data file has since been populated with real records. It is a
deliberate, package-wide convention: this frozen ``LibraryMetadata``
is a *registration-time* declaration, not a live view of the data
file. The live record count only becomes visible on the *registered*
``WASHER_LIBRARY`` object once something explicitly calls
``backend.library.population.populate_library(WASHER_LIBRARY)`` (which
calls ``replace_records`` and updates ``metadata.record_count`` via
``model_copy`` -- see ``registry.BaseLibrary.replace_records``); it is
never invoked automatically at package import.

Faz 2.8.5 deliberately does **not** hardcode a new static
``record_count``/``status``/``version`` here: doing so for washer
alone, while the other eight shells keep their Phase 1.3 declaration,
would itself be the "double source of truth" the task brief warns
against -- a static literal that silently drifts the moment
``washer_library.json`` gains or loses a record. Nor does it touch
``attach_source`` below, which is a distinct, pinned reference to the
original pre-migration source file (asserted verbatim by
``tests/test_library_migration.py``) used by ``load_from_source()`` /
the migration engine -- a different code path from the Faz 2.4.1+
population mechanism in ``backend.library.population``.

Instead, :func:`washer_library_data_file_state` below derives the
*real*, current state directly and deterministically from
``backend/library/data/washer_library.json`` (which carries its own
independent ``metadata`` block: ``version``, ``record_count``,
``primary_source``) every time it is called -- no cached literal, so
it cannot drift.
"""

from __future__ import annotations

from typing import Any, Dict

from .registry import BaseLibrary, LibraryMetadata, register

WASHER_LIBRARY = register(
    BaseLibrary(
        metadata=LibraryMetadata(
            name="Washer Library",
            version="0.1",
            organization="TorqPro",
            description=(
                "Master definitions for washers: inner/outer diameter, "
                "thickness, hardness, type and bearing pressure limits."
            ),
            source_standard="ISO 887",
            status="draft",
            record_count=0,
            last_revision="",
            supported_units=("mm", "MPa", "HV"),
        )
    )
)

# Ready-to-read future migration source (not loaded in Phase 1.3).
WASHER_LIBRARY.attach_source("data/Pul_Sertlik_Yuzey_Basinci.json")


#: The Faz 2.4.1+ population data file, as already mapped by
#: ``backend.library.population.POPULATION_SOURCES["washer library"]``.
#: Named here purely for readability at call sites -- this constant is
#: not consumed by ``population.py`` (which keeps its own mapping) and
#: does not replace or alias ``attach_source`` above.
WASHER_LIBRARY_DATA_FILE = "washer_library.json"


def washer_library_data_file_state() -> Dict[str, Any]:
    """Deterministic, real-time state of
    ``backend/library/data/washer_library.json``, independent of
    whether ``populate_library(WASHER_LIBRARY)`` has been called
    against the registered ``WASHER_LIBRARY`` object in this process.

    Always re-reads the file (a 223-record JSON file is a negligible,
    infrequent read; this function is not called at package import,
    so it carries none of the "I/O at import time" cost the Phase 1.3
    shells are written to avoid). Returns a plain dict rather than
    mutating ``WASHER_LIBRARY.metadata`` -- see module docstring for
    why the static declaration is intentionally left unchanged.

    Keys:
      - ``declared_status`` / ``declared_record_count``: the static
        Phase 1.3 shell values (``WASHER_LIBRARY.metadata.status`` /
        ``.record_count``), included so a caller can see the
        declared-vs-actual gap in one place.
      - ``data_file_version`` / ``data_file_record_count`` /
        ``data_file_primary_source``: read straight from the data
        file's own ``metadata`` block.
      - ``registry_record_count``: ``len(WASHER_LIBRARY.records)`` --
        what the *in-memory registered* library actually holds right
        now in this process (0 unless ``populate_library``/
        ``populate_all`` has already been called this session).
      - ``activation_hint``: how to bring the registered object's
        in-memory records in sync with the data file, if that has not
        already happened.
    """
    from pathlib import Path
    import json as _json

    data_path = Path(__file__).resolve().parent / "data" / WASHER_LIBRARY_DATA_FILE
    with data_path.open("r", encoding="utf-8") as handle:
        payload = _json.load(handle)
    file_metadata = payload.get("metadata", {})
    file_records = payload.get("records", [])

    return {
        "declared_status": WASHER_LIBRARY.metadata.status,
        "declared_record_count": WASHER_LIBRARY.metadata.record_count,
        "data_file_version": file_metadata.get("version"),
        "data_file_record_count": len(file_records),
        "data_file_primary_source": file_metadata.get("primary_source"),
        "registry_record_count": len(WASHER_LIBRARY.records),
        "activation_hint": (
            "backend.library.population.populate_library(WASHER_LIBRARY) "
            "syncs WASHER_LIBRARY.records and metadata.record_count from "
            "this data file; metadata.status stays 'draft' even after "
            "population (replace_records only updates record_count) -- "
            "this is existing, unmodified registry.py behaviour."
        ),
    }
