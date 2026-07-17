"""Reference-data record validation and deviation checks.

Moved unchanged from backend/app.py (Phase 1):
- ``QUALITY_SCHEMAS`` and ``validate_package_records`` (quality gate)
- deviation/tolerance arithmetic shared by calibration cases and
  golden cases (originally duplicated inline in both handlers).

Pure Python — no FastAPI, no database access.
"""

from __future__ import annotations

from . import units

QUALITY_SCHEMAS = {
  "proof_load": {
    "required_any": [["thread_code", "thread", "size"], ["nut_property_class", "nut_class", "property_class"], ["proof_stress_mpa", "proof_load_n"]],
    "numeric": ["proof_stress_mpa", "proof_load_n", "stress_area_mm2"]
  },
  "friction": {
    "required_any": [["coating", "coating_system", "surface"], ["mu_thread_nom", "mu_thread"], ["mu_bearing_nom", "mu_bearing"]],
    "numeric": ["mu_thread_min", "mu_thread_nom", "mu_thread_max", "mu_thread", "mu_bearing_min", "mu_bearing_nom", "mu_bearing_max", "mu_bearing"]
  },
  "washer": {
    "required_any": [["thread_code", "thread", "size"], ["bearing_pressure_limit_mpa", "allowable_bearing_pressure_mpa"]],
    "numeric": ["inside_diameter_mm", "outside_diameter_mm", "thickness_mm", "bearing_pressure_limit_mpa", "allowable_bearing_pressure_mpa"]
  },
  "compatibility": {
    "required_any": [["bolt_class", "bolt_property_class"], ["minimum_nut_class", "required_nut_class"]],
    "numeric": []
  }
}


def validate_package_records(dataset, records):
    """Validate uploaded reference-data records against the dataset schema.

    Moved unchanged from app.py; returns ``(is_valid, errors[:100])``.
    """
    schema = QUALITY_SCHEMAS.get(dataset)
    if not schema: return False, ["Tanımsız veri seti"]
    errors = []
    if not records: errors.append("Kayıt bulunamadı")
    for i, row in enumerate(records, 1):
        if not isinstance(row, dict):
            errors.append(f"Satır {i}: nesne değil"); continue
        for group in schema["required_any"]:
            if not any(row.get(k) not in (None, "") for k in group):
                errors.append(f"Satır {i}: zorunlu alan grubu eksik ({'/'.join(group)})")
        for key in schema["numeric"]:
            if key in row and row[key] not in (None, ""):
                try: float(str(row[key]).replace(",", "."))
                except Exception: errors.append(f"Satır {i}: {key} sayısal değil")
    return len(errors) == 0, errors[:100]


def deviation_pct(program_value: float, reference_value: float) -> float:
    """Relative deviation in percent.

    Original (calibration & golden cases):
    ``abs(program-reference)/abs(reference)*100``.
    Caller must ensure ``reference_value`` is nonzero (unchanged contract).
    """
    return units.fraction_to_percent(abs(program_value - reference_value) / abs(reference_value))


def tolerance_passed(error_pct: float, tolerance_pct: float) -> int:
    """1 if the deviation is within tolerance, else 0.

    Original: ``passed=1 if err<=x.tolerance_pct else 0``.
    """
    return 1 if error_pct <= tolerance_pct else 0
