#!/bin/bash
set -e

VERSION="${1:-0.23.0}"

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
TOOLBOX_DIR="$ROOT_DIR/mcp/toolbox"

mkdir -p "$TOOLBOX_DIR"
cd "$TOOLBOX_DIR"

echo "------------------------------------------------------------"
echo "CareOrchestra MCP Toolbox Setup"
echo "Version: $VERSION"
echo "Target:  $TOOLBOX_DIR"
echo "------------------------------------------------------------"

if [ -f "toolbox" ]; then
  echo "Toolbox binary already exists. Skipping download."
else
  echo "Downloading toolbox..."
  curl -O "https://storage.googleapis.com/genai-toolbox/v$VERSION/linux/amd64/toolbox"
  chmod +x toolbox
  echo "Toolbox downloaded."
fi

if [ -f "tools.yaml" ]; then
  echo "tools.yaml already exists."
else
  echo "Creating starter tools.yaml..."
  cat <<EOF > tools.yaml
sources:
  care_bq:
    kind: bigquery
    project: $(gcloud config get-value project 2>/dev/null)

tools:
  get_patients:
    kind: bigquery-sql
    source: care_bq
    statement: |
      SELECT patient_id, first_name, last_name, risk_level, status
      FROM \`$(gcloud config get-value project 2>/dev/null).careorchestra.patients\`
      LIMIT 20
    description: |
      Fetch patient basic details.

  get_recent_vitals:
    kind: bigquery-sql
    source: care_bq
    statement: |
      SELECT patient_id, vital_type, value, unit, recorded_at, abnormal_flag
      FROM \`$(gcloud config get-value project 2>/dev/null).careorchestra.vitals\`
      ORDER BY recorded_at DESC
      LIMIT 50
    description: |
      Fetch recent vitals.

  get_medications:
    kind: bigquery-sql
    source: care_bq
    statement: |
      SELECT patient_id, medicine_name, dosage, frequency, adherence_status
      FROM \`$(gcloud config get-value project 2>/dev/null).careorchestra.medications\`
      LIMIT 50
    description: |
      Fetch medication records.

  get_open_alerts:
    kind: bigquery-sql
    source: care_bq
    statement: |
      SELECT alert_id, patient_id, alert_type, severity, alert_message, status, created_at
      FROM \`$(gcloud config get-value project 2>/dev/null).careorchestra.alerts\`
      WHERE status = 'open'
      ORDER BY created_at DESC
      LIMIT 50
    description: |
      Fetch open alerts.

toolsets:
  care_toolset:
    - get_patients
    - get_recent_vitals
    - get_medications
    - get_open_alerts
EOF
  echo "Created tools.yaml"
fi

echo "------------------------------------------------------------"
echo "Toolbox setup complete."
echo "Next steps:"
echo "cd $TOOLBOX_DIR"
echo "./toolbox --tools-file=\"tools.yaml\""
echo "------------------------------------------------------------"