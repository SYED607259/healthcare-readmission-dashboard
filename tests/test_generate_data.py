import unittest

from pipeline.generate_data import build_synthetic_encounters
from pipeline.quality import REQUIRED_COLUMNS, validate_source_frame


class GenerateDataTests(unittest.TestCase):
    def test_generation_is_reproducible_and_valid(self):
        first = build_synthetic_encounters(rows=250, seed=7)
        second = build_synthetic_encounters(rows=250, seed=7)
        self.assertTrue(first.equals(second))
        self.assertEqual(len(first), 250)
        self.assertTrue(REQUIRED_COLUMNS.issubset(first.columns))
        self.assertEqual(validate_source_frame(first), [])

    def test_multiple_encounters_can_belong_to_one_patient(self):
        frame = build_synthetic_encounters(rows=500, seed=12)
        self.assertLess(frame["patient_id"].nunique(), len(frame))
        patient_consistency = frame.groupby("patient_id")[["age", "sex", "payer"]].nunique()
        self.assertTrue((patient_consistency <= 1).all().all())


if __name__ == "__main__":
    unittest.main()

