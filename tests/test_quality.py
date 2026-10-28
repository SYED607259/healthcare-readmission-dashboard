import unittest

from pipeline.generate_data import build_synthetic_encounters
from pipeline.quality import validate_source_frame


class QualityTests(unittest.TestCase):
    def test_duplicate_encounter_is_reported(self):
        frame = build_synthetic_encounters(rows=20)
        frame.loc[1, "encounter_id"] = frame.loc[0, "encounter_id"]
        self.assertIn("encounter_id contains duplicate values", validate_source_frame(frame))

    def test_invalid_age_is_reported(self):
        frame = build_synthetic_encounters(rows=20)
        frame.loc[0, "age"] = 150
        self.assertIn("age must be between 18 and 100", validate_source_frame(frame))


if __name__ == "__main__":
    unittest.main()

