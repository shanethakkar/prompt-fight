"""The pure combat resolver — the server-authoritative heart of the game.

`resolve(state, p1_action, p2_action, balance)` is a pure function: no I/O, input
state untouched (deep-copied), deterministic output. It implements the rules in
GAME_MECHANICS.md §7 exactly. See the M1 design notes for the pinned decisions:
signed HP, snapshot-delta simultaneity, fixed damage pipeline, effect/cooldown
staging, and deterministic (p1-before-p2) event ordering.
"""

from __future__ import annotations

from typing import Literal

from app.config import BalanceConfig
from app.models import (
    ActiveEffect,
    Category,
    GameState,
    JudgedAction,
    Outcome,
    PlayerState,
    ResolutionEvent,
    ResolveResult,
    Stat,
    Subtype,
)
from app.rules import (
    buff_shift,
    category_cooldown,
    effective_power,
    effective_speed,
    is_defense,
    mana_cost,
    type_multiplier,
)

PID = Literal["p1", "p2"]
_OPPONENT: dict[str, PID] = {"p1": "p2", "p2": "p1"}


def initial_game(
    balance: BalanceConfig,
    p1_name: str = "Player 1",
    p2_name: str = "Player 2",
) -> GameState:
    """Build a fresh match state from balance defaults."""

    def _player(name: str) -> PlayerState:
        return PlayerState(name=name, hp=balance.hp_start, mana=balance.mana_start)

    return GameState(turn=1, p1=_player(p1_name), p2=_player(p2_name))


def _display_state(players: dict[str, PlayerState], balance: BalanceConfig) -> dict[str, int]:
    """Post-event snapshot for the renderer: HP floored to [0, max], mana as-is."""
    return {
        "p1_hp": max(0, min(balance.hp_max, players["p1"].hp)),
        "p2_hp": max(0, min(balance.hp_max, players["p2"].hp)),
        "p1_mana": players["p1"].mana,
        "p2_mana": players["p2"].mana,
    }


def _event(
    pid: PID,
    action: JudgedAction,
    outcome: Outcome,
    damage: int,
    players: dict[str, PlayerState],
    balance: BalanceConfig,
) -> ResolutionEvent:
    assert action.template is not None  # normalized in JudgedAction validator
    return ResolutionEvent(
        actor=pid,
        template=action.template,
        outcome=outcome,
        damage=damage,
        narration=action.flavor_text,
        state_delta=_display_state(players, balance),
    )


def _attack_plan(
    atk_pid: PID,
    opp_pid: PID,
    actions: dict[str, JudgedAction],
    eff_power: dict[str, int],
    eff_speed: dict[str, int],
    defenders: set[str],
    balance: BalanceConfig,
) -> tuple[PID, int, Outcome, int]:
    """Resolve an attack to (target, signed_hp_delta, outcome, damage_to_show).

    Fixed pipeline: raw = eff_power x dmg_mult; x type chart (only vs a defending
    element); then mitigation on the typed value; floor 0.
    """
    atk = actions[atk_pid]
    raw = eff_power[atk_pid] * balance.attack_damage_multiplier

    if opp_pid not in defenders:
        # Undefended: elements are inert (no defender element), so neutral x1.0.
        dmg = max(0, round(raw))
        return opp_pid, -dmg, Outcome.hit_knockback, dmg

    defense = actions[opp_pid]
    typed = raw * type_multiplier(atk.element, defense.element, balance)

    if defense.subtype == Subtype.shield:
        block = eff_power[opp_pid] * balance.block_multiplier
        dmg = max(0, round(typed - block))
        outcome = Outcome.blocked if dmg == 0 else Outcome.partial
        return opp_pid, -dmg, outcome, dmg

    if defense.subtype == Subtype.dodge:
        if eff_speed[opp_pid] >= eff_speed[atk_pid]:
            return opp_pid, 0, Outcome.dodged, 0
        dmg = max(0, round(typed * balance.partial_dodge_damage_fraction))
        return opp_pid, -dmg, Outcome.partial, dmg

    # reflect
    if eff_power[opp_pid] >= eff_power[atk_pid]:
        returned = max(0, round(typed * balance.reflect_return_fraction))
        # Reflected damage lands on the attacker; not further type-charted.
        return atk_pid, -returned, Outcome.reflected, returned
    absorb = eff_power[opp_pid] * balance.block_multiplier
    dmg = max(0, round(typed - absorb))
    outcome = Outcome.blocked if dmg == 0 else Outcome.partial
    return opp_pid, -dmg, outcome, dmg


def _make_effect(action: JudgedAction, balance: BalanceConfig) -> ActiveEffect:
    shift = buff_shift(action, balance)
    turns = balance.buff_debuff_duration_turns
    if action.stat == Stat.speed:
        return ActiveEffect(speed_shift=shift, turns_remaining=turns)
    return ActiveEffect(power_shift=shift, turns_remaining=turns)


def resolve(
    state: GameState,
    p1_action: JudgedAction,
    p2_action: JudgedAction,
    balance: BalanceConfig,
) -> ResolveResult:
    ns = state.model_copy(deep=True)  # input immutability contract
    players: dict[str, PlayerState] = {"p1": ns.p1, "p2": ns.p2}
    actions: dict[str, JudgedAction] = {"p1": p1_action, "p2": p2_action}
    events: list[ResolutionEvent] = []

    # 1. Mana costs (base power), deducted for both, floored at 0.
    for pid in ("p1", "p2"):
        players[pid].mana = max(0, players[pid].mana - mana_cost(actions[pid], balance))

    # 2. Effective stats from turn-start buffs/debuffs (this turn's buffs don't apply).
    eff_power: dict[str, int] = {}
    eff_speed: dict[str, int] = {}
    for pid in ("p1", "p2"):
        p = players[pid]
        eff_power[pid] = effective_power(actions[pid], p.active_buff, p.active_debuff)
        eff_speed[pid] = effective_speed(actions[pid], p.active_buff, p.active_debuff)

    # Staging slots — installed at end-of-turn upkeep so they first bite next turn.
    pending_buff: dict[str, ActiveEffect | None] = {"p1": None, "p2": None}
    pending_debuff: dict[str, ActiveEffect | None] = {"p1": None, "p2": None}
    pending_cd: dict[str, dict[Category, int]] = {"p1": {}, "p2": {}}

    # 3. Defense priority tier: all defenses activate first (p1 then p2).
    defenders = {pid for pid in ("p1", "p2") if is_defense(actions[pid])}
    for pid in ("p1", "p2"):
        if pid in defenders:
            act = actions[pid]
            events.append(_event(pid, act, Outcome.defended, 0, players, balance))
            pending_cd[pid][act.category] = category_cooldown(act, balance)

    # 4. Non-defense actors grouped by effective speed (descending; ties simultaneous).
    actors = [pid for pid in ("p1", "p2") if pid not in defenders]
    if len(actors) == 2:
        if eff_speed["p1"] == eff_speed["p2"]:
            groups: list[list[PID]] = [["p1", "p2"]]
        elif eff_speed["p1"] > eff_speed["p2"]:
            groups = [["p1"], ["p2"]]
        else:
            groups = [["p2"], ["p1"]]
    elif len(actors) == 1:
        groups = [[actors[0]]]  # type: ignore[list-item]
    else:
        groups = []

    # 5. Resolve groups top-speed first, snapshot-delta within a group.
    ko = False
    for group in groups:
        if ko:
            for pid in group:
                events.append(_event(pid, actions[pid], Outcome.fizzled, 0, players, balance))
            continue

        deltas: dict[str, int] = {"p1": 0, "p2": 0}
        specs: list[tuple[PID, JudgedAction, Outcome, int]] = []
        for pid in group:  # p1 before p2 within a simultaneous group
            act = actions[pid]
            opp = _OPPONENT[pid]
            if act.category == Category.attack:
                target, delta, outcome, dmg = _attack_plan(
                    pid, opp, actions, eff_power, eff_speed, defenders, balance
                )
                deltas[target] += delta
                specs.append((pid, act, outcome, dmg))
            elif act.category == Category.heal:
                amount = round(eff_power[pid] * balance.heal_multiplier)
                deltas[pid] += amount
                specs.append((pid, act, Outcome.healed, amount))
            elif act.category == Category.buff:
                pending_buff[pid] = _make_effect(act, balance)
                specs.append((pid, act, Outcome.buffed, 0))
            elif act.category == Category.debuff:
                pending_debuff[opp] = _make_effect(act, balance)
                specs.append((pid, act, Outcome.debuffed, 0))
            pending_cd[pid][act.category] = category_cooldown(act, balance)

        # Apply summed deltas once vs the group's start HP: cap at max, never floor.
        for tid in ("p1", "p2"):
            if deltas[tid] != 0:
                players[tid].hp = min(balance.hp_max, players[tid].hp + deltas[tid])
        for pid, act, outcome, dmg in specs:
            events.append(_event(pid, act, outcome, dmg, players, balance))
        if players["p1"].hp <= 0 or players["p2"].hp <= 0:
            ko = True

    # 7. End-of-turn upkeep, both players, in exact order.
    for pid in ("p1", "p2"):
        p = players[pid]
        # (a) decrement pre-existing effects; drop expired.
        for slot in ("active_buff", "active_debuff"):
            eff: ActiveEffect | None = getattr(p, slot)
            if eff is not None:
                eff.turns_remaining -= 1
                if eff.turns_remaining <= 0:
                    setattr(p, slot, None)
        # (b) tick pre-existing cooldowns.
        p.cooldowns = {c: t - 1 for c, t in p.cooldowns.items() if t - 1 > 0}
        # (c) install pending effects/cooldowns (not decremented this turn).
        if pending_buff[pid] is not None:
            p.active_buff = pending_buff[pid]
        if pending_debuff[pid] is not None:
            p.active_debuff = pending_debuff[pid]
        for cat, turns in pending_cd[pid].items():
            if turns > 0:
                p.cooldowns[cat] = turns
        # (d) mana regen (capped).
        p.mana = min(balance.mana_max, p.mana + balance.mana_regen_per_turn)

    # 8. Match-over check (winner from signed HP), then floor HP for display.
    p1_hp, p2_hp = players["p1"].hp, players["p2"].hp
    # Match ends on a KO (either HP <= 0) or when the turn cap is reached; in
    # both cases the higher (signed) HP wins, equal is a draw.
    match_over = p1_hp <= 0 or p2_hp <= 0 or state.turn >= balance.max_turns
    winner: Literal["p1", "p2", "draw"] | None = _higher_hp(p1_hp, p2_hp) if match_over else None

    ns.turn = state.turn + 1
    players["p1"].hp = max(0, min(balance.hp_max, p1_hp))
    players["p2"].hp = max(0, min(balance.hp_max, p2_hp))

    return ResolveResult(events=events, state=ns, match_over=match_over, winner=winner)


def _higher_hp(p1_hp: int, p2_hp: int) -> Literal["p1", "p2", "draw"]:
    if p1_hp > p2_hp:
        return "p1"
    if p2_hp > p1_hp:
        return "p2"
    return "draw"
