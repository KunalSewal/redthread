"""Runtime settings, read from the environment (and .env at the repo root)."""

import os

from dotenv import load_dotenv

from redthread.paths import ROOT

load_dotenv(ROOT / ".env")

# Pinned model versions (not "-latest" aliases) so runs are reproducible. Verified on this key
# 2026-09-20: gemini-pro-latest -> gemini-3.1-pro-preview, gemini-flash-latest -> gemini-3.8-flash.
#
# Chosen by measurement rather than by tier. Replaying 28 closed cases as alerts
# (scripts/backtest.py), Flash 3.8 with thinking=high got 26/28 verdicts right against 23/28 for
# Pro 3.1, with much better calibration (Brier 0.005 vs 0.117 on the second sample) and no cleared
# case called fraud. Raising Pro's thinking level did not help. See runs/confirm_*.json.
REASONING_MODEL = os.getenv("REDTHREAD_REASONING_MODEL", "gemini-3.8-flash")

# Gemini 3 thinking level for reasoning calls: "low" | "high" | "" to leave the model's default.
THINKING_LEVEL = os.getenv("REDTHREAD_THINKING_LEVEL", "high")

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384
