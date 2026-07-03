"""Typed loader for the single source of truth: config/balance.json.

The loader anchors on this module's own path (never os.getcwd()) and walks
upward to find ``config/balance.json``. This keeps it correct whether the
process is started by ``uvicorn`` (CWD=backend/), ``pytest``, or CI. Balance
constants must never be hardcoded elsewhere — read them from here.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

_BALANCE_REL = Path("config") / "balance.json"
_BALANCE_ENV = "STICKMANCER_BALANCE_PATH"


def _find_balance_path() -> Path:
    """Locate config/balance.json regardless of the current working directory.

    Honors the ``STICKMANCER_BALANCE_PATH`` override, otherwise walks upward
    from this file until it finds ``config/balance.json``.
    """
    override = os.getenv(_BALANCE_ENV)
    if override:
        return Path(override).resolve()

    here = Path(__file__).resolve()
    for parent in (here, *here.parents):
        candidate = parent / _BALANCE_REL
        if candidate.is_file():
            return candidate

    raise FileNotFoundError(
        f"Could not locate {_BALANCE_REL} walking up from {here}. "
        f"Set {_BALANCE_ENV} to point at it explicitly."
    )


class CategoryFloats(BaseModel):
    """A per-category float map over the five action categories."""

    model_config = ConfigDict(extra="forbid")

    attack: float
    defense: float
    buff: float
    debuff: float
    heal: float


class CategoryInts(BaseModel):
    """A per-category int map over the five action categories."""

    model_config = ConfigDict(extra="forbid")

    attack: int
    defense: int
    buff: int
    debuff: int
    heal: int


class BalanceConfig(BaseModel):
    """Fully-typed mirror of config/balance.json.

    ``extra="forbid"`` makes drift a loud failure: any new key added to
    balance.json must be added here in the same change (new tunables imply
    new code that reads them).
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    comment: str = Field(alias="_comment", default="")

    judge_model: str
    judge_temperature: float
    moderation_model_check_enabled: bool

    hp_start: int
    hp_max: int
    mana_start: int
    mana_max: int
    mana_regen_per_turn: int

    cost_exponent: float
    category_cost_multipliers: CategoryFloats

    attack_damage_multiplier: float
    heal_multiplier: float
    block_multiplier: float
    buff_debuff_duration_turns: int
    partial_dodge_damage_fraction: float
    reflect_return_fraction: float

    category_cooldowns_turns: CategoryInts
    heavy_move_power_threshold: int
    heavy_move_extra_cooldown_turns: int

    type_advantage_multiplier: float
    type_disadvantage_multiplier: float
    # Placeholder data slated to change in the M6 balance pass — left as a plain map.
    type_chart_advantages: dict[str, list[str]]

    rewrites_per_turn: int
    max_turns: int
    input_timer_seconds: int | None = None
    rate_limit_judge_calls_per_minute_per_ip: int


@lru_cache(maxsize=1)
def load_balance() -> BalanceConfig:
    """Load and validate config/balance.json (cached)."""
    path = _find_balance_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    return BalanceConfig.model_validate(data)
