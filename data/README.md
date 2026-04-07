# CareOrchestra Demo Data

This directory contains the seed data and mock event payloads used to demonstrate the first CareOrchestra backend workflows.

## Directory Layout

- `seed/`: baseline patient, vitals, medications, medication logs, alerts, and appointments
- `mock_payloads/`: event triggers used to drive demo scenarios

## Demo Strategy

The first implementation should focus on patients `PT001` and `PT003` because they have the richest supporting context across vitals, medication history, adherence logs, and alerts.

- `PT001` is the best patient for vitals-driven and trend-driven workflows.
- `PT003` is the best patient for medication-risk and escalation workflows.
- `PT002` is still useful for a lower-risk care coordination scenario around appointments.

## Scenario 1: High Blood Pressure Escalation

- Payload: [mock_payloads/high_bp_event.json](mock_payloads/high_bp_event.json)
- Primary patient: `PT001`
- Core story: a new blood pressure reading arrives and confirms an already worsening hypertension trend.

Supporting seed data:

- [seed/patients.csv](seed/patients.csv): `PT001` has `hypertension,type2_diabetes`
- [seed/vitals.csv](seed/vitals.csv): `PT001` blood pressure climbs from `140/88` to `168/108`, then `165/100`
- [seed/medications.csv](seed/medications.csv): `PT001` is on `Lisinopril` and `Metformin`
- [seed/medication_logs.csv](seed/medication_logs.csv): `PT001` has missed and late doses
- [seed/alerts.csv](seed/alerts.csv): `PT001` already has hypertension-related alerts

Recommended agent behavior:

1. Monitoring agent detects `vitals_submitted`
2. Vitals agent pulls recent blood pressure history
3. Medication agent checks antihypertensive and diabetes adherence
4. Analysis agent classifies the combined risk
5. Escalation or reporting agent prepares clinician-facing output

Recommended BigQuery or MCP reads:

- patient profile
- recent vitals for `PT001`
- active medications for `PT001`
- medication logs for `PT001`
- recent alerts for `PT001`

## Scenario 2: Missed Insulin Dose

- Payload: [mock_payloads/missed_medication.json](mock_payloads/missed_medication.json)
- Primary patient: `PT003`
- Core story: a scheduled insulin dose is missed and the system detects both acute medication risk and a broader adherence pattern.

Supporting seed data:

- [seed/patients.csv](seed/patients.csv): `PT003` has `type1_diabetes,hypertension`
- [seed/medications.csv](seed/medications.csv): `PT003` is prescribed `Insulin Glargine`
- [seed/medication_logs.csv](seed/medication_logs.csv): `PT003` misses multiple insulin doses
- [seed/vitals.csv](seed/vitals.csv): `PT003` glucose is persistently high and rising
- [seed/alerts.csv](seed/alerts.csv): `PT003` already has medication-missed alerts

Recommended agent behavior:

1. Monitoring agent detects `medication_check`
2. Medication agent confirms the dose was missed within the grace period
3. Vitals agent reviews recent glucose values
4. Analysis agent raises the risk due to critical medication plus poor trend
5. Escalation agent recommends urgent action or provider notification

Recommended BigQuery or MCP reads:

- patient profile
- active medications for `PT003`
- medication logs for `PT003`
- recent glucose vitals for `PT003`
- recent alerts for `PT003`

## Scenario 3: Upcoming Follow-Up Appointment

- Payload: [mock_payloads/followup_needed.json](mock_payloads/followup_needed.json)
- Primary patient: `PT002`
- Core story: the system prepares a patient and provider for a follow-up visit rather than reacting to an urgent event.

Supporting seed data:

- [seed/appointments.csv](seed/appointments.csv): `PT002` has `APT001` scheduled
- [seed/vitals.csv](seed/vitals.csv): `PT002` has relatively stable blood pressure and heart rate
- [seed/medications.csv](seed/medications.csv): `PT002` is on cardiac medications
- [seed/medication_logs.csv](seed/medication_logs.csv): `PT002` has clean recent adherence
- [seed/alerts.csv](seed/alerts.csv): `PT002` has an appointment reminder alert

Recommended agent behavior:

1. Monitoring agent detects `appointment_upcoming`
2. Scheduler or reporting flow fetches appointment context
3. Vitals agent summarizes recent stability
4. Medication agent checks adherence status
5. Reporting agent prepares a pre-visit summary

Recommended BigQuery or MCP reads:

- patient profile
- upcoming appointments for `PT002`
- recent vitals for `PT002`
- active medications for `PT002`
- recent alerts for `PT002`

## Scenario 4: Blood Pressure Trend Warning

- Payload: [mock_payloads/trend_warning.json](mock_payloads/trend_warning.json)
- Primary patient: `PT001`
- Core story: the system runs a scheduled trend scan and detects deterioration before a new crisis event needs to be submitted manually.

Supporting seed data:

- [seed/vitals.csv](seed/vitals.csv): `PT001` has a sustained blood pressure rise over multiple readings
- [seed/alerts.csv](seed/alerts.csv): `PT001` already has a prior trend-related warning
- [seed/medications.csv](seed/medications.csv): `PT001` remains on blood pressure treatment
- [seed/medication_logs.csv](seed/medication_logs.csv): adherence gaps help explain the worsening pattern

Recommended agent behavior:

1. Monitoring agent triggers a scheduled `trend_check`
2. Vitals agent evaluates the last 30 days of blood pressure readings
3. Medication agent checks whether non-adherence may be contributing
4. Analysis agent determines whether this is moderate, high, or escalating risk
5. Reporting or escalation agent prepares the recommended next step

Recommended BigQuery or MCP reads:

- recent blood pressure time series for `PT001`
- active medications for `PT001`
- medication logs for `PT001`
- recent alerts for `PT001`

## First Implementation Focus

For the first implementation pass, prioritize these two vertical slices:

1. `PT001` for vitals escalation and trend detection
2. `PT003` for medication adherence and escalation

That gives the strongest demo coverage with the least amount of extra backend work, because those two patients already show clear deterioration patterns in the seed data.

## Practical Next Step

Once the query layer is wired to BigQuery, each scenario should be testable by loading one payload from `mock_payloads/` and confirming that the agents pull the expected context from the seed-backed tables.
