#!/bin/bash
set -e

PROJECT_ID="${1:-$(gcloud config get-value project 2>/dev/null)}"
DATASET_NAME="${2:-careorchestra}"
LOCATION="${3:-US}"
SEED_DIR="${4:-data/seed}"

if [ -z "$PROJECT_ID" ]; then
  echo "Error: Could not determine Google Cloud Project ID."
  echo "Usage: ./setup_bigquery.sh <PROJECT_ID> [DATASET_NAME] [LOCATION] [SEED_DIR]"
  exit 1
fi

echo "------------------------------------------------------------"
echo "CareOrchestra BigQuery Setup"
echo "Project:  $PROJECT_ID"
echo "Dataset:  $DATASET_NAME"
echo "Location: $LOCATION"
echo "Seed dir: $SEED_DIR"
echo "------------------------------------------------------------"

echo "[1/4] Checking dataset..."
if bq show --dataset "${PROJECT_ID}:${DATASET_NAME}" >/dev/null 2>&1; then
  echo "Dataset already exists."
else
  echo "Creating dataset..."
  bq mk --dataset --location="$LOCATION" "${PROJECT_ID}:${DATASET_NAME}"
fi

echo "[2/4] Creating tables..."

bq query --use_legacy_sql=false "
CREATE OR REPLACE TABLE \`${PROJECT_ID}.${DATASET_NAME}.patients\` (
    patient_id STRING NOT NULL,
    first_name STRING NOT NULL,
    last_name STRING NOT NULL,
    date_of_birth DATE,
  phone_number STRING,
    email STRING,
  conditions STRING,
  care_team STRING,
  created_at TIMESTAMP
);"

bq query --use_legacy_sql=false "
CREATE OR REPLACE TABLE \`${PROJECT_ID}.${DATASET_NAME}.vitals\` (
  record_id STRING NOT NULL,
    patient_id STRING NOT NULL,
    vital_type STRING,
  value FLOAT64,
    unit STRING,
  systolic INT64,
  diastolic INT64,
  measured_at TIMESTAMP NOT NULL
);"

bq query --use_legacy_sql=false "
CREATE OR REPLACE TABLE \`${PROJECT_ID}.${DATASET_NAME}.medications\` (
    medication_id STRING NOT NULL,
    patient_id STRING NOT NULL,
  name STRING NOT NULL,
    dosage STRING,
    frequency STRING,
  route STRING,
  reason STRING,
  start_date TIMESTAMP,
  end_date TIMESTAMP
);"

bq query --use_legacy_sql=false "
CREATE OR REPLACE TABLE \`${PROJECT_ID}.${DATASET_NAME}.medication_logs\` (
  log_id STRING NOT NULL,
  patient_id STRING NOT NULL,
  medication_id STRING NOT NULL,
  scheduled_time TIMESTAMP NOT NULL,
  actual_time TIMESTAMP,
  taken BOOL,
  notes STRING
);"

bq query --use_legacy_sql=false "
CREATE OR REPLACE TABLE \`${PROJECT_ID}.${DATASET_NAME}.alerts\` (
    alert_id STRING NOT NULL,
    patient_id STRING NOT NULL,
    alert_type STRING,
    severity STRING,
  title STRING,
  description STRING,
    created_at TIMESTAMP,
  acknowledged BOOL
);"

bq query --use_legacy_sql=false "
CREATE OR REPLACE TABLE \`${PROJECT_ID}.${DATASET_NAME}.appointments\` (
  appointment_id STRING NOT NULL,
  patient_id STRING NOT NULL,
  provider_id STRING NOT NULL,
  provider_name STRING,
  appointment_type STRING,
  scheduled_at TIMESTAMP NOT NULL,
  location STRING,
  notes STRING
);"

echo "[3/4] Loading seed CSVs if present..."

load_csv() {
  local table_name="$1"
  local file_path="$2"

  if [ -f "$file_path" ]; then
    echo "Loading $file_path -> ${PROJECT_ID}:${DATASET_NAME}.${table_name}"
    bq load \
      --source_format=CSV \
      --skip_leading_rows=1 \
      --null_marker="null" \
      --autodetect \
      "${PROJECT_ID}:${DATASET_NAME}.${table_name}" \
      "$file_path"
  else
    echo "Skipping $table_name. File not found: $file_path"
  fi
}

load_csv "patients" "${SEED_DIR}/patients.csv"
load_csv "vitals" "${SEED_DIR}/vitals.csv"
load_csv "medications" "${SEED_DIR}/medications.csv"
load_csv "alerts" "${SEED_DIR}/alerts.csv"
load_csv "appointments" "${SEED_DIR}/appointments.csv"
load_csv "medication_logs" "${SEED_DIR}/medication_logs.csv"

echo "[4/4] Final tables:"
bq ls "${PROJECT_ID}:${DATASET_NAME}"

echo "------------------------------------------------------------"
echo "BigQuery setup complete."
echo "------------------------------------------------------------"