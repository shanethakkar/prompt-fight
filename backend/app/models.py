"""Domain models: the effect-grammar contract, game state, and resolution events.

These Pydantic models are the single Python source of truth for the game's data
shapes. An `Action` is a small BUNDLE of typed `EffectComponent`s parsed from a
player's freeform prompt (DESIGN.md §3); the server resolves and prices them.
Flavor is infinite; the mechanical vocabulary here is small and generic. The
TypeScript types mirror these.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Closed-set enums (never invent members outside these)
# ---------------------------------------------------------------------------


class Element(StrEnum):
    physical = "physical"
    fire = "fire"
    water = "water"
    nature = "nature"
    lightning = "lightning"


class ComponentType(StrEnum):
    """The mechanical kinds a single effect component can be (DESIGN.md §3)."""

    damage = "damage"  # instant hp loss to the target
    heal = "heal"  # instant hp gain to the target
    dot = "dot"  # damage over time (poison/burn/bleed)
    hot = "hot"  # heal over time (regen)
    stat = "stat"  # persistent stat shift (empower/weaken/haste/slow/armor/expose)
    defense = "defense"  # a raised defensive stance (shield/dodge/reflect)
    barrier = "barrier"  # a durability pool that absorbs damage until it shatters
    control = "control"  # stun: the target skips their turn(s)
    summon = "summon"  # bring a new entity onto your side (staged, acts next turn)
    item = "item"  # equip one of your units with gear (a weapon and/or tags)


class ComponentTarget(StrEnum):
    """Whose player the component lands on. Wire value ``self`` -> ``caster``."""

    opponent = "opponent"
    caster = "self"


class StatKind(StrEnum):
    """Which stat a ``stat`` component shifts."""

    power = "power"
    speed = "speed"
    damage_taken = "damage_taken"  # <1 mult = armor, >1 = exposed


class DefenseSubtype(StrEnum):
    shield = "shield"
    dodge = "dodge"
    reflect = "reflect"


class Effectiveness(StrEnum):
    """How well an attack suits its target (kryptonite vs Superman). The judge picks
    the tier from the matchup; the server owns the multiplier and grounds the tier
    against the target's real tags (P3.3)."""

    resisted = "resisted"
    neutral = "neutral"
    strong = "strong"
    devastating = "devastating"


class Aptitude(StrEnum):
    """Whether the acting unit is fit to perform this action (P1.2 reliability).
    The judge assesses it from the actor's identity/gear; the server grounds a
    ``fit`` claim (an over-reach with no real basis drops to ``improvised``)."""

    fit = "fit"  # suited by identity/gear, or a mundane physical action
    improvised = "improvised"  # a credible in-fiction stretch with no real gear
    unfit = "unfit"  # no basis — an over-reach (weak + likely to fizzle/backfire)


class EffectKind(StrEnum):
    """The kinds of persistent effect that can sit in a player's effects list."""

    dot = "dot"
    hot = "hot"
    stat = "stat"
    defense = "defense"
    control = "control"  # A.2 (stun); reserved


class Template(StrEnum):
    """Renderer hint for playback animation (loosely mapped from component kind)."""

    projectile = "projectile"
    beam = "beam"
    melee = "melee"
    aoe_burst = "aoe_burst"
    shield_raise = "shield_raise"
    dodge = "dodge"
    reflect = "reflect"
    buff_aura = "buff_aura"
    debuff_cloud = "debuff_cloud"
    heal_glow = "heal_glow"


class Outcome(StrEnum):
    hit_knockback = "hit_knockback"
    blocked = "blocked"
    partial = "partial"
    dodged = "dodged"
    reflected = "reflected"
    healed = "healed"
    applied = "applied"  # a dot/hot/stat/defense/barrier effect took hold
    ticked = "ticked"  # an over-time effect fired at start of turn
    shattered = "shattered"  # a barrier's pool was fully depleted
    fizzled = "fizzled"  # component did nothing (e.g. cost/validation dropped it)
    missed = "missed"  # P1 reliability: the action whiffed (roll or evade)
    overload = "overload"  # P1 reliability: a crit — landed harder than intended
    backfired = "backfired"  # P1 reliability: an overreach rebounded on the caster


class Shape(StrEnum):
    circle = "circle"
    rect = "rect"
    triangle = "triangle"
    line = "line"
    zigzag = "zigzag"
    ring = "ring"
    star = "star"


class Size(StrEnum):
    small = "small"
    medium = "medium"
    large = "large"


# component kind -> renderer template (damage refines from Action.template)
COMPONENT_TEMPLATE: dict[ComponentType, Template] = {
    ComponentType.damage: Template.projectile,
    ComponentType.heal: Template.heal_glow,
    ComponentType.dot: Template.debuff_cloud,
    ComponentType.hot: Template.heal_glow,
    ComponentType.stat: Template.buff_aura,
    ComponentType.defense: Template.shield_raise,
    ComponentType.barrier: Template.shield_raise,
    ComponentType.control: Template.debuff_cloud,
    ComponentType.summon: Template.buff_aura,
    ComponentType.item: Template.buff_aura,
}

DEFENSE_TEMPLATE: dict[DefenseSubtype, Template] = {
    DefenseSubtype.shield: Template.shield_raise,
    DefenseSubtype.dodge: Template.dodge,
    DefenseSubtype.reflect: Template.reflect,
}


# ---------------------------------------------------------------------------
# The Action contract (judge output)
# ---------------------------------------------------------------------------


class Primitive(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shape: Shape
    size: Size = Size.medium
    color: str = "#9AA0A6"
    offset: tuple[int, int] = (0, 0)


class Visual(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primitives: list[Primitive] = Field(default_factory=list, max_length=4)


class EffectComponent(BaseModel):
    """One typed mechanical effect. The judge emits a permissive, flat shape (all
    params optional); the server validates required-per-type, clamps ranges, and
    drops anything invalid (see rules.normalize_components). ``extra="ignore"`` so
    a stray param from the judge (e.g. reserved ``kind``/``amount``) is dropped,
    never a 422.
    """

    model_config = ConfigDict(extra="ignore")

    type: ComponentType
    target: ComponentTarget = ComponentTarget.opponent
    element: Element = Element.physical
    power: int | None = None  # damage/heal/dot/hot/defense magnitude (1-10 scope)
    magnitude: int | None = None  # stat: signed change to the target's stat
    duration: int | None = None  # dot/hot/stat: turns the effect persists
    stat: StatKind | None = None  # stat: which stat shifts
    subtype: DefenseSubtype | None = None  # defense: shield/dodge/reflect
    # Which of the caster's units performs this / which unit it lands on. The
    # judge echoes server-minted ids; normalize_components validates them against
    # the real roster (invalid -> the relevant stickman). None -> stickman.
    source_id: str | None = None
    target_id: str | None = None
    # summon only: the new entity's name, hp, tags, and optional starting item.
    # Its weapon is anchored on this component's ``element`` + ``power``.
    name: str | None = None
    hp: int | None = None
    tags: list[str] | None = None
    item: str | None = None
    armor: int | None = None  # item only: a worn-armor rating (persistent % reduction)
    # damage/dot: the judge's matchup tier + the target trait that justifies it.
    # The server grounds ``eff_tag`` against the target's real tags (P3.3).
    effectiveness: Effectiveness = Effectiveness.neutral
    eff_tag: str | None = None
    # damage/dot: is the SOURCE unit fit to perform this (P1.2)? The judge assesses
    # it; the server grounds a ``fit`` claim against the actor's real identity/gear.
    aptitude: Aptitude = Aptitude.fit
    apt_basis: str | None = None  # the cited reason (gear/identity/improvisation)


class RosterUnit(BaseModel):
    """The judge's view of one unit — identity, rough HP, kit (no effects/barriers)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    kind: UnitKind = "stickman"
    hp: int
    max_hp: int
    weapon: Weapon | None = None
    tags: list[str] = Field(default_factory=list)
    items: list[Item] = Field(default_factory=list)


class Roster(BaseModel):
    """Compact battlefield the judge sees so it can resolve unit references ("my
    orc" -> an id), only act on units that exist, and (P3.3) judge matchups. The
    caster is always ``you``. Also drives server-side id validation."""

    model_config = ConfigDict(extra="forbid")

    you: list[RosterUnit] = Field(default_factory=list)
    foe: list[RosterUnit] = Field(default_factory=list)

    def caster_ids(self) -> set[str]:
        return {u.id for u in self.you}

    def opponent_ids(self) -> set[str]:
        return {u.id for u in self.foe}

    def caster_stickman(self) -> str | None:
        return next((u.id for u in self.you if u.kind == "stickman"), None)

    def opponent_stickman(self) -> str | None:
        return next((u.id for u in self.foe if u.kind == "stickman"), None)


class Action(BaseModel):
    """A bundle of 1-3 effect components plus shared presentation fields.

    Mana cost is NOT part of this schema — the server prices the whole bundle
    (see rules.bundle_cost). ``components`` is capped/validated server-side before
    it ever reaches the resolver.
    """

    model_config = ConfigDict(extra="forbid")

    components: list[EffectComponent] = Field(default_factory=list)
    element: Element = Element.physical
    speed: int = Field(default=5, ge=1, le=10)
    template: Template = Template.projectile
    visual: Visual = Field(default_factory=Visual)
    flavor_text: str = Field(default="", max_length=90)


# ---------------------------------------------------------------------------
# Game state — alternating single-action turns (see DESIGN.md)
# ---------------------------------------------------------------------------

Side = Literal["p1", "p2"]
# P1: match modes. "sandbox" = no mana/cooldown gate + reliability disabled
# (everything lands); "competitive" = gates + the reliability roll are live.
GameMode = Literal["sandbox", "competitive"]


class ActiveEffect(BaseModel):
    """A persistent effect sitting on a player. It ticks/decrements on that
    player's own turns. ``source`` is the caster (for over-time KO attribution).
    Fields are populated per ``kind``; unused ones stay at their defaults.
    """

    model_config = ConfigDict(extra="forbid")

    kind: EffectKind
    turns_remaining: int
    source: Side
    label: str = ""

    # dot / hot
    per_turn: int = 0
    element: Element = Element.physical

    # stat
    stat: StatKind | None = None
    magnitude: int = 0

    # defense stance (effective stats FROZEN at cast — the block lands on the
    # opponent's turn)
    subtype: DefenseSubtype | None = None
    power: int = 0
    speed: int = 0


class Barrier(BaseModel):
    """A durability pool that soaks incoming damage until depleted, then shatters.

    Deliberately NOT an ActiveEffect / not stored in ``effects``: it has no timer
    (it persists as gear until broken), so it must be exempt from the end-of-turn
    decrement and the effects-list size cap. Dots/hots bypass it.
    """

    model_config = ConfigDict(extra="forbid")

    pool: int  # remaining absorb points
    element: Element = Element.physical
    source: Side = "p1"
    label: str = "barrier"


UnitKind = Literal["stickman", "entity"]


class Weapon(BaseModel):
    """A unit's assumed weapon/kit — the anchor for its damage components (an
    archer's bow, a dragon's fire). Assigned by the judge at summon; server-clamped."""

    model_config = ConfigDict(extra="forbid")

    name: str = "fists"
    element: Element = Element.physical
    power: int = 4


class Item(BaseModel):
    """A piece of equipped gear, recorded on a unit for display + inspection.
    Equipping fans out into combat state: a weapon re-arms the unit; ``armor`` is a
    **persistent % damage reduction** folded into the damage pipeline (`armor ×
    damage_taken_per_point` less on every hit, until the unit dies); gear grants
    ``tags``. ``kind`` is inferred server-side (weapon has power; armor has armor)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    kind: Literal["weapon", "armor", "gear"] = "gear"
    element: Element | None = None
    power: int | None = None
    armor: int | None = None  # worn-armor rating -> persistent damage reduction
    tags: list[str] = Field(default_factory=list)


class Unit(BaseModel):
    """One combatant on the battlefield. Each side has a ``stickman`` (its core —
    if it dies, that side loses) plus zero or more summoned ``entities``. All
    per-unit combat state (hp/effects/barriers) lives here; mana and cooldowns
    are per-SIDE (one command per turn). ``id`` is a stable server-minted handle
    used for targeting (P3.1a+); ``kind`` distinguishes the core from helpers.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str = "Stickman"
    kind: UnitKind = "stickman"
    hp: int
    max_hp: int
    effects: list[ActiveEffect] = Field(default_factory=list)
    barriers: list[Barrier] = Field(default_factory=list)
    # Turns of immunity to incoming stun after one wears off (anti stun-lock).
    stun_immunity: int = 0
    # Kit + gear (P3.1b/P3.2). ``weapon`` anchors this unit's damage; ``tags`` are
    # descriptors (e.g. "undead", "kryptonian") that P3.3 matchups will read.
    weapon: Weapon | None = None
    tags: list[str] = Field(default_factory=list)
    items: list[Item] = Field(default_factory=list)


class SideState(BaseModel):
    """One player's side of the board: their resource pool + their unit roster."""

    model_config = ConfigDict(extra="forbid")

    name: str = "Player"
    mana: int
    # Only component-kinds currently on cooldown appear; missing => available.
    # Keyed by the cooldownable kinds only ("heal", "defense", "control").
    cooldowns: dict[str, int] = Field(default_factory=dict)
    stickman: Unit
    entities: list[Unit] = Field(default_factory=list)


class GameState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round: int = 1
    active: Side = "p1"  # whose side's turn it is
    p1: SideState
    p2: SideState
    # P1: the reliability RNG is seeded from match state so the resolver stays a
    # pure function and replays reproduce. `mode` gates whether reliability +
    # affordability apply. Both default so pre-P1 constructors stay valid.
    seed: int = 0
    mode: GameMode = "sandbox"


class EffectSummary(BaseModel):
    """Structured, narratable detail of a component's result. The client templates
    a readable sentence from it. Fields are populated per kind."""

    model_config = ConfigDict(extra="forbid")

    kind: str
    stat: StatKind | None = None
    magnitude: int | None = None
    duration: int | None = None
    per_turn: int | None = None
    absorbed: int | None = None  # flat stance absorption
    barrier_absorbed: int | None = None  # damage soaked by a durability pool
    barrier_remaining: int | None = None  # pool left after this hit
    effectiveness: str | None = None  # matchup tier if not neutral (P3.3)
    reliability: str | None = None  # P1 roll tier if not a clean full hit
    label: str = ""


class ResolutionEvent(BaseModel):
    """One playback beat: an over-time tick, or one resolved action component."""

    model_config = ConfigDict(extra="forbid")

    actor: Side  # which side caused this beat (caster; for a tick, the effect's source)
    target: Side
    kind: str  # component type, or "dot_tick" / "hot_tick" / "summon" / "removed"
    element: Element = Element.physical
    outcome: Outcome
    amount: int = 0  # hp delta magnitude (damage dealt or hp healed), always >= 0
    effect: EffectSummary | None = None
    template: Template | None = None
    narration: str = ""  # bundle flavor_text, set on the primary beat only
    # The specific units involved (P3.1b), so playback can say "Orc hits Archer".
    actor_id: str | None = None
    target_id: str | None = None
    actor_name: str | None = None
    target_name: str | None = None
    # Post-beat snapshot for the renderer: display HP/mana of both players.
    state_delta: dict[str, int] = Field(default_factory=dict)


class ResolveResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[ResolutionEvent]
    state: GameState
    match_over: bool
    winner: Side | Literal["draw"] | None = None
