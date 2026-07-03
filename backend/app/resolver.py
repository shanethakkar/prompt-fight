"""The pure combat resolver — alternating single-action turns with an effect
grammar (DESIGN.md §3).

`resolve_turn(state, action, balance)` resolves ONE bundle of effect components
for `state.active` and advances the turn. Pure: no I/O, input untouched
(deep-copied). The turn has three phases (plan rule 5):

  START  tick this player's dots/hots (magnitudes frozen at application), then
         check for a KO — a poison can drop the active player before they act,
         handing the win to the effect's source.
  ACT    apply each component: instant damage/heal, an over-time dot/hot, a
         persistent stat shift, or a raised defensive stance. Opponent-targeted
         effects land immediately; self-targeted ones are staged.
  END    decrement only this player's effects (use-before-decrement), install
         the staged self-effects, tick cooldowns, regen mana.

Each tick and each component becomes one ResolutionEvent, so a single turn can
emit several playback beats.
"""

from __future__ import annotations

from typing import Literal

from app.config import BalanceConfig
from app.models import (
    DEFENSE_TEMPLATE,
    Action,
    ActiveEffect,
    Barrier,
    ComponentTarget,
    ComponentType,
    DefenseSubtype,
    EffectComponent,
    EffectKind,
    EffectSummary,
    Element,
    GameState,
    Outcome,
    ResolutionEvent,
    ResolveResult,
    Side,
    SideState,
    Template,
    Unit,
)
from app.rules import (
    bundle_cost,
    damage_taken_mult,
    effective_power,
    effective_speed,
    kind_cooldowns,
    type_multiplier,
)

_OPPONENT: dict[str, Side] = {"p1": "p2", "p2": "p1"}


def initial_game(
    balance: BalanceConfig,
    p1_name: str = "Player 1",
    p2_name: str = "Player 2",
) -> GameState:
    def _side(key: str, name: str) -> SideState:
        return SideState(
            name=name,
            mana=balance.mana_start,
            stickman=Unit(id=f"{key}s", name=name, hp=balance.hp_start, max_hp=balance.hp_max),
        )

    return GameState(round=1, active="p1", p1=_side("p1", p1_name), p2=_side("p2", p2_name))


def _display(players: dict[str, SideState], balance: BalanceConfig) -> dict[str, int]:
    return {
        "p1_hp": max(0, min(balance.hp_max, players["p1"].stickman.hp)),
        "p2_hp": max(0, min(balance.hp_max, players["p2"].stickman.hp)),
        "p1_mana": players["p1"].mana,
        "p2_mana": players["p2"].mana,
    }


def _higher_hp(p1_hp: int, p2_hp: int) -> Side | Literal["draw"]:
    if p1_hp > p2_hp:
        return "p1"
    if p2_hp > p1_hp:
        return "p2"
    return "draw"


def _stance(player: Unit) -> ActiveEffect | None:
    return next((e for e in player.effects if e.kind is EffectKind.defense), None)


def _is_stunned(player: Unit) -> bool:
    return any(e.kind is EffectKind.control and e.turns_remaining > 0 for e in player.effects)


def _absorb_through_barriers(target: Unit, amount: int) -> tuple[int, int, int, list[str]]:
    """Soak ``amount`` through the target's durability pools (closest to HP).

    Barriers deplete in list order; a big hit cascades through several. Returns
    (hp_damage_left, total_absorbed, pool_remaining_after, shattered_labels).
    """
    if amount <= 0 or not target.barriers:
        return amount, 0, sum(b.pool for b in target.barriers), []
    absorbed = 0
    shattered: list[str] = []
    for barrier in list(target.barriers):
        if amount <= 0:
            break
        take = min(amount, barrier.pool)
        barrier.pool -= take
        amount -= take
        absorbed += take
        if barrier.pool <= 0:
            target.barriers.remove(barrier)
            shattered.append(barrier.label)
    remaining = sum(b.pool for b in target.barriers)
    return amount, absorbed, remaining, shattered


def _apply_damage(
    a_side: Side,
    o_side: Side,
    active: Unit,
    opponent: Unit,
    element: Element,
    atk_power: int,
    atk_speed: int,
    stance_available: bool,
    balance: BalanceConfig,
) -> tuple[Side, int, Outcome, EffectSummary | None]:
    """Resolve one instant-damage component through the pinned pipeline (rule 6):

    raw -> ×type (only vs a stance element) -> ×damage_taken (armor, always)
    -> flat stance block/dodge/reflect (consumed on use) -> floor 0.

    ``stance_available`` is False once an earlier component in the bundle already
    consumed the opponent's stance. Returns (target, damage, outcome, summary).
    """
    raw = atk_power * balance.attack_damage_multiplier
    dt_mult = damage_taken_mult(opponent.effects, balance)  # opponent's armor, always applies
    stance = _stance(opponent) if stance_available else None

    if stance is None:
        dmg = max(0, round(raw * dt_mult))  # undefended -> elements inert (neutral)
        return o_side, dmg, Outcome.hit_knockback, None

    opponent.effects.remove(stance)  # consume-on-hit
    typed = raw * type_multiplier(element, stance.element, balance) * dt_mult
    typed_i = max(0, round(typed))

    if stance.subtype is DefenseSubtype.shield:
        block = stance.power * balance.block_multiplier
        dmg = max(0, round(typed - block))
        outcome = Outcome.blocked if dmg == 0 else Outcome.partial
        return o_side, dmg, outcome, EffectSummary(kind="shield", absorbed=max(0, typed_i - dmg))

    if stance.subtype is DefenseSubtype.dodge:
        if stance.speed >= atk_speed:
            return o_side, 0, Outcome.dodged, EffectSummary(kind="dodge", absorbed=typed_i)
        dmg = max(0, round(typed * balance.partial_dodge_damage_fraction))
        return (
            o_side,
            dmg,
            Outcome.partial,
            EffectSummary(kind="dodge", absorbed=max(0, typed_i - dmg)),
        )

    # reflect
    if stance.power >= atk_power:
        returned = max(0, round(typed * balance.reflect_return_fraction))
        return a_side, returned, Outcome.reflected, EffectSummary(kind="reflect")
    absorb = stance.power * balance.block_multiplier
    dmg = max(0, round(typed - absorb))
    outcome = Outcome.blocked if dmg == 0 else Outcome.partial
    return o_side, dmg, outcome, EffectSummary(kind="reflect", absorbed=max(0, typed_i - dmg))


def resolve_turn(state: GameState, action: Action | None, balance: BalanceConfig) -> ResolveResult:
    """Resolve one bundle for the active player and advance the turn.

    ``action`` may be ``None`` (a skip). A stunned active player skips ACT
    regardless of the submitted action — the server never trusts the client to
    honor a stun.
    """
    ns = state.model_copy(deep=True)  # input immutability
    a_side = ns.active
    o_side = _OPPONENT[a_side]
    active_side = ns.p1 if a_side == "p1" else ns.p2
    opp_side = ns.p1 if o_side == "p1" else ns.p2
    # In P3.0 each side is a single stickman; targeting through entities lands in
    # P3.1. Binding the unit vars to the stickmen keeps the combat logic untouched;
    # only mana/cooldowns move to the SIDE (one command per turn).
    active = active_side.stickman
    opponent = opp_side.stickman
    players = {"p1": ns.p1, "p2": ns.p2}

    if active.hp <= 0 or opponent.hp <= 0:
        raise ValueError("cannot resolve a turn for a match that is already over")

    events: list[ResolutionEvent] = []

    # --- START OF TURN: this player's over-time effects tick (frozen magnitudes).
    for e in active.effects:
        if e.kind is EffectKind.dot:
            active.hp = max(0, active.hp - e.per_turn)
            events.append(
                ResolutionEvent(
                    actor=e.source,
                    target=a_side,
                    kind="dot_tick",
                    element=e.element,
                    outcome=Outcome.ticked,
                    amount=e.per_turn,
                    effect=EffectSummary(kind="dot", per_turn=e.per_turn, label=e.label),
                    template=Template.debuff_cloud,
                    state_delta=_display(players, balance),
                )
            )
        elif e.kind is EffectKind.hot:
            before = active.hp
            active.hp = min(balance.hp_max, active.hp + e.per_turn)
            events.append(
                ResolutionEvent(
                    actor=a_side,
                    target=a_side,
                    kind="hot_tick",
                    outcome=Outcome.ticked,
                    amount=active.hp - before,
                    effect=EffectSummary(kind="hot", per_turn=e.per_turn, label=e.label),
                    template=Template.heal_glow,
                    state_delta=_display(players, balance),
                )
            )

    # A dot can KO the active player before they ever act -> the source wins.
    if active.hp <= 0:
        return ResolveResult(events=events, state=ns, match_over=True, winner=o_side)

    # A stun makes the active player skip ACT. The START ticks above still fired,
    # so a stunned player can still be poisoned to death this turn.
    stunned = _is_stunned(active)
    if stunned:
        events.append(
            ResolutionEvent(
                actor=a_side,
                target=a_side,
                kind="stun_skip",
                outcome=Outcome.fizzled,
                effect=EffectSummary(kind="control", label="stunned"),
                template=Template.debuff_cloud,
                state_delta=_display(players, balance),
            )
        )
    components = [] if (stunned or action is None) else action.components
    flavor = action.flavor_text if action is not None else ""

    # --- ACT: pay the aggregate cost, then apply each component in order.
    active_side.mana = max(0, active_side.mana - bundle_cost(components, balance))
    atk_speed = effective_speed(action.speed if action is not None else 5, active.effects)
    staged: list[ActiveEffect] = []  # self-targeted effects installed post-decrement
    staged_barriers: list[Barrier] = []
    stance_available = True  # the opponent's stance is consumed by the first hit
    primary_narrated = False

    for c in components:
        narration = "" if primary_narrated else flavor
        target: Side = o_side
        outcome = Outcome.applied
        amount = 0
        summary: EffectSummary | None = None
        shatter: list[str] = []  # barrier labels that broke on this beat
        template = _component_template(c, action.template)

        if c.type is ComponentType.damage:
            atk_power = effective_power(c.power or 0, active.effects)
            target, amount, outcome, summary = _apply_damage(
                a_side,
                o_side,
                active,
                opponent,
                c.element,
                atk_power,
                atk_speed,
                stance_available,
                balance,
            )
            stance_available = False  # first damage consumes any stance; later hits land bare
            hit = active if target == a_side else opponent
            # Durability pools sit closest to HP: they soak whatever the stance let
            # through (a reflected hit is absorbed by the ATTACKER's own barrier).
            amount, absorbed, remaining, shatter = _absorb_through_barriers(hit, amount)
            if absorbed:
                summary = summary or EffectSummary(kind="barrier")
                summary.barrier_absorbed = absorbed
                summary.barrier_remaining = remaining
                if amount == 0:
                    outcome = Outcome.blocked  # the pool ate the whole hit
            hit.hp = max(0, hit.hp - amount)

        elif c.type is ComponentType.heal:
            before = active.hp
            active.hp = min(
                balance.hp_max, active.hp + round((c.power or 0) * balance.heal_multiplier)
            )
            target, outcome, amount = a_side, Outcome.healed, active.hp - before
            summary = EffectSummary(kind="heal", magnitude=active.hp - before)

        elif c.type is ComponentType.dot:
            per_turn = max(1, round((c.power or 0) * balance.dot_multiplier))
            opponent.effects.append(
                ActiveEffect(
                    kind=EffectKind.dot,
                    turns_remaining=c.duration or 1,
                    source=a_side,
                    per_turn=per_turn,
                    element=c.element,
                    label=_dot_label(c.element),
                )
            )
            summary = EffectSummary(
                kind="dot", per_turn=per_turn, duration=c.duration, label=_dot_label(c.element)
            )

        elif c.type is ComponentType.hot:
            per_turn = max(1, round((c.power or 0) * balance.hot_multiplier))
            staged.append(
                ActiveEffect(
                    kind=EffectKind.hot,
                    turns_remaining=c.duration or 1,
                    source=a_side,
                    per_turn=per_turn,
                    label="regen",
                )
            )
            target = a_side
            summary = EffectSummary(
                kind="hot", per_turn=per_turn, duration=c.duration, label="regen"
            )

        elif c.type is ComponentType.stat:
            label = _stat_label(c.stat, c.magnitude or 0)
            eff = ActiveEffect(
                kind=EffectKind.stat,
                turns_remaining=c.duration or 1,
                source=a_side,
                stat=c.stat,
                magnitude=c.magnitude or 0,
                label=label,
            )
            if c.target is ComponentTarget.caster:
                staged.append(eff)
                target = a_side
            else:
                opponent.effects.append(eff)
                target = o_side
            summary = EffectSummary(
                kind="stat", stat=c.stat, magnitude=c.magnitude, duration=c.duration, label=label
            )

        elif c.type is ComponentType.defense:
            subtype = c.subtype or DefenseSubtype.shield
            staged.append(
                ActiveEffect(
                    kind=EffectKind.defense,
                    turns_remaining=balance.defense_stance_duration_turns,
                    source=a_side,
                    subtype=subtype,
                    element=c.element,
                    power=effective_power(c.power or 0, active.effects),
                    speed=atk_speed,
                    label=subtype.value,
                )
            )
            target = a_side
            summary = EffectSummary(kind=subtype.value, label=subtype.value)

        elif c.type is ComponentType.barrier:
            pool = max(1, round((c.power or 0) * balance.barrier_pool_per_power))
            staged_barriers.append(
                Barrier(pool=pool, element=c.element, source=a_side, label="barrier")
            )
            target = a_side
            summary = EffectSummary(kind="barrier", barrier_remaining=pool)

        elif c.type is ComponentType.control:
            # A stun lands immediately on a non-stunned, non-immune opponent.
            if _is_stunned(opponent) or opponent.stun_immunity > 0:
                target, outcome = o_side, Outcome.fizzled
                summary = EffectSummary(kind="control", label="immune")
            else:
                opponent.effects.append(
                    ActiveEffect(
                        kind=EffectKind.control,
                        turns_remaining=c.duration or 1,
                        source=a_side,
                        label="stunned",
                    )
                )
                target = o_side
                summary = EffectSummary(kind="control", duration=c.duration, label="stunned")

        events.append(
            ResolutionEvent(
                actor=a_side,
                target=target,
                kind=c.type.value,
                element=c.element,
                outcome=outcome,
                amount=amount,
                effect=summary,
                template=template,
                narration=narration,
                state_delta=_display(players, balance),
            )
        )
        primary_narrated = True

        for label in shatter:  # one beat per pool that broke this component
            events.append(
                ResolutionEvent(
                    actor=a_side,
                    target=target,
                    kind="barrier_shatter",
                    outcome=Outcome.shattered,
                    effect=EffectSummary(kind="barrier", label=label),
                    template=Template.shield_raise,
                    state_delta=_display(players, balance),
                )
            )

    # --- END OF TURN upkeep for the ACTIVE player only.
    _decrement_effects(active)
    # When a stun wears off, grant the victim brief immunity (anti stun-lock);
    # otherwise count that immunity window down on their own turns.
    if stunned and not _is_stunned(active):
        active.stun_immunity = balance.stun_immunity_turns
    elif active.stun_immunity > 0:
        active.stun_immunity -= 1
    _install_staged(active, staged, balance)
    if staged_barriers:  # barriers have no timer; kept until broken, newest capped
        active.barriers.extend(staged_barriers)
        active.barriers = active.barriers[-balance.max_barriers_per_player :]
    active_side.cooldowns = {k: t - 1 for k, t in active_side.cooldowns.items() if t - 1 > 0}
    for k, cd in kind_cooldowns(components, balance).items():
        active_side.cooldowns[k] = cd
    active_side.mana = min(balance.mana_max, active_side.mana + balance.mana_regen_per_turn)

    # --- Match-over check + advance the turn.
    match_over = False
    winner: Side | Literal["draw"] | None = None
    if opponent.hp <= 0:
        match_over, winner = True, a_side
    elif active.hp <= 0:  # e.g. a reflected hit killed the attacker
        match_over, winner = True, o_side
    elif a_side == "p1":
        ns.active = "p2"
    else:
        ns.active = "p1"
        ns.round = state.round + 1
        if ns.round > balance.max_turns:
            match_over, winner = True, _higher_hp(ns.p1.stickman.hp, ns.p2.stickman.hp)

    if not events:  # an empty bundle still passes a turn; give playback one beat
        events.append(
            ResolutionEvent(
                actor=a_side,
                target=a_side,
                kind="fizzle",
                outcome=Outcome.fizzled,
                narration=flavor,
                state_delta=_display(players, balance),
            )
        )

    return ResolveResult(events=events, state=ns, match_over=match_over, winner=winner)


def _decrement_effects(player: Unit) -> None:
    """Tick down every effect on the player; drop the expired (use-before-decrement)."""
    kept: list[ActiveEffect] = []
    for e in player.effects:
        e.turns_remaining -= 1
        if e.turns_remaining > 0:
            kept.append(e)
    player.effects = kept


def _install_staged(player: Unit, staged: list[ActiveEffect], balance: BalanceConfig) -> None:
    """Install this turn's self-targeted effects (a new stance replaces the old),
    then cap the list at max_effects_per_player, keeping the newest."""
    for e in staged:
        if e.kind is EffectKind.defense:
            player.effects = [x for x in player.effects if x.kind is not EffectKind.defense]
        player.effects.append(e)
    if len(player.effects) > balance.max_effects_per_player:
        player.effects = player.effects[-balance.max_effects_per_player :]


def _component_template(c: EffectComponent, action_template: Template) -> Template:
    if c.type is ComponentType.damage:
        return action_template
    if c.type is ComponentType.defense and c.subtype is not None:
        return DEFENSE_TEMPLATE[c.subtype]
    if c.type is ComponentType.stat and c.target is ComponentTarget.caster:
        return Template.buff_aura
    if c.type is ComponentType.stat:
        return Template.debuff_cloud
    from app.models import COMPONENT_TEMPLATE

    return COMPONENT_TEMPLATE[c.type]


_DOT_LABELS = {
    Element.fire: "burn",
    Element.nature: "poison",
    Element.water: "chill",
    Element.lightning: "shock",
    Element.physical: "bleed",
}


def _dot_label(element: Element) -> str:
    return _DOT_LABELS.get(element, "bleed")


def _stat_label(stat, magnitude: int) -> str:
    from app.models import StatKind

    up = magnitude >= 0
    if stat is StatKind.power:
        return "empowered" if up else "weakened"
    if stat is StatKind.speed:
        return "hastened" if up else "slowed"
    if stat is StatKind.damage_taken:
        return "exposed" if up else "armored"
    return "affected"
