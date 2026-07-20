"""TorqPro Engineering Library - search engine (Phase 1.4 infrastructure).

Focused search entry points across the registered libraries: by
domain category (bolt/nut/washer/material/thread/coating/strength
class), by free-text keyword, and by referenced standard. Built only
on top of ``backend.library.registry``; touches no other package.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .registry import BaseLibrary, get_library, list_libraries
from .registry import search as _keyword_search

# Maps the domain vocabulary the library spec uses to registry keys.
CATEGORY_LIBRARY_MAP: Dict[str, str] = {
    "bolt": "bolt library",
    "nut": "nut library",
    "washer": "washer library",
    "material": "material library",
    "thread": "thread library",
    "coating": "coating library",
    "strength_class": "strength class library",
    "strength class": "strength class library",
    "lubrication": "lubrication library",
    "compatibility": "compatibility library",
    "oem": "oem library",
}


def search_by_category(category: str) -> Optional[BaseLibrary]:
    """Return the library matching a known domain category (e.g.
    'bolt', 'nut', 'thread', 'strength_class'), or ``None`` if the
    category is unrecognised or not registered."""
    key = CATEGORY_LIBRARY_MAP.get(category.strip().lower())
    if key is None:
        return None
    try:
        return get_library(key)
    except KeyError:
        return None


def search_by_keyword(term: str) -> List[BaseLibrary]:
    """Keyword search across library name/organization/description/
    source standard (delegates to the registry's existing search)."""
    return _keyword_search(term)


def search_by_standard(standard: str) -> List[BaseLibrary]:
    """Return libraries whose ``source_standard`` contains
    ``standard`` (case-insensitive, substring match)."""
    needle = standard.strip().lower()
    if not needle:
        return []
    matches = [
        lib for lib in list_libraries() if needle in lib.metadata.source_standard.lower()
    ]
    return sorted(matches, key=lambda lib: lib.metadata.key)


def search(
    keyword: str = "",
    category: Optional[str] = None,
    standard: Optional[str] = None,
) -> List[BaseLibrary]:
    """Combined search across the filters that were actually
    provided, intersected. With no filters, returns every registered
    library."""
    result_sets: List[List[BaseLibrary]] = []
    if keyword:
        result_sets.append(search_by_keyword(keyword))
    if category:
        found = search_by_category(category)
        result_sets.append([found] if found else [])
    if standard:
        result_sets.append(search_by_standard(standard))

    if not result_sets:
        return list_libraries()

    common = set(result_sets[0])
    for candidate in result_sets[1:]:
        common &= set(candidate)
    return sorted(common, key=lambda lib: lib.metadata.key)
