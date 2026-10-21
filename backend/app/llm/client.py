"""
LLM Client (Phase 4) — Groq via OpenAI-compatible API.

Uses the `openai` SDK pointed at Groq's base URL.
Falls back gracefully on:
  - Missing API key
  - Timeout (20 s, one retry on 5xx)
  - Invalid / non-JSON response
  - Any unexpected exception

Environment variables (from .env / .env.example):
  LLM_BASE_URL  — defaults to https://api.groq.com/openai/v1
  LLM_API_KEY   — your Groq API key (gsk_…)
  LLM_MODEL     — defaults to llama-3.3-70b-versatile
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

_GROQ_DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
_GROQ_DEFAULT_MODEL = "llama-3.3-70b-versatile"
_DEFAULT_TIMEOUT = 20.0
_DEFAULT_TEMPERATURE = 0.3


def _get_api_key() -> str:
    """Return the configured Groq/LLM API key from environment, checking .env if needed."""
    key = (
        os.getenv("GROQ_API_KEY", "")
        or os.getenv("LLM_API_KEY", "")
        or os.getenv("OPENAI_API_KEY", "")
    ).strip()
    if key:
        return key

    # If not yet set in environment, attempt loading .env
    try:
        from pathlib import Path
        from dotenv import load_dotenv

        root_env = Path(__file__).resolve().parents[3] / ".env"
        if root_env.is_file():
            load_dotenv(root_env, override=False)
        backend_env = Path(__file__).resolve().parents[2] / ".env"
        if backend_env.is_file():
            load_dotenv(backend_env, override=False)
        load_dotenv(override=False)
    except Exception:
        pass

    return (
        os.getenv("GROQ_API_KEY", "")
        or os.getenv("LLM_API_KEY", "")
        or os.getenv("OPENAI_API_KEY", "")
    ).strip()


def _get_client():
    """
    Build and return an OpenAI client configured for Groq.
    Supports GROQ_API_KEY, LLM_API_KEY, or OPENAI_API_KEY.
    Returns None if no API key is configured.
    """
    from openai import OpenAI

    api_key = _get_api_key()
    if not api_key:
        logger.warning(
            "Neither GROQ_API_KEY nor LLM_API_KEY is set — LLM ranker disabled, using heuristic fallback."
        )
        return None

    base_url = (
        os.getenv("GROQ_BASE_URL", "")
        or os.getenv("LLM_BASE_URL", "")
        or _GROQ_DEFAULT_BASE_URL
    ).strip() or _GROQ_DEFAULT_BASE_URL

    masked_key = f"{api_key[:7]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
    logger.debug("Initializing Groq client with base_url=%s, key=%s", base_url, masked_key)

    return OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=_DEFAULT_TIMEOUT,
        max_retries=0,  # We handle retries manually below
    )


_GROQ_FALLBACK_MODELS = ["openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b"]


def _get_model() -> str:
    return (
        os.getenv("GROQ_MODEL", "")
        or os.getenv("LLM_MODEL", "")
        or _GROQ_DEFAULT_MODEL
    ).strip() or _GROQ_DEFAULT_MODEL


def complete_json(system: str, user: str) -> dict[str, Any] | None:
    """
    Call the LLM and return the parsed JSON response dict.

    Returns:
        Parsed dict on success.
        None on any failure (missing key, timeout, bad JSON, 5xx).

    Retry policy:
        One retry on HTTP 5xx errors with a 2-second back-off.
        Graceful fallback to alternate Groq models on 429 (rate limit) or 404.
    """
    client = _get_client()
    if client is None:
        return None

    primary_model = _get_model()
    # Build candidate models list: primary first, followed by fallbacks without duplicates
    models_to_try = [primary_model] + [m for m in _GROQ_FALLBACK_MODELS if m != primary_model]

    from openai import APIStatusError, APITimeoutError

    for current_model in models_to_try:
        def _call_model(model_name: str) -> dict[str, Any] | None:
            try:
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=_DEFAULT_TEMPERATURE,
                    response_format={"type": "json_object"},
                )
                raw = response.choices[0].message.content
                if not raw:
                    logger.warning("LLM (%s) returned empty content.", model_name)
                    return None
                return json.loads(raw)

            except APITimeoutError:
                logger.warning("LLM (%s) request timed out after %.1fs.", model_name, _DEFAULT_TIMEOUT)
                return None

            except APIStatusError as exc:
                if exc.status_code >= 500:
                    logger.warning("LLM (%s) 5xx error (%s): %s", model_name, exc.status_code, exc.message)
                    raise  # Signal caller to retry
                if exc.status_code in (429, 404):
                    logger.warning("LLM (%s) status %s; will attempt fallback model if available.", model_name, exc.status_code)
                    return None
                logger.error("LLM (%s) API error (%s): %s", model_name, exc.status_code, exc.message)
                return None

            except json.JSONDecodeError as exc:
                logger.warning("LLM (%s) returned invalid JSON: %s", model_name, exc)
                return None

            except Exception as exc:
                logger.error("Unexpected LLM error with %s: %s", model_name, exc, exc_info=True)
                return None

        # Try current model
        try:
            result = _call_model(current_model)
        except Exception:
            # 5xx error — retry once after back-off
            logger.info("Retrying LLM (%s) call after 5xx error…", current_model)
            time.sleep(2.0)
            try:
                result = _call_model(current_model)
            except Exception as exc:
                logger.error("LLM (%s) retry also failed: %s", current_model, exc)
                result = None

        if result is not None:
            return result

    return None
