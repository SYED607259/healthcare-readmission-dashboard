#!/usr/bin/env bash
set -euo pipefail

python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pipeline.generate_data --rows 5000
spark-submit pipeline/spark_job.py \
  --input_path data/bronze/encounters \
  --output_path data

echo "Pipeline complete. Start the dashboard with: streamlit run app.py"

