# CareOrchestra

**A multi-agent AI system for chronic care coordination using Google ADK**

## Problem Statement

Patients with chronic conditions face critical gaps in care:
- **Missed follow-ups** due to busy schedules and poor reminders
- **Medication non-adherence** leading to worsening health outcomes
- **Undetected vital trends** that could signal serious problems before they become critical
- **Delayed escalation** to doctors when patients need immediate attention

CareOrchestra addresses these gaps using a coordinated team of AI agents that:
- Monitor patient vitals and detect abnormal patterns
- Track medication adherence and send timely reminders
- Synthesize multiple data sources for comprehensive risk assessment
- Escalate critical situations to doctors in real-time
- Generate clinical summaries for providers

## Solution Overview

CareOrchestra uses **Google's Agent Development Kit (ADK)** to orchestrate multiple specialized AI agents working together like a care team:

```
Patient Data & Events
         ↓
    Coordinator Agent (orchestrator)
    ├→ Monitoring Agent (detects events)
    ├→ Vitals Agent (analyzes vital signs)
    ├→ Medication Agent (tracks adherence)
    ├→ Analysis Agent (synthesizes findings)
    ├→ Escalation Agent (alerts doctors)
    └→ Reporting Agent (creates summaries)
         ↓
    Actionable Insights & Alerts
```

## Key Features

- **7 Specialized Agents** - Each focused on specific care coordination tasks
- **Real-Time Monitoring** - Detects abnormal vitals and medication adherence issues
- **Risk Stratification** - Synthesizes data to assess patient risk levels
- **Automated Escalation** - Routes high-risk cases to appropriate providers
- **Clinical Reporting** - Generates summaries for doctor and nurse workflows
- **Google Integration** - Gmail for alerts, Calendar for scheduling
- **BigQuery Backend** - Scalable database for patient data
- **Demo-Ready** - Comes with mock data for immediate testing

## Architecture

**Clean, modular design with clear separation of concerns:**

```
apps/adk_app/
├── agents/          # AI agents (Coordinator, Vitals, Medication, ...)
├── prompts/         # LLM prompts for each agent
├── tools/           # External integrations (BigQuery, Gmail, Calendar)
├── services/        # Data access layer (Patient, Vitals, Medication, ...)
├── schemas/         # Data models (Patient, Vitals, Medication, Alert, ...)
├── config.py        # Configuration management
└── app.py           # Main entry point
```

See [Architecture Documentation](docs/architecture.md) for details.

## Planned Integrations

- ✅ BigQuery (structured database)
- ✅ Gmail (alert delivery)
- ✅ Google Calendar (appointment scheduling)
- 🔲 MCP Toolbox for BigQuery (future)
- 🔲 FastAPI wrapper 
- 🔲 Streamlit frontend (future)
- 🔲 Advanced ML models for risk prediction (future)

## Getting Started

### Prerequisites

- Python 3.9+
- Google Cloud Project (for BigQuery integration)
- ADK credentials (configured in `.env`)

### Quick Start

```bash
# 1. Clone and setup
git clone <repo>
cd CareOrchestra

# 2. Configure environment
cp .env.example .env
# Edit .env with your GCP credentials

# 3. Install dependencies
pip install -r requirements.txt

# 4. Load mock data (for demo)
python infra/scripts/load_seed_data.py

# 5. Run the application
python -m apps.adk_app.app
```

See [Demo Script](docs/demo_script.md) for detailed testing scenarios.

## Documentation

- **[Architecture](docs/architecture.md)** - System design and components
- **[Agent Responsibilities](docs/agent_responsibilities.md)** - What each agent does
- **[Workflows](docs/workflows.md)** - Example care coordination flows
- **[BigQuery Schema](docs/bigquery_schema.md)** - Database structure
- **[Demo Script](docs/demo_script.md)** - Running demo scenarios

## Project Structure

```
CareOrchestra/
├── frontend/              # Placeholder for future UI
├── apps/
│   ├── adk_app/          # Main ADK application
│   └── api/              # Placeholder for FastAPI
├── mcp/
│   └── toolbox/          # MCP Toolbox config (future)
├── data/
│   ├── seed/             # Initial patient data
│   └── mock_payloads/    # Sample events for testing
├── infra/
│   ├── scripts/          # Setup and deployment
│   └── README.md
├── docs/                 # Documentation
├── tests/                # Unit, integration, e2e tests
├── README.md
├── .env.example
├── requirements.txt
├── pyproject.toml
└── .gitignore
```

## Agent Overview

| Agent | Purpose | Key Decisions |
|-------|---------|---------------|
| **Coordinator** | Main orchestrator | Routes events, synthesizes findings |
| **Monitoring** | Event detection | What triggered analysis? |
| **Vitals** | Vital analysis | Normal/abnormal/critical readings? |
| **Medication** | Adherence tracking | Missing doses? Pattern issues? |
| **Analysis** | Risk synthesis | What's the overall risk level? |
| **Escalation** | Critical alerts | Who needs to know? How urgent? |
| **Reporting** | Clinical summaries | What's important for providers? |

See [Agent Responsibilities](docs/agent_responsibilities.md) for detailed info.

## How to Run
activate the virtual env
`source care-env/bin/activate`

Run fast api entry point
`PYTHONPATH=. uvicorn apps.api.main:app --reload`


## Configuration

Configuration is managed via environment variables in `.env`:

```env
# Google Cloud
GCP_PROJECT_ID=your-project-id
GCP_LOCATION=us-central1
BIGQUERY_DATASET=care_orchestra

# Gmail Integration
GMAIL_SENDER_EMAIL=alerts@yourapp.com
GMAIL_USE_MOCK=true  # Set to false for real Gmail

# Application
USE_MOCK_DATA=true   # Use mock data during development
LOG_LEVEL=INFO
DEBUG=false
```

See [.env.example](.env.example) for all available options.

## Testing

The project is organized for comprehensive testing:

```bash
# Unit tests (individual components)
pytest tests/unit/

# Integration tests (multiple components)
pytest tests/integration/

# End-to-end tests (full workflows)
pytest tests/e2e/

# All tests
pytest tests/
```

See [Demo Script](docs/demo_script.md) for testing scenarios.

## Development Workflow

### Local Testing with Mock Data

1. Load seed data: `python infra/scripts/load_seed_data.py`
2. Run app: `python -m apps.adk_app.app`
3. Trigger events: See demo scenarios in [Demo Script](docs/demo_script.md)
4. Verify outputs: Check alerts, emails, reports

### Real Integration

1. Update `.env` with real GCP project
2. Configure real patient data in BigQuery
3. Run with `USE_MOCK_DATA=false`
4. Code doesn't change - same agents work with real data!

## Deployment

### Google Cloud Run (Target Platform)

CareOrchestra is designed for Cloud Run deployment:

```bash
# Build container
gcloud builds submit --tag gcr.io/PROJECT_ID/care-orchestra

# Deploy
gcloud run deploy care-orchestra \
  --image gcr.io/PROJECT_ID/care-orchestra \
  --platform managed \
  --set-env-vars GCP_PROJECT_ID=PROJECT_ID
```

See `infra/scripts/deploy.sh` for detailed deployment script.

## Next Steps

### Phase 1 (Current)
- ✅ Project structure and starter files
- ✅ Agent framework scaffolding
- 🔲 Basic ADK integration
- 🔲 Mock data workflows

### Phase 2
- [ ] Complete agent implementations
- [ ] Real BigQuery integration
- [ ] MCP Toolbox integration
- [ ] Unit and integration tests

### Phase 3
- [ ] FastAPI wrapper for REST API
- [ ] Streamlit frontend
- [ ] Production deployment

### Phase 4
- [ ] ML-based risk prediction
- [ ] EHR system integration
- [ ] Multi-tenant support

## Technology Stack

- **Language**: Python 3.9+
- **Agent Framework**: Google ADK
- **Database**: BigQuery
- **Integrations**: Gmail, Google Calendar
- **Testing**: pytest
- **Type Checking**: mypy

## Contributing

This is a starter project template. As you build out functionality:

1. Keep agents focused and single-responsibility
2. Use clear naming for services and tools
3. Add comprehensive docstrings
4. Write tests alongside code
5. Document workflows in `docs/`

## License

[Add license info]

## Contact

[Add contact info]

---

**Ready to get started?** See [Demo Script](docs/demo_script.md) for a hands-on walkthrough.

**Want to understand the design?** Read [Architecture](docs/architecture.md) and [Workflows](docs/workflows.md).

**Building your own agents?** Check [Agent Responsibilities](docs/agent_responsibilities.md) for patterns and best practices.
