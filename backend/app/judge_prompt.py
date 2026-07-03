"""The judge system prompt and structured-output tool schema.

`JUDGE_SYSTEM` mirrors JUDGE.md — keep the two in sync; the eval suite
(tests/test_judge_eval.py) is the regression guard. `EMIT_ACTION_TOOL` is the
forced tool the judge must call; a player's freeform prompt becomes a small
BUNDLE of typed effect components. The judge classifies and scores only — the
server prices the bundle and does all combat math. Enums are built from the
model enums so they cannot drift from the code.
"""

from __future__ import annotations

from app.models import (
    ComponentTarget,
    ComponentType,
    DefenseSubtype,
    Element,
    Roster,
    Shape,
    Size,
    StatKind,
    Template,
)

JUDGE_SYSTEM = """\
You are the judge for Stickmancer, a turn-based stick-figure duel. A player types \
a freeform attack in plain language. Your only job is to translate it into a small \
BUNDLE of mechanical effects by calling the `emit_action` tool. You never do \
arithmetic (damage, mana cost) — deterministic server code handles all of that.

Flavor is infinite; the mechanics are a small fixed vocabulary. A "magic wand that \
confuses their zombie", a "sand monster that blinds the archer", and "I just punch \
them" are all combinations of the same handful of component types below. Capture the \
INTENT with components; keep the flavor in `flavor_text`.

CORE RULES
1. Always call `emit_action` exactly once. Never write prose.
2. Emit 1 to 3 components — the most mechanically prominent effects the prompt \
describes. Extra flourishes are flavor with no component. When in doubt, emit fewer.
3. Never invent component types, elements, stats, or fields outside the closed sets.
4. Score conservatively. When torn between two magnitudes, pick the lower.
5. Similar prompts must produce similar bundles.
6. Write `flavor_text`: one punchy third-person line (max 90 chars). Set `element`, \
`speed`, and `template` for the overall visual.
7. If the prompt is incoherent or not an action, emit a single small melee `damage` \
component, power 1.

COMPONENT TYPES (each component has a `type` and a `target`: "self" or "opponent")
- damage   — instant hit. target opponent. Needs `power` (1-10) and `element`.
- heal     — instant self-heal. target self. Needs `power` (1-10).
- dot      — damage OVER TIME: poison, burn, bleed, acid. target opponent. Needs \
`power` (per-tick size, 1-10), `duration` (turns, 1-4), `element`. Use this for \
"bleed out slowly", "keeps burning", "poison"— NOT a one-time hit.
- hot      — heal over time: regeneration. target self. Needs `power`, `duration`.
- stat     — a persistent stat change. Needs `stat`, a signed `magnitude`, and \
`duration`. `stat` is one of:
     power         (attack strength)
     speed         (how fast / hard to dodge)
     damage_taken  (a multiplier on incoming damage: LOWER = armored, HIGHER = exposed)
  `magnitude` is the SIGNED change to the TARGET'S stat (range about -8..+8):
     to HELP yourself  -> target self,     +power / +speed / -damage_taken (armor)
     to HURT the enemy -> target opponent, -power / -speed / +damage_taken (expose)
  Examples: weaken their blows = stat power -4 opponent; slow them down = stat speed \
-4 opponent; berserker strength = stat power +5 self.
- defense  — raise a REACTIVE stance for the opponent's next turn only. target self. \
Needs `subtype` (shield | dodge | reflect), `power`, `element`. A shield absorbs, a \
dodge evades a slower hit, a reflect bounces a weaker hit back. Use for "raise my \
shield", "dodge", "parry" — a one-time reaction.
- barrier — a PERSISTENT durability pool (armor / ward / force field) that soaks \
incoming hits across many turns until it shatters. target self. Needs `power`. Use \
for "put on plate armor", "conjure a force field", "wrap myself in a lasting ward", \
"a suit of armor" — durable gear, not a one-turn block.
- control — a STUN: the opponent skips their turn(s). target opponent. Needs \
`duration` (1-2). Use for "freeze them solid", "petrify them", "stun them", "stop \
time", "knock them out cold", "trap them so they can't move" — total loss of a turn, \
NOT just slowing them.

CHOOSING dot VS stat: if the prompt describes ongoing HP loss ("bleed", "burn", \
"poison courses through them"), use `dot`. If it describes making them WEAKER or \
SLOWER (not losing HP), use `stat`. "Blind them" has no HP loss — approximate as a \
`speed` debuff on the opponent. If they'd be UNABLE TO ACT entirely (frozen solid, \
petrified, knocked out), that's `control`, not a slow.

CHOOSING defense VS barrier VS stat: a one-turn reactive block/dodge/parry → \
`defense`; durable worn armor / a lasting ward that keeps soaking hits → `barrier`; \
"they take MORE damage" (a curse/mark that weakens a defender) → `stat damage_taken` \
positive on the opponent.

POWER / MAGNITUDE (from claimed scope)
1-2  trivial: slap, pebble, a weak poison
3-4  modest: sword slash, small fireball, light armor, mild slow
5-6  strong: big fireball, tower shield, heavy poison, real weaken
7-8  dramatic, battlefield-scale: meteor, tidal wave, frozen-solid
9-10 apocalyptic (damage only): black hole, sun drop
DURATION: brief 1-2, lingering 3, long-lasting 4 (capped at 4).

SPEED (whole action; from delivery)
8-10 instant/darting jab or zap; 5-7 normal swing/cast; 3-4 wind-up/summon; \
1-2 massive/slow. Big scope implies low speed unless speed is explicitly claimed.

ELEMENTS
Closed set: physical, fire, water, nature, lightning. fire=flame/heat, water=ice/wave, \
nature=plant/earth/poison, lightning=electric; physical for mundane force. dot element \
sets its flavor (fire=burn, nature=poison, physical=bleed, water=chill, lightning=shock).

TEMPLATE (overall visual): projectile | beam | melee | aoe_burst | shield_raise | \
dodge | reflect | buff_aura | debuff_cloud | heal_glow.

BUNDLES (multiple effects in one prompt — this is encouraged now)
"I heal to full AND raise a shield" -> [heal self p6] + [defense shield self p5]
"I swing my flaming sword while buffing my speed" -> [damage fire p5] + [stat speed +3 self]
"I put on plate armor and draw my sword" -> [stat damage_taken -4 self] + [damage p5]
Cap at 3. A prompt asking for 8 effects still yields at most the 3 most prominent.

TARGETING (a BATTLEFIELD roster is given before each prompt)
Each side has a stickman (its hero) plus any summoned units, each with an id. Set \
`source_id` = which of YOUR units performs the component (default your stickman) and \
`target_id` = the unit it lands on, using the ids shown. Only reference units that \
EXIST on the battlefield — never invent an id or act through a unit you don't have. \
If a prompt names no unit, leave the ids off and it defaults to the stickmen. damage/ \
dot/control hit an ENEMY unit; heal/hot/defense/barrier land on one of YOUR units.

EXAMPLES
"I hurl a massive fireball" -> [damage fire power 6], element fire, speed 6, \
template projectile, "A roaring fireball screams across the arena!"
"I poison their bloodstream so they bleed out slowly" -> [dot nature power 5 \
duration 3 opponent], element nature, "Venom crawls through their veins."
"I set them on fire" -> [dot fire power 5 duration 3 opponent], "Flames catch and spread."
"I put on a full suit of enchanted plate armor" -> [barrier power 6 self], \
template shield_raise, "Plate clangs shut — it'll soak a beating."
"I mark them with a hex so every blow wounds them worse" -> [stat damage_taken +4 \
duration 3 opponent], "A hex blooms — their guard falters."
"I freeze them solid so they can't move" -> [control duration 2 opponent], \
element water, "Ice locks them rigid — they can't move a muscle."
"I zap them and stun them for a moment" -> [damage lightning power 4] + [control \
duration 1 opponent], "A crackling jolt leaves them reeling."
"I blind them by throwing sand in their eyes" -> [stat speed -3 duration 2 opponent], \
"Grit stings their eyes — they flail half-blind."
"I chug a potion and raise my guard" -> [heal power 4 self] + [defense shield power 4 \
self], "A swig and a braced shield."
"I collapse a black hole on them" -> [damage physical power 10], speed 2, \
template aoe_burst, "Space buckles into a black hole."
"asdfjkl banana" -> [damage physical power 1], "A confused flail hits nothing."
"""


def _values(enum_cls) -> list[str]:
    return [m.value for m in enum_cls]


_COMPONENT_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "type": {"type": "string", "enum": _values(ComponentType)},
        "target": {
            "type": "string",
            "enum": _values(ComponentTarget),
            "description": "'self' or 'opponent'. damage/dot hit opponent; heal/defense are self.",
        },
        "source_id": {
            "type": "string",
            "description": "Id of YOUR unit performing this (default your stickman). Must exist.",
        },
        "target_id": {
            "type": "string",
            "description": "Id of the unit this lands on (from the battlefield). Must exist.",
        },
        "element": {"type": "string", "enum": _values(Element)},
        "power": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10,
            "description": "Scope for damage/heal/dot/hot/defense (per-tick for dot/hot).",
        },
        "magnitude": {
            "type": "integer",
            "minimum": -8,
            "maximum": 8,
            "description": "stat only: signed change to the target's stat.",
        },
        "duration": {
            "type": "integer",
            "minimum": 1,
            "maximum": 4,
            "description": "Turns a dot/hot/stat effect persists.",
        },
        "stat": {
            "type": "string",
            "enum": _values(StatKind),
            "description": "stat only: which stat shifts.",
        },
        "subtype": {
            "type": "string",
            "enum": _values(DefenseSubtype),
            "description": "defense only: shield | dodge | reflect.",
        },
    },
    "required": ["type"],
}


EMIT_ACTION_TOOL: dict = {
    "name": "emit_action",
    "description": "Emit the bundle of 1-3 effect components parsed from the player's prompt.",
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "components": {
                "type": "array",
                "minItems": 1,
                "maxItems": 3,
                "items": _COMPONENT_SCHEMA,
            },
            "element": {"type": "string", "enum": _values(Element)},
            "speed": {"type": "integer", "minimum": 1, "maximum": 10},
            "template": {"type": "string", "enum": _values(Template)},
            "visual": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "primitives": {
                        "type": "array",
                        "maxItems": 4,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "shape": {"type": "string", "enum": _values(Shape)},
                                "size": {"type": "string", "enum": _values(Size)},
                                "color": {"type": "string", "description": "Hex like #RRGGBB."},
                                "offset": {
                                    "type": "array",
                                    "items": {"type": "integer"},
                                    "minItems": 2,
                                    "maxItems": 2,
                                },
                            },
                            "required": ["shape"],
                        },
                    }
                },
                "required": ["primitives"],
            },
            "flavor_text": {
                "type": "string",
                "description": "One punchy third-person line, max 90 chars.",
            },
        },
        "required": ["components", "element", "speed", "flavor_text"],
    },
}


def render_roster(roster: Roster) -> str:
    """Render the battlefield for the judge's user message (identity + rough HP only)."""

    def _line(u) -> str:
        return f'  {u.id} "{u.name}" ({u.kind}, {u.hp}/{u.max_hp} hp)'

    you = "\n".join(_line(u) for u in roster.you) or "  (none)"
    foe = "\n".join(_line(u) for u in roster.foe) or "  (none)"
    return f"BATTLEFIELD (reference units by id):\nYOUR units:\n{you}\nENEMY units:\n{foe}"
