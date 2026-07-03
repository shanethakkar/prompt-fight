"""Request/response models for the HTTP API (SPEC.md §6)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.models import Action, GameMode, GameState


class JudgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str
    # The full battlefield: the judge is now stateful (it resolves unit references
    # and only acts on units that exist). The server derives the compact roster
    # and the active side's mana/cooldowns from this.
    state: GameState
    match_id: str
    # Client-owned turn state; echoed back decremented. Defaults per balance.json.
    rewrites_remaining: int | None = None


class JudgeResponse(BaseModel):
    """Success carries action/mana_cost/affordable; a moderation reject carries error/message."""

    model_config = ConfigDict(extra="forbid")

    action: Action | None = None
    mana_cost: int | None = None
    affordable: bool | None = None
    # True if any component-kind in the bundle is currently on cooldown.
    on_cooldown: bool | None = None
    error: str | None = None
    message: str | None = None
    rewrites_remaining: int


class ResolveRequest(BaseModel):
    """Resolve one action bundle for the active player (state.active).

    ``action`` is null when the active player is stunned and skips their turn;
    the server also skips ACT on its own if the player is stunned regardless.
    """

    model_config = ConfigDict(extra="forbid")

    match_id: str
    state: GameState
    action: Action | None = None


class MatchConfig(BaseModel):
    """The balance constants the client needs for display (never hardcoded client-side)."""

    model_config = ConfigDict(extra="forbid")

    hp_max: int
    mana_max: int
    mana_regen_per_turn: int
    rewrites_per_turn: int
    max_turns: int
    mode: GameMode


class NewMatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    p1_name: str = "Player 1"
    p2_name: str = "Player 2"
    mode: GameMode = "sandbox"


class NewMatchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    match_id: str
    state: GameState
    config: MatchConfig
