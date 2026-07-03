# GAME_MECHANICS.md — Living Design Document

> **This file is the single source of truth for game rules.** Per `CLAUDE.md`, any change to a mechanic — in code, judge prompt, or config — must be reflected here in the same commit. Numbers shown below are the current values in `config/balance.json`; that file wins if they drift.

## 1. Match structure

- Two players, local hot-seat (one device, pass-and-play with hidden-input handoff screens).
- **Simultaneous turns:** both players secretly submit one action; actions resolve together.
- **One action per turn.** Always. No exceptions, no multi-effect actions.
- Match ends when a player's HP ≤ 0. If both reach ≤ 0 in the same resolution, the player at higher HP wins; equal → draw.
- Max-turn cap (default 30): at cap, higher remaining HP wins; equal → draw.

## 2. Resources

| Resource | Start | Max | Regen |
|---|---|---|---|
| HP | 100 | 100 | none |
| Mana | 10 | 20 | +3 at start of each turn |

- Actions cost mana (see §5). You cannot confirm an action you can't afford.
- Mana regen happens before the input phase, so displayed mana is spendable mana.

## 3. Action categories (closed set)

Every prompt is judged into **exactly one** category:

1. **Attack** — subtypes: `projectile`, `beam`, `melee`, `aoe`. Deals damage.
2. **Defense** — subtypes: `shield`, `dodge`, `reflect`. Mitigates incoming damage this turn.
3. **Buff** — temporary self-boost (power or speed, duration in turns).
4. **Debuff** — temporary opponent-weakening (power or speed, duration in turns).
5. **Heal** — restores HP (never above max).

**Anti-stacking rule (structural):** the `JudgedAction` schema can hold only one category, one element, one power value. Prompts requesting multiple effects ("a shield AND a sword AND 50 HP") are judged on the single most prominent effect; everything else is flavor text with zero mechanical weight. See `JUDGE.md` §3.

## 4. Stats

- **Power (1–10):** magnitude of the effect. Scales damage, block value, buff/debuff strength, heal amount.
- **Speed (1–10):** resolution ordering within the turn (see §7). Quick jabs are fast; huge windups are slow. The judge assigns both from the prompt's described scope per the rubric in `JUDGE.md` §6.

Damage = `power × attack_damage_multiplier` (default ×3) × type-chart modifier − applicable block value. Heal = `power × heal_multiplier` (default ×2.5). Buff/debuff = ±`power`-scaled stat shift for `duration` turns (default 2).

## 5. Mana cost (server-computed, never LLM-set)

`cost = ceil(power ^ cost_exponent × category_multiplier)` — parameters in `balance.json` (defaults: exponent 1.2; multipliers: attack 1.0, defense 0.8, buff 0.9, debuff 0.9, heal 1.1).

This is the power-scaling throttle: "I collapse a black hole onto you" is legal — the judge just scores it power 10, which prices it out of reach early and forces saving up. Imagination is unconstrained; drama isn't cheap.

## 6. Cooldowns

- Per-category cooldowns (in turns) apply after use — defaults: attack 0, defense 1, buff 2, debuff 2, heal 3.
- **Heavy-move rule:** any action with power ≥ 8 adds +1 turn to its category's cooldown.
- A category on cooldown cannot be selected; the judge response is checked against the player's cooldown state at confirm time.

## 7. Resolution order (within a turn)

1. **Priority tier — Defense first.** All Defense actions activate at the start of resolution regardless of speed (a shield raised is up for the whole turn).
2. **Everything else resolves in descending speed order.** Ties resolve simultaneously.
3. **KO check between resolutions:** if the faster action reduces the opponent to ≤ 0 HP, the slower action does not resolve. (Simultaneous ties: both resolve, then §1 tiebreak applies.)

### Defense interaction math
- **Shield:** incoming damage reduced by `shield_power × block_multiplier` (default ×3), floor 0. Element interaction per type chart (§8).
- **Dodge:** if `dodge_speed ≥ attack_speed`, take 0 damage; otherwise take `partial_dodge_damage_fraction` (default 50%) of damage.
- **Reflect:** if `reflect_power ≥ attack_power`, negate and return `reflect_return_fraction` (default 50%) of the damage to the attacker; otherwise absorb `reflect_power × block_multiplier` and take the remainder.
- Defense actions only affect incoming actions this turn; they do not persist.

## 8. Elements and type chart

Elements (closed set): `physical`, `fire`, `water`, `nature`, `lightning`.

Advantage chart (attacker → defender/defense element): fire > nature, nature > water, water > fire, lightning > water, nature > lightning (grounding). `physical` is neutral everywhere.

- Advantage: damage ×1.5. Disadvantage (reverse direction): ×0.75. Neutral: ×1.0.
- The chart also applies attack-element vs. shield-element (a water shield blocks fire extra well, etc.).
- Chart lives as an adjacency map in `balance.json` — placeholder values, expected to change in the M6 balance pass.

## 9. Prompt → cost preview flow

1. Player types a prompt, hits **Submit** (not yet committed).
2. One judge call; UI shows parsed effect (category, element, power, speed) + computed mana cost.
3. Player picks **Confirm** (locks the action) or **Rewrite**.
4. **Rewrite cap: 2 per turn.** After the cap, the last submitted judgeable action locks in automatically.
5. Judge runs at temperature 0 — identical prompts produce identical judgments (no cost-fishing).
6. Moderation rejections consume a rewrite, never mana. An unaffordable action cannot be confirmed and prompts a rewrite (consuming one).

## 10. Timers and AFK (v1)

- Optional per-submission timer, off by default for hot-seat (`balance.json: input_timer_seconds = null`).
- If enabled and expired with no submission, the player forfeits the turn (a zero-cost "falter" no-op resolves for them).

## 11. Out of scope in v1 (do not implement)

Online play, accounts, AI opponent (stub only), status-effect stacking beyond single buff/debuff timers, items/equipment, persistent progression. Additions here require user approval and a `SPEC.md` scope change.

---

*Changelog (append newest first):*
- 2026-07-01 — Initial version from design sessions. All numeric values are pre-playtest placeholders.
