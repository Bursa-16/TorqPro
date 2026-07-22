"""TorqPro Joint foundation (Faz 2.5A prerequisite).

Minimum real domain layer for Joint / JointRevision identity and revision
traceability. This is NOT the full engineering Joint aggregate described in
docs/01_DOMAIN_MODEL.md (no component tree, no interface/load-case editor,
no calculation orchestration). It exists solely to give
backend.production_validation a real, queryable FK target instead of a
stub or a nullable relationship. See docs/adr/ADR_2.5A_JOINT_AND_CALCULATION_REVISION_LINKAGE.md.
"""
