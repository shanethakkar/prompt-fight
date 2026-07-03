"""Resolution matrix for the effect-grammar resolver (resolver.py).

Covers the three-phase turn (start-of-turn ticks + KO, act, end-of-turn upkeep),
over-time effects, stat stacking, the pinned damage pipeline, defensive stances
(frozen + consume-on-hit), mana/cooldowns, KO/round-cap, and the pure contract.
"""

from __future__ import annotations

import pytest
from app.config import load_balance
from app.models import (
    Action,
    ActiveEffect,
    Barrier,
    DefenseSubtype,
    EffectKind,
    Element,
    GameState,
    Outcome,
    SideState,
    StatKind,
    Template,
    Unit,
)
from app.resolver import initial_game, resolve_turn
from app.rules import normalize_components

BAL = load_balance()


# ---- builders ---------------------------------------------------------------


def action(*raw, element="physical", speed=5, template="projectile", flavor="fx"):
    return Action(
        components=normalize_components(list(raw), BAL),
        element=Element(element),
        speed=speed,
        template=Template(template),
        flavor_text=flavor,
    )


def player(hp=100, mana=10, name="P", cooldowns=None, effects=None):
    # A "side" whose only unit is its stickman (P3.0 — entities land in P3.1).
    return SideState(
        name=name,
        mana=mana,
        cooldowns=cooldowns or {},
        stickman=Unit(id="s", name=name, hp=hp, max_hp=BAL.hp_max, effects=effects or []),
    )


def state(p1=None, p2=None, active="p1", round=1):
    return GameState(
        round=round, active=active, p1=p1 or player(name="P1"), p2=p2 or player(name="P2")
    )


def turn(st, act):
    return resolve_turn(st, act, BAL)


def dot_eff(per_turn=5, turns=2, source="p1", element="physical"):
    return ActiveEffect(
        kind=EffectKind.dot,
        per_turn=per_turn,
        turns_remaining=turns,
        source=source,
        element=Element(element),
    )


def stat_eff(stat, magnitude, turns=2, source="p1"):
    return ActiveEffect(
        kind=EffectKind.stat,
        stat=StatKind(stat),
        magnitude=magnitude,
        turns_remaining=turns,
        source=source,
    )


def stance(subtype="shield", element="physical", power=4, speed=5, turns=1, source="p2"):
    return ActiveEffect(
        kind=EffectKind.defense,
        subtype=DefenseSubtype(subtype),
        element=Element(element),
        power=power,
        speed=speed,
        turns_remaining=turns,
        source=source,
    )


def control_eff(turns=1, source="p1"):
    return ActiveEffect(kind=EffectKind.control, turns_remaining=turns, source=source)


WEAK = action({"type": "damage", "power": 1})
DMG5 = {"type": "damage", "power": 5}
DMG6 = {"type": "damage", "power": 6}


# ---------------------------------------------------------------------------
# Turn advancement
# ---------------------------------------------------------------------------


def test_p1_acts_then_p2_is_active():
    r = turn(state(active="p1"), action(DMG5))
    assert r.state.active == "p2" and r.state.round == 1
    assert r.state.p2.stickman.hp == 85  # 5*3 undefended
    assert r.events[0].actor == "p1" and r.events[0].target == "p2"


def test_round_advances_after_p2():
    r = turn(state(active="p2"), WEAK)
    assert r.state.active == "p1" and r.state.round == 2


def test_symmetric_for_p2():
    r = turn(state(active="p2"), action(DMG6))
    assert r.state.p1.stickman.hp == 82
    assert r.events[0].actor == "p2" and r.events[0].target == "p1"


def test_guard_rejects_over_match():
    with pytest.raises(ValueError):
        turn(state(p2=player(hp=0, name="P2")), action(DMG5))


# ---------------------------------------------------------------------------
# Damage vs a defensive stance (frozen, consume-on-hit)
# ---------------------------------------------------------------------------


def test_attack_into_shield_partial_and_consumed():
    st = state(p2=player(name="P2", effects=[stance(power=4)]))
    r = turn(st, action(DMG6))  # raw 18, block 12 -> 6
    assert r.state.p2.stickman.hp == 94
    assert r.events[0].outcome == Outcome.partial
    assert r.events[0].effect.kind == "shield" and r.events[0].effect.absorbed == 12
    assert not any(e.kind is EffectKind.defense for e in r.state.p2.stickman.effects)  # consumed


def test_shield_block_uses_frozen_power_not_current_buff():
    # p2 has +10 power, but the shield's block is frozen at cast (power 4).
    st = state(p2=player(name="P2", effects=[stance(power=4), stat_eff("power", 10, source="p2")]))
    r = turn(st, action(DMG6))
    assert r.state.p2.stickman.hp == 94  # block still 12


def test_dodge_fast_negates():
    st = state(p2=player(name="P2", effects=[stance(subtype="dodge", power=3, speed=7)]))
    r = turn(st, action(DMG6, speed=5))
    assert r.state.p2.stickman.hp == 100 and r.events[0].outcome == Outcome.dodged


def test_dodge_slow_partial():
    st = state(p2=player(name="P2", effects=[stance(subtype="dodge", power=3, speed=3)]))
    r = turn(st, action(DMG6, speed=7))
    assert r.state.p2.stickman.hp == 91  # round(18*0.5)=9


def test_reflect_win_returns_to_attacker():
    st = state(p2=player(name="P2", effects=[stance(subtype="reflect", power=6)]))
    r = turn(st, action(DMG6))  # 6>=6 -> return round(18*0.5)=9 to p1
    assert r.state.p2.stickman.hp == 100 and r.state.p1.stickman.hp == 91
    assert r.events[0].outcome == Outcome.reflected and r.events[0].target == "p1"


def test_reflect_self_ko_in_bundle():
    st = state(
        p1=player(hp=5, name="P1"),
        p2=player(name="P2", effects=[stance(subtype="reflect", power=10)]),
    )
    r = turn(st, action({"type": "damage", "power": 10}))  # 30 raw -> 15 back to p1 (5 hp)
    assert r.match_over and r.winner == "p2"


def test_reflect_lose_absorbs_remainder():
    st = state(p2=player(name="P2", effects=[stance(subtype="reflect", power=5)]))
    r = turn(st, action({"type": "damage", "power": 8}))  # 24 raw, absorb 15 -> 9
    assert r.state.p2.stickman.hp == 91 and r.events[0].outcome == Outcome.partial


FIRE6 = {"type": "damage", "power": 6, "element": "fire"}


def test_type_chart_on_shield():
    # fire(6) vs nature shield(2): 18*1.5=27, block 6 -> 21
    st = state(p2=player(name="P2", effects=[stance(power=2, element="nature")]))
    r = turn(st, action(FIRE6))
    assert r.state.p2.stickman.hp == 79 and r.events[0].amount == 21


# ---------------------------------------------------------------------------
# Damage pipeline: armor (damage_taken) multiplies, order pinned
# ---------------------------------------------------------------------------


def test_armor_multiplies_before_shield_subtract():
    # power10 raw30, armor -4 => *0.6 = 18, shield block 12 -> 6
    st = state(p2=player(name="P2", effects=[stance(power=4), stat_eff("damage_taken", -4)]))
    r = turn(st, action({"type": "damage", "power": 10}))
    assert r.state.p2.stickman.hp == 94


def test_type_applies_before_armor():
    # fire6 vs nature shield2 + armor-4: 18*1.5*0.6=16.2, block 6 -> round(10.2)=10
    st = state(
        p2=player(
            name="P2", effects=[stance(power=2, element="nature"), stat_eff("damage_taken", -4)]
        )
    )
    r = turn(st, action(FIRE6))
    assert r.state.p2.stickman.hp == 90


def test_armor_reduces_undefended_hit_and_persists():
    st = state(p2=player(name="P2", effects=[stat_eff("damage_taken", -4, turns=3)]))
    r = turn(st, action(DMG6))  # 18*0.6 = 10.8 -> 11
    assert r.state.p2.stickman.hp == 89
    # armor still present on p2 (multi-hit); untouched on the attacker's turn
    assert any(e.stat is StatKind.damage_taken for e in r.state.p2.stickman.effects)


# ---------------------------------------------------------------------------
# Barrier: durability pool (absorbs until shattered, no timer, poison bypasses)
# ---------------------------------------------------------------------------


def barrier(pool=15, source="p2", element="physical"):
    return Barrier(pool=pool, source=source, element=Element(element))


def test_barrier_absorbs_then_overflows_and_shatters():
    st = state(
        p2=player(
            name="P2",
            effects=[],
        )
    )
    st.p2.stickman.barriers = [barrier(pool=10)]
    r = turn(st, action(DMG5))  # raw 15: absorb 10 + shatter, 5 to hp
    dmg = next(e for e in r.events if e.kind == "damage")
    assert dmg.amount == 5 and dmg.effect.barrier_absorbed == 10
    assert [e.kind for e in r.events] == ["damage", "barrier_shatter"]
    assert r.state.p2.stickman.hp == 95 and r.state.p2.stickman.barriers == []


def test_barrier_full_absorb_marks_blocked():
    st = state(p2=player(name="P2"))
    st.p2.stickman.barriers = [barrier(pool=20)]
    r = turn(st, action(DMG5))  # raw 15 fully soaked
    dmg = next(e for e in r.events if e.kind == "damage")
    assert dmg.amount == 0 and dmg.outcome == Outcome.blocked
    assert r.state.p2.stickman.hp == 100 and r.state.p2.stickman.barriers[0].pool == 5


def test_barrier_absorbs_reflected_hit_on_the_attacker():
    st = state(
        p1=player(hp=100, name="P1"),
        p2=player(name="P2", effects=[stance(subtype="reflect", power=10)]),
    )
    st.p1.stickman.barriers = [barrier(pool=20, source="p1")]  # attacker's own barrier
    r = turn(st, action({"type": "damage", "power": 10}))  # raw30 -> reflect 15 back to p1
    assert r.state.p1.stickman.hp == 100 and r.state.p1.stickman.barriers[0].pool == 5


def test_barrier_not_decremented_on_owner_turn():
    st = state(p1=player(name="P1"))
    st.p1.stickman.barriers = [barrier(pool=15, source="p1")]
    r = turn(st, action({"type": "heal", "power": 4}))  # p1 acts, isn't hit
    assert r.state.p1.stickman.barriers[0].pool == 15  # no timer, untouched


def test_barrier_survives_the_effects_cap():
    effs = [stat_eff("power", 1, turns=5) for _ in range(6)]  # fill the effects cap
    st = state(p1=player(name="P1", effects=effs))
    st.p1.stickman.barriers = [barrier(pool=12, source="p1")]
    r = turn(
        st,
        action({"type": "stat", "stat": "power", "magnitude": 2, "target": "self", "duration": 2}),
    )
    assert len(r.state.p1.stickman.barriers) == 1 and r.state.p1.stickman.barriers[0].pool == 12


def test_poison_bypasses_barrier():
    st = state(active="p2", p2=player(name="P2", effects=[dot_eff(per_turn=6)]))
    st.p2.stickman.barriers = [barrier(pool=20, source="p2")]
    r = turn(st, WEAK)  # p2's start tick
    assert r.events[0].kind == "dot_tick" and r.events[0].amount == 6
    assert (
        r.state.p2.stickman.hp == 94 and r.state.p2.stickman.barriers[0].pool == 20
    )  # pool untouched


def test_stance_then_barrier_layer():
    st = state(p2=player(name="P2", effects=[stance(power=2)]))
    st.p2.stickman.barriers = [barrier(pool=10)]
    r = turn(st, action(DMG6))  # raw18, shield blocks 6 -> 12, barrier soaks 10 -> 2 to hp
    dmg = next(e for e in r.events if e.kind == "damage")
    assert dmg.amount == 2 and dmg.effect.absorbed == 6 and dmg.effect.barrier_absorbed == 10
    assert r.state.p2.stickman.hp == 98


def test_barrier_install_staged_and_capped():
    st = state(p1=player(name="P1"))
    st.p1.stickman.barriers = [
        barrier(pool=5, source="p1"),
        barrier(pool=5, source="p1"),
    ]  # already 2
    r = turn(st, action({"type": "barrier", "power": 6}))  # pool 18, caps to newest 2
    assert len(r.state.p1.stickman.barriers) == 2
    assert r.state.p1.stickman.barriers[-1].pool == 18  # newest kept


# ---------------------------------------------------------------------------
# Over-time: dot / hot ticks, frozen magnitude, start-of-turn KO
# ---------------------------------------------------------------------------


def test_dot_ticks_on_afflicted_turn_then_decrements():
    st = state(active="p2", p2=player(name="P2", effects=[dot_eff(per_turn=5, turns=2)]))
    r = turn(st, WEAK)  # p2's turn: poison ticks at start
    assert r.events[0].kind == "dot_tick" and r.events[0].amount == 5
    assert r.state.p2.stickman.hp == 95
    remaining = [e for e in r.state.p2.stickman.effects if e.kind is EffectKind.dot]
    assert remaining[0].turns_remaining == 1  # decremented after use


def test_two_dots_both_tick():
    st = state(
        active="p2",
        p2=player(
            name="P2",
            effects=[dot_eff(per_turn=4, element="fire"), dot_eff(per_turn=3, element="nature")],
        ),
    )
    r = turn(st, WEAK)
    ticks = [e for e in r.events if e.kind == "dot_tick"]
    assert sorted(e.amount for e in ticks) == [3, 4]
    assert r.state.p2.stickman.hp == 100 - 7


def test_hot_ticks_and_caps():
    st = state(
        active="p2",
        p2=player(
            hp=96,
            name="P2",
            effects=[ActiveEffect(kind=EffectKind.hot, per_turn=6, turns_remaining=2, source="p2")],
        ),
    )
    r = turn(st, WEAK)
    assert r.state.p2.stickman.hp == 100  # +6 capped at 100 => +4 applied
    assert r.events[0].kind == "hot_tick" and r.events[0].amount == 4


def test_start_of_turn_poison_ko_awards_source():
    st = state(active="p2", p2=player(hp=3, name="P2", effects=[dot_eff(per_turn=5, source="p1")]))
    r = turn(st, action(DMG6))
    assert r.match_over and r.winner == "p1"
    assert [e.kind for e in r.events] == ["dot_tick"]  # died before acting
    assert r.state.p2.stickman.hp == 0


def test_dot_bypasses_the_afflicteds_own_stance():
    # p2 has poison AND raises a shield this turn; the poison still ticks.
    st = state(active="p2", p2=player(name="P2", effects=[dot_eff(per_turn=6)]))
    r = turn(st, action({"type": "defense", "subtype": "shield", "power": 5}))
    assert r.events[0].kind == "dot_tick" and r.state.p2.stickman.hp == 94


def test_dot_applied_to_opponent_not_decremented_on_cast_turn():
    r = turn(
        state(active="p1"), action({"type": "dot", "power": 5, "duration": 3, "element": "nature"})
    )
    dots = [e for e in r.state.p2.stickman.effects if e.kind is EffectKind.dot]
    assert dots[0].turns_remaining == 3  # full duration; opponent hasn't ticked yet
    assert dots[0].per_turn == 5  # frozen at application


# ---------------------------------------------------------------------------
# Stat effects: staging, additive stacking, floors
# ---------------------------------------------------------------------------


def test_self_buff_is_staged_and_boosts_next_turn_only():
    # empower + strike in one bundle: this turn's strike is NOT boosted (staged).
    r = turn(
        state(active="p1"),
        action(
            {"type": "stat", "stat": "power", "magnitude": 5, "target": "self", "duration": 2}, DMG5
        ),
    )
    strike = next(e for e in r.events if e.kind == "damage")
    assert strike.amount == 15  # unboosted this turn
    r = turn(r.state, WEAK)  # P2
    r = turn(r.state, action(DMG5))  # P1 again -> now boosted
    assert next(e for e in r.events if e.kind == "damage").amount == 30  # (5+5)*3


def test_two_weakens_additive_and_floor_zero():
    st = state(
        active="p2",
        p2=player(
            name="P2", effects=[stat_eff("power", -3, turns=3), stat_eff("power", -3, turns=3)]
        ),
    )
    r = turn(st, action(DMG5))  # eff power 5-6 -> floored 0
    assert next(e for e in r.events if e.kind == "damage").amount == 0


def test_weaken_persists_exactly_duration_on_opponent():
    r = turn(
        state(active="p1"),
        action({"type": "stat", "stat": "power", "magnitude": -5, "duration": 2}),
    )  # p1 weakens p2
    weak = [e for e in r.state.p2.stickman.effects if e.kind is EffectKind.stat]
    assert weak[0].turns_remaining == 2
    r = turn(r.state, action(DMG5))  # P2#1 weakened -> 0
    assert next(e for e in r.events if e.kind == "damage").amount == 0
    r = turn(r.state, WEAK)  # P1 filler
    r = turn(r.state, action(DMG5))  # P2#2 weakened, then expires
    assert next(e for e in r.events if e.kind == "damage").amount == 0
    assert not any(e.kind is EffectKind.stat for e in r.state.p2.stickman.effects)
    r = turn(r.state, WEAK)  # P1 filler
    r = turn(r.state, action(DMG5))  # P2#3 normal
    assert next(e for e in r.events if e.kind == "damage").amount == 15


# ---------------------------------------------------------------------------
# Heal
# ---------------------------------------------------------------------------


def test_heal_restores_and_reports():
    r = turn(state(p1=player(hp=80, name="P1"), active="p1"), action({"type": "heal", "power": 4}))
    assert r.state.p1.stickman.hp == 90 and r.events[0].amount == 10  # round(4*2.5)


def test_heal_at_cap_applies_zero():
    r = turn(state(active="p1"), action({"type": "heal", "power": 10}))
    assert r.state.p1.stickman.hp == 100 and r.events[0].amount == 0


# ---------------------------------------------------------------------------
# Defensive stance lifecycle
# ---------------------------------------------------------------------------


def test_raise_shield_then_it_blocks_next_attack():
    r1 = turn(state(active="p1"), action({"type": "defense", "subtype": "shield", "power": 5}))
    assert any(e.kind is EffectKind.defense for e in r1.state.p1.stickman.effects)
    assert r1.state.p1.cooldowns.get("defense") == 1
    r2 = turn(r1.state, action(DMG6))  # p2 attacks: raw18, block15 -> 3
    assert r2.state.p1.stickman.hp == 97
    assert not any(e.kind is EffectKind.defense for e in r2.state.p1.stickman.effects)


def test_unused_shield_expires_by_owners_next_turn():
    r1 = turn(state(active="p1"), action({"type": "defense", "subtype": "shield", "power": 5}))
    r2 = turn(r1.state, action({"type": "heal", "power": 3}))  # p2 doesn't attack
    assert any(e.kind is EffectKind.defense for e in r2.state.p1.stickman.effects)  # still up
    r3 = turn(r2.state, WEAK)  # p1 acts -> stance expires at upkeep
    assert not any(e.kind is EffectKind.defense for e in r3.state.p1.stickman.effects)


def test_new_stance_replaces_old():
    st = state(p1=player(name="P1", effects=[stance(subtype="dodge", source="p1", turns=1)]))
    r = turn(st, action({"type": "defense", "subtype": "shield", "power": 5}))
    stances = [e for e in r.state.p1.stickman.effects if e.kind is EffectKind.defense]
    assert len(stances) == 1 and stances[0].subtype is DefenseSubtype.shield


# ---------------------------------------------------------------------------
# Cooldowns (kind-keyed; not decremented on cast turn)
# ---------------------------------------------------------------------------


def test_heal_cooldown_blocks_three_own_turns():
    r = turn(state(active="p1"), action({"type": "heal", "power": 4}))
    assert r.state.p1.cooldowns.get("heal") == 3  # not decremented on cast turn
    for expected in (2, 1):
        r = turn(r.state, WEAK)  # P2
        r = turn(r.state, action(DMG5, speed=9))  # P1 ticks
        assert r.state.p1.cooldowns.get("heal") == expected
    r = turn(r.state, WEAK)
    r = turn(r.state, action(DMG5, speed=9))
    assert "heal" not in r.state.p1.cooldowns


def test_defense_cooldown_and_heavy_bump():
    r = turn(state(active="p1"), action({"type": "defense", "subtype": "shield", "power": 5}))
    assert r.state.p1.cooldowns.get("defense") == 1
    r = turn(state(active="p1"), action({"type": "heal", "power": 9}))  # heavy heal
    assert r.state.p1.cooldowns.get("heal") == 4


def test_damage_and_stat_have_no_cooldown():
    r = turn(state(active="p1"), action({"type": "damage", "power": 8}))
    assert r.state.p1.cooldowns == {}
    r = turn(
        state(active="p1"),
        action({"type": "stat", "stat": "power", "magnitude": -8, "duration": 2}),
    )
    assert r.state.p1.cooldowns == {}


# ---------------------------------------------------------------------------
# Mana
# ---------------------------------------------------------------------------


def test_mana_cost_and_end_of_turn_regen():
    r = turn(state(active="p1"), action(DMG5))  # cost 7
    assert r.state.p1.mana == 7  # 10 - 7 + 4 regen


def test_mana_floors_at_zero():
    r = turn(state(p1=player(mana=2, name="P1"), active="p1"), action(DMG5))
    assert r.state.p1.mana == 4  # max(0, 2-7) + 4 regen


# ---------------------------------------------------------------------------
# Match-over & round cap
# ---------------------------------------------------------------------------


def test_attack_ko_ends_match():
    r = turn(state(p2=player(hp=15, name="P2")), action(DMG5))
    assert r.match_over and r.winner == "p1" and r.state.p2.stickman.hp == 0


def test_round_cap_tiebreak_at_boundary():
    st = state(p1=player(hp=80, name="P1"), p2=player(hp=60, name="P2"), active="p2", round=30)
    r = turn(st, WEAK)  # p2 completes round 30 -> round 31 > cap
    assert r.match_over and r.winner == "p1"  # 77 vs 60


def test_hp_floors_at_zero():
    r = turn(state(p2=player(hp=3, name="P2")), action(DMG5))
    assert r.state.p2.stickman.hp == 0


# ---------------------------------------------------------------------------
# Control (stun): skip a turn, poison still bites, anti stun-lock immunity
# ---------------------------------------------------------------------------


def test_stun_skips_turn_and_ignores_submitted_action():
    st = state(active="p2", p2=player(name="P2", effects=[control_eff(turns=1)]))
    r = turn(st, action({"type": "damage", "power": 9}))  # attack ignored while stunned
    assert any(e.kind == "stun_skip" for e in r.events)
    assert r.state.p1.stickman.hp == 100  # the submitted attack never landed
    assert not any(
        e.kind is EffectKind.control for e in r.state.p2.stickman.effects
    )  # 1-turn stun expired
    assert r.state.p2.stickman.stun_immunity == BAL.stun_immunity_turns


def test_stun_duration_two_skips_two_turns():
    st = state(active="p2", p2=player(name="P2", effects=[control_eff(turns=2)]))
    r = turn(st, None)  # skip #1
    assert any(e.kind == "stun_skip" for e in r.events)
    r = turn(r.state, WEAK)  # p1 filler
    r = turn(r.state, None)  # skip #2
    assert any(e.kind == "stun_skip" for e in r.events)
    assert not any(e.kind is EffectKind.control for e in r.state.p2.stickman.effects)


def test_stunned_player_still_dies_to_poison():
    st = state(
        active="p2",
        p2=player(
            hp=3, name="P2", effects=[dot_eff(per_turn=5, source="p1"), control_eff(turns=1)]
        ),
    )
    r = turn(st, None)
    assert r.match_over and r.winner == "p1"
    assert [e.kind for e in r.events] == ["dot_tick"]  # died at start, before the stun beat


def test_mana_regens_while_stunned():
    st = state(active="p2", p2=player(mana=5, name="P2", effects=[control_eff(turns=1)]))
    r = turn(st, None)
    assert r.state.p2.mana == 5 + BAL.mana_regen_per_turn


def test_stun_immunity_blocks_a_restun():
    st = state()
    st.p2.stickman.stun_immunity = 2
    r = turn(st, action({"type": "control", "duration": 1}))  # p1 tries to stun an immune p2
    assert next(e for e in r.events if e.kind == "control").outcome == Outcome.fizzled
    assert not any(e.kind is EffectKind.control for e in r.state.p2.stickman.effects)


def test_cannot_stun_an_already_stunned_target():
    st = state(p2=player(name="P2", effects=[control_eff(turns=1, source="p1")]))
    r = turn(st, action({"type": "control", "duration": 1}))
    assert next(e for e in r.events if e.kind == "control").outcome == Outcome.fizzled


def test_skip_none_action_passes_turn():
    r = turn(state(active="p1"), None)  # not stunned, just a skip
    assert r.state.active == "p2" and any(e.kind == "fizzle" for e in r.events)


def test_stun_lands_full_duration_on_opponent():
    r = turn(state(active="p1"), action({"type": "control", "duration": 2}))
    ctrl = [e for e in r.state.p2.stickman.effects if e.kind is EffectKind.control]
    assert ctrl and ctrl[0].turns_remaining == 2


# ---------------------------------------------------------------------------
# Multi-event playback ordering + pure-function contract
# ---------------------------------------------------------------------------


def test_start_tick_precedes_action_event():
    st = state(active="p2", p2=player(name="P2", effects=[dot_eff(per_turn=5)]))
    r = turn(st, action(DMG6))
    assert [e.kind for e in r.events] == ["dot_tick", "damage"]


def test_bundle_emits_one_event_per_component():
    r = turn(
        state(active="p1"),
        action({"type": "heal", "power": 4}, {"type": "defense", "subtype": "shield", "power": 4}),
    )
    assert [e.kind for e in r.events] == ["heal", "defense"]
    assert r.events[0].narration == "fx"  # flavor on the primary beat only
    assert r.events[1].narration == ""


def test_input_not_mutated():
    st = state(
        p1=player(hp=50, mana=8, name="P1", effects=[stat_eff("power", 3, source="p1")]),
        p2=player(hp=40, name="P2", effects=[dot_eff(per_turn=4)]),
        round=3,
    )
    snapshot = st.model_dump()
    turn(st, action(DMG6))
    assert st.model_dump() == snapshot


def test_deterministic():
    st = state()
    a = action(DMG6)
    assert turn(st, a).events[0].model_dump() == turn(st, a).events[0].model_dump()


def test_initial_game():
    g = initial_game(BAL, "A", "B")
    assert g.round == 1 and g.active == "p1"
    assert g.p1.stickman.hp == 100 and g.p1.mana == 12 and g.p1.name == "A"
    assert g.p1.stickman.effects == [] and g.p1.cooldowns == {}
