"""Resolution matrix for the alternating single-action resolver (resolver.py).

Covers turn advancement, effect/cooldown timing (owner-turn, install-after-tick),
defenses-as-stance (frozen + consume-on-hit), all attack interactions, mana,
KO/round-cap, and the pure-function contract.
"""

from __future__ import annotations

import pytest
from app.config import load_balance
from app.models import ActiveDefense, ActiveEffect, GameState, JudgedAction, Outcome, PlayerState
from app.resolver import initial_game, resolve_turn

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


def player(hp=100, mana=10, name="P", cooldowns=None, buff=None, debuff=None, defense=None):
    return PlayerState(
        name=name,
        hp=hp,
        mana=mana,
        cooldowns=cooldowns or {},
        active_buff=buff,
        active_debuff=debuff,
        active_defense=defense,
    )


def state(p1=None, p2=None, active="p1", round=1):
    return GameState(
        round=round, active=active, p1=p1 or player(name="P1"), p2=p2 or player(name="P2")
    )


def turn(st, action):
    return resolve_turn(st, action, BAL)


def shield_stance(power=4, speed=5, element="physical"):
    return ActiveDefense(
        subtype="shield", element=element, power=power, speed=speed, turns_remaining=1
    )


_WEAK = act("attack", "melee", power=1, speed=1)


# ---------------------------------------------------------------------------
# Turn advancement
# ---------------------------------------------------------------------------


def test_p1_acts_then_p2_is_active():
    r = turn(state(active="p1"), act("attack", "melee", power=5))
    assert r.state.active == "p2"
    assert r.state.round == 1  # round completes after p2 acts
    assert r.state.p2.hp == 85  # 5*3 undefended
    assert r.events[0].actor == "p1" and r.events[0].target == "p2"


def test_round_advances_after_p2():
    r = turn(state(active="p2"), _WEAK)
    assert r.state.active == "p1"
    assert r.state.round == 2


def test_symmetric_for_p2():
    r = turn(state(active="p2"), act("attack", "melee", power=6))
    assert r.state.p1.hp == 82  # p2 hit p1
    assert r.events[0].actor == "p2" and r.events[0].target == "p1"


def test_guard_rejects_over_match():
    with pytest.raises(ValueError):
        turn(state(p2=player(hp=0, name="P2")), act("attack", "melee"))


# ---------------------------------------------------------------------------
# Attacks vs a defensive stance (frozen, consume-on-hit)
# ---------------------------------------------------------------------------


def test_attack_into_shield_partial_and_consumed():
    st = state(p2=player(name="P2", defense=shield_stance(power=4)))
    r = turn(st, act("attack", "melee", power=6))  # raw 18, block 12 -> 6
    assert r.state.p2.hp == 94
    assert r.events[0].outcome == Outcome.partial
    assert r.events[0].effect.kind == "shield" and r.events[0].effect.absorbed == 12
    assert r.state.p2.active_defense is None  # consumed


def test_shield_block_uses_frozen_power_not_current_buff():
    # p2 has a +10 power buff but the shield's block is frozen at cast (power 4).
    st = state(
        p2=player(
            name="P2",
            defense=shield_stance(power=4),
            buff=ActiveEffect(power_shift=10, turns_remaining=2),
        )
    )
    r = turn(st, act("attack", "melee", power=6))
    assert r.state.p2.hp == 94  # block still 12, not (4+10)*3


def test_dodge_fast_negates():
    st = state(
        p2=player(
            name="P2",
            defense=ActiveDefense(
                subtype="dodge", element="physical", power=3, speed=7, turns_remaining=1
            ),
        )
    )
    r = turn(st, act("attack", "melee", power=6, speed=5))
    assert r.state.p2.hp == 100
    assert r.events[0].outcome == Outcome.dodged


def test_dodge_slow_partial():
    st = state(
        p2=player(
            name="P2",
            defense=ActiveDefense(
                subtype="dodge", element="physical", power=3, speed=3, turns_remaining=1
            ),
        )
    )
    r = turn(st, act("attack", "melee", power=6, speed=7))
    assert r.state.p2.hp == 91  # round(18*0.5)=9


def test_reflect_win_returns_to_attacker():
    st = state(
        p2=player(
            name="P2",
            defense=ActiveDefense(
                subtype="reflect", element="physical", power=6, speed=5, turns_remaining=1
            ),
        )
    )
    r = turn(st, act("attack", "melee", power=6))  # 6>=6 -> return round(18*0.5)=9 to p1
    assert r.state.p2.hp == 100
    assert r.state.p1.hp == 91
    assert r.events[0].outcome == Outcome.reflected and r.events[0].target == "p1"


def test_reflect_self_ko():
    st = state(
        p1=player(hp=5, name="P1"),
        p2=player(
            name="P2",
            defense=ActiveDefense(
                subtype="reflect", element="physical", power=10, speed=5, turns_remaining=1
            ),
        ),
    )
    r = turn(st, act("attack", "melee", power=10))  # 30 raw -> return 15 to p1 (5 hp)
    assert r.match_over and r.winner == "p2"


def test_reflect_lose_absorbs_remainder():
    st = state(
        p2=player(
            name="P2",
            defense=ActiveDefense(
                subtype="reflect", element="physical", power=5, speed=5, turns_remaining=1
            ),
        )
    )
    r = turn(st, act("attack", "melee", power=8))  # 24 raw, absorb 15 -> 9
    assert r.state.p2.hp == 91
    assert r.events[0].outcome == Outcome.partial


def test_type_chart_on_shield():
    # fire(6) vs nature shield(2): typed 18*1.5=27, block 6 -> 21
    st = state(
        p2=player(name="P2", defense=shield_stance(power=2, element="nature")),
    )
    r = turn(st, act("attack", "melee", power=6, element="fire"))
    assert r.state.p2.hp == 79
    assert r.events[0].damage == 21


# ---------------------------------------------------------------------------
# Defense lifecycle (raise / expire unused)
# ---------------------------------------------------------------------------


def test_raise_shield_then_it_blocks_next_attack():
    r1 = turn(state(active="p1"), act("defense", "shield", power=5))
    assert r1.state.p1.active_defense is not None
    assert r1.state.p1.cooldowns.get("defense") == 1
    # p2 attacks into it
    r2 = turn(r1.state, act("attack", "melee", power=6))  # raw18, block 15 -> 3
    assert r2.state.p1.hp == 97
    assert r2.state.p1.active_defense is None  # consumed


def test_unused_shield_expires_by_owners_next_turn():
    r1 = turn(state(active="p1"), act("defense", "shield", power=5))  # p1 shields
    r2 = turn(r1.state, act("heal", "heal", power=3))  # p2 heals (doesn't attack)
    assert r2.state.p1.active_defense is not None  # still up during p2's turn
    r3 = turn(r2.state, _WEAK)  # p1 acts -> shield expires at upkeep
    assert r3.state.p1.active_defense is None
    r4 = turn(r3.state, act("attack", "melee", power=6))  # p2 attacks, no shield now
    assert r4.state.p1.hp == 100 - 18


# ---------------------------------------------------------------------------
# Effect timing (the crux): owner-turn, use-before-decrement
# ---------------------------------------------------------------------------


def test_buff_boosts_exactly_next_two_own_turns():
    r = turn(state(active="p1"), act("buff", "buff", power=5, stat="power"))  # cast (P1#1)
    assert r.state.p1.active_buff.turns_remaining == 2
    r = turn(r.state, _WEAK)  # P2#1
    r = turn(r.state, act("attack", "melee", power=5, speed=9))  # P1#2 -> boosted
    assert r.events[0].damage == 30 and r.state.p1.active_buff.turns_remaining == 1
    r = turn(r.state, _WEAK)  # P2#2
    r = turn(r.state, act("attack", "melee", power=5, speed=9))  # P1#3 -> boosted, expires
    assert r.events[0].damage == 30 and r.state.p1.active_buff is None
    r = turn(r.state, _WEAK)  # P2#3
    r = turn(r.state, act("attack", "melee", power=5, speed=9))  # P1#4 -> normal
    assert r.events[0].damage == 15


def test_debuff_weakens_opponents_next_two_turns():
    r = turn(state(active="p1"), act("debuff", "debuff", power=5, stat="power"))  # p1 debuffs p2
    assert r.state.p2.active_debuff.turns_remaining == 2
    r = turn(r.state, act("attack", "melee", power=5))  # P2#1 -> weakened, 5-5=0 dmg
    assert r.events[0].damage == 0
    r = turn(r.state, _WEAK)  # P1 pass
    r = turn(r.state, act("attack", "melee", power=5))  # P2#2 -> weakened, expires
    assert r.events[0].damage == 0 and r.state.p2.active_debuff is None
    r = turn(r.state, _WEAK)  # P1 pass
    r = turn(r.state, act("attack", "melee", power=5))  # P2#3 -> normal 15
    assert r.events[0].damage == 15


def test_buff_single_slot_replacement():
    st = state(p1=player(name="P1", buff=ActiveEffect(power_shift=3, turns_remaining=2)))
    r = turn(st, act("buff", "buff", power=7, stat="speed"))  # replaces
    assert r.state.p1.active_buff.power_shift == 0
    assert r.state.p1.active_buff.speed_shift == 7
    assert r.state.p1.active_buff.turns_remaining == 2


# ---------------------------------------------------------------------------
# Cooldowns (owner-turn, not decremented on cast turn)
# ---------------------------------------------------------------------------


def test_heal_cooldown_blocks_three_own_turns():
    r = turn(state(active="p1"), act("heal", "heal", power=4))  # cast
    assert r.state.p1.cooldowns.get("heal") == 3  # not decremented on cast turn
    r = turn(r.state, _WEAK)  # P2
    r = turn(r.state, act("attack", "melee", power=5, speed=9))  # P1 acts, cd ticks
    assert r.state.p1.cooldowns.get("heal") == 2
    r = turn(r.state, _WEAK)
    r = turn(r.state, act("attack", "melee", power=5, speed=9))
    assert r.state.p1.cooldowns.get("heal") == 1
    r = turn(r.state, _WEAK)
    r = turn(r.state, act("attack", "melee", power=5, speed=9))
    assert "heal" not in r.state.p1.cooldowns  # available again


def test_heavy_move_bumps_cooldown():
    r = turn(state(active="p1"), act("attack", "melee", power=8))  # heavy attack
    assert r.state.p1.cooldowns.get("attack") == 1


def test_defense_cooldown():
    r = turn(state(active="p1"), act("defense", "shield", power=5))
    assert r.state.p1.cooldowns.get("defense") == 1


# ---------------------------------------------------------------------------
# Attacks / heal edge cases
# ---------------------------------------------------------------------------


def test_undefended_is_neutral_regardless_of_element():
    r = turn(state(active="p1"), act("attack", "projectile", power=6, element="fire"))
    assert r.state.p2.hp == 82  # 18, no element bonus without a defender


def test_zero_effective_power_deals_no_damage():
    st = state(p1=player(name="P1", debuff=ActiveEffect(power_shift=10, turns_remaining=2)))
    r = turn(st, act("attack", "melee", power=5))  # eff power 0
    assert r.state.p2.hp == 100 and r.events[0].damage == 0


def test_heal_at_cap_applies_zero():
    r = turn(state(active="p1"), act("heal", "heal", power=10))  # already full
    assert r.state.p1.hp == 100
    assert r.events[0].effect.kind == "heal" and r.events[0].effect.magnitude == 0


def test_heal_restores_and_reports_applied():
    r = turn(state(p1=player(hp=80, name="P1"), active="p1"), act("heal", "heal", power=4))
    assert r.state.p1.hp == 90  # +round(4*2.5)=10
    assert r.events[0].effect.magnitude == 10


# ---------------------------------------------------------------------------
# Match-over & round cap
# ---------------------------------------------------------------------------


def test_attack_ko_ends_match():
    st = state(p2=player(hp=15, name="P2"))
    r = turn(st, act("attack", "melee", power=5))  # 15 -> 0
    assert r.match_over and r.winner == "p1"
    assert r.state.p2.hp == 0


def test_round_cap_tiebreak_at_boundary():
    st = state(p1=player(hp=80, name="P1"), p2=player(hp=60, name="P2"), active="p2", round=30)
    r = turn(st, _WEAK)  # p2 completes round 30 -> round 31 > cap
    assert r.match_over and r.winner == "p1"  # 77 vs 60


def test_hp_floors_at_zero():
    st = state(p2=player(hp=3, name="P2"))
    r = turn(st, act("attack", "melee", power=5))  # 15 dmg
    assert r.state.p2.hp == 0  # not negative


# ---------------------------------------------------------------------------
# Mana
# ---------------------------------------------------------------------------


def test_mana_cost_and_end_of_turn_regen():
    r = turn(state(active="p1"), act("attack", "melee", power=5))
    assert r.state.p1.mana == 6  # 10 - 7 + 3, displayed = spendable next turn


def test_mana_floors_at_zero():
    r = turn(state(p1=player(mana=2, name="P1"), active="p1"), act("attack", "melee", power=5))
    assert r.state.p1.mana == 3  # max(0, 2-7) + 3


# ---------------------------------------------------------------------------
# Pure-function contract
# ---------------------------------------------------------------------------


def test_input_not_mutated():
    st = state(p1=player(hp=50, mana=8, name="P1"), p2=player(hp=40, name="P2"), round=3)
    snapshot = st.model_dump()
    turn(st, act("attack", "melee", power=6))
    assert st.model_dump() == snapshot


def test_deterministic():
    st = state()
    a = act("attack", "melee", power=6)
    assert turn(st, a).events[0].model_dump() == turn(st, a).events[0].model_dump()


def test_initial_game():
    g = initial_game(BAL, "A", "B")
    assert g.round == 1 and g.active == "p1"
    assert g.p1.hp == 100 and g.p1.mana == 10 and g.p1.name == "A"
