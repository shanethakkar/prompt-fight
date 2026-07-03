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


class ComponentWeights(BaseModel):
    """Per-component pricing weight — the exponent base contribution of each kind."""

    model_config = ConfigDict(extra="forbid")

    damage: float
    heal: float
    dot: float
    hot: float
    stat: float
    defense: float
    barrier: float
    control: float
    summon: float
    item: float


class KindCooldowns(BaseModel):
    """Cooldown turns keyed by the cooldownable component kinds only."""

    model_config = ConfigDict(extra="forbid")

    heal: int
    defense: int
    control: int


class ReliabilityConfig(BaseModel):
    """P1 reliability roll (competitive mode only). Reliability = Aptitude
    (competence) throttled by Ambition (reach); see GAME_MECHANICS §7b."""

    model_config = ConfigDict(extra="forbid")

    # Outcome tier -> damage multiplier for the rolled action.
    multipliers: dict[str, float]  # miss / partial / full / overload
    # Per competence tier (fit / improvised / unfit): base P(full-or-better),
    # how much of the success mass can crit, and the power the hit lands at.
    # improvised/unfit are exercised once P1.2 grounds real aptitude.
    competence_base: dict[str, float]
    competence_crit_scale: dict[str, float]
    competence_power_mult: dict[str, float]
    # Ambition: reach = max offensive power + step*(extra components); no penalty
    # below free_reach, then -slope in reliability per point over it.
    reach_component_step: float
    free_reach: float
    ambition_slope: float
    reliability_floor: float
    # Crit (overload) share of the success mass; grows with reach over free_reach.
    crit_base: float
    crit_reach_bonus: float
    crit_cap: float
    # Downside split (partial vs miss) + backfire (rebounds on the caster) carved
    # from the miss mass once reach hits backfire_reach.
    partial_share: float
    backfire_share: float
    backfire_reach: float
    backfire_self_fraction: float
    # Defender dodge-stance evasion, folded into the roll (replaces the old
    # deterministic dodge in competitive mode).
    evade_base: float
    evade_speed_step: float
    evade_cap: float
    dodge_miss_share: float


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
    component_weights: ComponentWeights
    # Super-additive bundle surcharge, keyed by component count ("1".."3").
    bundle_multipliers: dict[str, float]

    max_components: int
    max_units_per_command: int
    max_bundle_cost: int
    max_effects_per_player: int
    max_effect_duration: int
    max_stat_magnitude: int
    component_power_min: int
    component_power_max: int

    attack_damage_multiplier: float
    heal_multiplier: float
    dot_multiplier: float
    hot_multiplier: float
    block_multiplier: float
    partial_dodge_damage_fraction: float
    reflect_return_fraction: float

    barrier_pool_per_power: float
    max_barriers_per_player: int

    max_control_duration: int
    stun_immunity_turns: int

    max_entities_per_side: int
    summon_hp_min: int
    summon_hp_max: int

    damage_taken_per_point: float
    damage_taken_mult_floor: float
    damage_taken_mult_ceil: float

    effectiveness_multipliers: dict[str, float]
    offense_mult_ceil: float

    reliability: ReliabilityConfig

    defense_stance_duration_turns: int

    kind_cooldowns_turns: KindCooldowns
    heavy_move_power_threshold: int
    heavy_move_extra_cooldown_turns: int

    type_advantage_multiplier: float
    type_disadvantage_multiplier: float
    # Placeholder data slated to change in a later balance pass — a plain map.
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
