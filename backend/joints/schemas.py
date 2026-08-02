"""Pydantic request schemas for the joints HTTP API (Faz 2.8.17 Stage 2).

Thin, additive request models only -- no business logic and no
validation beyond basic shape/presence. Response bodies are the plain
dicts backend.joints.service already returns (the ``_row()`` shape);
this module deliberately does not wrap them in a response schema,
mirroring backend/production_validation/schemas.py's own convention
of leaving service dicts unwrapped for the API layer to return as-is.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class JointCreate(BaseModel):
    project_id: int
    joint_code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: Optional[str] = None


class JointRevisionCreate(BaseModel):
    """Faz 2.8.17 Stage 2: ``idempotency_key`` travels as an ordinary
    nullable request-body field. Stage 0's integration contract never
    specified a dedicated HTTP header for it, so none is invented
    here. Omitting it (or sending it as ``null``) preserves
    ``create_joint_revision()``'s original, pre-Stage-1 behaviour
    exactly -- every call creates a new revision; no lookup, no
    comparison, no conflict is possible.
    """

    snapshot: dict[str, Any] = Field(default_factory=dict)
    change_summary: Optional[str] = None
    idempotency_key: Optional[str] = None


__all__ = ["JointCreate", "JointRevisionCreate"]
