"""Domain models: the JudgedAction contract, game state, and resolution events.

These Pydantic models are the single Python source of truth for the game's data
shapes. `JudgedAction` mirrors JUDGE.md §4; `GameState`/`ResolutionEvent` mirror
SPEC.md §6. The TypeScript types (M3/M4) mirror these.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# Closed-set enums (never invent members outside these)
# ---------------------------------------------------------------------------


class Element(StrEnum):
    physical = "physical"
    fire = "fire"
    water = "water"
    nature = "nature"
    lightning = "lightning"


class Category(StrEnum):
    attack = "attack"
    defense = "defense"
    buff = "buff"
    debuff = "debuff"
    heal = "heal"


class Subtype(StrEnum):
    projectile = "projectile"
    beam = "beam"
    melee = "melee"
    aoe = "aoe"
    shield = "shield"
    dodge = "dodge"
    reflect = "reflect"
    buff = "buff"
    debuff = "debuff"
    heal = "heal"


class Template(StrEnum):
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


class Stat(StrEnum):
    power = "power"
    speed = "speed"


class Outcome(StrEnum):
    hit_knockback = "hit_knockback"
    blocked = "blocked"
    partial = "partial"
    dodged = "dodged"
    reflected = "reflected"
    healed = "healed"
    buffed = "buffed"
    debuffed = "debuffed"
    defended = "defended"  # a defense action activated (priority tier)
    fizzled = "fizzled"  # action did not resolve (actor KO'd first)


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


# Category membership and the deterministic subtype -> template mapping.
SUBTYPE_CATEGORY: dict[Subtype, Category] = {
    Subtype.projectile: Category.attack,
    Subtype.beam: Category.attack,
    Subtype.melee: Category.attack,
    Subtype.aoe: Category.attack,
    Subtype.shield: Category.defense,
    Subtype.dodge: Category.defense,
    Subtype.reflect: Category.defense,
    Subtype.buff: Category.buff,
    Subtype.debuff: Category.debuff,
    Subtype.heal: Category.heal,
}

SUBTYPE_TEMPLATE: dict[Subtype, Template] = {
    Subtype.projectile: Template.projectile,
    Subtype.beam: Template.beam,
    Subtype.melee: Template.melee,
    Subtype.aoe: Template.aoe_burst,
    Subtype.shield: Template.shield_raise,
    Subtype.dodge: Template.dodge,
    Subtype.reflect: Template.reflect,
    Subtype.buff: Template.buff_aura,
    Subtype.debuff: Template.debuff_cloud,
    Subtype.heal: Template.heal_glow,
}


# ---------------------------------------------------------------------------
# JudgedAction (JUDGE.md §4)
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


class JudgedAction(BaseModel):
    """One structured action parsed from a player's freeform prompt.

    `template` is normalized from `subtype` server-side. `stat` is meaningful
    only for buff/debuff (which stat the effect shifts); it is coerced to None
    for other categories. Mana cost is NOT part of this schema — the server
    computes it from `power` + `category` (see rules.mana_cost).
    """

    model_config = ConfigDict(extra="forbid")

    category: Category
    subtype: Subtype
    element: Element = Element.physical
    power: int = Field(ge=1, le=10)
    speed: int = Field(ge=1, le=10)
    stat: Stat | None = None
    template: Template | None = None
    visual: Visual = Field(default_factory=Visual)
    flavor_text: str = Field(default="", max_length=90)

    @model_validator(mode="after")
    def _normalize(self) -> JudgedAction:
        expected_category = SUBTYPE_CATEGORY[self.subtype]
        if self.category != expected_category:
            raise ValueError(
                f"subtype {self.subtype.value!r} belongs to category "
                f"{expected_category.value!r}, not {self.category.value!r}"
            )
        # Template follows deterministically from subtype (server corrects).
        self.template = SUBTYPE_TEMPLATE[self.subtype]
        # `stat` only applies to buff/debuff; default to power, drop elsewhere.
        if self.category in (Category.buff, Category.debuff):
            self.stat = self.stat or Stat.power
        else:
            self.stat = None
        return self


# ---------------------------------------------------------------------------
# Game state (SPEC.md §6)
# ---------------------------------------------------------------------------


class ActiveEffect(BaseModel):
    """An active buff (self) or debuff (on opponent). Shifts are signed magnitudes."""

    model_config = ConfigDict(extra="forbid")

    power_shift: int = 0
    speed_shift: int = 0
    turns_remaining: int


class PlayerState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = "Player"
    hp: int
    mana: int
    # Only categories currently on cooldown appear; missing => available.
    cooldowns: dict[Category, int] = Field(default_factory=dict)
    active_buff: ActiveEffect | None = None
    active_debuff: ActiveEffect | None = None


class GameState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn: int = 1
    p1: PlayerState
    p2: PlayerState


class ResolutionEvent(BaseModel):
    """One entry in the ordered playback list the renderer animates (SPEC.md §6)."""

    model_config = ConfigDict(extra="forbid")

    actor: Literal["p1", "p2"]
    template: Template
    outcome: Outcome
    damage: int = 0
    narration: str = ""
    # Post-event snapshot for the renderer: display HP/mana of both players.
    state_delta: dict[str, int] = Field(default_factory=dict)


class ResolveResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[ResolutionEvent]
    state: GameState
    match_over: bool
    winner: Literal["p1", "p2", "draw"] | None = None
