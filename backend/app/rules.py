"""Pure rule helpers reused by the resolver (and, in M2, the /api/judge endpoint).

No I/O; every function takes the loaded BalanceConfig explicitly so it stays
deterministic and unit-testable.
"""

from __future__ import annotations

import math

from app.config import BalanceConfig
from app.models import ActiveEffect, Category, Element, JudgedAction


def mana_cost(action: JudgedAction, balance: BalanceConfig) -> int:
    """Server-computed cost: ceil(power ** cost_exponent * category_multiplier).

    Uses the action's BASE power (matches the /api/judge cost preview); buffs
    and debuffs never change what a move costs.
    """
    multiplier = getattr(balance.category_cost_multipliers, action.category.value)
    return math.ceil(action.power**balance.cost_exponent * multiplier)


def type_multiplier(attacker: Element, defender: Element, balance: BalanceConfig) -> float:
    """Element multiplier for attacker-vs-defender (a defending action's element).

    Advantage -> type_advantage_multiplier; the reverse direction ->
    type_disadvantage_multiplier; otherwise neutral 1.0. `physical` has no
    advantages and appears in no advantage list, so it is always neutral.
    """
    advantages = balance.type_chart_advantages
    if defender.value in advantages.get(attacker.value, []):
        return balance.type_advantage_multiplier
    if attacker.value in advantages.get(defender.value, []):
        return balance.type_disadvantage_multiplier
    return 1.0


def effective_power(
    action: JudgedAction,
    buff: ActiveEffect | None,
    debuff: ActiveEffect | None,
) -> int:
    """Base power adjusted by the actor's active buff/debuff, floored at 0."""
    shift = (buff.power_shift if buff else 0) - (debuff.power_shift if debuff else 0)
    return max(0, action.power + shift)


def effective_speed(
    action: JudgedAction,
    buff: ActiveEffect | None,
    debuff: ActiveEffect | None,
) -> int:
    """Base speed adjusted by the actor's active buff/debuff, floored at 1."""
    shift = (buff.speed_shift if buff else 0) - (debuff.speed_shift if debuff else 0)
    return max(1, action.speed + shift)


def buff_shift(action: JudgedAction, balance: BalanceConfig) -> int:
    """Magnitude a buff/debuff shifts its target stat, from the action's base power."""
    return round(action.power * balance.buff_debuff_stat_shift_per_power)


def category_cooldown(action: JudgedAction, balance: BalanceConfig) -> int:
    """Cooldown turns applied after using this action, incl. the heavy-move bump."""
    base = getattr(balance.category_cooldowns_turns, action.category.value)
    if action.power >= balance.heavy_move_power_threshold:
        base += balance.heavy_move_extra_cooldown_turns
    return base


def is_defense(action: JudgedAction) -> bool:
    return action.category == Category.defense
