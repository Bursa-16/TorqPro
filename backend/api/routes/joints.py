"""Joint / Joint Revision HTTP API (Faz 2.8.17 Stage 2).

Thin FastAPI routes over the existing, already-tested
``backend.joints.service`` domain layer (Faz 2.5A foundation, extended
by Faz 2.8.17 Stage 1's idempotency support). No business logic, no
SQL, and no idempotency comparison lives in this module -- every one
of those already lives in ``backend.joints.service`` and is covered by
``tests/test_joints_foundation.py``; this module only does request
validation, authentication, the service call itself, response
serialization, and domain-exception -> ``HTTPException`` mapping.
Follows ``backend/api/routes/production_validation.py``'s established
pattern (``APIRouter``, Pydantic request schemas, ``Depends(user)``,
a single central ``_handle()`` exception-mapping helper) without
introducing a new convention.

Archived-joint idempotent-replay contract (Faz 2.8.17 Stage 1 design
decision, reflected here unchanged -- see
``backend.joints.service.create_joint_revision``'s own docstring for
the authoritative behaviour; this module reimplements none of it):

  - A replay (same ``joint_id`` + same ``idempotency_key`` + the same
    semantic ``snapshot``/``change_summary``/``created_by`` as the
    original successful call) returns the existing revision even if
    the joint has since been archived -- it is not a new write, so
    the archived-joint rule never applies to it.
  - A genuinely new write (a new ``idempotency_key``, or
    ``idempotency_key=None``) against an archived joint is rejected by
    the existing ``JointArchivedError`` rule, mapped to ``400`` below,
    exactly like any other archived-joint write attempt -- archived or
    not makes no difference to this route, because the route never
    checks joint status itself.
  - The same key reused with a *different* payload against an
    archived joint is still resolved as a key collision first --
    ``JointRevisionConflictError`` (``409``) -- because the
    idempotency lookup runs before the archived check inside
    ``backend.joints.service`` (Stage 1 Sec. 3/8), not because this
    route special-cases archived joints.

``POST /api/joints/{joint_id}/revisions`` returns the same response
shape and the same (FastAPI default) ``200`` status whether the call
created a new revision or replayed an existing one -- the service
layer does not report which case occurred, and this route does not
guess.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

router = APIRouter(tags=["joints"])

# `router` is assigned before these imports for the same reason
# backend/api/routes/production_validation.py already documents on
# its own equivalent import block: if backend.app ends up re-entering
# this module while it is still mid-import, the partially-initialized
# module already exposes a usable `router` attribute, which breaks a
# circular-import failure instead of propagating it.
from backend.api.dependencies import user  # noqa: E402
from backend.joints import schemas as s  # noqa: E402
from backend.joints import service as svc  # noqa: E402
from backend.joints.exceptions import (  # noqa: E402
    JointArchivedError,
    JointCodeConflictError,
    JointNotFoundError,
    JointRevisionConflictError,
    JointRevisionNotFoundError,
    JointRevisionStateError,
)


def _handle(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except (JointNotFoundError, JointRevisionNotFoundError) as exc:
        raise HTTPException(404, str(exc))
    except (JointRevisionConflictError, JointCodeConflictError) as exc:
        raise HTTPException(409, str(exc))
    except (JointArchivedError, JointRevisionStateError) as exc:
        raise HTTPException(400, str(exc))


# -------------------------------------------------------------------- joints

@router.post("/api/joints")
def create_joint(x: s.JointCreate, u=Depends(user)):
    return _handle(
        svc.create_joint, x.project_id, x.joint_code, x.name, x.description, u["id"]
    )


@router.get("/api/joints")
def list_joints(project_id: int | None = None, u=Depends(user)):
    return svc.list_joints(project_id)


@router.get("/api/joints/{joint_id}")
def get_joint(joint_id: int, u=Depends(user)):
    return _handle(svc.get_joint, joint_id)


# ----------------------------------------------------------- joint revisions

@router.post("/api/joints/{joint_id}/revisions")
def create_joint_revision(joint_id: int, x: s.JointRevisionCreate, u=Depends(user)):
    # Thin adapter only: revision-number generation, the archived-joint
    # check, and the entire idempotency lookup/compare/conflict decision
    # all happen inside svc.create_joint_revision -- this route neither
    # runs SQL nor re-implements any of that logic, it only unpacks the
    # validated request body into the existing service signature and
    # maps whatever the service decides onto an HTTP response.
    return _handle(
        svc.create_joint_revision,
        joint_id,
        x.snapshot,
        x.change_summary,
        u["id"],
        idempotency_key=x.idempotency_key,
    )


@router.get("/api/joints/revisions/{revision_id}")
def get_joint_revision(revision_id: int, u=Depends(user)):
    return _handle(svc.get_joint_revision, revision_id)


@router.post("/api/joints/revisions/{revision_id}/submit")
def submit_joint_revision(revision_id: int, u=Depends(user)):
    return _handle(svc.submit_joint_revision, revision_id, u["id"])


@router.post("/api/joints/revisions/{revision_id}/approve")
def approve_joint_revision(revision_id: int, u=Depends(user)):
    return _handle(svc.approve_joint_revision, revision_id, u["id"])


@router.post("/api/joints/revisions/{revision_id}/reject")
def reject_joint_revision(revision_id: int, u=Depends(user)):
    return _handle(svc.reject_joint_revision, revision_id, u["id"])
