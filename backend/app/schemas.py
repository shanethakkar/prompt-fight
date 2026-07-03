"""Request/response models for the HTTP API (SPEC.md §6)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.models import Category, GameState, JudgedAction


class PlayerSnapshot(BaseModel):
    """The judging-relevant slice of a player's state."""

    model_config = ConfigDict(extra="forbid")

    mana: int
    cooldowns: dict[Category, int] = Field(default_factory=dict)


class JudgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str
    player: PlayerSnapshot
    match_id: str
    # Client-owned turn state; echoed back decremented. Defaults per balance.json.
    rewrites_remaining: int | None = None


class JudgeResponse(BaseModel):
    """Success carries action/mana_cost/affordable; a moderation reject carries error/message."""

    model_config = ConfigDict(extra="forbid")

    action: JudgedAction | None = None
    mana_cost: int | None = None
    affordable: bool | None = None
    on_cooldown: bool | None = None
    error: str | None = None
    message: str | None = None
    rewrites_remaining: int


class ResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    match_id: str
    state: GameState
    p1_action: JudgedAction
    p2_action: JudgedAction


class MatchConfig(BaseModel):
    """The balance constants the client needs for display (never hardcoded client-side)."""

    model_config = ConfigDict(extra="forbid")

    hp_max: int
    mana_max: int
    mana_regen_per_turn: int
    rewrites_per_turn: int
    max_turns: int


class NewMatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    p1_name: str = "Player 1"
    p2_name: str = "Player 2"


class NewMatchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    match_id: str
    state: GameState
    config: MatchConfig
