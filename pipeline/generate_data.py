"""Generate deterministic synthetic hospital encounters for the portfolio pipeline.

The records are entirely synthetic and must never be represented as real patients or
production hospital data.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd


def build_synthetic_encounters(
    rows: int = 5_000,
    seed: int = 42,
    as_of_date: date = date(2026, 10, 1),
) -> pd.DataFrame:
    """Return reproducible synthetic encounter-level data."""
    if rows < 1:
        raise ValueError("rows must be greater than zero")

    rng = np.random.default_rng(seed)
    diagnoses = np.array(
        ["Heart Failure", "COPD", "Diabetes", "Pneumonia", "Renal Disease", "Hypertension"]
    )
    diagnosis_weights = np.array([0.18, 0.15, 0.22, 0.16, 0.12, 0.17])
    payers = np.array(["Medicare", "Medicaid", "Commercial", "Self-pay"])
    discharge_types = np.array(["Home", "Home Health", "Skilled Nursing", "Rehabilitation"])
    facilities = np.array(["North Medical", "Central Hospital", "West Community"])

    patient_count = max(100, int(rows * 0.72))
    patient_ids = np.array([f"PT-{10001 + i}" for i in range(patient_count)])
    patient_age = np.clip(rng.normal(64, 15, patient_count).round(), 18, 94).astype(int)
    patient_sex = rng.choice(["Female", "Male"], patient_count, p=[0.52, 0.48])
    patient_payer = rng.choice(payers, patient_count, p=[0.46, 0.23, 0.26, 0.05])
    patient_index = rng.integers(0, patient_count, rows)
    encounter_dates = pd.to_datetime(
        [
            as_of_date - timedelta(days=int(offset))
            for offset in rng.integers(0, 730, rows)
        ]
    )
    age = patient_age[patient_index]
    diagnosis = rng.choice(diagnoses, rows, p=diagnosis_weights)
    payer = patient_payer[patient_index]
    previous_admissions = np.clip(rng.poisson(1.15, rows), 0, 7)
    chronic_conditions = np.clip(rng.poisson(2.3, rows) + 1, 1, 8)
    length_of_stay = np.clip(
        rng.gamma(2.2, 2.1, rows) + (diagnosis == "Heart Failure") * 1.3,
        1,
        21,
    ).round().astype(int)
    emergency_admit = rng.random(rows) < 0.57
    missed_followup = rng.random(rows) < (
        0.12 + 0.05 * previous_admissions + 0.04 * (payer == "Self-pay")
    )
    discharge = rng.choice(discharge_types, rows, p=[0.56, 0.18, 0.17, 0.09])

    logit = (
        -4.15
        + 0.022 * (age - 50)
        + 0.42 * previous_admissions
        + 0.22 * (chronic_conditions - 1)
        + 0.055 * length_of_stay
        + 0.50 * emergency_admit
        + 0.88 * missed_followup
        + 0.32 * np.isin(diagnosis, ["Heart Failure", "COPD", "Renal Disease"])
        + 0.30 * np.isin(discharge, ["Skilled Nursing", "Rehabilitation"])
    )
    risk_probability = 1 / (1 + np.exp(-logit))
    readmitted = rng.random(rows) < risk_probability
    risk_score = np.clip(
        (100 / (1 + np.exp(-(logit + 0.35 * rng.normal(size=rows) + 0.35)))).round(),
        3,
        98,
    ).astype(int)
    risk_band = pd.cut(
        risk_score,
        bins=[-1, 34, 64, 100],
        labels=["Low", "Medium", "High"],
    ).astype(str)

    encounters = pd.DataFrame(
        {
            "encounter_id": [f"ENC-{1_000_001 + i}" for i in range(rows)],
            "patient_id": patient_ids[patient_index],
            "encounter_date": encounter_dates,
            "facility": rng.choice(facilities, rows, p=[0.39, 0.36, 0.25]),
            "age": age,
            "sex": patient_sex[patient_index],
            "payer": payer,
            "primary_diagnosis": diagnosis,
            "length_of_stay": length_of_stay,
            "previous_admissions": previous_admissions,
            "chronic_conditions": chronic_conditions,
            "emergency_admit": emergency_admit,
            "missed_followup": missed_followup,
            "discharge_disposition": discharge,
            "risk_score": risk_score,
            "risk_band": risk_band,
            "readmitted_30d": readmitted,
        }
    )
    return encounters.sort_values(["encounter_date", "encounter_id"]).reset_index(drop=True)


def write_synthetic_csv(output: Path, rows: int = 5_000, seed: int = 42) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    build_synthetic_encounters(rows=rows, seed=seed).to_csv(output, index=False)
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate synthetic readmission encounters")
    parser.add_argument("--output", type=Path, default=Path("data/bronze/encounters/encounters.csv"))
    parser.add_argument("--rows", type=int, default=5_000)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    path = write_synthetic_csv(args.output, rows=args.rows, seed=args.seed)
    print(f"Wrote {args.rows:,} synthetic encounters to {path}")

