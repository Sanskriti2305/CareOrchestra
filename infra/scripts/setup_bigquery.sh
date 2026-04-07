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

# ------------------------------------------------------------
# [1/4] Create dataset
# ------------------------------------------------------------
echo "[1/4] Checking dataset..."
if bq show --dataset "${PROJECT_ID}:${DATASET_NAME}" >/dev/null 2>&1; then
  echo "Dataset already exists."
else
  echo "Creating dataset..."
  bq mk --dataset --location="$LOCATION" "${PROJECT_ID}:${DATASET_NAME}"
fi

# ------------------------------------------------------------
# [2/4] Create tables
# ------------------------------------------------------------
echo "[2/4] Creating tables..."

# Patients (ONLY fields present in CSV)
bq query --use_legacy_sql=false "
CREATE OR REPLACE TABLE \`${PROJECT_ID}.${DATASET_NAME}.patients\` (
    patient_id STRING NOT NULL,
    first_name STRING NOT NULL,
    last_name STRING NOT NULL,
    date_of_birth DATE,
    phone STRING,
    email STRING,
    chronic_conditions STRING,
    created_at TIMESTAMP
);"

bq query --use_legacy_sql=false "
CREATE OR REPLACE TABLE \`${PROJECT_ID}.${DATASET_NAME}.vitals\` (
    vital_id STRING NOT NULL,
    patient_id STRING NOT NULL,
    vital_type STRING,
    value STRING,
    unit STRING,
    recorded_at TIMESTAMP NOT NULL,
    source STRING,
    abnormal_flag BOOL,
    created_at TIMESTAMP
);"

bq query --use_legacy_sql=false "
CREATE OR REPLACE TABLE \`${PROJECT_ID}.${DATASET_NAME}.medications\` (
    medication_id STRING NOT NULL,
    patient_id STRING NOT NULL,
    medicine_name STRING NOT NULL,
    dosage STRING,
    frequency STRING,
    start_date DATE,
    end_date DATE,
    prescribed_by STRING,
    adherence_status STRING,
    created_at TIMESTAMP
);"

bq query --use_legacy_sql=false "
CREATE OR REPLACE TABLE \`${PROJECT_ID}.${DATASET_NAME}.alerts\` (
    alert_id STRING NOT NULL,
    patient_id STRING NOT NULL,
    alert_type STRING,
    severity STRING,
    alert_message STRING,
    triggered_by_agent STRING,
    status STRING,
    created_at TIMESTAMP,
    resolved_at TIMESTAMP
);"

bq query --use_legacy_sql=false "
CREATE OR REPLACE TABLE \`${PROJECT_ID}.${DATASET_NAME}.doctors\` (
    doctor_id STRING NOT NULL,
    first_name STRING NOT NULL,
    last_name STRING NOT NULL,
    specialty STRING,
    hospital_name STRING,
    phone STRING,
    email STRING,
    department STRING,
    availability_status STRING,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);"

bq query --use_legacy_sql=false "
CREATE OR REPLACE TABLE \`${PROJECT_ID}.${DATASET_NAME}.nurses\` (
    nurse_id STRING NOT NULL,
    first_name STRING NOT NULL,
    last_name STRING NOT NULL,
    hospital_name STRING,
    phone STRING,
    email STRING,
    shift_start TIME,
    shift_end TIME,
    availability_status STRING,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);"

bq query --use_legacy_sql=false "
CREATE OR REPLACE TABLE \`${PROJECT_ID}.${DATASET_NAME}.family_members\` (
    family_member_id STRING NOT NULL,
    first_name STRING NOT NULL,
    last_name STRING NOT NULL,
    relationship_to_patient STRING,
    phone STRING,
    email STRING,
    address_line1 STRING,
    city STRING,
    state STRING,
    zip_code STRING,
    preferred_contact_method STRING,
    is_primary_contact BOOL,
    can_receive_alerts BOOL,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);"

# ------------------------------------------------------------
# [3/4] Load seed data
# ------------------------------------------------------------
echo "[3/4] Loading seed CSVs..."

# 🔥 Explicit patients load (NO AUTODETECT EVER)
echo "Loading patients..."

if [ -f "${SEED_DIR}/patients.csv" ]; then
  bq load \
    --replace \
    --source_format=CSV \
    --skip_leading_rows=1 \
    --schema=patient_id:STRING,first_name:STRING,last_name:STRING,date_of_birth:DATE,phone:STRING,email:STRING,chronic_conditions:STRING,created_at:TIMESTAMP \
    "${PROJECT_ID}:${DATASET_NAME}.patients" \
    "${SEED_DIR}/patients.csv"
else
  echo "Skipping patients (file not found)"
fi

# Generic loader for other tables
load_csv() {
  local table_name="$1"
  local file_path="$2"

  if [ -f "$file_path" ]; then
    echo "Loading $table_name..."
    bq load \
      --replace \
      --source_format=CSV \
      --skip_leading_rows=1 \
      --autodetect \
      "${PROJECT_ID}:${DATASET_NAME}.${table_name}" \
      "$file_path"
  else
    echo "Skipping $table_name (file not found)"
  fi
}

load_csv "vitals" "${SEED_DIR}/vitals.csv"
load_csv "medications" "${SEED_DIR}/medications.csv"
load_csv "alerts" "${SEED_DIR}/alerts.csv"
load_csv "appointments" "${SEED_DIR}/appointments.csv"
load_csv "medication_logs" "${SEED_DIR}/medication_logs.csv"

# ------------------------------------------------------------
# [4/4] Verify
# ------------------------------------------------------------
echo "[4/4] Final tables:"
bq ls "${PROJECT_ID}:${DATASET_NAME}"

echo "------------------------------------------------------------"
echo "BigQuery setup complete ✅"
echo "------------------------------------------------------------"