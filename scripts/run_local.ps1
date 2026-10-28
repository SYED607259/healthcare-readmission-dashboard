$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
    py -3.11 -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\python.exe -m pipeline.generate_data --rows 5000
& .\.venv\Scripts\spark-submit.cmd pipeline\spark_job.py `
    --input_path data\bronze\encounters `
    --output_path data

Write-Host "Pipeline complete. Start the dashboard with:"
Write-Host ".\.venv\Scripts\streamlit.exe run app.py"

