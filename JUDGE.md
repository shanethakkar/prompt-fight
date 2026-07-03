# JUDGE.md — Judge Rubric, Schema, and Evals

The judge is the game's only AI component: an LLM that converts a freeform player prompt into one structured `JudgedAction`. It classifies and scores — it never computes mana cost, damage, or any balance-affecting arithmetic (all of that is deterministic server code).

> Any change to this file or the judge system prompt requires the eval suite (§7) to pass before merging. See `CLAUDE.md` testing gates.

## 1. Model configuration

- Model: config value (`balance.json: judge_model`), default a small fast cloud model (Claude Haiku via Anthropic API; Groq-hosted small model acceptable).
- `temperature = 0` — identical prompts must judge identically (prevents cost-preview fishing).
- Structured output enforced (tool/JSON schema mode). A malformed response is retried once, then falls back to a "sputter" no-op action with an apologetic narration.
- The judge system prompt is built from this file: rules (§2–§3), rubric (§6), schema (§4), and few-shot examples (§8).

## 2. Judge instructions (core rules)

1. Output exactly one `JudgedAction` conforming to the schema. No prose outside the JSON.
2. Classify into exactly one category/subtype from the closed sets. Never invent categories, elements, or fields.
3. Score `power` and `speed` strictly from the rubric in §6, based on the prompt's *claimed scope*, not its wording flair.
4. Fill `visual` with 1–4 shape primitives approximating what the player described (§5).
5. Write `flavor_text`: one short, punchy third-person narration line (max 90 chars) for playback.
6. If the prompt is incoherent or not an action, return category `attack`, subtype `melee`, power 1, speed 5, physical — a harmless flail — with fitting flavor text.

## 3. Single-effect extraction (anti-stacking)

The schema structurally holds one effect. When a prompt requests multiple effects, select the **single most mechanically prominent** one (the first clearly actionable effect if prominence ties) and treat all others as flavor text with zero mechanical weight.

- "Give me a shield, a sword, a tank, and 50 more health" → Defense/shield (first prominent effect); sword/tank/health are flavor.
- "I throw a fireball while healing myself" → Attack/projectile/fire; heal is flavor.
- Renaming mechanics doesn't create mechanics: "an indestructible fortress" is Defense/shield with power capped at 10 like everything else.

## 4. JudgedAction schema

Defined once here; mirrored as a Pydantic model (backend) and TypeScript type (frontend) — all three change together or not at all.

```json
{
  "category": "attack | defense | buff | debuff | heal",
  "subtype": "projectile | beam | melee | aoe | shield | dodge | reflect | buff | debuff | heal",
  "element": "physical | fire | water | nature | lightning",
  "power": 1-10,
  "speed": 1-10,
  "template": "projectile | beam | melee | aoe_burst | shield_raise | dodge | reflect | buff_aura | debuff_cloud | heal_glow",
  "visual": {
    "primitives": [
      { "shape": "circle | rect | triangle | line | zigzag | ring | star",
        "size": "small | medium | large",
        "color": "#RRGGBB",
        "offset": [x, y] }
    ]
  },
  "flavor_text": "string, max 90 chars"
}
```

Notes: `subtype` must belong to `category`. `template` follows deterministically from `subtype` (server validates and corrects). `mana_cost` is **not** in the schema — the server computes it from `power` + `category` per `balance.json`.

## 5. Visual primitives guidance

Compose 1–4 primitives to sketch the described thing: sword = large `line` + small `rect` crossguard; fireball = medium orange `circle` + small `triangle` tail; lightning = large yellow `zigzag`; shield = large `rect` or `ring`; heal = green `star`/`ring`. Colors should default to the element's palette (fire=orange/red, water=blue, nature=green, lightning=yellow, physical=gray) unless the player specifies otherwise.

## 6. Scoring rubric

**Power (from claimed scope):**
| Power | Scope of claim | Examples |
|---|---|---|
| 1–2 | Trivial/mundane | slap, pebble toss, small poke |
| 3–4 | Modest weapon or minor magic | sword slash, small fireball, light shield |
| 5–6 | Strong martial/magical | big fireball, lightning strike, tower shield |
| 7–8 | Dramatic, battlefield-scale | meteor, tidal wave, fortress wall |
| 9–10 | Apocalyptic/cosmic claims | black hole, sun drop, "destroy everything" |

**Speed (from described delivery):**
| Speed | Delivery | Examples |
|---|---|---|
| 8–10 | Instant/darting | jab, dart, finger-snap zap |
| 5–7 | Normal swing/cast | sword slash, thrown fireball |
| 3–4 | Wind-up/summoned | summoning circle, charging beam |
| 1–2 | Massive/slow | meteor falling, tectonic attack |

Big scope naturally implies low speed; the judge should reflect that unless the prompt explicitly claims speed (which raises the power interpretation ceiling — "an instant black hole" is still power 10, speed can be at most 4 for scope ≥ 9; enforce this cap).

**Consistency rule:** similar prompts must score similarly. When in doubt between two power values, pick the lower.

## 7. Eval suite

`backend/tests/fixtures/judge_eval.json`: ≥ 30 fixture prompts, each with expected `category`, `element`, and an inclusive `power` range (±1 tolerance). Run with pytest against the live judge at temperature 0. Required coverage:

- ≥ 2 prompts per category (10+)
- ≥ 4 anti-stacking greedy prompts (must yield exactly one effect, expected category asserted)
- ≥ 3 absurd-scope prompts (must land power 9–10, not error)
- ≥ 2 incoherent prompts (must produce the harmless-flail fallback)
- ≥ 3 near-duplicate pairs (must judge into identical category and power)
- Grow the file whenever playtesting reveals an exploit or misjudgment (M6 balance pass).

## 8. Few-shot examples (included in judge system prompt)

**"I hurl a massive fireball at my opponent"**
```json
{"category":"attack","subtype":"projectile","element":"fire","power":6,"speed":6,"template":"projectile","visual":{"primitives":[{"shape":"circle","size":"medium","color":"#FF6A00","offset":[0,0]},{"shape":"triangle","size":"small","color":"#FFB300","offset":[-12,0]}]},"flavor_text":"A roaring fireball screams across the arena!"}
```

**"I call a lightning bolt down from the sky"**
```json
{"category":"attack","subtype":"beam","element":"lightning","power":7,"speed":7,"template":"beam","visual":{"primitives":[{"shape":"zigzag","size":"large","color":"#FFE13A","offset":[0,-40]}]},"flavor_text":"The sky splits — lightning hammers down!"}
```

**"Give me a shield and a sword and a tank and 50 more health"**
```json
{"category":"defense","subtype":"shield","element":"physical","power":4,"speed":6,"template":"shield_raise","visual":{"primitives":[{"shape":"rect","size":"large","color":"#9AA0A6","offset":[10,0]}]},"flavor_text":"A shield snaps up — the rest was wishful thinking."}
```

**"I collapse a black hole on top of them"**
```json
{"category":"attack","subtype":"aoe","element":"physical","power":10,"speed":2,"template":"aoe_burst","visual":{"primitives":[{"shape":"circle","size":"large","color":"#1A1A1A","offset":[0,0]},{"shape":"ring","size":"large","color":"#7B2FF7","offset":[0,0]}]},"flavor_text":"Space itself buckles as a black hole yawns open."}
```

**"I chug a healing potion"**
```json
{"category":"heal","subtype":"heal","element":"nature","power":4,"speed":7,"template":"heal_glow","visual":{"primitives":[{"shape":"star","size":"small","color":"#35C759","offset":[0,-20]},{"shape":"ring","size":"medium","color":"#8CE99A","offset":[0,0]}]},"flavor_text":"A quick swig — wounds knit closed in a green glow."}
```

**"asdfjkl banana"**
```json
{"category":"attack","subtype":"melee","element":"physical","power":1,"speed":5,"template":"melee","visual":{"primitives":[{"shape":"line","size":"small","color":"#9AA0A6","offset":[8,0]}]},"flavor_text":"A confused flail connects with nothing in particular."}
```
