"""TorqPro VDI 2230 Core - formula identifiers.

Phase 2.2. Closed, stable set of formula ids for the first VDI 2230
calculation slice. A ``str`` Enum so values compare equal to their own
plain-string form and serialize cleanly (JSON, logs, trace payloads).
"""

from __future__ import annotations

from enum import Enum


class FormulaId(str, Enum):
    """Identifier of a single traceable VDI 2230 core formula."""

    VDI2230_AS = "VDI2230_AS"
    VDI2230_PRELOAD = "VDI2230_PRELOAD"
    VDI2230_CB = "VDI2230_CB"
    VDI2230_CC = "VDI2230_CC"
    VDI2230_PHI = "VDI2230_PHI"
    VDI2230_FS = "VDI2230_FS"
    VDI2230_RESULT = "VDI2230_RESULT"


__all__ = ["FormulaId"]
