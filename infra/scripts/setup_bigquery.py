import argparse
import os
from google.cloud import bigquery
from dotenv import load_dotenv


def ensure_dataset(client: bigquery.Client, project_id: str, dataset_id: str, location: str) -> None:
    dataset_ref = f"{project_id}.{dataset_id}"
    dataset = bigquery.Dataset(dataset_ref)
    dataset.location = location
    client.create_dataset(dataset, exists_ok=True)


def ensure_table(client: bigquery.Client, project_id: str, dataset_id: str, table_name: str, schema: list[bigquery.SchemaField]) -> None:
    table_ref = f"{project_id}.{dataset_id}.{table_name}"
    table = bigquery.Table(table_ref, schema=schema)
    client.create_table(table, exists_ok=True)


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Set up BigQuery dataset/tables for CareOrchestra")
    parser.add_argument("--project-id", default=os.getenv("GCP_PROJECT_ID"), help="GCP project ID")
    parser.add_argument("--dataset", default="careorchestra", help="BigQuery dataset name")
    parser.add_argument("--location", default=os.getenv("GCP_LOCATION", "US"), help="BigQuery dataset location")
    args = parser.parse_args()

    if not args.project_id:
        raise SystemExit("Missing --project-id and GCP_PROJECT_ID is not set")

    client = bigquery.Client(project=args.project_id)

    ensure_dataset(client, args.project_id, args.dataset, args.location)

    ensure_table(
        client,
        args.project_id,
        args.dataset,
        "patients",
        [
            bigquery.SchemaField("patient_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("first_name", "STRING"),
            bigquery.SchemaField("last_name", "STRING"),
            bigquery.SchemaField("chronic_conditions", "STRING"),
            bigquery.SchemaField("date_of_birth", "DATE"),
            bigquery.SchemaField("updated_at", "TIMESTAMP"),
            bigquery.SchemaField("created_at", "TIMESTAMP"),
        ],
    )

    ensure_table(
        client,
        args.project_id,
        args.dataset,
        "vitals",
        [
            bigquery.SchemaField("patient_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("vital_type", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("value", "FLOAT"),
            bigquery.SchemaField("unit", "STRING"),
            bigquery.SchemaField("measured_at", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("created_at", "TIMESTAMP"),
        ],
    )

    ensure_table(
        client,
        args.project_id,
        args.dataset,
        "medications",
        [
            bigquery.SchemaField("medication_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("patient_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("medication_name", "STRING"),
            bigquery.SchemaField("dosage", "STRING"),
            bigquery.SchemaField("frequency", "STRING"),
            bigquery.SchemaField("start_date", "TIMESTAMP"),
            bigquery.SchemaField("end_date", "TIMESTAMP"),
            bigquery.SchemaField("created_at", "TIMESTAMP"),
        ],
    )

    ensure_table(
        client,
        args.project_id,
        args.dataset,
        "medication_logs",
        [
            bigquery.SchemaField("patient_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("medication_id", "STRING"),
            bigquery.SchemaField("medication_name", "STRING"),
            bigquery.SchemaField("scheduled_time", "TIMESTAMP"),
            bigquery.SchemaField("actual_time", "TIMESTAMP"),
            bigquery.SchemaField("taken", "BOOL"),
            bigquery.SchemaField("raw_response", "STRING"),
            bigquery.SchemaField("follow_up_message", "STRING"),
            bigquery.SchemaField("reminder_sent", "BOOL"),
            bigquery.SchemaField("created_at", "TIMESTAMP"),
        ],
    )

    ensure_table(
        client,
        args.project_id,
        args.dataset,
        "alerts",
        [
            bigquery.SchemaField("patient_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("alert_type", "STRING"),
            bigquery.SchemaField("severity", "STRING"),
            bigquery.SchemaField("title", "STRING"),
            bigquery.SchemaField("description", "STRING"),
            bigquery.SchemaField("acknowledged", "BOOL"),
            bigquery.SchemaField("created_at", "TIMESTAMP"),
        ],
    )

    ensure_table(
        client,
        args.project_id,
        args.dataset,
        "escalation_contacts",
        [
            bigquery.SchemaField("patient_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("contact_email", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("priority", "INT64"),
        ],
    )

    ensure_table(
        client,
        args.project_id,
        args.dataset,
        "escalation_logs",
        [
            bigquery.SchemaField("patient_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("risk_level", "STRING"),
            bigquery.SchemaField("alert_content", "STRING"),
            bigquery.SchemaField("contacts_notified", "STRING"),
            bigquery.SchemaField("created_at", "TIMESTAMP"),
        ],
    )

    ensure_table(
        client,
        args.project_id,
        args.dataset,
        "appointments",
        [
            bigquery.SchemaField("appointment_id", "STRING"),
            bigquery.SchemaField("patient_id", "STRING"),
            bigquery.SchemaField("provider_id", "STRING"),
            bigquery.SchemaField("provider_name", "STRING"),
            bigquery.SchemaField("appointment_type", "STRING"),
            bigquery.SchemaField("scheduled_at", "TIMESTAMP"),
            bigquery.SchemaField("location", "STRING"),
            bigquery.SchemaField("notes", "STRING"),
            bigquery.SchemaField("created_at", "TIMESTAMP"),
            bigquery.SchemaField("cancelled", "BOOL"),
            bigquery.SchemaField("completed", "BOOL"),
        ],
    )

    print(f"BigQuery setup complete: {args.project_id}.{args.dataset}")


if __name__ == "__main__":
    main()
