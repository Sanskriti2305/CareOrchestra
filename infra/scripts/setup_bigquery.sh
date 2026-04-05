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
    gender STRING,
    phone STRING,
    email STRING,
    address_line1 STRING,
    address_line2 STRING,
    city STRING,
    state STRING,
    zip_code STRING,
    emergency_contact_name STRING,
    emergency_contact_phone STRING,
    blood_group STRING,
    primary_language STRING,
    chronic_conditions STRING,
    allergies STRING,
    medication_summary STRING,
    risk_level STRING,
    status STRING,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
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

echo "[3/4] Loading seed CSVs if present..."

load_csv() {
  local table_name="$1"
  local file_path="$2"

  if [ -f "$file_path" ]; then
    echo "Loading $file_path -> ${PROJECT_ID}:${DATASET_NAME}.${table_name}"
    bq load \
      --source_format=CSV \
      --skip_leading_rows=1 \
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