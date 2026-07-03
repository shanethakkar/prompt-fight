# GAME_MECHANICS.md — Living Design Document

> **This file is the single source of truth for game rules.** Per `CLAUDE.md`, any change to a mechanic — in code, judge prompt, or config — must be reflected here in the same commit. Numbers shown below are the current values in `config/balance.json`; that file wins if they drift.

> **Effect grammar landed (2026-07-03).** The engine no longer classifies a prompt into one of 5 closed categories. It parses each prompt into a small **bundle of typed effect components** (DESIGN.md §3) that the server resolves and prices. This delivers persistent gear (armor), over-time effects (poison/burn/regen), real stat statuses, and multi-effect prompts. **Deferred (not yet implemented):** `control`/stun turn-skip (A.2), `resource` mana drain (A.3), `hit_chance`/blind + the full reliability/miss system and competitive/sandbox balancing modes (P1), entities/minions (P3). Where this doc says "deferred," the judge approximates with the nearest available component (e.g. freeze → heavy speed debuff, blind → speed debuff).

## 1. Match structure

- Two players, local hot-seat (one device, pass-and-play). **Open info** — no hidden inputs.
- **State is unit-based (P3.0):** each side is a `SideState{name, mana, cooldowns, stickman, entities}`. Every side has a **stickman** (its core) plus zero or more summoned **entities** (the summon/command layer lands in P3.1). All combat state (hp, effects, barriers) is **per-unit**; mana and cooldowns are **per-side** (one command per turn). **A side loses when its stickman's hp reaches 0** — entities are expendable helpers, not extra health bars.
- **Alternating single-action turns (Worms-style):** P1 acts, the result plays out, then P2 acts, then P1… (P1 starts; seeded starter-randomization is a P1 follow-up). Each turn the active player submits exactly **one** action (a bundle of up to 3 components), resolved immediately against the current state.
- Match ends the instant a player's HP reaches 0. **HP floors at 0** (no signed accounting). A player can now be KO'd **at the start of their own turn** by a damage-over-time effect before they act — the win goes to the effect's source (§7).
- **Round cap:** `max_turns` (default 30) counts **rounds** (one turn each). It is checked only at a **round boundary** (after P2 acts) so both players have taken equal actions; then higher HP wins, equal → draw.

## 2. Resources

| Resource | Start | Max | Regen |
|---|---|---|---|
| HP | 100 | 100 | none (except a `hot` effect you cast — §3) |
| Mana | 12 | 22 | +4 at the end of each of your own turns |

- Actions cost mana (see §5). You cannot confirm an action you can't afford (outside sandbox mode).
- Regen is applied at the **end** of your turn, so the mana shown when it's your turn to act is exactly what's spendable.

## 3. The effect grammar (open-ended)

Flavor is infinite; the mechanical vocabulary is a small fixed set. The judge (`JUDGE.md`) turns a freeform prompt into an **`Action`** = a bundle of **1–3 `EffectComponent`s** plus shared presentation (`element`, `speed`, `template`, `flavor_text`). Each component has a `type` and a `target` (`self` or `opponent`):

| Component | Target | Params | Effect |
|---|---|---|---|
| `damage` | opponent | `power` 1–10, `element` | Instant HP loss through the damage pipeline (§7). |
| `heal` | self | `power` 1–10 | Instant HP gain, `power × heal_multiplier` (×2.5), capped at `hp_max`. |
| `dot` | opponent | `power` 1–10, `duration` 1–4, `element` | Damage over time (poison/burn/bleed). Ticks `round(power × dot_multiplier)` (×1.0) at the afflicted's start-of-turn. |
| `hot` | self | `power` 1–10, `duration` 1–4 | Heal over time (regen). Ticks `round(power × hot_multiplier)` (×1.5) at your start-of-turn. |
| `stat` | either | `stat`, signed `magnitude` (±8), `duration` 1–4 | Persistent stat shift. `stat` ∈ {`power`, `speed`, `damage_taken`}. |
| `defense` | self | `subtype` (shield/dodge/reflect), `power`, `element` | A one-shot reactive stance for the opponent's next turn (§7). |
| `barrier` | self | `power`, `element` | A **durability pool** (armor/ward/force field): `pool = power × barrier_pool_per_power` (×3) absorb points that soak incoming hits until the pool shatters. **No timer** — persists as gear until broken. Dots bypass it. |
| `control` | opponent | `duration` 1–2 | A **stun** (freeze/petrify/knock-out): the target skips their turn(s). Dropped if the target is already stunned or briefly immune (§7). |
| `summon` | self | `name`, `hp` 15–80, weapon (`element`+`power`), `tags`, `item?` | Bring a **new entity** onto your side (P3.1b). The judge assigns its kit from world knowledge (archer→bow, dragon→fire/high-hp). **Staged** (acts next turn) and **dedicated** (a summoning command carries no attack). Capped at `max_entities_per_side` (3). |
| `item` | self | `name`, weapon (`element`+`power`)?, `tags` | **Equip** one of your units (P3.2). A *weapon*-item (re)arms it — a flaming sword makes its attacks fire; an *armor/trinket* item adds `tags` (kryptonite armor) that P3.3 matchups read. Applies immediately; stays until the unit dies. |

**Entities & commands (P3.1b).** Each side is a **stickman** (its core) + up to 3 summoned **entities**, each a targetable unit with its own HP/effects/weapon/tags. A command references units by server-minted **id**: `source_id` = which of *your* units acts (an entity's damage is anchored on its **weapon**, not the prompt's power), `target_id` = which unit it lands on (poison *their orc* while their stickman is untouched). Targeting a unit that no longer exists **fizzles** (never silently retargets). **Team-up combos (P3.1c):** one command can direct up to `max_units_per_command` (2) of your units — **one `damage` per source unit** (a stickman-only command still caps at one attack) — e.g. "my orc and my wizard both blast the dragon" → two `damage` components. The cost cap scales with the number of participating units (`max_bundle_cost × participants`), so a big combo can cost more than one turn's mana and you bank for it.

**Three mitigation flavors, don't confuse them:** `defense` = a *one-turn* reactive block/dodge/parry (consumed by the next hit); `barrier` = *durable worn armor* that soaks many hits over many turns until it shatters; `stat(damage_taken)` = a *percentage* multiplier (a temporary "brace" `−`, or a curse/`expose` `+` that makes a target take more).

**`stat` sign convention:** `magnitude` is the signed change to the **target's** stat. Help yourself → `+power` / `+speed` / `−damage_taken` (armor). Hurt the enemy → `−power` / `−speed` / `+damage_taken` (expose). `damage_taken` is a multiplier on incoming damage: each point = ±`damage_taken_per_point` (10%); multiple `damage_taken` effects **multiply**, clamped to `[0.25, 2.5]`.

**Server-side caps (enforced in `rules.normalize_components`, never trusted from the judge):** at most `max_components` (3) components, at most **1 `damage`** component per bundle, powers clamped 1–10, `magnitude` clamped ±8, `duration` clamped 1–4. Invalid components (e.g. a `stat` with no `stat` kind or zero magnitude) are dropped; a bundle that empties out becomes a harmless sputter.

## 4. Persistent effects and stat folding

A player carries a **list** of active effects (`PlayerState.effects`, capped at `max_effects_per_player` = 6, newest kept). Effects are applied to the target and tick/decrement on **that player's own turns** (§7). **Barriers are kept in a separate list** (`PlayerState.barriers`, capped at `max_barriers_per_player` = 2): they have no timer, so they must be exempt from the effect decrement and the effects-list cap. At read time the resolver folds the list into live numbers:

- **effective power** = `base + Σ(power stat magnitudes)`, floor 0.
- **effective speed** = `base + Σ(speed stat magnitudes)`, floor 1.
- **damage-taken multiplier** = `Π(1 + magnitude × 0.1)` over `damage_taken` effects, clamped `[0.25, 2.5]`.

**Stacking:** same-stat power/speed effects are **additive** (two weakens sum); `damage_taken` effects are **multiplicative**; `dot`/`hot` effects **coexist** (each ticks independently); a `defense` stance is a **single slot** — a new stance replaces the old.

## 5. Mana cost (server-computed, aggregate — never LLM-set)

The whole bundle is priced together (summing per-component costs was a burst exploit). The exponent is applied **per component**, then summed — this keeps a single move's cost identical to a lone action while making multi-effect bundles affordable:

`cost = min(max_bundle_cost, ceil( Σ(component_weightᵢ ^ cost_exponent) × bundle_mult[n] ))`

- **component_weight:** `damage` = `power×1.0`, `heal` = `power×1.0`, `defense` = `power×0.75`, `barrier` = `power×1.5`, `dot` = `power×duration×0.28`, `hot` = `power×duration×0.32`, `stat` = `|magnitude|×duration×0.42`.
- **bundle_mult** (super-additive surcharge by component count): 1 → 1.0, 2 → 1.15, 3 → 1.3.
- **cost_exponent** = 1.2; **max_bundle_cost** = 20 (just under mana_max 22). A single `damage` reproduces the old attack curve: power 5 → 7, power 6 → 9, power 10 → 16.
- **No burst discount:** because `Σ(wᵢ^e) ≥ max(wᵢ)^e` and `bundle_mult ≥ 1`, a bundle never costs less than its most expensive component alone. Typical 2-effect bundles land ~13–18 (heal+shield 13, damage+dot 15, lifesteal 18); 3-effect bundles ~18–22.

This is the power-scaling throttle: "I collapse a black hole onto you" is legal — the judge scores it power 10, which prices it out of reach early and forces saving up. Imagination is unconstrained; drama isn't cheap.

## 6. Cooldowns

Cooldowns are keyed by **component kind**, and only the turtle/lock levers are throttled: `heal` (3), `defense`/`barrier` (1, shared), `control` (2). `damage`, `dot`, and `stat` ride on mana alone and have **no cooldown**.

- **Heavy-move rule:** a `heal`/`defense` component with power ≥ 8 adds +1 turn to that kind's cooldown.
- A bundle whose kind is on cooldown cannot be confirmed; `/api/judge` reports `on_cooldown` = true if **any** cooldownable kind in the bundle is currently blocked.

## 7. Resolving a turn (three phases)

Each turn the **active player A** acts against **opponent O**. The turn runs START → ACT → END, and **each tick and each component becomes one playback event** (a turn can emit several beats).

1. **START — over-time ticks.** For each `dot` on A, deal its frozen `per_turn` (bypassing stances and armor); for each `hot` on A, heal its frozen `per_turn` (capped). **Then check KO:** if A hit 0 HP from a dot, the match ends immediately and **O (the dot's source) wins** — A never acts.
2. **Stun check.** If A is stunned (an active `control` effect), A **skips ACT entirely** — no mana, no components (a stun-skip beat is emitted). This is server-authoritative: a stunned player skips regardless of what action the client submitted (or `null`). The START ticks above still fired, so a stunned player can still be poisoned to death.
3. **ACT — pay + apply.** Pay the aggregate mana cost (floor 0). Apply each component in order: `damage` (through the pipeline below), `heal`, `dot`/`stat`-on-opponent/`control` (land on O **immediately**), `hot`/`stat`-on-self/`defense`/`barrier` (**staged** — installed at END, so an "empower + strike" boosts your *next* strike, not this one). A `control` is dropped if O is already stunned or within a post-stun immunity window. HP floors at 0.
4. **END — upkeep (A only).** Decrement A's effect timers (use-before-decrement) and drop the expired; when a `control` on A just expired, grant A `stun_immunity_turns` (2) of immunity to further stun (else count that window down); install A's staged self-effects (a new stance replaces the old; effects list capped at 6, barriers at 2); tick A's cooldowns and apply this bundle's new cooldowns; regen A's mana (capped, **even while stunned**). O's effects/cooldowns are untouched — they tick on O's turns.
5. **Match-over check**, then advance (P1↔P2; a P2 action closes the round and checks the round cap, §1).

**Consequences of owner-turn timing:** a self-buff cast on your turn first bites on your *next* turn and lasts exactly `duration` of your turns; a `dot`/debuff lands on O immediately and ticks on O's next `duration` turns; a cooldown-N move blocks exactly your next N turns.

### Damage pipeline (per `damage` component, pinned order)
`raw = effective_power × attack_damage_multiplier` (×3) → `× type_multiplier` (only vs a stance's element, §8) → `× damage_taken_mult` (O's `damage_taken` %, always) → **then** the flat stance block/dodge/reflect (consumed on use) → **then a `barrier` absorbs** (durability pool, closest to HP: soaks in list order, cascades through several, and each emptied pool **shatters**) → floor 0. Because the HP-application point is shared, a **reflected** hit is absorbed by the *attacker's own* barrier. A `dot` tick bypasses stances, `damage_taken`, and barriers (it was frozen at application).

### Defenses are stances (frozen, consume-on-hit)
A `defense` component raised on your turn doesn't block anything yet — it **persists as a stance** for the opponent's next attack, with effective power/speed/element **frozen at cast**. It is **consumed the moment it mitigates an attack**, else expires at your next END (`defense_stance_duration_turns`, default 1). Mitigation applies to the *typed, armor-adjusted* damage:
- **Shield:** reduce incoming damage by `shield_power × block_multiplier` (×3), floor 0.
- **Dodge:** if `dodge_speed ≥ attacker's effective speed`, take 0; else take `partial_dodge_damage_fraction` (50%).
- **Reflect:** if `reflect_power ≥ attacker's effective power`, negate and return `reflect_return_fraction` (50%) **to the attacker** (can KO them); else absorb `reflect_power × block_multiplier` and take the remainder.

*Open-info caveat: a deterministic dodge is easy to play around (attack faster than the visible dodge). DESIGN P1's reliability system replaces this with a probabilistic evade.*

## 8. Elements and type chart

Elements (closed set): `physical`, `fire`, `water`, `nature`, `lightning`.

Advantage chart (attacker → defending stance's element): fire > nature, nature > water, water > fire, lightning > water, nature > lightning (grounding). `physical` is neutral everywhere.

- Advantage: ×1.5. Disadvantage (reverse): ×0.75. Neutral: ×1.0.
- The chart compares the attacker's element against the **defending stance's element** only. **Elements are inert against an undefended target** (no persistent element on players), so an unblocked attack is always ×1.0. `damage_taken` armor is element-agnostic and applies whether or not a stance is present.
- Chart lives as an adjacency map in `balance.json` — placeholder values, expected to change in a later balance pass.

## 9. Prompt → cost preview flow

1. Player types a prompt, hits **Submit** (not yet committed).
2. One judge call; the UI shows the parsed component bundle + aggregate mana cost.
3. Player picks **Confirm** (locks the action) or **Rewrite**.
4. **Rewrite cap: 2 per turn.** After the cap, the last submitted judgeable action locks in automatically.
5. Judge runs at temperature 0 — identical prompts produce identical bundles (no cost-fishing).
6. Moderation rejections consume a rewrite, never mana. An unaffordable action cannot be confirmed and prompts a rewrite. **Sandbox mode** ignores the affordability/cooldown gates client-side (the structural component caps in §3 still apply server-side).

## 10. Timers and AFK (v1)

- Optional per-submission timer, off by default for hot-seat (`balance.json: input_timer_seconds = null`).
- If enabled and expired with no submission, the player forfeits the turn (a zero-cost "falter" no-op resolves for them).

## 11. Out of scope / deferred

Not implemented yet, in rough priority order: **A.3** `resource` (mana drain/grant); **P1** `hit_chance`/blind + the reliability/miss system and competitive-vs-sandbox balance modes; **P3** entities/minions (summon/charm/taunt). Online play, accounts, AI opponent, items/equipment, and persistent progression remain out of scope; additions require user approval and a `SPEC.md` scope change.

---

*Changelog (append newest first):*
- 2026-07-03 — **Team-up combos (P3.1c).** A command may direct up to 2 of your units at once (one `damage` per source unit), replacing the old ≤1-damage-per-command rule; `max_components` 3→4, and the cost cap now scales with participant count so a multi-unit alpha strike isn't a burst bargain (you bank for it). The judge emits one component per acting unit with its `source_id`.
- 2026-07-03 — **Entity layer (P3.0/P3.1a/P3.1b).** The board is now 2 rosters of units. P3.0 reshaped state into `SideState{stickman, entities}` (win = stickman death) behavior-identically. P3.1a made the judge **stateful** (it gets a compact roster and echoes server-minted unit ids; `normalize` validates them). P3.1b added the **`summon`** component: entities with LLM-assigned kits (assumed weapons + tags), a staged/dedicated lifecycle, per-unit targeting (an entity's damage anchored on its weapon; poison hits a *specific* unit), entity death that removes without a loss, and a roster-table UI. Deferred: P3.1c combos, P3.2 items, P3.3 effectiveness/kryptonite crits, P3.4 charm.
- 2026-07-03 — **Real stun (`control`, A.2).** Added a `control` component: the target skips their turn(s). START ticks + poison-KO still run first (a stunned player can be poisoned to death); then the stunned player skips ACT — server-authoritative (`/api/resolve` now accepts `action: null`, and skips regardless of the submitted action). Anti stun-lock: a `control` is dropped if the target is already stunned or within a `stun_immunity_turns` (2) window granted when a stun wears off; plus control cooldown 2, `max_control_duration` 2, and a high cost (weight × duration). Judge maps "freeze solid"/"petrify"/"knock out" → `control` ("blind"/"slow" stay a speed debuff).
- 2026-07-03 — **Durability armor (`barrier`).** Added a `barrier` component: a persistent absorb pool (`power × 3` points) that soaks incoming damage until it shatters — no timer, kept in a separate `PlayerState.barriers` list (exempt from the effect decrement + cap). Sits closest to HP in the damage pipeline (after the stance layer); dots bypass it; a reflected hit is soaked by the attacker's own barrier. The judge now maps durable gear ("plate armor", "force field", "ward") → `barrier`, keeping `defense` for one-shot blocks and `stat(damage_taken)` for expose/brace. (Also shipped: a frontend combat ledger — presentation only, no rule change.)
- 2026-07-03 — **Cost retune.** Bundle pricing now applies the exponent **per component** then sums (`Σ(wᵢ^e)`, was `(Σ wᵢ)^e`) — single-move costs are unchanged but 2-effect bundles dropped from the ~20 cap to ~13–18. Softened weights (heal 1.1→1.0, defense 0.8→0.75, dot/hot/stat down) and bundle multipliers (2: 1.3→1.15, 3: 1.7→1.3); mana economy up (start 10→12, max 20→22, regen 3→4). No-burst-discount invariant preserved.
- 2026-07-03 — **Effect grammar (Stage A).** Replaced the 5 closed categories with an open-ended bundle of typed `EffectComponent`s (`damage`/`heal`/`dot`/`hot`/`stat`/`defense`). Rewrote §3–§8: persistent effect **list** (armor/poison/regen/weaken now persist and stack), **aggregate** bundle pricing with a super-additive surcharge, **component-kind** cooldowns, a three-phase turn with **start-of-turn over-time ticks + a new poison-KO path**, staged self-effects, and the pinned damage pipeline (type → armor → stance). Judge now emits a permissive component list; the server normalizes/clamps/caps. Deferred: stun, resource, blind/reliability, entities.
- 2026-07-03 — **Turn model → alternating single-action turns** (Worms-style, was simultaneous). Resolver is now `resolve_turn(state, action)`; deleted speed-ordering / snapshot-delta / double-KO tiebreak / defense-priority tier. HP floors at 0. Effect/cooldown upkeep is end-of-*your*-turn (owner-turn timing). **Defenses are now persistent stances** (frozen at cast, consume-on-hit, expire next turn). Round cap checked at the round boundary. Events enriched (`target` + `effect` summary) for clear result narration.
- 2026-07-02 — M1 resolver: pinned previously-ambiguous rules (signed-HP double-KO tiebreak, fixed damage pipeline, effect/cooldown staging, reflect returns to attacker, elements inert vs. undefended, buff/debuff single-slot). Superseded by the effect grammar above.
- 2026-07-01 — Initial version from design sessions. All numeric values are pre-playtest placeholders.
