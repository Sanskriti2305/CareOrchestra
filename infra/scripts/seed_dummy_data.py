import argparse
import datetime as dt
import os
import random
from dotenv import load_dotenv
from google.cloud import bigquery


FIRST_NAMES = ["Ava", "Noah", "Mia", "Ethan", "Liam", "Sophia", "Mason", "Emma"]
LAST_NAMES = ["Carter", "Reed", "Patel", "Nguyen", "Brooks", "Diaz", "Shah", "Turner"]
CONDITIONS = [
    "hypertension",
    "type2_diabetes",
    "heart_disease",
    "asthma",
]
MEDICATION_POOL = [
    ("Lisinopril", "10mg", "once daily"),
    ("Metformin", "500mg", "twice daily"),
    ("Atorvastatin", "20mg", "once daily"),
    ("Amlodipine", "5mg", "once daily"),
]


def insert_rows(client: bigquery.Client, table_ref: str, rows: list[dict]) -> None:
    if not rows:
        return
    errors = client.insert_rows_json(table_ref, rows)
    if errors:
        raise RuntimeError(f"Insert errors for {table_ref}: {errors}")


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Seed dummy data for CareOrchestra BigQuery tables")
    parser.add_argument("--project-id", default=os.getenv("GCP_PROJECT_ID"), help="GCP project ID")
    parser.add_argument("--dataset", default=os.getenv("BIGQUERY_DATASET", "careorchestra"), help="BigQuery dataset")
    parser.add_argument("--count", type=int, default=5, help="Number of patients to create")
    parser.add_argument("--prefix", default="PT9", help="Patient ID prefix")
    args = parser.parse_args()

    if not args.project_id:
        raise SystemExit("Missing --project-id and GCP_PROJECT_ID is not set")

    client = bigquery.Client(project=args.project_id)
    now = dt.datetime.utcnow().replace(microsecond=0)

    patient_rows: list[dict] = []
    vitals_rows: list[dict] = []
    medication_rows: list[dict] = []
    medication_log_rows: list[dict] = []
    escalation_rows: list[dict] = []

    created_ids: list[str] = []

    for i in range(args.count):
        pid = f"{args.prefix}{100 + i}"
        created_ids.append(pid)

        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        condition = random.choice(CONDITIONS)
        dob = dt.date(1958 + random.randint(0, 30), random.randint(1, 12), random.randint(1, 28))

        patient_rows.append(
            {
                "patient_id": pid,
                "first_name": first,
                "last_name": last,
                "chronic_conditions": condition,
                "date_of_birth": dob.isoformat(),
                "updated_at": now.isoformat() + "Z",
                "created_at": now.isoformat() + "Z",
            }
        )

        # Vitals expected by agents
        vitals_rows.extend(
            [
                {
                    "patient_id": pid,
                    "vital_type": "bp_systolic",
                    "value": float(random.randint(118, 168)),
                    "unit": "mmHg",
                    "measured_at": (now - dt.timedelta(hours=2)).isoformat() + "Z",
                    "created_at": now.isoformat() + "Z",
                },
                {
                    "patient_id": pid,
                    "vital_type": "bp_diastolic",
                    "value": float(random.randint(72, 104)),
                    "unit": "mmHg",
                    "measured_at": (now - dt.timedelta(hours=2)).isoformat() + "Z",
                    "created_at": now.isoformat() + "Z",
                },
                {
                    "patient_id": pid,
                    "vital_type": "heart_rate",
                    "value": float(random.randint(62, 118)),
                    "unit": "bpm",
                    "measured_at": (now - dt.timedelta(hours=1)).isoformat() + "Z",
                    "created_at": now.isoformat() + "Z",
                },
                {
                    "patient_id": pid,
                    "vital_type": "glucose",
                    "value": float(random.randint(86, 238)),
                    "unit": "mg/dL",
                    "measured_at": (now - dt.timedelta(hours=1)).isoformat() + "Z",
                    "created_at": now.isoformat() + "Z",
                },
                {
                    "patient_id": pid,
                    "vital_type": "spo2",
                    "value": float(random.randint(89, 99)),
                    "unit": "%",
                    "measured_at": (now - dt.timedelta(minutes=45)).isoformat() + "Z",
                    "created_at": now.isoformat() + "Z",
                },
            ]
        )

        med_name, dosage, freq = random.choice(MEDICATION_POOL)
        med_id = f"MED-{pid}"
        medication_rows.append(
            {
                "medication_id": med_id,
                "patient_id": pid,
                "medication_name": med_name,
                "dosage": dosage,
                "frequency": freq,
                "start_date": (now - dt.timedelta(days=30)).isoformat() + "Z",
                "end_date": None,
                "created_at": now.isoformat() + "Z",
            }
        )

        medication_log_rows.append(
            {
                "patient_id": pid,
                "medication_id": med_id,
                "medication_name": med_name,
                "scheduled_time": (now - dt.timedelta(hours=8)).isoformat() + "Z",
                "actual_time": (now - dt.timedelta(hours=8, minutes=15)).isoformat() + "Z",
                "taken": random.choice([True, True, True, False]),
                "raw_response": "yes",
                "follow_up_message": "Keep taking your medicines on time.",
                "reminder_sent": True,
                "created_at": now.isoformat() + "Z",
            }
        )

        escalation_rows.append(
            {
                "patient_id": pid,
                "contact_email": "doctor1@clinic.com",
                "priority": 1,
            }
        )

    base = f"{args.project_id}.{args.dataset}"
    insert_rows(client, f"{base}.patients", patient_rows)
    insert_rows(client, f"{base}.vitals", vitals_rows)
    insert_rows(client, f"{base}.medications", medication_rows)
    insert_rows(client, f"{base}.medication_logs", medication_log_rows)
    insert_rows(client, f"{base}.escalation_contacts", escalation_rows)

    print("Seed complete")
    print("PATIENT_IDS=" + ",".join(created_ids))


if __name__ == "__main__":
    main()
