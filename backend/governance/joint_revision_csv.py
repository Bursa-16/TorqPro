"""TorqPro Engineering Governance - Faz 2.8.16 Stage 3: read-only,
deterministic CSV export of the joint revision governance query.

HTTP-independent by design: no FastAPI import, no HTTP response
construction of any kind -- the API route in
``backend/governance/api.py`` is the only place this module's output
is wrapped in an HTTP response. This module never touches the
database or the governance event store directly; it reuses the
existing, already-tested Faz 2.8.16 Stage 1/Stage 3 query pipeline
(:func:`~backend.governance.joint_revision_query.query_all_joint_revision_projections`)
for every bit of source reading, filtering, and sorting -- no
projection-mapping, search, or sort logic is duplicated here.

Export is pagination-independent by construction: it calls the
*unpaginated* Stage 3 query function, never the paginated one, so it
is never silently truncated at
:data:`~backend.governance.joint_revision_query.MAX_PAGE_SIZE` (see
that function's own docstring for why the paginated function is
unsuitable for export).
"""

from __future__ import annotations

import csv
import io
from typing import Optional, Sequence, Tuple

from .adapters.joint_revision import JointRevisionProjection
from .joint_revision_query import (
    DEFAULT_SORT_BY,
    DEFAULT_SORT_ORDER,
    query_all_joint_revision_projections,
)

#: Fixed, deterministic CSV column order (Faz 2.8.16 Stage 3 contract
#: -- explicitly independent of the Stage 2 API's JSON field order,
#: which is not itself a contract this module needs to mirror).
CSV_COLUMNS: Tuple[str, ...] = (
    "joint_revision_id",
    "source_system",
    "source_status",
    "lifecycle_group",
    "canonical_status",
    "outcome",
    "safe_reason",
)

#: UTF-8 byte-order mark, prepended exactly once by
#: :func:`serialize_joint_revision_projections_csv` -- chosen for
#: Excel compatibility with TorqPro's Turkish-language ``safe_reason``
#: content (see the Stage 3 scope document, "CSV Encoding and BOM",
#: for the full decision record). No other function in this module
#: ever adds this prefix, so a double-BOM is structurally impossible.
UTF8_BOM = b"\xef\xbb\xbf"

#: Deterministic export filename -- the same for every request,
#: regardless of ``joint_id``/``search``/``sort_by``/``sort_order``;
#: no timestamp, no random suffix (Stage 3 contract).
EXPORT_FILENAME = "joint-revisions-export.csv"

#: Leading characters that a spreadsheet application may interpret as
#: the start of a formula. Checked against a value only *after*
#: stripping leading whitespace (space, tab, CR, LF, ...) -- a
#: leading tab or carriage return in front of a genuine trigger
#: character is itself a documented formula-injection bypass
#: technique, not a reason to skip the check.
_FORMULA_TRIGGER_CHARS: Tuple[str, ...] = ("=", "+", "-", "@")


def _safe_csv_cell(value: Optional[object]) -> str:
    """Render one field's value as CSV-injection-safe text.

    - ``None`` becomes ``""`` -- never the literal text ``"None"``.
    - Any other value is converted with ``str()`` first (so this
      accepts the raw values already present on a
      :class:`~backend.governance.adapters.joint_revision.JointRevisionProjection`
      unchanged -- ``int``, ``str``, or a ``str``-backed enum's
      ``.value`` already resolved by the caller).
    - If the value, *after stripping leading whitespace*, begins with
      one of :data:`_FORMULA_TRIGGER_CHARS`, a single leading ``'``
      is prepended to the **original, unstripped** text -- guarding
      the whole cell (including any leading whitespace a spreadsheet
      might otherwise ignore on the way to a hidden formula) without
      altering it in any other way. Normal text and an empty string
      are returned unchanged.

    Deterministic; never mutates its argument (it only ever reads a
    ``str``/``int``/``None`` value passed in -- no source object is
    touched here at all, see :func:`_projection_to_row`).
    """
    if value is None:
        return ""
    text = str(value)
    stripped_leading = text.lstrip()
    if stripped_leading and stripped_leading[0] in _FORMULA_TRIGGER_CHARS:
        return "'" + text
    return text


def _projection_to_row(projection: JointRevisionProjection) -> Tuple[str, ...]:
    """One :class:`JointRevisionProjection` -> one CSV data row, in
    :data:`CSV_COLUMNS` order. ``joint_revision_id`` is numeric and
    is never CSV-injection-guarded (per the Stage 3 contract: a
    formula-trigger check on an ``int`` is meaningless). Every other
    column goes through :func:`_safe_csv_cell`. An enum field
    (``lifecycle_group``) is resolved to its plain ``.value`` string
    first, matching the same safe string representation the Stage 2
    JSON API already uses for it -- never a Python ``repr()`` or the
    enum's qualified name.

    Never mutates ``projection`` -- only reads its existing
    attributes.
    """
    lifecycle_group = projection.lifecycle_group
    lifecycle_text = lifecycle_group.value if lifecycle_group is not None else None
    return (
        str(projection.joint_revision_id),
        _safe_csv_cell(projection.source_system),
        _safe_csv_cell(projection.source_status),
        _safe_csv_cell(lifecycle_text),
        _safe_csv_cell(projection.canonical_status),
        _safe_csv_cell(projection.outcome),
        _safe_csv_cell(projection.safe_reason),
    )


def _build_csv_text(projections: Sequence[JointRevisionProjection]) -> str:
    """Build the full CSV document as ``str`` (header row + one data
    row per projection, in the given order -- this function performs
    no sorting or filtering of its own, it only serializes the
    sequence it is given). Uses the standard library ``csv`` module
    exclusively (no manual comma-joining); quoting is left entirely
    to ``csv.writer`` (``csv.QUOTE_MINIMAL``, its default). Line
    terminator is the RFC 4180 ``\\r\\n``. The header row is always
    present, even for an empty ``projections`` sequence -- which
    produces a header-only document, never a fully empty one.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(CSV_COLUMNS)
    for projection in projections:
        writer.writerow(_projection_to_row(projection))
    return buffer.getvalue()


def serialize_joint_revision_projections_csv(
    projections: Sequence[JointRevisionProjection],
) -> bytes:
    """Serialize an already-fetched, already-filtered/sorted sequence
    of projections to CSV bytes: UTF-8 encoded, with a single leading
    byte-order mark (:data:`UTF8_BOM`) for Excel compatibility. This
    is the one, single point in this module where the BOM is added --
    :func:`export_joint_revision_projections_csv` never adds a second
    one, and this function is also directly usable/testable on its
    own without needing the query pipeline. Deterministic: the same
    input sequence always produces byte-identical output.
    """
    text = _build_csv_text(projections)
    return UTF8_BOM + text.encode("utf-8")


def export_joint_revision_projections_csv(
    *,
    joint_id: Optional[int] = None,
    search: Optional[str] = None,
    sort_by: str = DEFAULT_SORT_BY,
    sort_order: str = DEFAULT_SORT_ORDER,
) -> bytes:
    """High-level, HTTP-independent CSV export entry point.

    Reuses :func:`~backend.governance.joint_revision_query.query_all_joint_revision_projections`
    for the entire validate -> read -> search -> sort pipeline --
    this function defines no filtering, sorting, or validation logic
    of its own, and forwards ``sort_by``/``sort_order`` validation
    failures unchanged (raises
    :class:`~backend.governance.joint_revision_query.JointRevisionQueryValidationError`,
    which this module does not catch -- the API layer, exactly as in
    Stage 2, is responsible for mapping it to an HTTP ``422``).

    Pagination-independent: every filtered/sorted record is exported,
    regardless of how many there are (never capped at
    :data:`~backend.governance.joint_revision_query.MAX_PAGE_SIZE`).

    Read-only: no mutation, no governance event, no filesystem write
    -- the CSV document is built entirely in memory and returned as
    ``bytes``.

    Source-read-failure safety is inherited unchanged from the Stage
    1 pipeline: if the source read fails,
    ``query_all_joint_revision_projections`` receives an empty list
    from the existing, already-tested safe-empty-result contract, so
    this function produces a header-only CSV document -- never an
    error row, never a leaked exception message.
    """
    projections = query_all_joint_revision_projections(
        joint_id=joint_id, search=search, sort_by=sort_by, sort_order=sort_order
    )
    return serialize_joint_revision_projections_csv(projections)


__all__ = [
    "CSV_COLUMNS",
    "UTF8_BOM",
    "EXPORT_FILENAME",
    "serialize_joint_revision_projections_csv",
    "export_joint_revision_projections_csv",
]
