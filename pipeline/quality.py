"""Data contracts and lightweight quality checks for source encounters."""

from __future__ import annotations

import pandas as pd


REQUIRED_COLUMNS = {
    "encounter_id",
    "patient_id",
    "encounter_date",
    "facility",
    "age",
    "sex",
    "payer",
    "primary_diagnosis",
    "length_of_stay",
    "previous_admissions",
    "chronic_conditions",
    "emergency_admit",
    "missed_followup",
    "discharge_disposition",
    "risk_score",
    "risk_band",
    "readmitted_30d",
}


def validate_source_frame(frame: pd.DataFrame) -> list[str]:
    """Return human-readable contract violations; an empty list means pass."""
    errors: list[str] = []
    missing = sorted(REQUIRED_COLUMNS - set(frame.columns))
    if missing:
        return [f"missing required columns: {', '.join(missing)}"]
    if frame.empty:
        errors.append("source contains no records")
    if frame["encounter_id"].isna().any():
        errors.append("encounter_id contains null values")
    if frame["encounter_id"].duplicated().any():
        errors.append("encounter_id contains duplicate values")
    if frame["patient_id"].isna().any():
        errors.append("patient_id contains null values")
    if not frame["age"].between(18, 100).all():
        errors.append("age must be between 18 and 100")
    if not frame["length_of_stay"].between(1, 60).all():
        errors.append("length_of_stay must be between 1 and 60")
    if not frame["risk_score"].between(0, 100).all():
        errors.append("risk_score must be between 0 and 100")
    if not set(frame["risk_band"].dropna().unique()).issubset({"Low", "Medium", "High"}):
        errors.append("risk_band contains an unsupported value")
    parsed_dates = pd.to_datetime(frame["encounter_date"], errors="coerce")
    if parsed_dates.isna().any():
        errors.append("encounter_date contains invalid dates")
    return errors


def assert_valid_source(frame: pd.DataFrame) -> None:
    errors = validate_source_frame(frame)
    if errors:
        raise ValueError("; ".join(errors))

