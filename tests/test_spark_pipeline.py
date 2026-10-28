import tempfile
import unittest
from pathlib import Path

try:
    from pyspark.sql import SparkSession
except ImportError:  # pragma: no cover - permits lightweight local unit tests
    SparkSession = None

from pipeline.generate_data import write_synthetic_csv


@unittest.skipIf(SparkSession is None, "pyspark is not installed")
class SparkPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[2]")
            .appName("caresignal-test")
            .config("spark.ui.enabled", "false")
            .getOrCreate()
        )
        cls.spark.sparkContext.setLogLevel("ERROR")

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def test_end_to_end_row_reconciliation(self):
        from pipeline.spark_job import run_pipeline

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_synthetic_csv(root / "bronze" / "encounters.csv", rows=120)
            counts = run_pipeline(
                self.spark,
                str(root / "bronze"),
                str(root / "output"),
            )
            fact = self.spark.read.parquet(str(root / "output" / "gold" / "fact_encounter"))
            self.assertEqual(counts, {"raw": 120, "silver": 120, "rejected": 0})
            self.assertEqual(fact.count(), 120)
            self.assertEqual(fact.select("encounter_id").distinct().count(), 120)


if __name__ == "__main__":
    unittest.main()

