"""FastAPI application entry point.

M0: health check only. The judge (/api/judge) and resolver (/api/resolve)
endpoints arrive in M1/M2.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.config import load_balance

app = FastAPI(title="Stickmancer")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check that also proves balance.json loads and validates."""
    cfg = load_balance()
    return {"status": "ok", "judge_model": cfg.judge_model}
