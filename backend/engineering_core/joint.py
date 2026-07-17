"""Joint-level engineering pre-check evaluation.

This is the calculation body of the ``/api/engineering/check`` endpoint,
moved unchanged from backend/app.py (Phase 1). The returned dict keys
and values are identical to the original API response — the route
handler in app.py now only validates input (Pydantic) and delegates here.
"""

from __future__ import annotations

from . import geometry, materials, preload, torque


def evaluate_joint(*, diameter_mm: float, pitch_mm: float, stress_area_mm2: float,
                   rp02_mpa: float, target_yield_ratio: float,
                   mu_thread_min: float, mu_thread_nom: float, mu_thread_max: float,
                   mu_bearing_min: float, mu_bearing_nom: float, mu_bearing_max: float,
                   effective_bearing_diameter_mm: float, engagement_mm: float,
                   internal_rm_mpa: float, bolt_rm_mpa: float,
                   nut_proof_mpa: float) -> dict:
    """Evaluate preload, min/nom/max tightening torque and thread safety factors.

    Behaviour-preserving move of the original handler body; parameter names
    match the ``EngineeringCheck`` API model one-to-one.
    """
    d2 = geometry.pitch_diameter_mm(diameter_mm, pitch_mm)
    d3 = geometry.minor_diameter_mm(diameter_mm, pitch_mm)
    F = preload.preload_from_yield_n(rp02_mpa, stress_area_mm2, target_yield_ratio)
    tau_i = materials.shear_strength_mpa(internal_rm_mpa)
    tau_b = materials.shear_strength_mpa(bolt_rm_mpa)
    cap_i = tau_i * geometry.thread_shear_area_mm2(d2, engagement_mm)
    cap_b = tau_b * geometry.thread_shear_area_mm2(d3, engagement_mm)
    return {
        "preload_n": F,
        "torque_min_nm": torque.tightening_torque_nm(F, d2, pitch_mm, mu_thread_min, mu_bearing_min, effective_bearing_diameter_mm),
        "torque_nom_nm": torque.tightening_torque_nm(F, d2, pitch_mm, mu_thread_nom, mu_bearing_nom, effective_bearing_diameter_mm),
        "torque_max_nm": torque.tightening_torque_nm(F, d2, pitch_mm, mu_thread_max, mu_bearing_max, effective_bearing_diameter_mm),
        "nut_proof_util_pct": preload.proof_load_utilization_pct(F, nut_proof_mpa, stress_area_mm2),
        "internal_thread_sf": cap_i / F,
        "external_thread_sf": cap_b / F,
    }
