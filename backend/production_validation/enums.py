"""Enumerations for the production validation domain."""
from __future__ import annotations

STUDY_TYPES = (
    "short_term_capability",
    "long_term_performance",
    "torque_validation",
    "preload_validation",
    "residual_torque",
    "breakaway_torque",
    "audit_measurement",
    "prototype_validation",
    "serial_production_validation",
)

STUDY_STATUSES = (
    "draft",
    "data_collection",
    "completed",
    "under_review",
    "approved",
    "rejected",
    "archived",
)

# Allowed forward transitions for ValidationStudy.status.
STUDY_TRANSITIONS = {
    "draft": {"data_collection", "archived"},
    "data_collection": {"completed", "archived"},
    "completed": {"under_review", "archived"},
    "under_review": {"approved", "rejected", "archived"},
    "approved": {"archived"},
    "rejected": {"data_collection", "archived"},
    "archived": set(),
}

CHARACTERISTIC_TYPES = (
    "tightening_torque",
    "residual_torque",
    "breakaway_torque",
    "preload",
    "angle",
    "friction_coefficient",
    "dimension",
    "custom",
)

DATASET_SOURCE_TYPES = ("manual", "csv", "device_import", "api")

APPROVAL_ROLES = ("admin", "engineer")
