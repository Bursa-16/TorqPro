"""TorqPro Engineering Core - formula traceability metadata (Phase 2.8.21).

Governance-and-visibility-only extension. Mirrors the architecture
already proven out in ``backend.vdi2230_core.trace`` (frozen dataclass
+ closed ``str`` Enum of formula ids + ``get_trace()``/``all_traces()``
accessors) rather than inventing a second, incompatible governance
framework -- see ``docs/adr/`` conventions and
``docs/05_ENGINEERING_FORMULA_SPECIFICATION.md`` §20-21.

Status semantics are shared, not duplicated: ``APPROVED`` and
``PROVISIONAL`` are imported directly from
``backend.vdi2230_core.trace`` (the single source of truth for those
two values). Only the two additional states this package's formulas
actually need -- ``EXPERIMENTAL`` and ``UNVERIFIED`` -- are defined
here, plus ``DEPRECATED`` for future use; none of the three re-defines
or shadows a value already owned by ``vdi2230_core``.

No formula, coefficient, or numerical result implemented in
``backend.engineering_core`` is changed by this module. This module
only *describes* the existing, unchanged functions in
``backend.engineering_core.torque/friction/geometry/materials/preload/
joint`` -- it imports none of them and calls none of them, matching
the read-only boundary already established by
``backend.calculation_engine.formula_validation``.

Inventory scope (Phase 2.8.21, Stage 2): every formula actually
reachable from ``backend.engineering_core.joint.evaluate_joint`` --
the function backing the live ``/api/engineering/check`` endpoint.
Topics that were requested for inventory but have **no implementation**
anywhere in ``backend.engineering_core`` (plain tensile stress from a
supplied force/area, torsional stress, von Mises equivalent stress,
bearing/contact pressure) are intentionally NOT given a catalog entry
here -- inventing a placeholder trace for a formula that does not
exist would misrepresent coverage. See
``docs/phases/PHASE_2.8.21_ENGINEERING_CORE_TRACEABILITY.md`` §2 for
the explicit "requested, not found" list.

No entry in this catalog is, or may be marked, ``APPROVED``: none of
these formulas has completed independent source sign-off, a
golden-case fixture, and engineering review per
``docs/05_ENGINEERING_FORMULA_SPECIFICATION.md`` §20. This module
never asserts standards compliance (see ``prohibited_claims`` on every
entry).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Tuple

from backend.vdi2230_core.trace import APPROVED, PROVISIONAL

#: Additional status values this package's formulas need, beyond the
#: two (``APPROVED``, ``PROVISIONAL``) imported above from
#: ``vdi2230_core.trace`` -- that import is the single source of truth
#: for those two; nothing here re-defines them.
EXPERIMENTAL = "EXPERIMENTAL"
DEPRECATED = "DEPRECATED"
UNVERIFIED = "UNVERIFIED"

#: Closed set of statuses valid for an ``EngineeringCoreFormulaTrace``.
#: Same five semantic classes requested for Faz 2.8.21 (APPROVED,
#: PROVISIONAL, EXPERIMENTAL, DEPRECATED, UNVERIFIED); APPROVED/
#: PROVISIONAL come from vdi2230_core.trace, not redefined here.
VALID_STATUSES = (APPROVED, PROVISIONAL, EXPERIMENTAL, DEPRECATED, UNVERIFIED)


class MissingEngineeringCoreFormulaError(KeyError):
    """Raised by :func:`get_trace` for an unregistered formula id."""


class EngineeringCoreFormulaId(str, Enum):
    """Identifier of a single traceable ``engineering_core`` formula.

    Closed set, Phase 2.8.21 scope only -- see module docstring for
    what was investigated but intentionally excluded.
    """

    ENGCORE_TIGHTENING_TORQUE = "ENGCORE_TIGHTENING_TORQUE"
    ENGCORE_THREAD_FRICTION_ANGLE = "ENGCORE_THREAD_FRICTION_ANGLE"
    ENGCORE_PITCH_DIAMETER = "ENGCORE_PITCH_DIAMETER"
    ENGCORE_MINOR_DIAMETER = "ENGCORE_MINOR_DIAMETER"
    ENGCORE_HELIX_ANGLE = "ENGCORE_HELIX_ANGLE"
    ENGCORE_THREAD_SHEAR_AREA = "ENGCORE_THREAD_SHEAR_AREA"
    ENGCORE_SHEAR_STRENGTH_FROM_RM = "ENGCORE_SHEAR_STRENGTH_FROM_RM"
    ENGCORE_PRELOAD_FROM_YIELD = "ENGCORE_PRELOAD_FROM_YIELD"
    ENGCORE_PROOF_LOAD_UTILIZATION = "ENGCORE_PROOF_LOAD_UTILIZATION"
    ENGCORE_JOINT_CHECK = "ENGCORE_JOINT_CHECK"


@dataclass(frozen=True)
class EngineeringCoreFormulaTrace:
    """Traceability record for a single ``engineering_core`` formula.

    Superset of ``vdi2230_core.trace.FormulaTrace``'s fields (that
    dataclass is not reused directly because its field set is
    narrower than Faz 2.8.21's requested metadata model -- this is
    the "smallest additive extension" called for when the existing
    mechanism cannot directly carry the needed shape, per the phase
    brief's Stage 1).
    """

    formula_id: EngineeringCoreFormulaId
    name: str
    domain: str
    implementation: str
    source_level: str
    source_reference: str
    status: str
    confidence: str
    assumptions: Tuple[str, ...]
    limitations: Tuple[str, ...]
    intended_use: str
    prohibited_claims: Tuple[str, ...]
    validation_basis: str
    affected_outputs: Tuple[str, ...]

    def __post_init__(self) -> None:
        if self.status not in VALID_STATUSES:
            raise ValueError(
                f"{self.formula_id}: status {self.status!r} not in "
                f"VALID_STATUSES {VALID_STATUSES}"
            )

    def to_dict(self) -> Dict[str, object]:
        return {
            "formula_id": self.formula_id.value,
            "name": self.name,
            "domain": self.domain,
            "implementation": self.implementation,
            "source_level": self.source_level,
            "source_reference": self.source_reference,
            "status": self.status,
            "confidence": self.confidence,
            "assumptions": list(self.assumptions),
            "limitations": list(self.limitations),
            "intended_use": self.intended_use,
            "prohibited_claims": list(self.prohibited_claims),
            "validation_basis": self.validation_basis,
            "affected_outputs": list(self.affected_outputs),
        }


_NO_STANDARDS_CLAIM: Tuple[str, ...] = (
    "ISO 16224 compliant",
    "VDI 2230 compliant",
    "FCA C2001 compliant",
    "ASME validated",
    "production approval without independent engineering validation",
)

_CATALOG: Dict[EngineeringCoreFormulaId, EngineeringCoreFormulaTrace] = {
    EngineeringCoreFormulaId.ENGCORE_TIGHTENING_TORQUE: EngineeringCoreFormulaTrace(
        formula_id=EngineeringCoreFormulaId.ENGCORE_TIGHTENING_TORQUE,
        name="Tightening torque (helix + thread/bearing friction angle model)",
        domain="torque_preload",
        implementation="backend.engineering_core.torque.tightening_torque_nm",
        source_level="L1_L2_STRUCTURAL_ANALOGUE",
        source_reference=(
            "Structural form matches the standard screw-thread mechanics "
            "torque-preload relation (same shape as VDI 2230 Sec. 5 / "
            "Shigley Ch. 8 / Bickford); not itself cited to a specific "
            "edition or clause in this repository. Moved unchanged from "
            "the original backend/app.py prototype (Phase 1); never "
            "independently re-derived against a primary text."
        ),
        status=PROVISIONAL,
        confidence="MEDIUM",
        assumptions=(
            "60-degree metric thread half-angle (math.pi/6) hard-coded",
            "Single nominal thread/bearing friction coefficient per call "
            "(min/nom/max bracketing done by the caller, not internally)",
        ),
        limitations=(
            "No independent primary-source derivation on file",
            "Does not model tightening scatter, torque-angle, or "
            "yield-controlled methods",
        ),
        intended_use="Preliminary engineering estimate, quick joint check",
        prohibited_claims=_NO_STANDARDS_CLAIM,
        validation_basis="Structural/dimensional plausibility only; no golden-case fixture",
        affected_outputs=("torque_min_nm", "torque_nom_nm", "torque_max_nm"),
    ),
    EngineeringCoreFormulaId.ENGCORE_THREAD_FRICTION_ANGLE: EngineeringCoreFormulaTrace(
        formula_id=EngineeringCoreFormulaId.ENGCORE_THREAD_FRICTION_ANGLE,
        name="Effective thread friction angle (rho' = atan(mu / cos(30deg)))",
        domain="friction",
        implementation="backend.engineering_core.friction.thread_friction_angle_rad",
        source_level="L1_L2_STRUCTURAL_ANALOGUE",
        source_reference=(
            "Standard virtual/effective friction angle correction for a "
            "60-degree V-thread (half-angle 30 degrees); same structural "
            "form used across screw-thread mechanics literature. Not "
            "cited to a specific edition in this repository."
        ),
        status=PROVISIONAL,
        confidence="MEDIUM",
        assumptions=("60-degree metric thread half-angle assumed for every caller",),
        limitations=("No independent primary-source citation on file",),
        intended_use="Internal helper for ENGCORE_TIGHTENING_TORQUE only",
        prohibited_claims=_NO_STANDARDS_CLAIM,
        validation_basis="Structural plausibility only",
        affected_outputs=("torque_min_nm", "torque_nom_nm", "torque_max_nm"),
    ),
    EngineeringCoreFormulaId.ENGCORE_PITCH_DIAMETER: EngineeringCoreFormulaTrace(
        formula_id=EngineeringCoreFormulaId.ENGCORE_PITCH_DIAMETER,
        name="Metric thread pitch diameter (d2 = d - 0.6495*P)",
        domain="thread_geometry",
        implementation="backend.engineering_core.geometry.pitch_diameter_mm",
        source_level="L1",
        source_reference=(
            "ISO 68-1 metric thread pitch-diameter factor (0.6495); "
            "same constant duplicated (not imported) in "
            "backend/vdi2230_core/stress_area.py to preserve that "
            "package's import isolation -- both copies agree."
        ),
        status=PROVISIONAL,
        confidence="HIGH",
        assumptions=("ISO 68-1 basic metric thread profile (60-degree, coarse or fine pitch)",),
        limitations=("Not independently re-verified against the ISO 68-1 primary text this phase",),
        intended_use="d2 basis for downstream torque, stress-area, and thread-shear calculations",
        prohibited_claims=_NO_STANDARDS_CLAIM,
        validation_basis="Constant matches a second, independently-written module (vdi2230_core.stress_area); no primary-text cross-check performed this phase",
        affected_outputs=("torque_min_nm", "torque_nom_nm", "torque_max_nm", "internal_thread_sf"),
    ),
    EngineeringCoreFormulaId.ENGCORE_MINOR_DIAMETER: EngineeringCoreFormulaTrace(
        formula_id=EngineeringCoreFormulaId.ENGCORE_MINOR_DIAMETER,
        name="Metric thread minor diameter (d3 = d - 1.2269*P)",
        domain="thread_geometry",
        implementation="backend.engineering_core.geometry.minor_diameter_mm",
        source_level="L1",
        source_reference=(
            "ISO 68-1 metric thread minor-diameter factor (1.2269); "
            "same constant duplicated (not imported) in "
            "backend/vdi2230_core/stress_area.py -- both copies agree."
        ),
        status=PROVISIONAL,
        confidence="HIGH",
        assumptions=("ISO 68-1 basic metric thread profile",),
        limitations=("Not independently re-verified against the ISO 68-1 primary text this phase",),
        intended_use="d3 basis for downstream stress-area and thread-shear calculations",
        prohibited_claims=_NO_STANDARDS_CLAIM,
        validation_basis="Constant matches a second, independently-written module (vdi2230_core.stress_area); no primary-text cross-check performed this phase",
        affected_outputs=("external_thread_sf",),
    ),
    EngineeringCoreFormulaId.ENGCORE_HELIX_ANGLE: EngineeringCoreFormulaTrace(
        formula_id=EngineeringCoreFormulaId.ENGCORE_HELIX_ANGLE,
        name="Thread helix (lead) angle (atan(P / (pi*d2)))",
        domain="thread_geometry",
        implementation="backend.engineering_core.geometry.helix_angle_rad",
        source_level="L1",
        source_reference="Standard single-start helix angle definition; geometric identity, not a modeling choice",
        status=PROVISIONAL,
        confidence="HIGH",
        assumptions=("Single-start thread",),
        limitations=("Multi-start threads not handled by this function",),
        intended_use="Internal helper for ENGCORE_TIGHTENING_TORQUE only",
        prohibited_claims=_NO_STANDARDS_CLAIM,
        validation_basis="Geometric identity; not a disputed formula",
        affected_outputs=("torque_min_nm", "torque_nom_nm", "torque_max_nm"),
    ),
    EngineeringCoreFormulaId.ENGCORE_THREAD_SHEAR_AREA: EngineeringCoreFormulaTrace(
        formula_id=EngineeringCoreFormulaId.ENGCORE_THREAD_SHEAR_AREA,
        name="Approximate thread (stripping) shear area",
        domain="thread_stripping",
        implementation="backend.engineering_core.geometry.thread_shear_area_mm2",
        source_level="L4_PARTIAL_ALIGNMENT",
        source_reference=(
            "Model family: approximate thread stripping, historical "
            "formula 0.5*pi*d_effective*Le, called with d2 (internal "
            "thread capacity) or d3 (external/bolt capacity) -- never "
            "with nominal diameter d. Structurally matches RoyMech's "
            "published 'convenient formula' (Ass = 0.5*pi*dp*Le, "
            "www.roymech.co.uk/Useful_Tables/Screws/Thread_Calcs.html), "
            "itself presented there as an approximation of the more "
            "exact FED-STD-H28/2B and Machinery's Handbook 18th ed. "
            "formula (which additionally accounts for pitch-diameter "
            "tolerance via a 0.57735*(E-K) term this codebase does not "
            "implement). No ISO/DIN/VDI primary-standard citation found "
            "for this exact form during the read-only source-validation "
            "review that preceded this phase; "
            "the coefficient's physical derivation ('half the material "
            "is cut away by the thread') is sourced only to an "
            "unverified engineering-forum reply (eng-tips.com, 2011), "
            "not a citable derivation."
        ),
        status=PROVISIONAL,
        confidence="LOW",
        assumptions=(
            "Uniform 0.5 coefficient regardless of thread size, pitch, or tolerance class",
            "Same-strength assumption implicit in RoyMech's convenient-formula derivation",
            "Uses d2 for internal-thread capacity, d3 for external/bolt capacity (not nominal d)",
        ),
        limitations=(
            "No primary-standard (ISO/DIN/VDI/ASME) validation on file",
            "Does not account for pitch-diameter tolerance (Esmin/Knmax spread) the way "
            "FED-STD-H28/Machinery's Handbook's more exact formula does",
            "Frontend (frontend/index.html) re-implements this formula independently in "
            "JavaScript; the two are not covered by any shared/parity regression test",
        ),
        intended_use="Preliminary/approximate engineering estimate only",
        prohibited_claims=_NO_STANDARDS_CLAIM,
        validation_basis=(
            "Secondary-literature structural alignment (RoyMech) only; no golden-case "
            "fixture against a primary standard or Machinery's Handbook worked example"
        ),
        affected_outputs=("internal_thread_sf", "external_thread_sf"),
    ),
    EngineeringCoreFormulaId.ENGCORE_SHEAR_STRENGTH_FROM_RM: EngineeringCoreFormulaTrace(
        formula_id=EngineeringCoreFormulaId.ENGCORE_SHEAR_STRENGTH_FROM_RM,
        name="Shear strength from tensile strength (tau = 0.58*Rm)",
        domain="material_strength",
        implementation="backend.engineering_core.materials.shear_strength_mpa",
        source_level="L3_PLAUSIBLE_UNVERIFIED",
        source_reference=(
            "0.58 is close to the von Mises shear/tensile ratio "
            "(1/sqrt(3) = 0.577), a commonly-cited approximation in "
            "mechanics-of-materials literature, but the code carries no "
            "comment or citation confirming this is the intended "
            "derivation -- it is only a plausible match, not a "
            "documented one."
        ),
        status=UNVERIFIED,
        confidence="LOW",
        assumptions=("Ductile material, ideal von-Mises-like shear/tensile ratio (if that is indeed the source)",),
        limitations=("Coefficient's origin is not documented in the codebase; plausible match to 1/sqrt(3) only",),
        intended_use="Preliminary estimate feeding ENGCORE_THREAD_SHEAR_AREA-based capacity only",
        prohibited_claims=_NO_STANDARDS_CLAIM,
        validation_basis="No citation found in repository; plausibility inference only",
        affected_outputs=("internal_thread_sf", "external_thread_sf"),
    ),
    EngineeringCoreFormulaId.ENGCORE_PRELOAD_FROM_YIELD: EngineeringCoreFormulaTrace(
        formula_id=EngineeringCoreFormulaId.ENGCORE_PRELOAD_FROM_YIELD,
        name="Target preload from yield-utilization ratio (F = Rp0.2 * As * ratio)",
        domain="preload",
        implementation="backend.engineering_core.preload.preload_from_yield_n",
        source_level="L1_L2_STRUCTURAL_ANALOGUE",
        source_reference=(
            "Same quick-target-preload model as "
            "backend/vdi2230_core/preload.py:target_preload_n (that "
            "module's own docstring: 'explicitly NOT the validated "
            "multi-factor VDI 2230 assembly-preload method')."
        ),
        status=PROVISIONAL,
        confidence="MEDIUM",
        assumptions=("Utilization ratio supplied by caller is a valid fraction of Rp0.2",),
        limitations=("Not the full VDI 2230 assembly-preload/tightening-scatter method",),
        intended_use="Quick target preload estimate",
        prohibited_claims=_NO_STANDARDS_CLAIM,
        validation_basis="Matches an independently-written sibling module (vdi2230_core.preload); no primary-text cross-check performed this phase",
        affected_outputs=("preload_n",),
    ),
    EngineeringCoreFormulaId.ENGCORE_PROOF_LOAD_UTILIZATION: EngineeringCoreFormulaTrace(
        formula_id=EngineeringCoreFormulaId.ENGCORE_PROOF_LOAD_UTILIZATION,
        name="Nut proof-load utilization percentage",
        domain="preload",
        implementation="backend.engineering_core.preload.proof_load_utilization_pct",
        source_level="L1",
        source_reference="Direct ratio of applied preload to nut proof load capacity (Rp*As); definitional, not a modeling choice",
        status=PROVISIONAL,
        confidence="HIGH",
        assumptions=(),
        limitations=("Inherits any upstream uncertainty in preload_n and stress_area_mm2",),
        intended_use="Preliminary nut capacity check",
        prohibited_claims=_NO_STANDARDS_CLAIM,
        validation_basis="Definitional ratio; not independently disputed",
        affected_outputs=("nut_proof_util_pct",),
    ),
    EngineeringCoreFormulaId.ENGCORE_JOINT_CHECK: EngineeringCoreFormulaTrace(
        formula_id=EngineeringCoreFormulaId.ENGCORE_JOINT_CHECK,
        name="Composite joint pre-check (preload, torque window, thread safety factors, nut utilization)",
        domain="joint_analysis",
        implementation="backend.engineering_core.joint.evaluate_joint",
        source_level="COMPOSITE",
        source_reference=(
            "Orchestrates ENGCORE_PRELOAD_FROM_YIELD, ENGCORE_TIGHTENING_TORQUE "
            "(x3 for min/nom/max friction), ENGCORE_PROOF_LOAD_UTILIZATION, and "
            "ENGCORE_THREAD_SHEAR_AREA (x2, internal via d2 and external via d3) "
            "into one response. Inherits the weakest-link status/confidence of "
            "its components (currently ENGCORE_SHEAR_STRENGTH_FROM_RM at "
            "UNVERIFIED / LOW is the binding constraint on internal_thread_sf "
            "and external_thread_sf)."
        ),
        status=PROVISIONAL,
        confidence="LOW",
        assumptions=("All component-formula assumptions above apply simultaneously",),
        limitations=(
            "internal_thread_sf and external_thread_sf are only as reliable as "
            "the weakest component (thread-shear-area model + 0.58 shear-strength "
            "factor, both LOW/UNVERIFIED)",
            "Backs the live /api/engineering/check endpoint, but is not currently "
            "invoked by any frontend/index.html screen -- the user-visible "
            "'hizli hesap' (quick calc) screen computes its own displayed "
            "internal/external thread safety factors independently in "
            "JavaScript, not via this endpoint (see PHASE_2.8.21 doc §4)",
        ),
        intended_use="Preliminary engineering pre-check only; not a production release gate",
        prohibited_claims=_NO_STANDARDS_CLAIM,
        validation_basis="No golden-case fixture; regression tests only assert internal_thread_sf/external_thread_sf > 0",
        affected_outputs=(
            "preload_n", "torque_min_nm", "torque_nom_nm", "torque_max_nm",
            "nut_proof_util_pct", "internal_thread_sf", "external_thread_sf",
        ),
    ),
}


def get_trace(formula_id: EngineeringCoreFormulaId) -> EngineeringCoreFormulaTrace:
    """Return the registered trace for ``formula_id``.

    Raises :class:`MissingEngineeringCoreFormulaError` if unregistered
    -- defensive guard; every enum member is populated above.
    """
    try:
        return _CATALOG[formula_id]
    except KeyError as exc:
        raise MissingEngineeringCoreFormulaError(
            f"No trace registered for engineering_core formula id: {formula_id!r}"
        ) from exc


def all_traces() -> Dict[EngineeringCoreFormulaId, EngineeringCoreFormulaTrace]:
    """Return a shallow copy of the full trace catalog."""
    return dict(_CATALOG)


__all__ = [
    "EngineeringCoreFormulaId",
    "EngineeringCoreFormulaTrace",
    "MissingEngineeringCoreFormulaError",
    "get_trace",
    "all_traces",
    "APPROVED",
    "PROVISIONAL",
    "EXPERIMENTAL",
    "DEPRECATED",
    "UNVERIFIED",
    "VALID_STATUSES",
]
