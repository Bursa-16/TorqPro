"""TorqPro Engineering Library - friction condition library (Faz 2.6.2A shell).

Metadata-only definition for combination-dependent friction data: the
overall/split friction coefficient, nut factor and scatter values
that depend on a *pairing* of coating + lubricant + assembly
condition, rather than on either alone (see
``docs/adr/ADR-0010-coating-lubrication-friction-data-ownership.md``).

No records are populated in this phase. This module only establishes
the registry shell, mirroring how ``joint_hardware_library.py``
started in Faz 2.4.1C before its own (still pending) population
phase. Populating real records -- including migrating the 15 Tablo
9.4 records currently on ``LubricationRecord`` -- is Faz 2.6.2B,
governed by the migration plan in ADR-0010 and
``docs/phases/PHASE_2.6.2A_COATING_FRICTION_DATA_OWNERSHIP.md``.
"""

from __future__ import annotations

from .registry import BaseLibrary, LibraryMetadata, register

FRICTION_CONDITION_LIBRARY = register(
    BaseLibrary(
        metadata=LibraryMetadata(
            name="Friction Condition Library",
            version="0.1",
            organization="TorqPro",
            description=(
                "Combination-dependent friction data: overall/split "
                "friction coefficient, nut factor and scatter values "
                "keyed by coating + lubricant + assembly-condition "
                "pairing, referencing CoatingRecord/LubricationRecord "
                "by id. Faz 2.6.2A infrastructure shell only -- no "
                "record populated yet."
            ),
            source_standard="",
            status="draft",
            record_count=0,
            last_revision="",
            supported_units=("dimensionless", "degC"),
        )
    )
)

# Ready-to-read future population source (empty in Faz 2.6.2A -- see
# module docstring). Mirrors the "explicit, opt-in" convention already
# established by every other domain shell in this package.
FRICTION_CONDITION_LIBRARY.attach_source("data/friction_condition_library.json")
