"""Pure rule helpers reused by the resolver and the /api/judge endpoint.

No I/O; every function takes the loaded BalanceConfig explicitly so it stays
deterministic and unit-testable. This module owns three jobs:

* normalization — turn the judge's permissive component list into a validated,
  clamped, capped list the resolver can trust (``normalize_components``);
* pricing — cost the whole bundle in aggregate (``bundle_cost``), never
  per-component (summing per-component costs was a burst exploit);
* effective stats — fold a player's persistent effect list into the numbers the
  resolver reads (``effective_power``/``effective_speed``/``damage_taken_mult``).
"""

from __future__ import annotations

import math
from typing import Any

from app.config import BalanceConfig
from app.models import (
    ActiveEffect,
    ComponentTarget,
    ComponentType,
    DefenseSubtype,
    EffectComponent,
    EffectKind,
    Element,
    StatKind,
)

# ---------------------------------------------------------------------------
# Permissive judge output -> validated component list
# ---------------------------------------------------------------------------


def _as_enum(value: Any, enum_cls, default):
    try:
        return enum_cls(value)
    except (ValueError, KeyError):
        return default


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_components(raw: list[Any], balance: BalanceConfig) -> list[EffectComponent]:
    """Validate/clamp/cap the judge's raw component dicts into trusted components.

    Rules (DESIGN.md §3, plan rule 1): fill required-per-type defaults, clamp
    every numeric to its balance range, drop anything meaningless, enforce
    at most one instant-``damage`` component, and truncate to ``max_components``.
    Returns [] when nothing survives (the caller then sputters).
    """
    pmin, pmax = balance.component_power_min, balance.component_power_max
    dmax = balance.max_effect_duration
    mmax = balance.max_stat_magnitude

    out: list[EffectComponent] = []
    seen_damage = False

    for item in raw:
        if len(out) >= balance.max_components:
            break
        if not isinstance(item, dict):
            continue
        ctype = _as_enum(item.get("type"), ComponentType, None)
        if ctype is None:
            continue

        element = _as_enum(item.get("element"), Element, Element.physical)
        power = _clamp(_int(item.get("power"), 4), pmin, pmax)
        duration = _clamp(_int(item.get("duration"), 2), 1, dmax)

        if ctype is ComponentType.damage:
            if seen_damage:
                continue  # at most one instant-damage component per bundle
            seen_damage = True
            out.append(
                EffectComponent(
                    type=ctype, target=ComponentTarget.opponent, element=element, power=power
                )
            )
        elif ctype is ComponentType.heal:
            out.append(EffectComponent(type=ctype, target=ComponentTarget.caster, power=power))
        elif ctype is ComponentType.dot:
            out.append(
                EffectComponent(
                    type=ctype,
                    target=ComponentTarget.opponent,
                    element=element,
                    power=power,
                    duration=duration,
                )
            )
        elif ctype is ComponentType.hot:
            out.append(
                EffectComponent(
                    type=ctype, target=ComponentTarget.caster, power=power, duration=duration
                )
            )
        elif ctype is ComponentType.stat:
            stat = _as_enum(item.get("stat"), StatKind, None)
            magnitude = _clamp(_int(item.get("magnitude"), 0), -mmax, mmax)
            if stat is None or magnitude == 0:
                continue  # a stat shift with no stat or no magnitude is a no-op
            target = _as_enum(item.get("target"), ComponentTarget, ComponentTarget.opponent)
            out.append(
                EffectComponent(
                    type=ctype, target=target, stat=stat, magnitude=magnitude, duration=duration
                )
            )
        elif ctype is ComponentType.defense:
            subtype = _as_enum(item.get("subtype"), DefenseSubtype, DefenseSubtype.shield)
            out.append(
                EffectComponent(
                    type=ctype,
                    target=ComponentTarget.caster,
                    element=element,
                    power=power,
                    subtype=subtype,
                )
            )
        elif ctype is ComponentType.barrier:
            out.append(
                EffectComponent(
                    type=ctype, target=ComponentTarget.caster, element=element, power=power
                )
            )

    return out


# ---------------------------------------------------------------------------
# Aggregate pricing (plan rule 2 — price the bundle, never the sum of parts)
# ---------------------------------------------------------------------------


def component_weight(c: EffectComponent, balance: BalanceConfig) -> float:
    """The exponent-base contribution of one component to the bundle price."""
    w = balance.component_weights
    if c.type is ComponentType.damage:
        return (c.power or 0) * w.damage
    if c.type is ComponentType.heal:
        return (c.power or 0) * w.heal
    if c.type is ComponentType.dot:
        return (c.power or 0) * (c.duration or 1) * w.dot
    if c.type is ComponentType.hot:
        return (c.power or 0) * (c.duration or 1) * w.hot
    if c.type is ComponentType.stat:
        return abs(c.magnitude or 0) * (c.duration or 1) * w.stat
    if c.type is ComponentType.defense:
        return (c.power or 0) * w.defense
    if c.type is ComponentType.barrier:
        return (c.power or 0) * w.barrier
    return 0.0


def bundle_cost(components: list[EffectComponent], balance: BalanceConfig) -> int:
    """Aggregate mana cost: ceil(Σ(weightᵢ^exponent) × bundle_mult[n]), capped.

    The exponent is applied PER component and then summed (not to the summed
    weight), which keeps a 1-component bundle's cost identical to a lone move
    while making multi-component bundles affordable. It still guarantees no
    burst discount: Σ(wᵢ^e) ≥ max(wᵢ)^e and bundle_mult ≥ 1, so a bundle never
    costs less than its most expensive component alone.
    """
    if not components:
        return 0
    total = sum(component_weight(c, balance) ** balance.cost_exponent for c in components)
    n = len(components)
    mult = balance.bundle_multipliers.get(
        str(n), balance.bundle_multipliers[str(balance.max_components)]
    )
    return min(balance.max_bundle_cost, math.ceil(total * mult))


def kind_cooldowns(components: list[EffectComponent], balance: BalanceConfig) -> dict[str, int]:
    """Cooldowns to apply after this bundle, keyed by the cooldownable kinds.

    Only heal/defense/control are throttled (the turtle/lock levers); damage,
    dot, and stat ride on mana alone. A heavy (power >= threshold) heal/defense
    adds an extra turn.
    """
    cds: dict[str, int] = {}
    for c in components:
        if c.type is ComponentType.heal:
            key, base = "heal", balance.kind_cooldowns_turns.heal
        elif c.type in (ComponentType.defense, ComponentType.barrier):
            # Barrier shares the defensive-stance cooldown (both are "put up a guard").
            key, base = "defense", balance.kind_cooldowns_turns.defense
        else:
            continue
        if (c.power or 0) >= balance.heavy_move_power_threshold:
            base += balance.heavy_move_extra_cooldown_turns
        cds[key] = max(cds.get(key, 0), base)
    return cds


# ---------------------------------------------------------------------------
# Effective stats — fold a player's persistent effect list into live numbers
# ---------------------------------------------------------------------------


def _stat_sum(effects: list[ActiveEffect], stat: StatKind) -> int:
    return sum(e.magnitude for e in effects if e.kind is EffectKind.stat and e.stat is stat)


def effective_power(base: int, effects: list[ActiveEffect]) -> int:
    """Base power adjusted by the player's additive power-stat effects, floor 0."""
    return max(0, base + _stat_sum(effects, StatKind.power))


def effective_speed(base: int, effects: list[ActiveEffect]) -> int:
    """Base speed adjusted by the player's additive speed-stat effects, floor 1."""
    return max(1, base + _stat_sum(effects, StatKind.speed))


def damage_taken_mult(effects: list[ActiveEffect], balance: BalanceConfig) -> float:
    """Multiplicative damage-taken factor from armor/expose effects, clamped.

    Each ``damage_taken`` stat effect contributes (1 + magnitude × per_point);
    they multiply (two armors stack multiplicatively) then clamp to [floor, ceil].
    """
    mult = 1.0
    for e in effects:
        if e.kind is EffectKind.stat and e.stat is StatKind.damage_taken:
            mult *= 1 + e.magnitude * balance.damage_taken_per_point
    return max(balance.damage_taken_mult_floor, min(balance.damage_taken_mult_ceil, mult))


def type_multiplier(attacker: Element, defender: Element, balance: BalanceConfig) -> float:
    """Element multiplier for attacker-vs-defender (a defending stance's element).

    Advantage -> type_advantage_multiplier; the reverse -> disadvantage; else
    neutral 1.0. ``physical`` has no advantages, so it is always neutral.
    """
    advantages = balance.type_chart_advantages
    if defender.value in advantages.get(attacker.value, []):
        return balance.type_advantage_multiplier
    if attacker.value in advantages.get(defender.value, []):
        return balance.type_disadvantage_multiplier
    return 1.0
