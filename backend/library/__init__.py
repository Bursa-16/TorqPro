"""TorqPro Engineering Library (Phase 1.3 infrastructure).

Independent professional engineering data layer, separate from the
calculation engine. This phase only introduces the registry and
per-domain metadata shells:

- No engineering formulas were moved or changed
  (``backend.engineering_core`` is untouched).
- No standards metadata was moved or changed
  (``backend.standards`` is untouched).
- No records were migrated from the existing JSON reference files
  under ``data/``; those files remain the current source of truth.
- No API or frontend behaviour changed.

Modules:
- registry:               LibraryMetadata / BaseLibrary / register /
                           get_library / list_libraries / search / validate
- bolt_library:            bolt/screw/stud master definitions (shell)
- nut_library:             nut master definitions (shell)
- washer_library:          washer master definitions (shell)
- thread_library:          thread geometry definitions (shell)
- material_library:        material property sets (shell)
- coating_library:         surface/coating specifications (shell)
- lubrication_library:     lubricant specs and friction conditions (shell)
- strength_class_library:  bolt/nut property class reference (shell)
- compatibility:           bolt/nut/washer compatibility rule set (shell)
"""

from __future__ import annotations

from .registry import (
    BaseLibrary,
    LibraryMetadata,
    get_library,
    list_libraries,
    register,
    search,
    validate,
)
from . import (
    bolt_library,
    coating_library,
    compatibility,
    lubrication_library,
    material_library,
    nut_library,
    strength_class_library,
    thread_library,
    washer_library,
)

__all__ = [
    "LibraryMetadata",
    "BaseLibrary",
    "register",
    "get_library",
    "list_libraries",
    "search",
    "validate",
    "bolt_library",
    "nut_library",
    "washer_library",
    "thread_library",
    "material_library",
    "coating_library",
    "lubrication_library",
    "strength_class_library",
    "compatibility",
]
