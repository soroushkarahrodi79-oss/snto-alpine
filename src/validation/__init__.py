"""SNTO validation layer — ground-truth & pseudo-validation (F5).

Field-observation schema and satellite↔terrain agreement metrics (Spearman
correlation, control–impact BACI contrast) to demonstrate that the satellite
EHS tracks degradation observed on the ground.
"""
from src.validation.agreement import (
    AgreementReport,
    ContrastResult,
    bootstrap_spearman_ci,
    cliffs_delta,
    control_impact_contrast,
    spearman_correlation,
    validate_satellite_vs_field,
)
from src.validation.confusion import (
    ConfusionReport,
    build_pairs,
    confusion_matrix,
    field_degraded,
    satellite_alert,
)
from src.validation.field import (
    ErosionClass,
    FieldObservation,
    field_index_by_asset,
    split_impact_control,
)
from src.validation.io import (
    load_field_observations,
    write_template,
)

__all__ = [
    "AgreementReport",
    "ContrastResult",
    "bootstrap_spearman_ci",
    "cliffs_delta",
    "control_impact_contrast",
    "spearman_correlation",
    "validate_satellite_vs_field",
    "ConfusionReport",
    "build_pairs",
    "confusion_matrix",
    "field_degraded",
    "satellite_alert",
    "ErosionClass",
    "FieldObservation",
    "field_index_by_asset",
    "split_impact_control",
    "load_field_observations",
    "write_template",
]
