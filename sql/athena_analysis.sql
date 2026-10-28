-- Run after the Gold crawler completes. Replace the database name if ProjectName changed.
USE caresignal_readmission_analytics;

-- Executive facility comparison.
SELECT
    facility,
    encounters,
    readmissions,
    ROUND(readmission_rate * 100, 2) AS readmission_rate_pct,
    ROUND(average_length_of_stay, 2) AS average_length_of_stay,
    high_risk_encounters
FROM caresignal_mart_facility_readmission
ORDER BY readmission_rate DESC;

-- Diagnosis-level readmission analysis.
SELECT
    primary_diagnosis,
    encounters,
    readmissions,
    ROUND(readmission_rate * 100, 2) AS readmission_rate_pct,
    ROUND(average_risk_score, 2) AS average_risk_score
FROM caresignal_mart_diagnosis_readmission
ORDER BY readmission_rate DESC;

-- Referential-integrity check across the star schema.
SELECT COUNT(*) AS orphaned_fact_rows
FROM caresignal_fact_encounter f
LEFT JOIN caresignal_dim_patient p ON f.patient_sk = p.patient_sk
LEFT JOIN caresignal_dim_facility h ON f.facility_sk = h.facility_sk
LEFT JOIN caresignal_dim_diagnosis d ON f.diagnosis_sk = d.diagnosis_sk
LEFT JOIN caresignal_dim_date dt ON f.date_sk = dt.date_sk
WHERE p.patient_sk IS NULL
   OR h.facility_sk IS NULL
   OR d.diagnosis_sk IS NULL
   OR dt.date_sk IS NULL;

-- Duplicate business-key check; expected result is zero rows.
SELECT encounter_id, COUNT(*) AS duplicate_count
FROM caresignal_fact_encounter
GROUP BY encounter_id
HAVING COUNT(*) > 1;

