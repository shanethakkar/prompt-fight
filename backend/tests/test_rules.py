"""Unit tests for the pure rule helpers (rules.py)."""

from __future__ import annotations

import pytest
from app.config import load_balance
from app.models import ActiveEffect, Element, JudgedAction
from app.rules import (
    buff_shift,
    category_cooldown,
    effective_power,
    effective_speed,
    mana_cost,
    type_multiplier,
)

BAL = load_balance()


def _act(category, subtype, power=5, speed=5, element="physical", stat=None):
    return JudgedAction(
        category=category,
        subtype=subtype,
        power=power,
        speed=speed,
        element=element,
        stat=stat,
    )


# ---- mana_cost: ceil(power ** cost_exponent * category_multiplier) -----------


@pytest.mark.parametrize(
    "category,subtype,power,expected",
    [
        ("attack", "projectile", 1, 1),
        ("attack", "projectile", 5, 7),
        ("attack", "projectile", 10, 16),
        ("heal", "heal", 5, 8),
        ("heal", "heal", 10, 18),
        ("defense", "shield", 5, 6),
        ("defense", "shield", 10, 13),
        ("buff", "buff", 5, 7),
        ("debuff", "debuff", 5, 7),
    ],
)
def test_mana_cost(category, subtype, power, expected):
    assert mana_cost(_act(category, subtype, power=power), BAL) == expected


def test_mana_cost_ignores_buffs():
    # Cost is from base power; effective power is irrelevant here.
    assert mana_cost(_act("attack", "melee", power=5), BAL) == 7


# ---- type_multiplier ---------------------------------------------------------


@pytest.mark.parametrize(
    "attacker,defender,expected",
    [
        ("fire", "nature", 1.5),  # fire > nature
        ("nature", "fire", 0.75),  # reverse
        ("water", "fire", 1.5),  # water > fire
        ("fire", "water", 0.75),  # reverse
        ("nature", "water", 1.5),  # nature > water
        ("lightning", "water", 1.5),  # lightning > water
        ("nature", "lightning", 1.5),  # nature > lightning (grounding)
        ("lightning", "nature", 0.75),  # reverse
        ("physical", "fire", 1.0),  # physical neutral everywhere
        ("fire", "physical", 1.0),
        ("fire", "lightning", 1.0),  # unrelated
    ],
)
def test_type_multiplier(attacker, defender, expected):
    assert type_multiplier(Element(attacker), Element(defender), BAL) == expected


# ---- effective stats + clamping ---------------------------------------------


def test_effective_power_buff_and_debuff():
    a = _act("attack", "melee", power=5)
    assert effective_power(a, ActiveEffect(power_shift=3, turns_remaining=1), None) == 8
    assert effective_power(a, None, ActiveEffect(power_shift=2, turns_remaining=1)) == 3


def test_effective_power_floors_at_zero():
    a = _act("attack", "melee", power=5)
    huge = ActiveEffect(power_shift=10, turns_remaining=1)
    assert effective_power(a, None, huge) == 0


def test_effective_speed_floors_at_one():
    a = _act("attack", "melee", power=5, speed=2)
    huge = ActiveEffect(speed_shift=5, turns_remaining=1)
    assert effective_speed(a, None, huge) == 1


def test_buff_shift_from_power():
    assert buff_shift(_act("buff", "buff", power=5), BAL) == 5
    assert buff_shift(_act("buff", "buff", power=7), BAL) == 7


# ---- category_cooldown incl. heavy-move rule ---------------------------------


def test_category_cooldown_base():
    assert category_cooldown(_act("attack", "melee", power=5), BAL) == 0
    assert category_cooldown(_act("heal", "heal", power=5), BAL) == 3
    assert category_cooldown(_act("defense", "shield", power=5), BAL) == 1


def test_heavy_move_adds_cooldown():
    # power >= 8 adds +1 to the category cooldown.
    assert category_cooldown(_act("attack", "melee", power=8), BAL) == 1
    assert category_cooldown(_act("heal", "heal", power=9), BAL) == 4
