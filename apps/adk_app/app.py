import logging
import os
from dotenv import load_dotenv

# Internal Imports
from apps.adk_app.agents.coordinator import CoordinatorAgent
from apps.adk_app.agents.vitals import VitalsAgent
from apps.adk_app.agents.monitoring import MonitoringAgent
from apps.adk_app.agents.medication import MedicationAgent
from apps.adk_app.agents.analysis import AnalysisAgent
from apps.adk_app.agents.reporting import ReportingAgent
from apps.adk_app.config import get_config

# 1. Load the environment variables BEFORE anything else happens
load_dotenv()

logger = logging.getLogger(__name__)

class CareOrchestraApp:
    def __init__(self):
        """Initialize the application container."""
        # 2. Load configuration
        self.config = get_config()
        
        # 3. Configure logging
        self.setup_logging()
        
        # 4. Storage for our agents
        self.agents = {}
        
        # 5. Initialize agents
        self.initialize_agents()

    def setup_logging(self) -> None:
        """Configure logging for the application."""
        # Default to local logging. Cloud logging is opt-in to avoid noisy startup
        # failures when IAM permission logging.logEntries.create is missing.
        logging.basicConfig(
            level=getattr(logging, self.config.log_level.upper(), logging.INFO),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

        enable_gcp_logging = os.getenv("ENABLE_GCP_LOGGING", "false").lower() == "true"
        if not enable_gcp_logging:
            logger.info(f"Standard logging initialized at level {self.config.log_level}")
            return

        try:
            import google.cloud.logging

            cloud_client = google.cloud.logging.Client()
            cloud_client.setup_logging()
            logger.info("Google Cloud Logging initialized.")
        except Exception as exc:
            logger.warning("Cloud logging disabled, falling back to standard logging: %s", exc)

    def initialize_agents(self) -> None:
        """Initialize all specialized agents."""
        logger.info("Initializing Agentic Layer...")
        
        # Create Worker Agents
        self.agents["vitals"] = VitalsAgent()
        self.agents["medication"] = MedicationAgent()
        self.agents["monitoring"] = MonitoringAgent()
        self.agents["analysis"] = AnalysisAgent()
        self.agents["reporting"] = ReportingAgent()
        
        # Create Coordinator
        self.agents["coordinator"] = CoordinatorAgent()
        logger.info("All agents initialized successfully.")
    
    async def process_event(self, event: dict) -> dict:
        """Routes incoming patient messages to the Coordinator."""
        coordinator = self.agents.get("coordinator")
        if not coordinator:
            return {"status": "error", "message": "Coordinator not initialized"}
            
        # The coordinate function handles the Gemini logic
        return await coordinator.coordinate(event)