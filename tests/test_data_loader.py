import tempfile
import unittest
from pathlib import Path

import pandas as pd

from data_loader import load_dashboard_data
from pipeline.generate_data import build_synthetic_encounters


class DataLoaderTests(unittest.TestCase):
    def test_fallback_is_used_without_gold_output(self):
        fallback = build_synthetic_encounters(rows=10)
        with tempfile.TemporaryDirectory() as directory:
            loaded = load_dashboard_data(fallback, Path(directory) / "missing")
        self.assertEqual(len(loaded), 10)

    def test_gold_csv_is_loaded(self):
        frame = build_synthetic_encounters(rows=12)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            frame.to_csv(path / "part-00000.csv", index=False)
            loaded = load_dashboard_data(pd.DataFrame(), path)
        self.assertEqual(len(loaded), 12)
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(loaded["encounter_date"]))


if __name__ == "__main__":
    unittest.main()

