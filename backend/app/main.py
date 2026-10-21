"""
DineMate FastAPI application entry point.

Loads .env, configures logging, mounts the /api router.
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load .env from root or backend directory
_root_env = Path(__file__).resolve().parents[2] / ".env"
if _root_env.is_file():
    load_dotenv(_root_env, override=False)
_backend_env = Path(__file__).resolve().parents[1] / ".env"
if _backend_env.is_file():
    load_dotenv(_backend_env, override=False)
load_dotenv(override=False)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s -- %(message)s",
)
_logger = logging.getLogger("dinemate.startup")
_key_configured = bool((os.getenv("GROQ_API_KEY") or os.getenv("LLM_API_KEY") or "").strip())
_logger.info("DineMate backend starting (Groq LLM key configured: %s)", _key_configured)

from app.api.routes import router as api_router  # noqa: E402 -- after dotenv load

app = FastAPI(title="DineMate", version="0.1.0")

allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
]
env_origins = os.getenv("CORS_ORIGINS", "")
if env_origins:
    allowed_origins.extend([origin.strip() for origin in env_origins.split(",") if origin.strip()])

_logger.info("CORS allowed origins: %s", allowed_origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.get("/health", tags=["infra"])
def health() -> dict[str, str]:
    """Liveness probe -- never calls the LLM or catalog."""
    return {"status": "ok"}
