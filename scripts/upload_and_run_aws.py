"""Upload pipeline assets to S3 and optionally start the AWS Glue job."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import boto3

from pipeline.generate_data import write_synthetic_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upload CareSignal assets and run Glue")
    parser.add_argument("--bucket", required=True, help="CloudFormation DataBucketName output")
    parser.add_argument("--job-name", help="CloudFormation GlueJobName output")
    parser.add_argument("--rows", type=int, default=5_000)
    parser.add_argument("--region", default=None)
    parser.add_argument("--run", action="store_true", help="Start the Glue job after upload")
    parser.add_argument("--wait", action="store_true", help="Wait for the Glue job to finish")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    session = boto3.Session(region_name=args.region)
    s3 = session.client("s3")
    source = write_synthetic_csv(
        Path("data/bronze/encounters/encounters.csv"), rows=args.rows, seed=42
    )
    assets = [
        (source, "bronze/encounters/encounters.csv"),
        (Path("pipeline/spark_job.py"), "scripts/spark_job.py"),
    ]
    for local, key in assets:
        s3.upload_file(str(local), args.bucket, key)
        print(f"Uploaded {local} to s3://{args.bucket}/{key}")

    if not args.run:
        return
    if not args.job_name:
        raise SystemExit("--job-name is required when --run is supplied")

    glue = session.client("glue")
    run_id = glue.start_job_run(JobName=args.job_name)["JobRunId"]
    print(f"Started Glue job {args.job_name}; run ID: {run_id}")
    if not args.wait:
        return
    while True:
        state = glue.get_job_run(JobName=args.job_name, RunId=run_id)["JobRun"]["JobRunState"]
        print(f"Glue state: {state}")
        if state in {"SUCCEEDED", "FAILED", "STOPPED", "TIMEOUT", "ERROR"}:
            if state != "SUCCEEDED":
                raise SystemExit(f"Glue job ended with state {state}")
            return
        time.sleep(20)


if __name__ == "__main__":
    main()

