"""FastAPI application entry point.

Endpoints: /api/new_match (initial state + display config), /api/judge
(moderation -> judge -> server-computed cost), /api/resolve (thin wrapper over
the pure M1 resolver). The API key lives only in backend env.
"""

from __future__ import annotations

import secrets
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import load_balance
from app.judge import judge
from app.models import ResolveResult
from app.moderation import moderate
from app.resolver import initial_game, resolve_turn
from app.rules import build_roster, bundle_cost, kind_cooldowns, success_odds
from app.schemas import (
    JudgeRequest,
    JudgeResponse,
    MatchConfig,
    NewMatchRequest,
    NewMatchResponse,
    ResolveRequest,
)

app = FastAPI(title="Stickmancer")

# Local hot-seat: the browser (localhost:3000) calls this backend directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check that also proves balance.json loads and validates."""
    cfg = load_balance()
    return {"status": "ok", "judge_model": cfg.judge_model}


@app.post("/api/new_match", response_model=NewMatchResponse)
def api_new_match(req: NewMatchRequest) -> NewMatchResponse:
    """Start a match: initial state + the display constants the client needs."""
    balance = load_balance()
    # Mint the reliability seed here, at the I/O boundary — the resolver itself
    # stays pure and reads the seed back off the state.
    seed = secrets.randbits(63)
    return NewMatchResponse(
        match_id=uuid.uuid4().hex,
        state=initial_game(balance, req.p1_name, req.p2_name, seed=seed, mode=req.mode),
        config=MatchConfig(
            hp_max=balance.hp_max,
            mana_max=balance.mana_max,
            mana_regen_per_turn=balance.mana_regen_per_turn,
            rewrites_per_turn=balance.rewrites_per_turn,
            max_turns=balance.max_turns,
            mode=req.mode,
        ),
    )


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

    caster = req.state.active
    active_side = req.state.p1 if caster == "p1" else req.state.p2
    roster = build_roster(req.state, caster)
    action = judge(req.prompt, balance, roster=roster)
    cost = bundle_cost(action.components, balance)
    pending_cds = kind_cooldowns(action.components, balance)
    on_cooldown = any(active_side.cooldowns.get(kind, 0) > 0 for kind in pending_cds)
    # Informed odds (P1): the same pure function the resolver rolls against, so the
    # preview is honest. Sandbox / non-offensive -> {"full": 1.0}.
    odds = success_odds(action, req.state, balance)
    return JudgeResponse(
        action=action,
        mana_cost=cost,
        affordable=active_side.mana >= cost,
        on_cooldown=on_cooldown,
        success_odds=odds,
        rewrites_remaining=rewrites_after,
    )


@app.post("/api/resolve", response_model=ResolveResult)
def api_resolve(req: ResolveRequest) -> ResolveResult:
    """Resolve one action for the active player (pure server logic)."""
    try:
        return resolve_turn(req.state, req.action, load_balance())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
