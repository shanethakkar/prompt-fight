"""Full resolution matrix for the pure resolver (resolver.py).

Covers ordering/KO, snapshot-delta simultaneity, all defense interactions, the
type-chart pipeline, buff/debuff timing, cooldowns, mana, tiebreaks, and the
pure-function contract (immutability + determinism).
"""

from __future__ import annotations

from app.config import load_balance
from app.models import ActiveEffect, Category, GameState, JudgedAction, Outcome, PlayerState
from app.resolver import initial_game, resolve

BAL = load_balance()


def act(category, subtype, power=5, speed=5, element="physical", stat=None, flavor="fx"):
    return JudgedAction(
        category=category,
        subtype=subtype,
        power=power,
        speed=speed,
        element=element,
        stat=stat,
        flavor_text=flavor,
    )


def player(hp=100, mana=10, name="P", cooldowns=None, buff=None, debuff=None):
    return PlayerState(
        name=name,
        hp=hp,
        mana=mana,
        cooldowns=cooldowns or {},
        active_buff=buff,
        active_debuff=debuff,
    )


def state(p1=None, p2=None, turn=1):
    return GameState(turn=turn, p1=p1 or player(name="P1"), p2=p2 or player(name="P2"))


def _p1_event(result):
    return next(e for e in result.events if e.actor == "p1")


def _weak():
    return act("attack", "melee", power=1, speed=1)


# ---------------------------------------------------------------------------
# Ordering & KO
# ---------------------------------------------------------------------------


def test_faster_resolves_first():
    r = resolve(state(), act("attack", "melee", power=5, speed=8), _weak(), BAL)
    assert [e.actor for e in r.events] == ["p1", "p2"]
    assert r.state.p2.hp == 85  # 5*3 undefended
    assert r.state.p1.hp == 97  # p2's weak 1*3


def test_undefended_is_neutral_regardless_of_element():
    r = resolve(
        state(),
        act("attack", "projectile", power=6, speed=8, element="fire"),
        _weak(),
        BAL,
    )
    assert r.state.p2.hp == 82  # 6*3 = 18, no element bonus without a defender


def test_ko_skips_slower_action():
    r = resolve(
        state(p2=player(hp=20, name="P2")),
        act("attack", "melee", power=10, speed=8),
        act("attack", "melee", power=10, speed=2),
        BAL,
    )
    assert r.match_over and r.winner == "p1"
    assert r.state.p1.hp == 100  # slower attack never landed
    assert [(e.actor, e.outcome) for e in r.events] == [
        ("p1", Outcome.hit_knockback),
        ("p2", Outcome.fizzled),
    ]


def test_simultaneous_double_ko_is_draw():
    r = resolve(
        state(p1=player(hp=25, name="P1"), p2=player(hp=25, name="P2")),
        act("attack", "melee", power=10, speed=5),
        act("attack", "melee", power=10, speed=5),
        BAL,
    )
    assert r.match_over and r.winner == "draw"


def test_asymmetric_double_ko_less_overkill_wins():
    # p1 deals 30 (p2 -> -20); p2 deals 15 (p1 -> -5). p1 less negative -> wins.
    r = resolve(
        state(p1=player(hp=10, name="P1"), p2=player(hp=10, name="P2")),
        act("attack", "melee", power=10, speed=5),
        act("attack", "melee", power=5, speed=5),
        BAL,
    )
    assert r.match_over and r.winner == "p1"


def test_exact_lethal_zero_is_ko():
    r = resolve(
        state(p2=player(hp=15, name="P2")),
        act("attack", "melee", power=5, speed=8),
        act("heal", "heal", power=1, speed=1),
        BAL,
    )
    assert r.match_over and r.winner == "p1"
    assert r.state.p2.hp == 0  # slower heal fizzled


# ---------------------------------------------------------------------------
# Snapshot-delta simultaneity
# ---------------------------------------------------------------------------


def test_simultaneous_heal_survives_lethal():
    # p1 at 20: +25 heal and -30 damage in the same tick -> net -5 -> 15, alive.
    r = resolve(
        state(p1=player(hp=20, name="P1")),
        act("heal", "heal", power=10, speed=5),
        act("attack", "melee", power=10, speed=5),
        BAL,
    )
    assert not r.match_over
    assert r.state.p1.hp == 15


def test_simultaneous_heal_at_cap_is_snapshot_delta():
    # Full HP, +10 heal and -30 damage simultaneously -> 80 (not 70 from heal-first).
    r = resolve(
        state(p1=player(hp=100, name="P1")),
        act("heal", "heal", power=4, speed=5),
        act("attack", "melee", power=10, speed=5),
        BAL,
    )
    assert r.state.p1.hp == 80


# ---------------------------------------------------------------------------
# Defense interactions
# ---------------------------------------------------------------------------


def test_shield_full_block():
    r = resolve(
        state(),
        act("attack", "melee", power=5, speed=5),
        act("defense", "shield", power=5, speed=5),
        BAL,
    )
    assert r.state.p2.hp == 100
    assert _p1_event(r).outcome == Outcome.blocked
    assert _p1_event(r).damage == 0


def test_shield_partial_block():
    r = resolve(
        state(),
        act("attack", "melee", power=6, speed=5),
        act("defense", "shield", power=3, speed=5),
        BAL,
    )
    assert r.state.p2.hp == 91  # 18 - 9
    assert _p1_event(r).outcome == Outcome.partial


def test_shield_floors_at_zero():
    r = resolve(
        state(),
        act("attack", "melee", power=2, speed=5),
        act("defense", "shield", power=5, speed=5),
        BAL,
    )
    assert r.state.p2.hp == 100  # 6 - 15 -> floor 0


def test_dodge_fast_negates():
    r = resolve(
        state(),
        act("attack", "melee", power=6, speed=5),
        act("defense", "dodge", power=3, speed=7),
        BAL,
    )
    assert r.state.p2.hp == 100
    assert _p1_event(r).outcome == Outcome.dodged


def test_dodge_slow_takes_partial():
    r = resolve(
        state(),
        act("attack", "melee", power=6, speed=7),
        act("defense", "dodge", power=3, speed=3),
        BAL,
    )
    assert r.state.p2.hp == 91  # round(18 * 0.5) = 9
    assert _p1_event(r).outcome == Outcome.partial


def test_reflect_win_returns_to_attacker():
    r = resolve(
        state(),
        act("attack", "melee", power=6, speed=5),
        act("defense", "reflect", power=6, speed=5),
        BAL,
    )
    assert r.state.p2.hp == 100  # reflector unharmed
    assert r.state.p1.hp == 91  # attacker took round(18 * 0.5) = 9
    assert _p1_event(r).outcome == Outcome.reflected
    assert _p1_event(r).damage == 9


def test_reflect_self_ko():
    r = resolve(
        state(p1=player(hp=10, name="P1")),
        act("attack", "melee", power=10, speed=5),
        act("defense", "reflect", power=10, speed=5),
        BAL,
    )
    assert r.match_over and r.winner == "p2"


def test_reflect_lose_absorbs_remainder():
    r = resolve(
        state(),
        act("attack", "melee", power=8, speed=5),
        act("defense", "reflect", power=5, speed=5),
        BAL,
    )
    assert r.state.p2.hp == 91  # 24 - 15 = 9
    assert _p1_event(r).outcome == Outcome.partial


def test_reflect_lose_remainder_floors_zero():
    # water(5) vs nature reflect(4): typed 15*0.75=11.25, absorb 12 -> floor 0.
    r = resolve(
        state(),
        act("attack", "melee", power=5, speed=5, element="water"),
        act("defense", "reflect", power=4, speed=5, element="nature"),
        BAL,
    )
    assert r.state.p2.hp == 100
    assert _p1_event(r).outcome == Outcome.blocked


def test_both_defend_no_damage():
    r = resolve(
        state(),
        act("defense", "shield", power=5, speed=5),
        act("defense", "shield", power=5, speed=5),
        BAL,
    )
    assert r.state.p1.hp == 100 and r.state.p2.hp == 100
    assert len(r.events) == 2
    assert all(e.outcome == Outcome.defended for e in r.events)
    assert r.state.p1.cooldowns.get(Category.defense) == 1


def test_defense_events_come_first():
    r = resolve(
        state(),
        act("defense", "shield", power=5, speed=1),
        act("attack", "melee", power=6, speed=9),
        BAL,
    )
    assert r.events[0].actor == "p1" and r.events[0].outcome == Outcome.defended
    assert r.state.p1.hp == 97  # 18 raw - 15 shield block = 3 damage


# ---------------------------------------------------------------------------
# Type chart (pipeline order + scope)
# ---------------------------------------------------------------------------


def test_type_advantage_vs_shield_is_type_then_block():
    # fire(6) vs nature shield(2): typed 18*1.5=27, block 6 -> 21 (NOT (18-6)*1.5=18).
    r = resolve(
        state(),
        act("attack", "melee", power=6, speed=5, element="fire"),
        act("defense", "shield", power=2, speed=5, element="nature"),
        BAL,
    )
    assert r.state.p2.hp == 79
    assert _p1_event(r).damage == 21


def test_type_disadvantage_vs_shield():
    # water(4) vs nature shield(2): typed 12*0.75=9, block 6 -> 3.
    r = resolve(
        state(),
        act("attack", "melee", power=4, speed=5, element="water"),
        act("defense", "shield", power=2, speed=5, element="nature"),
        BAL,
    )
    assert r.state.p2.hp == 97


def test_type_neutral_vs_shield():
    r = resolve(
        state(),
        act("attack", "melee", power=6, speed=5, element="physical"),
        act("defense", "shield", power=2, speed=5, element="physical"),
        BAL,
    )
    assert r.state.p2.hp == 88  # 18 - 6


def test_type_applies_to_dodge_partial():
    # fire(4) vs nature dodge(slow): typed 12*1.5=18, partial round(18*0.5)=9.
    r = resolve(
        state(),
        act("attack", "melee", power=4, speed=7, element="fire"),
        act("defense", "dodge", power=3, speed=3, element="nature"),
        BAL,
    )
    assert r.state.p2.hp == 91


# ---------------------------------------------------------------------------
# Buffs & debuffs (timing, stat, staging, replacement)
# ---------------------------------------------------------------------------


def test_buff_power_raises_next_attack():
    r1 = resolve(
        state(),
        act("buff", "buff", power=5, speed=5, stat="power"),
        _weak(),
        BAL,
    )
    assert r1.state.p1.active_buff is not None
    assert r1.state.p1.active_buff.power_shift == 5
    assert r1.state.p1.active_buff.turns_remaining == 2

    r2 = resolve(r1.state, act("attack", "melee", power=5, speed=9), _weak(), BAL)
    assert _p1_event(r2).damage == 30  # effective power 10 -> 30


def test_buff_bites_exactly_next_two_turns():
    r1 = resolve(state(), act("buff", "buff", power=5, speed=5, stat="power"), _weak(), BAL)
    assert r1.state.p1.active_buff.turns_remaining == 2

    r2 = resolve(r1.state, act("attack", "melee", power=5, speed=9), _weak(), BAL)
    assert _p1_event(r2).damage == 30
    assert r2.state.p1.active_buff.turns_remaining == 1

    r3 = resolve(r2.state, act("attack", "melee", power=5, speed=9), _weak(), BAL)
    assert _p1_event(r3).damage == 30
    assert r3.state.p1.active_buff is None  # dropped after T+2 upkeep

    r4 = resolve(r3.state, act("attack", "melee", power=5, speed=9), _weak(), BAL)
    assert _p1_event(r4).damage == 15  # buff gone


def test_buff_speed_reorders_next_turn():
    r1 = resolve(state(), act("buff", "buff", power=5, speed=5, stat="speed"), _weak(), BAL)
    assert r1.state.p1.active_buff.speed_shift == 5
    # base speed 5 + 5 = 10 now beats p2's 7.
    r2 = resolve(
        r1.state,
        act("attack", "melee", power=5, speed=5),
        act("attack", "melee", power=5, speed=7),
        BAL,
    )
    assert [e.actor for e in r2.events][0] == "p1"


def test_debuff_does_not_weaken_same_turn():
    # p1 debuffs first (speed 9); p2's same-turn attack still lands at full power.
    r1 = resolve(
        state(),
        act("debuff", "debuff", power=5, speed=9, stat="power"),
        act("attack", "melee", power=5, speed=5),
        BAL,
    )
    p2_ev = next(e for e in r1.events if e.actor == "p2")
    assert p2_ev.damage == 15
    assert r1.state.p2.active_debuff.power_shift == 5

    r2 = resolve(
        r1.state,
        _weak(),
        act("attack", "melee", power=5, speed=5),
        BAL,
    )
    assert next(e for e in r2.events if e.actor == "p2").damage == 0  # 5 - 5 -> 0


def test_debuffed_to_zero_still_costs_mana():
    r = resolve(
        state(p2=player(name="P2", debuff=ActiveEffect(power_shift=10, turns_remaining=2))),
        _weak(),
        act("attack", "melee", power=5, speed=5),
        BAL,
    )
    assert next(e for e in r.events if e.actor == "p2").damage == 0
    assert r.state.p2.mana == 6  # 10 - 7 (base-power cost) + 3 regen


def test_debuff_speed_reorders():
    r = resolve(
        state(p2=player(name="P2", debuff=ActiveEffect(speed_shift=5, turns_remaining=2))),
        act("attack", "melee", power=5, speed=5),
        act("attack", "melee", power=5, speed=7),
        BAL,
    )
    assert [e.actor for e in r.events][0] == "p1"  # p2 slowed 7 -> 2


def test_buff_single_slot_replacement():
    r = resolve(
        state(p1=player(name="P1", buff=ActiveEffect(power_shift=3, turns_remaining=2))),
        act("buff", "buff", power=7, speed=5, stat="speed"),
        _weak(),
        BAL,
    )
    assert r.state.p1.active_buff.power_shift == 0
    assert r.state.p1.active_buff.speed_shift == 7
    assert r.state.p1.active_buff.turns_remaining == 2


# ---------------------------------------------------------------------------
# Cooldowns
# ---------------------------------------------------------------------------


def test_defense_cooldown_blocks_one_turn():
    r1 = resolve(state(), act("defense", "shield", power=5, speed=5), _weak(), BAL)
    assert r1.state.p1.cooldowns.get(Category.defense) == 1
    r2 = resolve(r1.state, act("attack", "melee", power=5, speed=5), _weak(), BAL)
    assert Category.defense not in r2.state.p1.cooldowns  # ticked to 0, available T+2


def test_new_cooldown_not_decremented_on_cast_turn():
    r = resolve(state(), act("heal", "heal", power=5, speed=5), _weak(), BAL)
    assert r.state.p1.cooldowns.get(Category.heal) == 3


def test_heavy_move_bumps_attack_cooldown():
    r = resolve(state(), act("attack", "melee", power=8, speed=5), _weak(), BAL)
    assert r.state.p1.cooldowns.get(Category.attack) == 1


def test_heavy_move_bumps_heal_cooldown():
    r = resolve(state(), act("heal", "heal", power=8, speed=5), _weak(), BAL)
    assert r.state.p1.cooldowns.get(Category.heal) == 4


# ---------------------------------------------------------------------------
# Mana
# ---------------------------------------------------------------------------


def test_mana_deduction_and_regen():
    r = resolve(
        state(),
        act("attack", "melee", power=5, speed=5),
        act("attack", "melee", power=5, speed=5),
        BAL,
    )
    assert r.state.p1.mana == 6 and r.state.p2.mana == 6  # 10 - 7 + 3


def test_mana_floors_at_zero():
    r = resolve(
        state(p1=player(mana=2, name="P1")),
        act("attack", "melee", power=5, speed=5),
        _weak(),
        BAL,
    )
    assert r.state.p1.mana == 3  # max(0, 2 - 7) + 3


def test_mana_regen_caps_at_max():
    r = resolve(
        state(p1=player(mana=19, name="P1")),
        act("attack", "melee", power=1, speed=5),
        _weak(),
        BAL,
    )
    assert r.state.p1.mana == 20  # 19 - 1 + 3 -> cap 20


def test_initial_game_defaults():
    g = initial_game(BAL, "A", "B")
    assert g.turn == 1
    assert g.p1.hp == 100 and g.p1.mana == 10
    assert g.p2.hp == 100 and g.p2.mana == 10


# ---------------------------------------------------------------------------
# Heal cap & tiebreaks
# ---------------------------------------------------------------------------


def test_heal_caps_at_max():
    r = resolve(
        state(p1=player(hp=90, name="P1")),
        act("heal", "heal", power=10, speed=9),
        act("defense", "shield", power=3, speed=5),
        BAL,
    )
    assert r.state.p1.hp == 100  # 90 + 25 -> cap 100, no incoming damage


def test_max_turn_cap_tiebreak():
    r = resolve(
        state(p1=player(hp=80, name="P1"), p2=player(hp=60, name="P2"), turn=30),
        act("attack", "melee", power=1, speed=5),
        act("attack", "melee", power=1, speed=5),
        BAL,
    )
    assert r.match_over and r.winner == "p1"  # 77 vs 57


# ---------------------------------------------------------------------------
# Pure-function contract
# ---------------------------------------------------------------------------


def test_input_state_not_mutated():
    s0 = state(
        p1=player(hp=50, mana=8, name="P1"),
        p2=player(hp=40, mana=8, name="P2"),
        turn=3,
    )
    snapshot = s0.model_dump()
    resolve(
        s0, act("attack", "melee", power=6, speed=8), act("attack", "melee", power=6, speed=2), BAL
    )
    assert s0.model_dump() == snapshot


def test_deterministic_and_p1_before_p2_on_tie():
    s0 = state()
    a1 = act("attack", "melee", power=5, speed=5)
    a2 = act("attack", "melee", power=6, speed=5)
    r1 = resolve(s0, a1, a2, BAL)
    r2 = resolve(s0, a1, a2, BAL)
    assert [e.model_dump() for e in r1.events] == [e.model_dump() for e in r2.events]
    assert [e.actor for e in r1.events] == ["p1", "p2"]
