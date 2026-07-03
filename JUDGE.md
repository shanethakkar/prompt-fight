# JUDGE.md — Judge Rubric, Schema, and Evals

The judge is the game's only AI component: an LLM that converts a freeform player prompt into one structured **`Action`** — a small bundle of typed effect components. It classifies and scores — it never computes mana cost, damage, or any balance-affecting arithmetic (all of that is deterministic server code).

> Any change to this file or the judge system prompt requires the eval suite (§7) to pass before merging. See `CLAUDE.md` testing gates.

## 1. Model configuration

- Model: config value (`balance.json: judge_model`), default a small fast cloud model (Claude Haiku via Anthropic API).
- `temperature = 0` — identical prompts must judge identically (prevents cost-preview fishing).
- Structured output enforced via **forced tool-use**: the judge must call a single `emit_action` tool (`tool_choice` forces it) whose input schema mirrors §4. A malformed/absent tool call is retried once, then falls back to a "sputter" no-op (a single power-1 melee `damage` component).
- The judge system prompt lives in `backend/app/judge_prompt.py` (`JUDGE_SYSTEM`), which mirrors this file. Keep the two in sync; the eval suite (§7) is the regression guard.
- **Server-side normalization is the safety net.** The judge's component list is *permissive* (all params optional). `rules.normalize_components` validates required-per-type, clamps every numeric to its balance range, enforces the structural caps (§3), and drops anything invalid — so a judge mistake degrades gracefully instead of crashing or exploiting.
- **Stateful (P3.1a):** `/api/judge` sends the full battlefield; the server renders a compact **roster** (each side's units with a server-minted `id`, name, kind, rough HP) into the prompt. The judge echoes ids in each component's `source_id` (which of *your* units acts, default your stickman) and `target_id` (which unit it lands on) — it **never invents an id**. `normalize_components` validates every id against the real roster (invalid → the relevant stickman); the resolver never trusts a raw id. With no roster passed (offline evals), the judge behaves statelessly as before.

## 2. Judge instructions (core rules)

1. Always call `emit_action` exactly once. No prose.
2. Emit **1–3 components** — the most mechanically prominent effects the prompt describes. Extra flourishes are flavor with no component. When in doubt, emit fewer.
3. Never invent component types, elements, stats, or fields outside the closed sets.
4. Score conservatively (claimed scope, not wording flair). When torn between two magnitudes, pick the lower. Similar prompts must produce similar bundles.
5. Fill `element`, `speed`, `template`, and `flavor_text` for the overall visual (§5/§6). `flavor_text`: one punchy third-person line, max 90 chars.
6. If the prompt is incoherent or not an action, emit a single small melee `damage` component, power 1.

## 3. Components and bundling (flavor infinite, mechanics small)

Capture INTENT with components; keep flavor in `flavor_text`. A "magic wand that confuses their zombie", a "sand monster that blinds the archer", and "I punch them" are all combinations of the same handful of component types. Each component has a `type` and a `target` (`self` | `opponent`):

- **`damage`** (opponent) — instant hit. `power` 1–10, `element`.
- **`heal`** (self) — instant self-heal. `power` 1–10.
- **`dot`** (opponent) — damage over time (poison/burn/bleed). `power` (per-tick), `duration` 1–4, `element`. Use for ongoing HP loss — *not* a one-time hit.
- **`hot`** (self) — heal over time (regen). `power`, `duration`.
- **`stat`** (either) — persistent stat shift. `stat` ∈ {`power`, `speed`, `damage_taken`}, signed `magnitude` (about −8..+8), `duration`. `magnitude` is the signed change to the **target's** stat: help yourself (`+power`/`+speed`/`−damage_taken` armor), hurt the enemy (`−power`/`−speed`/`+damage_taken` expose).
- **`defense`** (self) — a one-shot reactive stance for the opponent's next turn. `subtype` (shield/dodge/reflect), `power`, `element`.
- **`barrier`** (self, or `target_id` an owned unit) — a persistent durability pool (worn armor / ward / force field) that soaks hits across many turns until it shatters. **This is how a unit gets real damage protection — always use it for armor** (plate/diamond/iron armor, "give my orc a suit of armor", a force field). `power` (the armor rating), `element`.
- **`control`** (opponent) — a stun: the target skips their turn(s). `duration` (1–2). For "freeze solid", "petrify", "stun", "knock out", "stop time".
- **`summon`** (self, P3.1b) — bring a new entity onto your side. `name`, `hp` **strictly by size** (8–75; a common animal is *not* a tank: rat/imp ~8, dog/goblin ~15, wolf/soldier ~25, orc/knight ~35, ogre/troll/golem ~50, dragon/giant/god ~70), weapon (`element`+`power`) inferred from what it IS (archer→bow, dragon→fire/high-hp), optional `tags`/`item`. A summon takes the whole command (no attacking); the unit acts next turn. Reference existing units by id (`source_id`/`target_id`) — "my orc attacks their wizard".
- **`item`** (self, P3.2) — equip one of your units (`target_id`) with a **weapon** or a **matchup trinket**. `name` + for a weapon `element`+`power` ((re)arms the unit), or for gear whose point is a matchup `tags` (e.g. `["kryptonite"]`). "Give my orc a flaming sword", "forge kryptonite armor". **An item does NOT reduce damage** — for protective armor use `barrier` (for a named suit, emit the `barrier` *and* an `item` so it shows as worn gear).

**Effectiveness (P3.3).** A `damage`/`dot` may carry `effectiveness` (resisted/neutral/strong/devastating) + `eff_tag` (the target trait it hinges on), from the *semantic* matchup — kryptonite vs a `kryptonian` → devastating; water vs `fire` → strong; a mundane hit vs a near-invulnerable target → resisted. Only leave neutral when the target really has that tag **and** the attack is the right counter. The server drops any tier the target's tags (and a specially-equipped attacker) don't ground, so you can't crit a bare punch — equip the counter first.

**Aptitude (P1.2).** A `damage`/`dot` carries `aptitude` (fit/improvised/unfit) + `apt_basis` (the reason), judged from **who is acting** (its name/kind/tags/items/weapon). A mundane physical action (punch, throw, swing a held weapon) is `fit` for anyone. A *specialized* one (a spell, elemental breath, a magic blast) is `fit` only for a suited actor — a summoned mage/dragon, or a unit with the right item (a wand) or an elemental weapon; a bare stickman attempting it is `improvised` (a credible workaround with no gear, e.g. "grabs a torch to throw fire") or `unfit` (a bare over-reach). The **server is authoritative on `fit`** (it grounds gear/identity, so a wand-equipped stickman *is* fit even if you're conservative) and only uses your improvised-vs-unfit call for the no-gear case; competence sets the reliability floor + a power multiplier (competitive mode).

**`dot` vs `stat`:** ongoing HP loss ("bleed", "burn", "poison") → `dot`. Making them weaker/slower (no HP loss) → `stat`. **`defense` vs `barrier` vs `stat(damage_taken)`:** one-turn block/dodge/parry → `defense`; durable worn armor / lasting ward → `barrier`; "they take more damage" (curse/mark) → `stat damage_taken +` on the opponent. **`stat(speed)` vs `control`:** merely slower/blinded → `stat speed −`; unable to act at all (frozen solid, petrified, knocked out) → `control`. **Deferred approximations** (until later phases add them): "blind" → a `speed` debuff on the opponent; "drain their mana" → nearest available.

**Bundles are encouraged.** "I heal to full and raise a shield" → `heal(self)` + `defense(shield, self)`; "I swing my flaming sword while buffing my speed" → `damage(fire)` + `stat(speed, +, self)`. A prompt asking for 8 effects still yields at most the 3 most prominent (the server truncates regardless).

## 4. `Action` schema

Defined once here; mirrored as a Pydantic model (backend) and TypeScript type (frontend) — all three change together or not at all.

```json
{
  "components": [
    {
      "type": "damage | heal | dot | hot | stat | defense",
      "target": "self | opponent",
      "element": "physical | fire | water | nature | lightning",
      "power": 1-10,               // damage/heal/dot/hot/defense
      "magnitude": -8..8,          // stat: signed change to target's stat
      "duration": 1-4,             // dot/hot/stat
      "stat": "power | speed | damage_taken",   // stat only
      "subtype": "shield | dodge | reflect"     // defense only
    }
  ],
  "element": "physical | fire | water | nature | lightning",
  "speed": 1-10,
  "template": "projectile | beam | melee | aoe_burst | shield_raise | dodge | reflect | buff_aura | debuff_cloud | heal_glow",
  "visual": { "primitives": [ { "shape": "...", "size": "...", "color": "#RRGGBB", "offset": [x, y] } ] },
  "flavor_text": "string, max 90 chars"
}
```

Notes: `components` holds 1–3 entries (the tool caps `maxItems` at 3; the server enforces ≤1 `damage`). Only `type` is required per component — every other param is optional and filled/clamped server-side. `mana_cost` is **not** in the schema — the server prices the whole bundle (`rules.bundle_cost`) from component weights + a super-additive count surcharge.

## 5. Visual primitives guidance

Compose 1–4 primitives to sketch the described thing: sword = large `line` + small `rect` crossguard; fireball = medium orange `circle` + small `triangle` tail; lightning = large yellow `zigzag`; shield = large `rect` or `ring`; heal = green `star`/`ring`. Colors default to the element's palette (fire=orange/red, water=blue, nature=green, lightning=yellow, physical=gray) unless the player specifies otherwise.

## 6. Scoring rubric

**Power / magnitude (from claimed scope):**
| Level | Scope | Examples |
|---|---|---|
| 1–2 | Trivial | slap, pebble, weak poison |
| 3–4 | Modest | sword slash, small fireball, light armor, mild slow |
| 5–6 | Strong | big fireball, tower shield, heavy poison, real weaken |
| 7–8 | Battlefield-scale | meteor, tidal wave, frozen-solid |
| 9–10 | Apocalyptic (damage only) | black hole, sun drop |

**Duration:** brief 1–2, lingering 3, long-lasting 4 (capped at 4). **Speed** (whole action): 8–10 instant/darting, 5–7 normal swing/cast, 3–4 wind-up/summon, 1–2 massive/slow. Big scope implies low speed unless speed is explicitly claimed.

**Elements:** fire=flame/heat, water=ice/wave, nature=plant/earth/poison, lightning=electric, physical=mundane force. A `dot`'s element sets its flavor (fire=burn, nature=poison, physical=bleed, water=chill, lightning=shock).

**Consistency rule:** similar prompts must score similarly. When in doubt, pick lower.

## 7. Eval suite

`backend/tests/fixtures/judge_eval.json`: fixture prompts, each asserting on the emitted component bundle via optional keys (`types_exact`, `contains`, `excludes`, `min/max_components`, `element`, `power`, and per-type `checks` on stat/target/magnitude/power/duration). Run with pytest against the live judge at temperature 0 (`uv run pytest -m live`). Required coverage:

- Each component type in isolation (damage/heal/dot/hot; stat × power/speed/damage_taken; defense × shield/dodge/reflect).
- The stress prompts that used to flatten: poison → `dot`, plate armor → persistent `stat(damage_taken, −)`, "heal AND shield" → 2 components, freeze → heavy speed debuff, blind → opponent stat.
- Multi-effect bundles (must emit ≥ 2 components).
- Count-restraint prompts ("give me 8 things") — must yield ≤ `max_components`.
- Near-duplicate pairs — must produce the same component-type multiset.
- Grow the file whenever playtesting reveals an exploit or misjudgment.

## 8. Few-shot examples (included in judge system prompt)

- **"I hurl a massive fireball"** → `[damage fire power 6]`, element fire, speed 6, template projectile.
- **"I poison their bloodstream so they bleed out slowly"** → `[dot nature power 5 duration 3 opponent]`.
- **"I put on a full suit of enchanted plate armor"** → `[barrier power 6 self]`, template shield_raise (durable gear → a barrier pool, not a one-shot shield).
- **"I freeze them solid so they can't move"** → `[control duration 2 opponent]`, element water (can't act at all → a stun, not a slow).
- **"I heal myself to full and raise a shield"** → `[heal power 6 self] + [defense shield power 5 self]`.
- **"I collapse a black hole on them"** → `[damage physical power 10]`, speed 2, template aoe_burst.
- **"asdfjkl banana"** → `[damage physical power 1]` (the sputter).
