"""Shared pytest configuration for DineMate backend tests.

By default, the LLM client is disabled across all tests so that:
  - Tests are deterministic and offline.
  - The LLM_API_KEY in .env does not interfere with Phase 3/service tests.
  - Tests that want to exercise LLM paths can monkeypatch a mock response.
"""
import pytest


@pytest.fixture(autouse=True)
def disable_llm_client(monkeypatch):
    """Patch LLM client to return None (no API call) for every test by default."""
    import app.llm.client as llm_module
    monkeypatch.setattr(llm_module, "_get_client", lambda: None)
