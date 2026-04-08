param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectId,

    [string]$Dataset = "careorchestra",

    [string]$Location = "US",

    [switch]$LoadSeed
)

$ErrorActionPreference = "Stop"

function Run-BqQuery {
    param([string]$Sql)

    bq query --project_id=$ProjectId --use_legacy_sql=false $Sql | Out-Null
}

Write-Host "------------------------------------------------------------"
Write-Host "CareOrchestra BigQuery Setup (PowerShell)"
Write-Host "Project:  $ProjectId"
Write-Host "Dataset:  $Dataset"
Write-Host "Location: $Location"
Write-Host "------------------------------------------------------------"

# 1) Dataset
$datasetRef = "$ProjectId`:$Dataset"
$datasetExists = $true
try {
    bq show --dataset $datasetRef | Out-Null
} catch {
    $datasetExists = $false
}

if (-not $datasetExists) {
    Write-Host "Creating dataset $datasetRef ..."
    bq mk --dataset --location=$Location $datasetRef | Out-Null
} else {
    Write-Host "Dataset already exists."
}

# 2) Tables required by active agent code
Write-Host "Creating/updating tables..."

Run-BqQuery "
CREATE TABLE IF NOT EXISTS `$ProjectId.$Dataset.patients`
(
  patient_id STRING NOT NULL,
  first_name STRING,
  last_name STRING,
  chronic_conditions STRING,
  date_of_birth DATE,
  updated_at TIMESTAMP,
  created_at TIMESTAMP
)
"

Run-BqQuery "
CREATE TABLE IF NOT EXISTS `$ProjectId.$Dataset.vitals`
(
  patient_id STRING NOT NULL,
  vital_type STRING NOT NULL,
  value FLOAT64,
  unit STRING,
  measured_at TIMESTAMP NOT NULL,
  created_at TIMESTAMP
)
"

Run-BqQuery "
CREATE TABLE IF NOT EXISTS `$ProjectId.$Dataset.medications`
(
  medication_id STRING NOT NULL,
  patient_id STRING NOT NULL,
  medication_name STRING,
  dosage STRING,
  frequency STRING,
  start_date TIMESTAMP,
  end_date TIMESTAMP,
  created_at TIMESTAMP
)
"

Run-BqQuery "
CREATE TABLE IF NOT EXISTS `$ProjectId.$Dataset.medication_logs`
(
  patient_id STRING NOT NULL,
  medication_id STRING,
  medication_name STRING,
  scheduled_time TIMESTAMP,
  actual_time TIMESTAMP,
  taken BOOL,
  raw_response STRING,
  follow_up_message STRING,
  reminder_sent BOOL,
  created_at TIMESTAMP
)
"

Run-BqQuery "
CREATE TABLE IF NOT EXISTS `$ProjectId.$Dataset.alerts`
(
  patient_id STRING NOT NULL,
  alert_type STRING,
  severity STRING,
  title STRING,
  description STRING,
  acknowledged BOOL,
  created_at TIMESTAMP
)
"

Run-BqQuery "
CREATE TABLE IF NOT EXISTS `$ProjectId.$Dataset.escalation_contacts`
(
  patient_id STRING NOT NULL,
  contact_email STRING NOT NULL,
  priority INT64
)
"

Run-BqQuery "
CREATE TABLE IF NOT EXISTS `$ProjectId.$Dataset.escalation_logs`
(
  patient_id STRING NOT NULL,
  risk_level STRING,
  alert_content STRING,
  contacts_notified STRING,
  created_at TIMESTAMP
)
"

# Optional app-related table
Run-BqQuery "
CREATE TABLE IF NOT EXISTS `$ProjectId.$Dataset.appointments`
(
  appointment_id STRING,
  patient_id STRING,
  provider_id STRING,
  provider_name STRING,
  appointment_type STRING,
  scheduled_at TIMESTAMP,
  location STRING,
  notes STRING,
  created_at TIMESTAMP,
  cancelled BOOL,
  completed BOOL
)
"

# 3) Optional seed loading
if ($LoadSeed) {
    Write-Host "Loading seed CSV files from data/seed ..."

    $seedRoot = Join-Path $PSScriptRoot "..\..\data\seed"
    $seedRoot = [System.IO.Path]::GetFullPath($seedRoot)

    function Load-CsvIfPresent {
        param(
            [string]$TableName,
            [string]$FileName,
            [string]$Schema = ""
        )

        $file = Join-Path $seedRoot $FileName
        if (-not (Test-Path $file)) {
            Write-Host "Skipping $TableName ($FileName not found)"
            return
        }

        Write-Host "Loading $TableName from $FileName ..."
        if ($Schema -ne "") {
            bq load --project_id=$ProjectId --replace --source_format=CSV --skip_leading_rows=1 --schema=$Schema "$ProjectId`:$Dataset.$TableName" $file | Out-Null
        } else {
            bq load --project_id=$ProjectId --replace --source_format=CSV --skip_leading_rows=1 --autodetect "$ProjectId`:$Dataset.$TableName" $file | Out-Null
        }
    }

    Load-CsvIfPresent -TableName "patients" -FileName "patients.csv" -Schema "patient_id:STRING,first_name:STRING,last_name:STRING,date_of_birth:DATE,phone:STRING,email:STRING,chronic_conditions:STRING,created_at:TIMESTAMP"
    Load-CsvIfPresent -TableName "vitals" -FileName "vitals.csv"
    Load-CsvIfPresent -TableName "medications" -FileName "medications.csv"
    Load-CsvIfPresent -TableName "medication_logs" -FileName "medication_logs.csv"
    Load-CsvIfPresent -TableName "alerts" -FileName "alerts.csv"
    Load-CsvIfPresent -TableName "appointments" -FileName "appointments.csv"
}

Write-Host "Final tables:"
bq ls $datasetRef

Write-Host "------------------------------------------------------------"
Write-Host "BigQuery setup complete."
Write-Host "------------------------------------------------------------"
