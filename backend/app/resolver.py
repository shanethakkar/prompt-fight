"""The pure combat resolver — alternating single-action turns (see DESIGN.md).

`resolve_turn(state, action, balance)` resolves ONE action for `state.active`,
against the current state (including the opponent's raised defensive stance),
then advances the turn. Pure: no I/O, input untouched (deep-copied), one event
out. The M1 damage/type/effect math (rules.py) is reused; only the turn
orchestration changed (no simultaneity → no speed-ordering, snapshot-delta,
double-KO tiebreak, or defense-priority tier). See GAME_MECHANICS.md §7.
"""

from __future__ import annotations

from typing import Literal

from app.config import BalanceConfig
from app.models import (
    ActiveDefense,
    ActiveEffect,
    Category,
    EffectSummary,
    GameState,
    JudgedAction,
    Outcome,
    PlayerState,
    ResolutionEvent,
    ResolveResult,
    Side,
    Stat,
    Subtype,
)
from app.rules import (
    buff_shift,
    category_cooldown,
    effective_power,
    effective_speed,
    mana_cost,
    type_multiplier,
)

_OPPONENT: dict[str, Side] = {"p1": "p2", "p2": "p1"}


def initial_game(
    balance: BalanceConfig,
    p1_name: str = "Player 1",
    p2_name: str = "Player 2",
) -> GameState:
    def _player(name: str) -> PlayerState:
        return PlayerState(name=name, hp=balance.hp_start, mana=balance.mana_start)

    return GameState(round=1, active="p1", p1=_player(p1_name), p2=_player(p2_name))


def _display(players: dict[str, PlayerState], balance: BalanceConfig) -> dict[str, int]:
    return {
        "p1_hp": max(0, min(balance.hp_max, players["p1"].hp)),
        "p2_hp": max(0, min(balance.hp_max, players["p2"].hp)),
        "p1_mana": players["p1"].mana,
        "p2_mana": players["p2"].mana,
    }


def _higher_hp(p1_hp: int, p2_hp: int) -> Side | Literal["draw"]:
    if p1_hp > p2_hp:
        return "p1"
    if p2_hp > p1_hp:
        return "p2"
    return "draw"


def _attack(
    a_side: Side,
    o_side: Side,
    opponent: PlayerState,
    action: JudgedAction,
    eff_power: int,
    eff_speed: int,
    balance: BalanceConfig,
) -> tuple[Side, int, Outcome, EffectSummary | None]:
    """Resolve an attack vs the opponent's frozen defensive stance (consumed on use).

    Returns (target, damage, outcome, effect). Pipeline: raw -> type chart (only
    vs a defending element) -> mitigation -> floor 0.
    """
    raw = eff_power * balance.attack_damage_multiplier
    stance = opponent.active_defense
    if stance is None:
        dmg = max(0, round(raw))  # undefended -> elements inert (neutral)
        return o_side, dmg, Outcome.hit_knockback, None

    typed = raw * type_multiplier(action.element, stance.element, balance)
    typed_i = max(0, round(typed))
    opponent.active_defense = None  # consume-on-hit

    if stance.subtype == Subtype.shield:
        block = stance.power * balance.block_multiplier
        dmg = max(0, round(typed - block))
        outcome = Outcome.blocked if dmg == 0 else Outcome.partial
        return o_side, dmg, outcome, EffectSummary(kind="shield", absorbed=max(0, typed_i - dmg))

    if stance.subtype == Subtype.dodge:
        if stance.speed >= eff_speed:
            return o_side, 0, Outcome.dodged, EffectSummary(kind="dodge", absorbed=typed_i)
        dmg = max(0, round(typed * balance.partial_dodge_damage_fraction))
        return (
            o_side,
            dmg,
            Outcome.partial,
            EffectSummary(kind="dodge", absorbed=max(0, typed_i - dmg)),
        )

    # reflect
    if stance.power >= eff_power:
        returned = max(0, round(typed * balance.reflect_return_fraction))
        return a_side, returned, Outcome.reflected, EffectSummary(kind="reflect")
    absorb = stance.power * balance.block_multiplier
    dmg = max(0, round(typed - absorb))
    outcome = Outcome.blocked if dmg == 0 else Outcome.partial
    return o_side, dmg, outcome, EffectSummary(kind="reflect", absorbed=max(0, typed_i - dmg))


def _make_effect(stat: Stat | None, shift: int, duration: int) -> ActiveEffect:
    eff = ActiveEffect(turns_remaining=duration)
    if stat == Stat.speed:
        eff.speed_shift = shift
    else:
        eff.power_shift = shift
    return eff


def resolve_turn(state: GameState, action: JudgedAction, balance: BalanceConfig) -> ResolveResult:
    """Resolve one action for the active player and advance the turn."""
    ns = state.model_copy(deep=True)  # input immutability
    a_side = ns.active
    o_side = _OPPONENT[a_side]
    active = ns.p1 if a_side == "p1" else ns.p2
    opponent = ns.p1 if o_side == "p1" else ns.p2
    players = {"p1": ns.p1, "p2": ns.p2}

    if active.hp <= 0 or opponent.hp <= 0:
        raise ValueError("cannot resolve a turn for a match that is already over")

    assert action.template is not None  # normalized in the JudgedAction validator

    # 1. Effective stats from the active player's current buff/debuff.
    eff_power = effective_power(action, active.active_buff, active.active_debuff)
    eff_speed = effective_speed(action, active.active_buff, active.active_debuff)

    # 2. Pay mana (base power), floor 0.
    active.mana = max(0, active.mana - mana_cost(action, balance))

    # 3. Apply the action. Newly-created SELF effects are staged (installed after
    #    the end-of-turn tick); a debuff lands on the opponent's slot now (it is
    #    the opponent's effect and only ticks on their turns).
    duration = balance.buff_debuff_duration_turns
    pending_buff: ActiveEffect | None = None
    pending_defense: ActiveDefense | None = None
    target: Side = o_side
    outcome = Outcome.hit_knockback
    damage = 0
    effect: EffectSummary | None = None
    cat = action.category

    if cat == Category.attack:
        target, damage, outcome, effect = _attack(
            a_side, o_side, opponent, action, eff_power, eff_speed, balance
        )
        hit = active if target == a_side else opponent
        hit.hp = max(0, hit.hp - damage)
    elif cat == Category.heal:
        before = active.hp
        active.hp = min(balance.hp_max, active.hp + round(eff_power * balance.heal_multiplier))
        target, outcome = a_side, Outcome.healed
        effect = EffectSummary(kind="heal", magnitude=active.hp - before)
    elif cat == Category.defense:
        pending_defense = ActiveDefense(
            subtype=action.subtype,
            element=action.element,
            power=eff_power,
            speed=eff_speed,
            turns_remaining=balance.defense_stance_duration_turns,
        )
        target, outcome = a_side, Outcome.defended
        effect = EffectSummary(kind=action.subtype.value)
    elif cat == Category.buff:
        shift = buff_shift(action, balance)
        pending_buff = _make_effect(action.stat, shift, duration)
        target, outcome = a_side, Outcome.buffed
        kind = "hasten" if action.stat == Stat.speed else "empower"
        effect = EffectSummary(kind=kind, stat=action.stat, magnitude=shift, duration=duration)
    elif cat == Category.debuff:
        shift = buff_shift(action, balance)
        opponent.active_debuff = _make_effect(action.stat, shift, duration)
        target, outcome = o_side, Outcome.debuffed
        kind = "slow" if action.stat == Stat.speed else "weaken"
        effect = EffectSummary(kind=kind, stat=action.stat, magnitude=shift, duration=duration)

    new_cd = category_cooldown(action, balance)

    # 4. End-of-turn upkeep for the ACTIVE player only (use-before-decrement,
    #    install-after-tick), then mana regen so their next input shows spendable
    #    mana. The opponent's effects/cooldowns tick on the opponent's own turns.
    for slot in ("active_buff", "active_debuff", "active_defense"):
        eff: ActiveEffect | ActiveDefense | None = getattr(active, slot)
        if eff is not None:
            eff.turns_remaining -= 1
            if eff.turns_remaining <= 0:
                setattr(active, slot, None)
    active.cooldowns = {c: t - 1 for c, t in active.cooldowns.items() if t - 1 > 0}
    if pending_buff is not None:
        active.active_buff = pending_buff
    if pending_defense is not None:
        active.active_defense = pending_defense
    if new_cd > 0:
        active.cooldowns[cat] = new_cd
    active.mana = min(balance.mana_max, active.mana + balance.mana_regen_per_turn)

    event = ResolutionEvent(
        actor=a_side,
        target=target,
        template=action.template,
        outcome=outcome,
        damage=damage,
        effect=effect,
        narration=action.flavor_text,
        state_delta=_display(players, balance),
    )

    # 5. Match-over check + advance the turn. A death (only the active player can
    #    deal damage this turn) ends it immediately; otherwise the turn cap is
    #    checked only at a round boundary (after p2 acts) so actions are equal.
    match_over = False
    winner: Side | Literal["draw"] | None = None
    if opponent.hp <= 0:
        match_over, winner = True, a_side
    elif active.hp <= 0:  # e.g. reflected onto the attacker
        match_over, winner = True, o_side
    elif a_side == "p1":
        ns.active = "p2"
    else:
        ns.active = "p1"
        ns.round = state.round + 1
        if ns.round > balance.max_turns:
            match_over, winner = True, _higher_hp(ns.p1.hp, ns.p2.hp)

    return ResolveResult(events=[event], state=ns, match_over=match_over, winner=winner)
