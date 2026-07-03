"""FastAPI application entry point.

M2: /api/judge (moderation -> judge -> server-computed cost) and /api/resolve
(thin wrapper over the pure M1 resolver). The API key lives only in backend env.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.config import load_balance
from app.judge import judge
from app.models import ResolveResult
from app.moderation import moderate
from app.resolver import resolve
from app.rules import mana_cost
from app.schemas import JudgeRequest, JudgeResponse, ResolveRequest

app = FastAPI(title="Stickmancer")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check that also proves balance.json loads and validates."""
    cfg = load_balance()
    return {"status": "ok", "judge_model": cfg.judge_model}


@app.post("/api/judge", response_model=JudgeResponse)
def api_judge(req: JudgeRequest) -> JudgeResponse:
    """Moderate, judge into a structured action, and price it server-side."""
    balance = load_balance()
    rewrites_left = (
        req.rewrites_remaining if req.rewrites_remaining is not None else balance.rewrites_per_turn
    )
    # A judged submission or a moderation reject both consume a rewrite (§9).
    rewrites_after = max(0, rewrites_left - 1)

    verdict = moderate(req.prompt, balance)
    if not verdict.allowed:
        return JudgeResponse(
            error="moderation",
            message=verdict.message,
            rewrites_remaining=rewrites_after,
        )

    action = judge(req.prompt, balance)
    cost = mana_cost(action, balance)
    return JudgeResponse(
        action=action,
        mana_cost=cost,
        affordable=req.player.mana >= cost,
        on_cooldown=req.player.cooldowns.get(action.category, 0) > 0,
        rewrites_remaining=rewrites_after,
    )


@app.post("/api/resolve", response_model=ResolveResult)
def api_resolve(req: ResolveRequest) -> ResolveResult:
    """Resolve both actions against the current state (pure server logic)."""
    return resolve(req.state, req.p1_action, req.p2_action, load_balance())
