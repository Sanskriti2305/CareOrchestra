"""
Unit test conftest: pre-mock Google Cloud and Gemini clients so that
modules with module-level side effects (BigQueryClient, genai.Client) can
be imported without live credentials.
"""

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


# ---------------------------------------------------------------------------
# Build minimal google.* stubs so module-level instantiation doesn't fail
# ---------------------------------------------------------------------------

def _make_google_stubs():
    """Return a google package stub that satisfies module-level imports."""
    google_pkg = types.ModuleType("google")
    google_pkg.__path__ = []  # make it a package

    # google.cloud
    cloud_pkg = types.ModuleType("google.cloud")
    cloud_pkg.__path__ = []
    google_pkg.cloud = cloud_pkg

    # google.cloud.bigquery
    bq_mod = types.ModuleType("google.cloud.bigquery")
    mock_bq_client_cls = MagicMock()
    mock_bq_client_cls.return_value = MagicMock()
    bq_mod.Client = mock_bq_client_cls
    bq_mod.QueryJobConfig = MagicMock
    bq_mod.ScalarQueryParameter = MagicMock
    cloud_pkg.bigquery = bq_mod

    # google.genai
    genai_mod = types.ModuleType("google.genai")
    mock_genai_client = MagicMock()
    genai_mod.Client = MagicMock(return_value=mock_genai_client)
    google_pkg.genai = genai_mod

    # google.genai.types
    genai_types_mod = types.ModuleType("google.genai.types")
    genai_types_mod.Content = MagicMock
    genai_types_mod.Part = MagicMock
    genai_types_mod.GenerateContentConfig = MagicMock
    genai_types_mod.AutomaticFunctionCallingConfig = MagicMock
    genai_mod.types = genai_types_mod

    # google.auth (needed by cloud client stubs)
    auth_mod = types.ModuleType("google.auth")
    google_pkg.auth = auth_mod

    # google.oauth2 (needed by GmailSender real mode)
    oauth2_mod = types.ModuleType("google.oauth2")
    oauth2_mod.__path__ = []
    google_pkg.oauth2 = oauth2_mod
    sa_mod = types.ModuleType("google.oauth2.service_account")
    mock_sa_creds = MagicMock()
    mock_sa_creds.with_subject = MagicMock(return_value=mock_sa_creds)
    sa_mod.Credentials = MagicMock(
        from_service_account_file=MagicMock(return_value=mock_sa_creds)
    )
    oauth2_mod.service_account = sa_mod

    # google.adk.agents
    adk_pkg = types.ModuleType("google.adk")
    adk_pkg.__path__ = []
    google_pkg.adk = adk_pkg
    adk_agents_mod = types.ModuleType("google.adk.agents")
    adk_agents_mod.Agent = MagicMock
    adk_pkg.agents = adk_agents_mod

    # google.cloud.logging (used by app.py)
    logging_mod = types.ModuleType("google.cloud.logging")
    logging_mod.Client = MagicMock
    cloud_pkg.logging = logging_mod

    return {
        "google": google_pkg,
        "google.cloud": cloud_pkg,
        "google.cloud.bigquery": bq_mod,
        "google.cloud.logging": logging_mod,
        "google.genai": genai_mod,
        "google.genai.types": genai_types_mod,
        "google.auth": auth_mod,
        "google.oauth2": oauth2_mod,
        "google.oauth2.service_account": sa_mod,
        "google.adk": adk_pkg,
        "google.adk.agents": adk_agents_mod,
    }


# Inject stubs before any agent module is imported
_google_stubs = _make_google_stubs()
for _name, _mod in _google_stubs.items():
    if _name not in sys.modules:
        sys.modules[_name] = _mod

# Also stub openai (used by Symptoms_agent)
if "openai" not in sys.modules:
    _openai_stub = types.ModuleType("openai")
    _openai_stub.OpenAI = MagicMock
    sys.modules["openai"] = _openai_stub

# Stub googleapiclient (used by GmailSender real mode)
if "googleapiclient" not in sys.modules:
    _gac_pkg = types.ModuleType("googleapiclient")
    _gac_pkg.__path__ = []
    _gac_discovery = types.ModuleType("googleapiclient.discovery")
    _gac_discovery.build = MagicMock(return_value=MagicMock())
    _gac_errors = types.ModuleType("googleapiclient.errors")
    _gac_errors.HttpError = type("HttpError", (Exception,), {})
    _gac_pkg.discovery = _gac_discovery
    _gac_pkg.errors = _gac_errors
    sys.modules["googleapiclient"] = _gac_pkg
    sys.modules["googleapiclient.discovery"] = _gac_discovery
    sys.modules["googleapiclient.errors"] = _gac_errors
