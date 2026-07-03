"""Unit tests for the pure rule helpers (rules.py): normalization, aggregate
pricing, kind cooldowns, and effective-stat folding over the effect list."""

from __future__ import annotations

import pytest
from app.config import load_balance
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
from app.rules import (
    bundle_cost,
    damage_taken_mult,
    effective_power,
    effective_speed,
    kind_cooldowns,
    normalize_components,
    type_multiplier,
)

BAL = load_balance()


def dmg(power=6, element="physical"):
    return EffectComponent(type=ComponentType.damage, element=Element(element), power=power)


def stat_eff(stat, magnitude, turns=2, source="p1"):
    return ActiveEffect(
        kind=EffectKind.stat,
        stat=StatKind(stat),
        magnitude=magnitude,
        turns_remaining=turns,
        source=source,
    )


# ---------------------------------------------------------------------------
# normalize_components: validate / clamp / cap / drop
# ---------------------------------------------------------------------------


def test_normalize_fills_and_clamps():
    out = normalize_components([{"type": "damage", "power": 99, "element": "fire"}], BAL)
    assert len(out) == 1
    assert out[0].power == 10 and out[0].element is Element.fire
    assert out[0].target is ComponentTarget.opponent


def test_normalize_drops_unknown_type():
    assert normalize_components([{"type": "teleport"}, {"type": "damage", "power": 3}], BAL) == [
        EffectComponent(type=ComponentType.damage, target=ComponentTarget.opponent, power=3)
    ]


def test_normalize_at_most_one_damage():
    out = normalize_components(
        [{"type": "damage", "power": 5}, {"type": "damage", "power": 8}], BAL
    )
    assert [c.type for c in out] == [ComponentType.damage]
    assert out[0].power == 5  # the first survives


def test_normalize_truncates_to_max_components():
    raw = [
        {"type": "damage", "power": 5},
        {"type": "heal", "power": 4},
        {"type": "defense", "subtype": "shield", "power": 4},
        {"type": "hot", "power": 3, "duration": 3},
    ]
    assert len(normalize_components(raw, BAL)) == BAL.max_components == 3


def test_normalize_stat_requires_stat_and_magnitude():
    assert normalize_components([{"type": "stat", "magnitude": 4}], BAL) == []  # no stat kind
    assert normalize_components([{"type": "stat", "stat": "power", "magnitude": 0}], BAL) == []
    out = normalize_components(
        [{"type": "stat", "stat": "power", "magnitude": -99, "duration": 9, "target": "self"}], BAL
    )
    assert out[0].magnitude == -BAL.max_stat_magnitude
    assert out[0].duration == BAL.max_effect_duration
    assert out[0].target is ComponentTarget.caster


def test_normalize_heal_and_hot_default_to_self():
    out = normalize_components(
        [{"type": "heal", "power": 4}, {"type": "hot", "power": 3, "duration": 2}], BAL
    )
    assert all(c.target is ComponentTarget.caster for c in out)


def test_normalize_defense_defaults_shield():
    out = normalize_components([{"type": "defense", "power": 5}], BAL)
    assert out[0].subtype is DefenseSubtype.shield
    assert out[0].target is ComponentTarget.caster


def test_normalize_ignores_non_dicts():
    assert normalize_components(["nope", 3, {"type": "damage", "power": 2}], BAL)[0].power == 2


# ---------------------------------------------------------------------------
# bundle_cost: aggregate, super-additive, capped
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "power,expected",
    [(1, 1), (5, 7), (6, 9), (10, 16)],  # ceil(power**1.2) with weight 1.0
)
def test_single_damage_cost_matches_legacy_curve(power, expected):
    assert bundle_cost([dmg(power=power)], BAL) == expected


def test_heal_and_defense_single_costs():
    heal = EffectComponent(type=ComponentType.heal, power=5)
    shield = EffectComponent(type=ComponentType.defense, subtype=DefenseSubtype.shield, power=5)
    assert bundle_cost([heal], BAL) == 8  # ceil((5*1.1)**1.2)
    assert bundle_cost([shield], BAL) == 6  # ceil((5*0.8)**1.2)


def test_bundle_is_super_additive():
    a = EffectComponent(type=ComponentType.stat, stat=StatKind.power, magnitude=3, duration=2)
    b = EffectComponent(type=ComponentType.stat, stat=StatKind.speed, magnitude=3, duration=2)
    combined = bundle_cost([a, b], BAL)
    assert combined > bundle_cost([a], BAL)
    assert combined > bundle_cost([b], BAL)


def test_bundle_cost_capped_at_max():
    big = [
        EffectComponent(type=ComponentType.damage, power=10),
        EffectComponent(type=ComponentType.heal, power=10),
        EffectComponent(type=ComponentType.defense, subtype=DefenseSubtype.shield, power=10),
    ]
    assert bundle_cost(big, BAL) == BAL.max_bundle_cost


def test_empty_bundle_is_free():
    assert bundle_cost([], BAL) == 0


# ---------------------------------------------------------------------------
# kind_cooldowns: only heal/defense throttled; heavy bump
# ---------------------------------------------------------------------------


def test_kind_cooldowns_only_heal_and_defense():
    comps = [
        dmg(power=8),  # heavy but damage has no cooldown
        EffectComponent(type=ComponentType.heal, power=4),
        EffectComponent(type=ComponentType.defense, subtype=DefenseSubtype.shield, power=4),
    ]
    cds = kind_cooldowns(comps, BAL)
    assert cds == {"heal": 3, "defense": 1}


def test_kind_cooldowns_heavy_move_bump():
    comps = [EffectComponent(type=ComponentType.heal, power=9)]  # >= threshold 8
    assert kind_cooldowns(comps, BAL) == {"heal": 4}


def test_stat_and_dot_have_no_cooldown():
    comps = [
        EffectComponent(type=ComponentType.stat, stat=StatKind.power, magnitude=-4, duration=2),
        EffectComponent(type=ComponentType.dot, power=5, duration=3),
    ]
    assert kind_cooldowns(comps, BAL) == {}


# ---------------------------------------------------------------------------
# effective stats folded over the effect list
# ---------------------------------------------------------------------------


def test_effective_power_sums_additively():
    effects = [stat_eff("power", 3), stat_eff("power", 2)]
    assert effective_power(5, effects) == 10  # 5 + 3 + 2


def test_effective_power_floors_at_zero():
    assert effective_power(5, [stat_eff("power", -10)]) == 0


def test_effective_speed_floors_at_one():
    assert effective_speed(2, [stat_eff("speed", -9)]) == 1


def test_damage_taken_mult_multiplies_and_floors():
    armor = [stat_eff("damage_taken", -4), stat_eff("damage_taken", -4)]
    # (1-0.4)*(1-0.4) = 0.36
    assert damage_taken_mult(armor, BAL) == pytest.approx(0.36)
    heavy = [stat_eff("damage_taken", -8), stat_eff("damage_taken", -8)]
    assert damage_taken_mult(heavy, BAL) == BAL.damage_taken_mult_floor  # clamped


def test_damage_taken_mult_expose_increases():
    assert damage_taken_mult([stat_eff("damage_taken", 4)], BAL) == pytest.approx(1.4)


def test_damage_taken_mult_neutral_when_no_armor():
    assert damage_taken_mult([stat_eff("power", 3)], BAL) == 1.0


# ---------------------------------------------------------------------------
# type_multiplier (unchanged element chart)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "attacker,defender,expected",
    [
        ("fire", "nature", 1.5),
        ("nature", "fire", 0.75),
        ("water", "fire", 1.5),
        ("physical", "fire", 1.0),
        ("fire", "lightning", 1.0),
    ],
)
def test_type_multiplier(attacker, defender, expected):
    assert type_multiplier(Element(attacker), Element(defender), BAL) == expected
