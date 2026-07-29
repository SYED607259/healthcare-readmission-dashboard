# Healthcare Patient Risk & Readmission Analysis

A portfolio-ready Streamlit dashboard for exploring 30-day hospital readmission patterns,
prioritizing high-risk patients, comparing facility performance, and exporting care-management
worklists.

## Demo login

- Username: `admin`
- Password: `CareSignal2026!`

Accounts created through the registration form are stored locally with PBKDF2-SHA256 password
hashing and per-user random salts. The local SQLite account database is excluded from Git.

## Run locally

```powershell
streamlit run app.py
```

The application generates a deterministic synthetic dataset at runtime. It contains no real
patient information and is not intended for clinical use.

## Dashboard modules

- Executive KPI and monthly trend overview
- High-risk patient work queue
- Diagnosis, discharge, and facility analysis
- Patient-level risk-factor explorer
- Downloadable CSV data and methodology notes
- Secure sign-in, account registration, and logout
