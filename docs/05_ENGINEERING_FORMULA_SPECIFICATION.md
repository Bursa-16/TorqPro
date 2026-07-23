# TorqPro Engineering Formula Specification


> **Document set:** TorqPro Software Design Specification (SDS) v1.0  
> **Status:** Approved baseline for implementation planning; engineering equations marked PROVISIONAL are not approved for production calculations.  
> **Product owner:** İlhan Çekiç  
> **Last updated:** 2026-07-16  
> **Source of truth:** This repository. When code and documentation conflict, stop implementation and open an ADR/change request.

## 1. Authority and status

This document defines formula architecture and approved corrections. It is **not yet a certified calculation standard**. Every formula has a status:

- APPROVED: validated against controlled references and golden cases.
- PROVISIONAL: concept accepted, equation/source validation incomplete.
- TEST_DERIVED: value/model requires test evidence.
- NOT_IMPLEMENTED: planned only.

Production claims require an approved formula pack and independent engineering validation.

## 2. Symbol and unit policy

Internal base units: N, mm, MPa (= N/mm²), Nm at API boundary with explicit conversion to Nmm, °C/K, radians and seconds. Every value object includes value and unit. Symbols are not reused for both displacement and compliance.

Key symbols:

| Symbol | Meaning | Unit |
|---|---|---|
| `F_M` | assembly preload | N |
| `F_A` | external axial separating load | N |
| `Phi` | load factor | dimensionless |
| `F_S` | service bolt force | N |
| `F_K,res` | residual clamp force | N |
| `delta_b`, `delta_c` | bolt/clamped-part compliance | mm/N |
| `c_b`, `c_c` | stiffness | N/mm |
| `M_A` | applied tightening torque | Nm |
| `mu_G`, `mu_K` | thread/bearing friction | dimensionless |
| `A_s` | tensile stress area | mm² |

## 3. Load sharing (mandatory corrected model)

For a concentric axial load under the valid linear-elastic assumptions:

```text
Phi = c_b / (c_b + c_c)
delta_F_b = Phi * F_A
F_S = F_M + Phi * F_A
delta_F_K = (1 - Phi) * F_A
F_K_res = F_M - (1 - Phi) * F_A
```

The earlier expression `F_M - Phi*F_A` for residual clamp is rejected. Eccentric loading and load-introduction factors require a detailed VDI-based module and are PROVISIONAL.

## 4. Quick torque estimate

```text
M_A = K * d * F_M
F_M = M_A / (K * d)
```

`K` is dimensionless nut factor and `d` nominal diameter. This is QUICK/EMPIRICAL and must show the source and range of K. It is not the detailed solver.

A separate transfer coefficient with dimensions may be supported, but it must not be named or treated as dimensionless K.

## 5. Detailed tightening torque

The architecture decomposes torque:

```text
M_A = M_G + M_K + M_P + M_misc
M_G = F_M * (d_2/2) * tan(phi_thread + rho_prime)
tan(phi_thread) = P / (pi*d_2)
tan(rho_prime) = mu_G / cos(alpha/2)
M_K = F_M * mu_K * D_Km/2
```

Equivalent expanded forms may be used after validation. `M_P` prevailing torque is measured/test-derived or supplier/OEM approved; do not invent a universal `mu_p`.

Classification: DETAILED, currently PROVISIONAL pending reference verification and golden cases.

## 6. Preload range and tightening scatter

The system distinguishes target, minimum, maximum and achieved distribution. Scatter may arise from torque tool, friction, prevailing torque, geometry and process. A simplistic symmetric percentage is allowed only in quick mode and must be labelled.

Detailed uncertainty uses parameter distributions and Monte Carlo/variance propagation. Correlations must be configurable. Results include seed, sample count and confidence interval.

## 7. Bolt stiffness

Use compliance sum by regions:

```text
delta_b = sum(L_i / (E_i * A_i)) + local_compliances
c_b = 1 / delta_b
```

Regions may include shank, free thread, engaged thread/head/nut substitution lengths. A single `EA/L` is only a quick approximation.

## 8. Clamped-part stiffness

For serial compressed regions:

```text
delta_c = sum(L_i / (E_i * A_eff_i))
c_c = 1 / delta_c
```

`A_eff` must follow an approved pressure-cone/equivalent-compression-body method. Directly summing `E*A/L` for serial parts is rejected.

## 9. Assembly and service stress

```text
sigma_assembly = F_M / A_s
sigma_service_max = (F_M + Phi*F_A) / A_s
```

During tightening, combined axial/torsional equivalent stress may be evaluated:

```text
tau = M_G / W_t
sigma_v = sqrt(sigma_axial^2 + 3*tau^2)
eta_yield = sigma_v / R_limit
```

The applicable proof/yield limit and torsional section modulus require validated definitions.

## 10. Separation and slip

```text
separation if F_K_res <= required_min_clamp
V_allow = n_f * mu_interface * F_K_res / S_slip
```

For multi-bolt groups, load distribution and moment effects require a separate module. `mu_interface` is not thread friction.

## 11. Bearing pressure

Effective annular area:

```text
A_B = pi/4 * (D_outer^2 - D_hole^2)
p_B = F / A_B
```

Geometry-specific models are required for flange heads, washers, countersunk heads and soft interfaces. Allowable pressure is material/condition/temperature dependent.

## 12. Thread stripping

Thread stripping shall separately check external and internal threads, effective engagement, unequal load distribution, tolerance and both material strengths. Generic `pi*d*Le*k` is only a PROVISIONAL framework. Current engineering pre-check outputs must be described as preliminary safety estimates until validated.

## 13. Settlement/embedment

```text
f_Z = sum(settlement_length_i)
delta_F_Z = f_Z / (delta_b + delta_c)
F_M_after = F_M_initial - delta_F_Z
```

Settlement values are empirical/test/standard-derived with surface and interface context. Never multiply by preload when compliance already converts length to force.

## 14. Thermal preload change

```text
Delta_L_c = sum(alpha_i * L_i * Delta_T_i)
Delta_L_b = alpha_b * L_b * Delta_T_b
Delta_F_T = (Delta_L_c - Delta_L_b) / (delta_b + delta_c)
F_M_T = F_M_0 + Delta_F_T
```

Sign and boundary conditions must be explained. Temperature-dependent modulus and strength must come from approved property sets. Status: PROVISIONAL.

## 15. Relaxation and creep

No universal logarithmic or exponential coefficient shall be hard-coded. Models are TEST_DERIVED and selected by material/interface/temperature. Inputs include time, temperature, stress, gasket/polymer presence and evidence. Outputs show model source and applicability.

## 16. Fatigue

The bolt load range derives from load partition:

```text
Delta_F_b = Phi * Delta_F_A
sigma_a = Delta_F_b / (2*A_s)
sigma_m = (F_b_max + F_b_min) / (2*A_s)
```

Detailed evaluation must account for thread-root fatigue class, rolled-thread process, size, surface, mean stress, load spectrum and safety factors. Goodman is optional advisory, not a replacement for the approved bolted-joint method.

## 17. Torque-angle and yield strategies

Torque-angle requires rundown/snug phase, joint rotational stiffness, elastic angle, prevailing torque compensation and tool trace. A linear `T=K_theta*theta` is only a local approximation. Yield-point detection requires measured curve algorithms and validation datasets.

## 18. Formula trace schema

Each result stores:

```json
{
  "formula_id": "LOAD-004",
  "formula_pack_version": "1.0.0",
  "classification": "DETAILED",
  "validation_status": "PROVISIONAL",
  "inputs": [{"name":"F_M","value":40000,"unit":"N","source":"calculation"}],
  "outputs": [{"name":"F_K_res","value":32000,"unit":"N"}],
  "assumptions": ["concentric axial loading", "linear elastic"],
  "references": ["licensed implementation note"],
  "warnings": []
}
```

## 19. Standards mapping policy

- VDI 2230: systematic bolted-joint design and load/deformation methodology; implementation requires licensed references and validation.
- ISO 16047: torque/clamp-force testing, not the sole design-equation source.
- ISO 2320: prevailing-torque steel nuts and performance/testing.
- ISO 898 series: mechanical/physical properties for bolts, nuts and washers as applicable.
- FIAT 01391 and 01393/01: customer/OEM rule packs and forecast/validation workflows according to licensed documents.

## 20. Validation requirement

No formula pack becomes APPROVED without:

1. source review and equation/unit check;
2. independent hand calculations;
3. golden cases covering boundaries;
4. comparison with trusted software/test results where permitted;
5. documented tolerances;
6. review and sign-off by qualified mechanical engineer;
7. regression tests locking expected outputs.

## 21. Friction Condition module linkage (Faz 2.6)

**Naming (Faz 2.6 rename, 2026-07-23):** the source of `mu_G`/`mu_K` (thread/bearing friction, Section 2) and future `mu_thread`/`mu_bearing`/K-factor/scatter values is the **Friction Condition** module, not a "Lubrication Module". Lubrication is one subsection of Friction Condition; the module also covers surface condition, coatings, thread/bearing condition and related engineering warnings (see docs/09_LIBRARY_SPECIFICATION.md §10, ADR-0009).

Current implementation status (Faz 2.6.0, architecture/spec only):

- Section 5's `M_G`/`M_K` decomposition is already implemented (`backend/engineering_core/friction.py`, `torque.py`), fed by direct API `mu_thread`/`mu_bearing` input (`EngineeringCheck` model, `backend/app.py`). It is not yet library-sourced.
- A percentage breakdown of `M_G`/`M_K`/useful-clamp-force generation (torque distribution reporting) is NOT_IMPLEMENTED; planned for Faz 2.6.3, additive on top of the existing formula -- no change to the Section 5 equation itself.
- `backend.library.models.LubricationRecord` (Lubrication subsection of Friction Condition) now carries schema fields for `mu_thread_min/max`, `mu_bearing_min/max`, `k_factor_min/max` and `scatter_percent`, but no record populates them yet: per docs/12_CLAUDE_CONTEXT.md §4, no coefficient is invented without an approved, cited source. Populating and wiring these into Section 4/5's `K`/`mu_G`/`mu_K` is Faz 2.6.2/2.6.3 scope.
- 15 Tablo-9.4-derived reference records (surface condition x dry/oiled/MoS2-with-oil, textbook_reference/reference_only) were added in Faz 2.6.0 as `overall_friction_coefficient_min/max` with `friction_model = combined_or_unspecified` -- a single combined coefficient, not a `mu_G`/`mu_K` split, and therefore not yet usable as direct Section 5 input.
- **Faz 2.6.2A (2026-07-23):** ownership of verified `mu_thread`/`mu_bearing`/`K`/scatter/overall-coefficient data is now formally assigned to the new `FrictionConditionRecord` (`docs/adr/ADR-0010-coating-lubrication-friction-data-ownership.md`), not to `CoatingRecord` or `LubricationRecord` -- a friction coefficient is a property of a coating+lubricant+condition *combination*, not of either component alone. Section 5's `mu_G`/`mu_K` inputs will eventually be sourced from `FrictionConditionRecord` once Faz 2.6.2B populates it with cited data and Faz 2.6.3 wires the calculation path; `FrictionConditionRecord` currently ships with zero records (schema/decision phase only).

