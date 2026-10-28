"""Load pipeline Gold output for the Streamlit dashboard with a safe fallback."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd


BOOLEAN_COLUMNS = ["emergency_admit", "missed_followup", "readmitted_30d"]


def _normalize(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["encounter_date"] = pd.to_datetime(result["encounter_date"], errors="coerce")
    for column in BOOLEAN_COLUMNS:
        if result[column].dtype != bool:
            result[column] = (
                result[column].astype(str).str.strip().str.lower().map({"true": True, "false": False})
            )
    return result.dropna(subset=["encounter_date"]).sort_values("encounter_date").reset_index(drop=True)


def load_dashboard_data(fallback: pd.DataFrame, gold_path: str | Path | None = None) -> pd.DataFrame:
    """Load Gold dashboard CSV parts; return fallback when no pipeline output exists."""
    configured = gold_path or os.getenv("CARESIGNAL_GOLD_PATH", "data/gold/dashboard")
    directory = Path(configured)
    files = sorted(directory.glob("part-*.csv")) if directory.exists() else []
    if not files:
        return fallback.copy()
    loaded = pd.concat((pd.read_csv(file) for file in files), ignore_index=True)
    return _normalize(loaded)

