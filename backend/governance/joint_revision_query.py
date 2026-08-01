"""TorqPro Engineering Governance - Faz 2.8.16 Stage 1: read-only,
deterministic search/sort/pagination query foundation over the
existing joint revision governance projection.

Scope (Faz 2.8.16 Stage 1 only): this module is a pure Python
domain/service layer with no FastAPI or HTTP dependency. It defines
no API route, changes no existing route, and produces no HTTP status
code -- :class:`JointRevisionQueryValidationError` is a plain domain
exception; mapping it to an HTTP ``422`` response is explicitly
deferred to Stage 2 (see module docstring of
``backend.governance.api``).

This module defines **no new projection or mapping logic of its
own**. It calls the existing, already-tested
:func:`backend.governance.adapters.joint_revision.project_joint_revisions_bulk`
exactly once per query and only searches, sorts, and paginates the
list it returns -- never re-deriving ``source_status``,
``canonical_status``, or ``outcome`` itself. It never writes to the
``joints``/``joint_revisions`` tables, never writes a governance
event, and never mutates the list ``project_joint_revisions_bulk``
returns (every search/sort step below builds a new list).

Query pipeline (fixed order, every call):

    1. Validate ``page``/``page_size``/``sort_by``/``sort_order``
       (never touches source data -- an invalid parameter raises
       before any read happens).
    2. Read + project source data via the existing bulk adapter
       (optionally filtered by ``joint_id``, exactly as that adapter
       already supports).
    3. Search (substring, case-insensitive, over a fixed field set).
    4. Sort (deterministic, allow-listed field, explicit tie-breaker).
    5. Compute ``total`` (post-search, pre-pagination count).
    6. Slice the requested page.

Source-error safety: :func:`project_joint_revisions_bulk` is
documented and tested to never raise -- on any internal source read
failure it returns ``[]`` rather than propagating an exception (see
``backend/governance/adapters/joint_revision.py``). This module
relies on that existing contract unchanged: a source read failure
therefore flows through this pipeline as an empty list, producing
``items=(), total=0, total_pages=0`` -- never a fabricated error item
and never a leaked traceback/path. This module adds no ``try/except``
of its own around that call, for the same reason
``backend/governance/api.py``'s existing bulk route has none.
"""

from __future__ import annotations

import math
from typing import Optional, Tuple

from pydantic import BaseModel, ConfigDict

from .adapters.joint_revision import JointRevisionProjection, project_joint_revisions_bulk
from .exceptions import GovernanceError

#: Default query parameters -- match the existing bulk endpoint's
#: only real ordering guarantee (ascending ``joint_revision_id``) so
#: a caller that never passes search/sort/pagination arguments sees
#: the same order it already sees today.
DEFAULT_SORT_BY = "joint_revision_id"
DEFAULT_SORT_ORDER = "asc"
DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 25

#: No existing pagination limit constant was found anywhere else in
#: the repository (searched `backend/` for `page_size`/`per_page`), so
#: this is a new, Stage-1-local constant, not a reuse of an existing
#: one.
MAX_PAGE_SIZE = 200

#: Allow-listed ``sort_by`` fields. ``lifecycle_group`` and
#: ``safe_reason`` are deliberately excluded -- see module docstring
#: section "Excluded sort/search fields" below for the evidence-based
#: reasoning recorded in the Stage 1 scope document.
ALLOWED_SORT_FIELDS: Tuple[str, ...] = (
    "joint_revision_id",
    "source_status",
    "canonical_status",
    "outcome",
)

ALLOWED_SORT_ORDERS: Tuple[str, ...] = ("asc", "desc")

#: Fields searched, in the fixed order used to build the free-text
#: haystack for one projection. ``lifecycle_group`` is excluded --
#: see the Stage 1 scope document's "Search Contract" section: within
#: this mechanism's data, ``lifecycle_group`` only ever takes the one
#: constant value ``"review"`` (whenever it is not ``None``), because
#: every joint revision projected by this adapter belongs to the same
#: governance lifecycle group by construction -- it carries no
#: discriminating information a search over ``outcome`` does not
#: already provide.
_SEARCHABLE_FIELDS: Tuple[str, ...] = (
    "joint_revision_id",
    "source_status",
    "canonical_status",
    "outcome",
    "safe_reason",
)


class JointRevisionQueryValidationError(GovernanceError):
    """Raised when a query parameter (``page``, ``page_size``,
    ``sort_by``, or ``sort_order``) fails domain-level validation.
    Always raised *before* any source data is read -- see
    :func:`query_joint_revision_projections`'s validate-first
    pipeline order.

    HTTP-independent by design: this module raises no HTTP status
    code and has no FastAPI dependency. Stage 2 is responsible for
    mapping this exception to an HTTP ``422`` response.

    The message is deterministic, never contains a file path or
    traceback, and safely echoes only the offending parameter name
    and value (via ``repr()``, so it renders even for a non-string
    value such as a ``bool`` or ``float``).
    """

    def __init__(self, parameter: str, value: object, reason: str) -> None:
        self.parameter = parameter
        self.value = value
        self.reason = reason
        super().__init__(f"invalid '{parameter}' value {value!r}: {reason}")


class JointRevisionQueryResult(BaseModel):
    """Typed, immutable result of
    :func:`query_joint_revision_projections`. Domain/service-layer
    model -- not a FastAPI response model (Stage 2 decides how, or
    whether, to reuse it at the API boundary).

    ``total`` is the count *after* search filtering and *before*
    pagination slicing. ``items`` holds only the requested page's
    records. ``model_config`` uses ``frozen=True`` (matching this
    package's existing ``extra="forbid"`` convention on
    :class:`~backend.governance.adapters.joint_revision.JointRevisionProjection`)
    so a caller cannot mutate a result after it is returned; because
    ``items`` is a ``tuple`` rather than a ``list``, it also cannot be
    appended/removed from in place, and it holds no shared reference
    back to any source-table row -- these are the same
    :class:`JointRevisionProjection` instances the adapter already
    returned, not database rows.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: Tuple[JointRevisionProjection, ...]
    total: int
    page: int
    page_size: int
    total_pages: int


def _validate_page(page: object) -> int:
    if isinstance(page, bool) or not isinstance(page, int):
        raise JointRevisionQueryValidationError("page", page, "must be an integer")
    if page < 1:
        raise JointRevisionQueryValidationError("page", page, "must be >= 1")
    return page


def _validate_page_size(page_size: object) -> int:
    if isinstance(page_size, bool) or not isinstance(page_size, int):
        raise JointRevisionQueryValidationError("page_size", page_size, "must be an integer")
    if page_size < 1:
        raise JointRevisionQueryValidationError("page_size", page_size, "must be >= 1")
    if page_size > MAX_PAGE_SIZE:
        raise JointRevisionQueryValidationError(
            "page_size", page_size, f"must be <= {MAX_PAGE_SIZE}"
        )
    return page_size


def _validate_sort_by(sort_by: object) -> str:
    if sort_by not in ALLOWED_SORT_FIELDS:
        raise JointRevisionQueryValidationError(
            "sort_by", sort_by, f"must be one of {ALLOWED_SORT_FIELDS}"
        )
    return sort_by  # type: ignore[return-value]


def _validate_sort_order(sort_order: object) -> str:
    if sort_order not in ALLOWED_SORT_ORDERS:
        raise JointRevisionQueryValidationError(
            "sort_order", sort_order, f"must be one of {ALLOWED_SORT_ORDERS}"
        )
    return sort_order  # type: ignore[return-value]


def _normalize_search(search: Optional[str]) -> Optional[str]:
    """``None``/empty/whitespace-only all normalize to ``None`` (no
    filter -- every record matches). A real search term is trimmed
    and lower-cased once here, so every field comparison at match
    time is a plain substring check with no repeated normalization.
    """
    if search is None:
        return None
    trimmed = search.strip()
    if not trimmed:
        return None
    return trimmed.lower()


def _searchable_text(projection: JointRevisionProjection) -> Tuple[str, ...]:
    """Safe string representation of every searchable field on one
    projection, in ``_SEARCHABLE_FIELDS`` order. A ``None`` field is
    skipped entirely -- never rendered as the literal text ``"None"``
    -- so a search for ``"none"`` cannot spuriously match a record
    only because one of its fields happens to be unset.
    """
    values = []
    for field in _SEARCHABLE_FIELDS:
        value = getattr(projection, field)
        if value is None:
            continue
        values.append(str(value))
    return tuple(values)


def _matches_search(projection: JointRevisionProjection, normalized_search: str) -> bool:
    for text in _searchable_text(projection):
        if normalized_search in text.lower():
            return True
    return False


def _sort_value(projection: JointRevisionProjection, sort_by: str):
    """The comparison value for one projection's ``sort_by`` field.
    Text fields are lower-cased for case-insensitive sorting;
    ``joint_revision_id`` is returned as-is (an ``int``, never
    ``None``)."""
    value = getattr(projection, sort_by)
    if sort_by == "joint_revision_id" or value is None:
        return value
    return value.lower()


def _sorted_projections(
    projections: list, sort_by: str, sort_order: str
) -> list:
    """Deterministic sort with an explicit tie-breaker and an
    explicit ``None`` placement rule.

    - ``joint_revision_id`` is never ``None`` and is itself the
      tie-breaker, so sorting by it uses a single pass with no
      duplicate/secondary key.
    - For every other allow-listed field, a ``None`` value always
      sorts **last, regardless of ``sort_order``** (an
      ``unsupported_status``/``not_found``/``invalid_source_record``/
      ``source_unavailable`` record has no ``source_status``/
      ``canonical_status`` of its own to compare -- putting it last
      in both directions is the one placement that stays meaningful
      whichever direction the user picked, tested explicitly).
    - The tie-breaker for equal (non-``None``) values, and for
      ``None`` values among themselves, is always
      ``joint_revision_id`` ascending -- **even when ``sort_order`` is
      ``"desc"``** for the primary field. This is implemented with
      two chained stable sorts (Python's ``sorted`` is guaranteed
      stable): first establish ascending-id order, then sort by the
      primary value with the requested direction; the stable sort
      preserves the ascending-id order among equal primary values.
    - Never mutates its ``projections`` argument: every step below
      builds a new list via a comprehension or ``sorted()``, never
      ``list.sort()`` on the caller's list.
    """
    items = list(projections)
    reverse = sort_order == "desc"

    if sort_by == "joint_revision_id":
        return sorted(items, key=lambda p: p.joint_revision_id, reverse=reverse)

    non_null = [p for p in items if _sort_value(p, sort_by) is not None]
    null_items = [p for p in items if _sort_value(p, sort_by) is None]

    id_ascending = sorted(non_null, key=lambda p: p.joint_revision_id)
    value_sorted = sorted(id_ascending, key=lambda p: _sort_value(p, sort_by), reverse=reverse)
    null_sorted = sorted(null_items, key=lambda p: p.joint_revision_id)

    return value_sorted + null_sorted


def query_all_joint_revision_projections(
    *,
    joint_id: Optional[int] = None,
    search: Optional[str] = None,
    sort_by: str = DEFAULT_SORT_BY,
    sort_order: str = DEFAULT_SORT_ORDER,
) -> Tuple[JointRevisionProjection, ...]:
    """Faz 2.8.16 Stage 3 addition: the same validate -> read ->
    search -> sort pipeline as :func:`query_joint_revision_projections`,
    **without pagination** -- every filtered/sorted record is
    returned, regardless of :data:`MAX_PAGE_SIZE`.

    Added for callers (CSV export) that must never silently truncate
    a result at ``MAX_PAGE_SIZE`` records -- calling the paginated
    function with ``page_size=MAX_PAGE_SIZE`` would do exactly that
    for any dataset larger than the page-size cap, which is not an
    acceptable substitute for "export every filtered record."

    This function defines no search/sort/validation logic of its own:
    it calls exactly the same private helpers
    (:func:`_validate_sort_by`, :func:`_validate_sort_order`,
    :func:`_normalize_search`, :func:`_matches_search`,
    :func:`_sorted_projections`) that
    :func:`query_joint_revision_projections` uses internally --
    :func:`query_joint_revision_projections` is refactored (Stage 3)
    to call *this* function for its own validate/read/search/sort
    step, so the two public functions share one implementation of
    that pipeline rather than two independently-maintained copies.
    This is a behavior-preserving refactor: every one of Stage 1's 62
    existing tests for :func:`query_joint_revision_projections`
    passes unchanged (see
    ``tests/governance/test_joint_revision_query.py``), because its
    public signature, return type, and every documented behavior are
    unchanged -- only ``page``/``page_size`` validation and the final
    pagination slice remain in that function's own body.

    Validation (``sort_by``/``sort_order``) happens before any source
    read, exactly as in the paginated function. ``joint_id`` is
    forwarded unchanged to
    :func:`~backend.governance.adapters.joint_revision.project_joint_revisions_bulk`.
    Read-only: performs no mutation, no governance event, no
    persistence of any kind.
    """
    validated_sort_by = _validate_sort_by(sort_by)
    validated_sort_order = _validate_sort_order(sort_order)
    normalized_search = _normalize_search(search)

    projections = project_joint_revisions_bulk(joint_id=joint_id)

    if normalized_search is not None:
        projections = [p for p in projections if _matches_search(p, normalized_search)]

    sorted_items = _sorted_projections(projections, validated_sort_by, validated_sort_order)
    return tuple(sorted_items)


def query_joint_revision_projections(
    *,
    joint_id: Optional[int] = None,
    search: Optional[str] = None,
    sort_by: str = DEFAULT_SORT_BY,
    sort_order: str = DEFAULT_SORT_ORDER,
    page: int = DEFAULT_PAGE,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> JointRevisionQueryResult:
    """Search, sort, and paginate the existing joint revision
    governance projection (Faz 2.8.16 Stage 1).

    Read-only and side-effect-free: never writes to the ``joints``/
    ``joint_revisions`` tables, never writes a governance event, and
    performs no mutation or persistence of any kind -- it is a pure
    function of its arguments and the current source data.

    Parameters are keyword-only. ``joint_id`` is forwarded unchanged
    to :func:`~backend.governance.adapters.joint_revision.project_joint_revisions_bulk`
    -- this function adds no additional validation or interpretation
    of it.

    Validation happens first, before any source data is read: an
    invalid ``page``/``page_size``/``sort_by``/``sort_order`` raises
    :class:`JointRevisionQueryValidationError` without ever calling
    the bulk adapter. ``search`` needs no validation -- any string
    (including ``None``/empty/whitespace-only, all of which mean "no
    filter") is accepted.

    Returns a :class:`JointRevisionQueryResult` whose ``total``
    reflects the post-search, pre-pagination record count, and whose
    ``items`` holds only the requested page. A ``page`` beyond the
    last available page is not an error -- it returns an empty
    ``items`` tuple with the same, correctly-computed ``total``/
    ``total_pages``.

    Faz 2.8.16 Stage 3: the validate-sort/order -> read -> search ->
    sort steps are delegated to
    :func:`query_all_joint_revision_projections` (this function only
    validates ``page``/``page_size`` and applies the final pagination
    slice) -- see that function's docstring for why this refactor is
    behavior-preserving.
    """
    validated_page = _validate_page(page)
    validated_page_size = _validate_page_size(page_size)

    sorted_items = query_all_joint_revision_projections(
        joint_id=joint_id, search=search, sort_by=sort_by, sort_order=sort_order
    )

    total = len(sorted_items)
    total_pages = math.ceil(total / validated_page_size) if total else 0

    start = (validated_page - 1) * validated_page_size
    end = start + validated_page_size
    page_items = tuple(sorted_items[start:end])

    return JointRevisionQueryResult(
        items=page_items,
        total=total,
        page=validated_page,
        page_size=validated_page_size,
        total_pages=total_pages,
    )


__all__ = [
    "DEFAULT_SORT_BY",
    "DEFAULT_SORT_ORDER",
    "DEFAULT_PAGE",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "ALLOWED_SORT_FIELDS",
    "ALLOWED_SORT_ORDERS",
    "JointRevisionQueryValidationError",
    "JointRevisionQueryResult",
    "query_joint_revision_projections",
    "query_all_joint_revision_projections",
]
