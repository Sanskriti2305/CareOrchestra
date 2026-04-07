# Infrastructure & Deployment Scripts

This folder contains scripts for infrastructure setup, BigQuery initialization, MCP toolbox setup, and deployment.

---

## Scripts

### setup.sh

Sets up development environment:

* Creates Python virtual environment
* Installs dependencies from requirements.txt
* Creates .env from .env.example

**Usage**:

```bash
bash infra/scripts/setup.sh
```

---

### setup_bigquery.sh

Sets up BigQuery for CareOrchestra:

* Creates dataset (`careorchestra`)
* Creates all required tables (patients, vitals, medications, alerts, etc.)
* Loads seed data from `data/seed/*.csv`

**Usage**:

```bash
chmod +x infra/scripts/setup_bigquery.sh
./infra/scripts/setup_bigquery.sh <PROJECT_ID>
```

**Example**:

```bash
./infra/scripts/setup_bigquery.sh cohort1-hackathon-492410
```

---

### setup_toolbox.sh

Sets up MCP Toolbox for BigQuery integration:

* Downloads MCP Toolbox binary
* Creates `tools.yaml` configuration
* Connects MCP to BigQuery dataset

**Usage**:

```bash
chmod +x infra/scripts/setup_toolbox.sh
./infra/scripts/setup_toolbox.sh
```

---

### Running MCP Toolbox

After setup, start MCP server:

```bash
cd mcp/toolbox
./toolbox --tools-file="tools.yaml"
```

Verify:

* `/api/toolset` → tools visible
* `/ui` → run queries against BigQuery

---

### load_seed_data.py (optional)

Loads mock patient data into BigQuery:

* Patients
* Vitals
* Medications
* Alerts

**Usage**:

```bash
python infra/scripts/load_seed_data.py
```

---

### deploy.sh

Deploys CareOrchestra to Google Cloud Run:

* Builds Docker image
* Pushes to Container Registry
* Deploys service with environment variables

**Usage**:

```bash
bash infra/scripts/deploy.sh --project-id YOUR_PROJECT_ID
```

---

## Recommended Setup Flow

```bash
# 1. Clone repo
git clone <repo-url>
cd CareOrchestra

# 2. Set project
gcloud config set project <PROJECT_ID>

# 3. Setup BigQuery
./infra/scripts/setup_bigquery.sh <PROJECT_ID>

# 4. Setup MCP Toolbox
./infra/scripts/setup_toolbox.sh

# 5. Start MCP
cd mcp/toolbox
./toolbox --tools-file="tools.yaml"
```

---

## Mock Event Data

Located in:

```
data/mock_payloads/
```

Used for:

* Simulating real-time events
* Testing Monitoring Agent
* Driving multi-agent workflows

Examples:

* High blood pressure event
* Missed medication
* Upcoming appointment

---

## Implementation Notes

These scripts provide a working baseline for:

* BigQuery as structured data layer
* MCP Toolbox as access layer
* ADK agents as orchestration layer

Future improvements:

* Strong schema validation
* Partitioned BigQuery tables
* CI/CD automation
* Secure secret management
* Observability and logging

---

See [README.md](../../README.md) for the project overview and [data/README.md](../../data/README.md) for the demo scenarios and dataset details.
