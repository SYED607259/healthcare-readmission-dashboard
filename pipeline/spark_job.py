"""Reusable PySpark ETL job for local Spark and AWS Glue 5.1.

Input: encounter CSV files in the Bronze path.
Output: Silver Parquet, rejected records, Gold star-schema tables and marts.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql import types as T


SOURCE_SCHEMA = T.StructType(
    [
        T.StructField("encounter_id", T.StringType(), False),
        T.StructField("patient_id", T.StringType(), False),
        T.StructField("encounter_date", T.StringType(), False),
        T.StructField("facility", T.StringType(), False),
        T.StructField("age", T.IntegerType(), False),
        T.StructField("sex", T.StringType(), False),
        T.StructField("payer", T.StringType(), False),
        T.StructField("primary_diagnosis", T.StringType(), False),
        T.StructField("length_of_stay", T.IntegerType(), False),
        T.StructField("previous_admissions", T.IntegerType(), False),
        T.StructField("chronic_conditions", T.IntegerType(), False),
        T.StructField("emergency_admit", T.BooleanType(), False),
        T.StructField("missed_followup", T.BooleanType(), False),
        T.StructField("discharge_disposition", T.StringType(), False),
        T.StructField("risk_score", T.IntegerType(), False),
        T.StructField("risk_band", T.StringType(), False),
        T.StructField("readmitted_30d", T.BooleanType(), False),
    ]
)


def _path(root: str, child: str) -> str:
    return f"{root.rstrip('/')}/{child.strip('/')}"


def _valid_condition() -> Any:
    return (
        F.col("encounter_id").isNotNull()
        & F.col("patient_id").isNotNull()
        & F.col("encounter_date").isNotNull()
        & F.col("facility").isNotNull()
        & F.col("primary_diagnosis").isNotNull()
        & F.col("age").between(18, 100)
        & F.col("length_of_stay").between(1, 60)
        & F.col("risk_score").between(0, 100)
        & F.col("risk_band").isin("Low", "Medium", "High")
    )


def transform_encounters(raw: DataFrame) -> tuple[DataFrame, DataFrame]:
    """Clean, standardize and split valid and rejected records."""
    prepared = (
        raw.withColumn("encounter_date", F.to_date("encounter_date"))
        .withColumn("facility", F.trim("facility"))
        .withColumn("primary_diagnosis", F.trim("primary_diagnosis"))
        .withColumn("payer", F.trim("payer"))
        .withColumn("sex", F.initcap(F.trim("sex")))
        .withColumn("discharge_disposition", F.trim("discharge_disposition"))
        .withColumn(
            "age_group",
            F.when(F.col("age") < 45, "18-44")
            .when(F.col("age") < 65, "45-64")
            .when(F.col("age") < 80, "65-79")
            .otherwise("80+"),
        )
        .withColumn("ingested_at", F.current_timestamp())
        .withColumn("ingestion_date", F.current_date())
        .withColumn("source_file", F.input_file_name())
    )

    duplicate_keys = prepared.groupBy("encounter_id").count().filter(F.col("count") > 1)
    classified = (
        prepared.join(
            duplicate_keys.select("encounter_id", F.col("count").alias("duplicate_count")),
            "encounter_id",
            "left",
        )
        .withColumn(
            "rejection_reason",
            F.when(F.col("duplicate_count").isNotNull(), "duplicate encounter_id").when(
                ~_valid_condition(), "failed required-field or range validation"
            ),
        )
        .drop("duplicate_count")
    )
    rejected = classified.filter(F.col("rejection_reason").isNotNull())
    valid = classified.filter(F.col("rejection_reason").isNull()).drop("rejection_reason")
    return valid, rejected


def build_gold_tables(silver: DataFrame) -> dict[str, DataFrame]:
    patient = silver.select("patient_id", "age", "age_group", "sex", "payer").dropDuplicates(
        ["patient_id"]
    )
    dim_patient = patient.withColumn("patient_sk", F.xxhash64("patient_id")).select(
        "patient_sk", "patient_id", "age", "age_group", "sex", "payer"
    )
    dim_facility = (
        silver.select("facility")
        .dropDuplicates()
        .withColumn("facility_sk", F.xxhash64("facility"))
        .select("facility_sk", "facility")
    )
    dim_diagnosis = (
        silver.select("primary_diagnosis")
        .dropDuplicates()
        .withColumn("diagnosis_sk", F.xxhash64("primary_diagnosis"))
        .select("diagnosis_sk", "primary_diagnosis")
    )
    dim_date = (
        silver.select(F.col("encounter_date").alias("calendar_date"))
        .dropDuplicates()
        .withColumn("date_sk", F.date_format("calendar_date", "yyyyMMdd").cast("int"))
        .withColumn("year", F.year("calendar_date"))
        .withColumn("quarter", F.quarter("calendar_date"))
        .withColumn("month", F.month("calendar_date"))
        .withColumn("month_name", F.date_format("calendar_date", "MMMM"))
        .select("date_sk", "calendar_date", "year", "quarter", "month", "month_name")
    )

    fact = (
        silver.withColumn("patient_sk", F.xxhash64("patient_id"))
        .withColumn("facility_sk", F.xxhash64("facility"))
        .withColumn("diagnosis_sk", F.xxhash64("primary_diagnosis"))
        .withColumn("date_sk", F.date_format("encounter_date", "yyyyMMdd").cast("int"))
        .select(
            "encounter_id",
            "patient_sk",
            "facility_sk",
            "diagnosis_sk",
            "date_sk",
            "discharge_disposition",
            "length_of_stay",
            "previous_admissions",
            "chronic_conditions",
            "emergency_admit",
            "missed_followup",
            "risk_score",
            "risk_band",
            "readmitted_30d",
            "ingestion_date",
        )
    )

    facility_mart = (
        silver.groupBy("facility")
        .agg(
            F.count("encounter_id").alias("encounters"),
            F.sum(F.col("readmitted_30d").cast("int")).alias("readmissions"),
            F.avg(F.col("readmitted_30d").cast("double")).alias("readmission_rate"),
            F.avg("length_of_stay").alias("average_length_of_stay"),
            F.sum(F.when(F.col("risk_band") == "High", 1).otherwise(0)).alias(
                "high_risk_encounters"
            ),
        )
        .orderBy(F.desc("readmission_rate"))
    )
    diagnosis_mart = (
        silver.groupBy("primary_diagnosis")
        .agg(
            F.count("encounter_id").alias("encounters"),
            F.sum(F.col("readmitted_30d").cast("int")).alias("readmissions"),
            F.avg(F.col("readmitted_30d").cast("double")).alias("readmission_rate"),
            F.avg("risk_score").alias("average_risk_score"),
        )
        .orderBy(F.desc("readmission_rate"))
    )
    monthly_mart = (
        silver.withColumn("month", F.date_trunc("month", "encounter_date"))
        .groupBy("month")
        .agg(
            F.count("encounter_id").alias("encounters"),
            F.sum(F.col("readmitted_30d").cast("int")).alias("readmissions"),
            F.avg(F.col("readmitted_30d").cast("double")).alias("readmission_rate"),
        )
        .orderBy("month")
    )

    dashboard = silver.select(
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
    )

    return {
        "dim_patient": dim_patient,
        "dim_facility": dim_facility,
        "dim_diagnosis": dim_diagnosis,
        "dim_date": dim_date,
        "fact_encounter": fact,
        "mart_facility_readmission": facility_mart,
        "mart_diagnosis_readmission": diagnosis_mart,
        "mart_monthly_readmission": monthly_mart,
        "dashboard": dashboard,
    }


def run_pipeline(spark: SparkSession, input_path: str, output_path: str) -> dict[str, int]:
    raw = spark.read.option("header", True).schema(SOURCE_SCHEMA).csv(input_path)
    raw_count = raw.count()
    silver, rejected = transform_encounters(raw)
    silver_count = silver.count()
    rejected_count = rejected.count()

    silver.write.mode("overwrite").partitionBy("ingestion_date").parquet(
        _path(output_path, "silver/encounters")
    )
    rejected.write.mode("overwrite").parquet(_path(output_path, "silver/rejected_encounters"))

    for name, frame in build_gold_tables(silver).items():
        target = _path(output_path, f"gold/{name}")
        if name == "dashboard":
            frame.coalesce(1).write.mode("overwrite").option("header", True).csv(target)
        else:
            frame.write.mode("overwrite").parquet(target)

    counts = {"raw": raw_count, "silver": silver_count, "rejected": rejected_count}
    manifest = spark.createDataFrame(
        [
            (
                datetime.now(timezone.utc).isoformat(),
                input_path,
                output_path,
                raw_count,
                silver_count,
                rejected_count,
                "PASS" if raw_count == silver_count + rejected_count else "FAIL",
            )
        ],
        [
            "run_timestamp_utc",
            "input_path",
            "output_path",
            "raw_count",
            "silver_count",
            "rejected_count",
            "reconciliation_status",
        ],
    )
    manifest.coalesce(1).write.mode("overwrite").json(_path(output_path, "manifests/latest"))
    if raw_count != silver_count + rejected_count:
        raise RuntimeError(f"row reconciliation failed: {json.dumps(counts)}")
    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CareSignal PySpark ETL job")
    parser.add_argument("--input_path", required=True)
    parser.add_argument("--output_path", required=True)
    parser.add_argument("--app_name", default="caresignal-readmission-etl")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    spark = SparkSession.builder.appName(args.app_name).getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    try:
        counts = run_pipeline(spark, args.input_path, args.output_path)
        print(f"Pipeline completed: {json.dumps(counts, sort_keys=True)}")
    finally:
        spark.stop()


if __name__ == "__main__":
    main()

