"""Runtime settings, read from the environment (and .env at the repo root)."""

import os

from dotenv import load_dotenv

from redthread.paths import ROOT

load_dotenv(ROOT / ".env")

# Pinned model versions (not "-latest" aliases) so runs are reproducible. Verified available
# for this project's key on 2026-09-20.
REASONING_MODEL = os.getenv("REDTHREAD_REASONING_MODEL", "gemini-3.1-pro-preview")
FAST_MODEL = os.getenv("REDTHREAD_FAST_MODEL", "gemini-3.8-flash")

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384
