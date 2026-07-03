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
    Effectiveness,
    EffectKind,
    Element,
    GameState,
    Roster,
    RosterUnit,
    Side,
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


def build_roster(state: GameState, caster: Side) -> Roster:
    """The compact battlefield the judge sees + drives id validation (stickman first)."""

    def _units(key: str) -> list[RosterUnit]:
        side = state.p1 if key == "p1" else state.p2
        return [
            RosterUnit(
                id=u.id,
                name=u.name,
                kind=u.kind,
                hp=max(0, u.hp),
                max_hp=u.max_hp,
                weapon=u.weapon,
                tags=u.tags,
                items=u.items,
            )
            for u in (side.stickman, *side.entities)
        ]

    foe = "p2" if caster == "p1" else "p1"
    return Roster(you=_units(caster), foe=_units(foe))


def _resolve_ids(comp: EffectComponent, roster: Roster) -> None:
    """Ground a component's source/target to real unit ids (invalid -> stickman).

    The resolver never trusts a raw id; every reference is validated against the
    live roster here. ``source`` is always a caster unit; ``target`` is a caster
    unit for self-effects, else an opponent unit.
    """
    caster = roster.caster_ids()
    comp.source_id = comp.source_id if comp.source_id in caster else roster.caster_stickman()
    if comp.target is ComponentTarget.caster:
        comp.target_id = comp.target_id if comp.target_id in caster else roster.caster_stickman()
    else:
        opp = roster.opponent_ids()
        comp.target_id = comp.target_id if comp.target_id in opp else roster.opponent_stickman()


def normalize_components(
    raw: list[Any], balance: BalanceConfig, roster: Roster | None = None
) -> list[EffectComponent]:
    """Validate/clamp/cap the judge's raw component dicts into trusted components.

    Rules (DESIGN.md §3, plan rule 1): fill required-per-type defaults, clamp
    every numeric to its balance range, drop anything meaningless, enforce
    at most one instant-``damage`` component, and truncate to ``max_components``.
    When a ``roster`` is given, every source/target unit id is validated against
    it (invalid -> the relevant stickman). Returns [] when nothing survives.
    """
    pmin, pmax = balance.component_power_min, balance.component_power_max
    dmax = balance.max_effect_duration
    mmax = balance.max_stat_magnitude

    out: list[EffectComponent] = []
    seen_control = False

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
        comp: EffectComponent | None = None

        if ctype is ComponentType.damage:
            # Multiple damage components are allowed (a combo) but capped to one
            # per source unit downstream in _enforce_combo_caps.
            comp = EffectComponent(
                type=ctype, target=ComponentTarget.opponent, element=element, power=power
            )
        elif ctype is ComponentType.heal:
            comp = EffectComponent(type=ctype, target=ComponentTarget.caster, power=power)
        elif ctype is ComponentType.dot:
            comp = EffectComponent(
                type=ctype,
                target=ComponentTarget.opponent,
                element=element,
                power=power,
                duration=duration,
            )
        elif ctype is ComponentType.hot:
            comp = EffectComponent(
                type=ctype, target=ComponentTarget.caster, power=power, duration=duration
            )
        elif ctype is ComponentType.stat:
            stat = _as_enum(item.get("stat"), StatKind, None)
            magnitude = _clamp(_int(item.get("magnitude"), 0), -mmax, mmax)
            if stat is None or magnitude == 0:
                continue  # a stat shift with no stat or no magnitude is a no-op
            target = _as_enum(item.get("target"), ComponentTarget, ComponentTarget.opponent)
            comp = EffectComponent(
                type=ctype, target=target, stat=stat, magnitude=magnitude, duration=duration
            )
        elif ctype is ComponentType.defense:
            subtype = _as_enum(item.get("subtype"), DefenseSubtype, DefenseSubtype.shield)
            comp = EffectComponent(
                type=ctype,
                target=ComponentTarget.caster,
                element=element,
                power=power,
                subtype=subtype,
            )
        elif ctype is ComponentType.barrier:
            comp = EffectComponent(
                type=ctype, target=ComponentTarget.caster, element=element, power=power
            )
        elif ctype is ComponentType.control:
            if seen_control:
                continue  # at most one stun per bundle
            seen_control = True
            cdur = _clamp(_int(item.get("duration"), 1), 1, balance.max_control_duration)
            comp = EffectComponent(type=ctype, target=ComponentTarget.opponent, duration=cdur)
        elif ctype is ComponentType.summon:
            raw_tags = item.get("tags")
            tags = [str(t)[:20] for t in raw_tags][:4] if isinstance(raw_tags, list) else []
            item_name = item.get("item")
            comp = EffectComponent(
                type=ctype,
                target=ComponentTarget.caster,
                element=element,  # the new unit's weapon element
                power=power,  # the new unit's weapon power (anchors its attacks)
                name=str(item.get("name") or "summon")[:24],
                hp=_clamp(_int(item.get("hp"), 40), balance.summon_hp_min, balance.summon_hp_max),
                tags=tags,
                item=str(item_name)[:24] if isinstance(item_name, str) else None,
            )
        elif ctype is ComponentType.item:
            raw_tags = item.get("tags")
            tags = [str(t)[:20] for t in raw_tags][:4] if isinstance(raw_tags, list) else []
            # A weapon-item carries a `power`; a trinket/armor item just carries tags.
            wpn = _clamp(_int(item.get("power"), 0), 0, pmax) if "power" in item else 0
            comp = EffectComponent(
                type=ctype,
                target=ComponentTarget.caster,
                element=element,
                power=wpn or None,
                name=str(item.get("name") or "item")[:24],
                tags=tags,
            )

        if comp is None:
            continue
        src, tid = item.get("source_id"), item.get("target_id")
        comp.source_id = src if isinstance(src, str) else None
        comp.target_id = tid if isinstance(tid, str) else None
        if comp.type in (ComponentType.damage, ComponentType.dot):
            comp.effectiveness = _as_enum(
                item.get("effectiveness"), Effectiveness, Effectiveness.neutral
            )
            et = item.get("eff_tag")
            comp.eff_tag = str(et)[:24] if isinstance(et, str) else None
        out.append(comp)

    # "Can't summon and attack the same turn": a bundle that summons carries no
    # offensive component (whole-bundle rule; per-source relaxation is a later step).
    if any(c.type is ComponentType.summon for c in out):
        offensive = {ComponentType.damage, ComponentType.dot, ComponentType.control}
        out = [c for c in out if c.type not in offensive]

    if roster is not None:
        for c in out:
            _resolve_ids(c, roster)
            _ground_effectiveness(c, roster)
    return _enforce_combo_caps(out, balance)


def _ground_effectiveness(comp: EffectComponent, roster: Roster) -> None:
    """Anti-exploit: a matchup tier above neutral needs BOTH ends grounded in real
    battlefield state. (1) The cited ``eff_tag`` must be a REAL tag on the target
    (you actually summoned a kryptonian / it wears kryptonite armor). (2) The
    attacker must be specially equipped — carry a tag/item or an elemental weapon —
    so a bare fist can't "devastate" Superman; you must equip the counter first.
    Otherwise the tier is forced back to neutral."""
    if comp.effectiveness is Effectiveness.neutral:
        return
    target = next((u for u in roster.foe if u.id == comp.target_id), None)
    source = next((u for u in roster.you if u.id == comp.source_id), None)
    tag = (comp.eff_tag or "").lower()
    target_has_tag = bool(target and tag and tag in {t.lower() for t in target.tags})
    attacker_special = bool(
        source
        and (
            source.tags
            or source.items
            or (source.weapon and source.weapon.element != Element.physical)
        )
    )
    if not (target_has_tag and attacker_special):
        comp.effectiveness = Effectiveness.neutral
        comp.eff_tag = None


def effectiveness_mult(tier: Effectiveness, balance: BalanceConfig) -> float:
    return balance.effectiveness_multipliers.get(tier.value, 1.0)


def _enforce_combo_caps(
    out: list[EffectComponent], balance: BalanceConfig
) -> list[EffectComponent]:
    """Bound a command's breadth: at most one ``damage`` per source unit and at
    most ``max_units_per_command`` distinct units acting. Without a roster every
    source is None, so this collapses to the classic <=1-damage-per-command rule."""
    kept: list[EffectComponent] = []
    damaged: set[str | None] = set()
    units: list[str] = []
    for c in out:
        sid = c.source_id
        if sid is not None and sid not in units:
            if len(units) >= balance.max_units_per_command:
                continue  # a unit beyond the command's participant cap
            units.append(sid)
        if c.type is ComponentType.damage:
            if sid in damaged:
                continue  # at most one instant-damage per source unit
            damaged.add(sid)
        kept.append(c)
    return kept


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
    if c.type is ComponentType.control:
        return w.control * (c.duration or 1)
    if c.type is ComponentType.summon:
        # A summon's price scales with the body it puts on the board (hp + weapon).
        return ((c.hp or 0) / 10 + (c.power or 0)) * w.summon
    if c.type is ComponentType.item:
        # Cheap utility; a weapon-item costs a touch more than a trinket.
        return (2 + (c.power or 0)) * w.item
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
    # The cap scales with how many units act — a multi-unit combo may cost more
    # than one turn's mana, so you bank for it (affordability naturally gates it).
    participants = max(1, len({c.source_id for c in components if c.source_id is not None}))
    return min(balance.max_bundle_cost * participants, math.ceil(total * mult))


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
        elif c.type is ComponentType.control:
            key, base = "control", balance.kind_cooldowns_turns.control
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
