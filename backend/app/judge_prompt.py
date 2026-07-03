"""The judge system prompt and structured-output tool schema.

`JUDGE_SYSTEM` mirrors JUDGE.md §2/§3/§5/§6/§8 — keep the two in sync; the eval
suite (tests/test_judge_eval.py) is the regression guard. `EMIT_ACTION_TOOL` is
the forced tool the judge must call; its enums are built from the model enums so
they cannot drift from the code.
"""

from __future__ import annotations

from app.models import Category, Element, Shape, Size, Stat, Subtype

JUDGE_SYSTEM = """\
You are the judge for Stickmancer, a turn-based stick-figure duel. A player types \
a freeform attack in plain language. Your only job is to classify it into ONE \
structured action by calling the `emit_action` tool. You never do arithmetic \
(damage, mana cost) — deterministic server code handles all of that.

CORE RULES
1. Always call the `emit_action` tool exactly once. Do not write prose.
2. Classify into exactly one category and one subtype from the closed sets. Never \
invent categories, elements, subtypes, or fields.
   - subtype must belong to its category:
     attack -> projectile | beam | melee | aoe
     defense -> shield | dodge | reflect
     buff -> buff ; debuff -> debuff ; heal -> heal
3. Score `power` (1-10) and `speed` (1-10) strictly from the rubric below, based on \
the prompt's CLAIMED SCOPE, not its wording flair. When in doubt between two power \
values, pick the lower. Similar prompts must score similarly.
4. For buff/debuff ONLY, set `stat` to the stat the effect shifts: `speed` when the \
prompt is about hastening/slowing/quickness, otherwise `power`. Omit `stat` for all \
other categories.
5. Fill `visual` with 1-4 shape primitives approximating what the player described.
6. Write `flavor_text`: one short, punchy third-person narration line (max 90 chars).
7. If the prompt is incoherent or not an action, emit a harmless flail: \
category attack, subtype melee, power 1, speed 5, element physical.

SINGLE-EFFECT EXTRACTION (anti-stacking)
The action holds exactly ONE effect. When a prompt asks for several \
("a shield AND a sword AND 50 health"), pick the SINGLE most mechanically prominent \
effect (the first clearly actionable one if prominence ties); everything else is \
flavor with zero mechanical weight. Renaming a mechanic doesn't create a new one: \
"an indestructible fortress" is just a shield.

POWER (from claimed scope)
1-2  trivial/mundane: slap, pebble toss, small poke
3-4  modest weapon or minor magic: sword slash, small fireball, light shield
5-6  strong martial/magical: big fireball, lightning strike, tower shield
7-8  dramatic, battlefield-scale: meteor, tidal wave, fortress wall
9-10 apocalyptic/cosmic: black hole, sun drop, "destroy everything"

SPEED (from described delivery)
8-10 instant/darting: jab, dart, finger-snap zap
5-7  normal swing/cast: sword slash, thrown fireball
3-4  wind-up/summoned: summoning circle, charging beam
1-2  massive/slow: meteor falling, tectonic attack
Big scope implies low speed unless the prompt explicitly claims speed. An "instant \
black hole" is still power 10; its speed can be at most 4 for scope >= 9.

ELEMENTS
Closed set: physical, fire, water, nature, lightning. Default to the element the \
prompt implies (fire=flame/heat, water=ice/wave, nature=plant/earth/poison, \
lightning=electric); use physical for mundane force with no element.

VISUAL PRIMITIVES
Compose 1-4 primitives sketching the thing: sword = large line + small rect \
crossguard; fireball = medium orange circle + small triangle tail; lightning = \
large yellow zigzag; shield = large rect or ring; heal = green star/ring. Colors \
default to the element palette (fire=orange/red, water=blue, nature=green, \
lightning=yellow, physical=gray) unless the player specifies otherwise.

EXAMPLES
"I hurl a massive fireball at my opponent"
-> attack/projectile/fire, power 6, speed 6, "A roaring fireball screams across the arena!"
"I call a lightning bolt down from the sky"
-> attack/beam/lightning, power 7, speed 7, "The sky splits - lightning hammers down!"
"Give me a shield and a sword and a tank and 50 more health"
-> defense/shield/physical, power 4, speed 6, "A shield snaps up - the rest was wishful thinking."
"I collapse a black hole on top of them"
-> attack/aoe/physical, power 10, speed 2, "Space itself buckles as a black hole yawns open."
"I chug a healing potion"
-> heal/heal/nature, power 4, speed 7, "A quick swig - wounds knit closed in a green glow."
"I channel raw power into my fists" (buff, stat power)
-> buff/buff/physical, power 5, speed 4, stat power, "Red energy crackles around clenched fists."
"I hurl mud in their eyes to slow them down" (debuff, stat speed)
-> debuff/debuff/nature, power 4, speed 6, stat speed, "Mud fouls the enemy's footing."
"asdfjkl banana"
-> attack/melee/physical, power 1, speed 5, "A confused flail connects with nothing in particular."
"""


def _values(enum_cls) -> list[str]:
    return [m.value for m in enum_cls]


EMIT_ACTION_TOOL: dict = {
    "name": "emit_action",
    "description": "Emit the one structured action parsed from the player's prompt.",
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "category": {"type": "string", "enum": _values(Category)},
            "subtype": {
                "type": "string",
                "enum": _values(Subtype),
                "description": "Must belong to `category` (see rules).",
            },
            "element": {"type": "string", "enum": _values(Element)},
            "power": {
                "type": "integer",
                "minimum": 1,
                "maximum": 10,
                "description": "Magnitude from the rubric (claimed scope).",
            },
            "speed": {
                "type": "integer",
                "minimum": 1,
                "maximum": 10,
                "description": "Delivery speed from the rubric.",
            },
            "stat": {
                "type": "string",
                "enum": _values(Stat),
                "description": "Only for buff/debuff: which stat shifts. Omit otherwise.",
            },
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
                                "color": {
                                    "type": "string",
                                    "description": "Hex like #RRGGBB.",
                                },
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
        "required": ["category", "subtype", "element", "power", "speed", "flavor_text"],
    },
}
