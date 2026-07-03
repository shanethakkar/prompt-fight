# GAME_MECHANICS.md — Living Design Document

> **This file is the single source of truth for game rules.** Per `CLAUDE.md`, any change to a mechanic — in code, judge prompt, or config — must be reflected here in the same commit. Numbers shown below are the current values in `config/balance.json`; that file wins if they drift.

> **⚠️ Redesign in progress (2026-07-02):** `DESIGN.md` is the agreed direction — an open-ended **generic effect grammar** (bundled components, not one of 5 categories), two **modes** (competitive / sandbox), and a **reliability (miss/fizzle) system**. The rules below describe the **currently implemented** engine; they are revised phase-by-phase per DESIGN §7. In particular §3 (closed categories / single-effect) and §11 (out-of-scope: minions, status stacking) are superseded by that direction.

## 1. Match structure

- Two players, local hot-seat (one device, pass-and-play). **Open info** — no hidden inputs.
- **Alternating single-action turns (Worms-style):** P1 acts, the result plays out, then P2 acts, then P1… (P1 starts; seeded starter-randomization is a P1 follow-up). Each turn the active player takes exactly **one** action, resolved immediately against the current state (including the opponent's raised defensive stance).
- Match ends the instant a player's HP reaches 0. Only the active player deals damage on their turn, so a double-KO is impossible — **HP floors at 0** (no signed accounting).
- **Round cap:** `max_turns` (default 30) counts **rounds** (one turn each). It is checked only at a **round boundary** (after P2 acts) so both players have taken equal actions; then higher HP wins, equal → draw.

## 2. Resources

| Resource | Start | Max | Regen |
|---|---|---|---|
| HP | 100 | 100 | none |
| Mana | 10 | 20 | +3 at the end of each of your own turns |

- Actions cost mana (see §5). You cannot confirm an action you can't afford.
- Regen is applied at the **end** of your turn, so the mana shown when it's your turn to act is exactly what's spendable.

## 3. Action categories (closed set)

Every prompt is judged into **exactly one** category:

1. **Attack** — subtypes: `projectile`, `beam`, `melee`, `aoe`. Deals damage.
2. **Defense** — subtypes: `shield`, `dodge`, `reflect`. Mitigates incoming damage this turn.
3. **Buff** — temporary self-boost of one stat (power **or** speed) for `duration` turns. Which stat is set by the judge via the `stat` field on `JudgedAction` (`JUDGE.md` §4).
4. **Debuff** — temporary opponent-weakening of one stat (power **or** speed) for `duration` turns; stat likewise chosen by the judge.
5. **Heal** — restores HP (never above max).

Buffs and debuffs occupy **single slots**: a player has at most one active buff (self) and one active debuff (from the opponent) at a time. Re-casting **replaces** the current one (no stacking — see §11).

**Anti-stacking rule (structural):** the `JudgedAction` schema can hold only one category, one element, one power value. Prompts requesting multiple effects ("a shield AND a sword AND 50 HP") are judged on the single most prominent effect; everything else is flavor text with zero mechanical weight. See `JUDGE.md` §3.

## 4. Stats

- **Power (1–10):** magnitude of the effect. Scales damage, block value, buff/debuff strength, heal amount.
- **Speed (1–10):** resolution ordering within the turn (see §7). Quick jabs are fast; huge windups are slow. The judge assigns both from the prompt's described scope per the rubric in `JUDGE.md` §6.

**Base vs. effective stats.** The judge assigns *base* power/speed. During resolution an action uses *effective* stats: `effective = base + active_buff_shift − active_debuff_shift`, clamped so effective **power ≥ 0** and effective **speed ≥ 1** (no upper cap). Effective stats drive attack/heal/defense magnitude and the dodge/reflect comparisons. **Base** power (not effective) drives three things: mana cost (§5), the heavy-move ≥ 8 cooldown bump (§6), and the buff/debuff shift magnitude below — so buffs never feed back into their own cost, cooldown class, or strength.

- **Damage** (fixed pipeline, in order): `raw = effective_power × attack_damage_multiplier` (default ×3); `typed = raw × type_chart_modifier` (§8); then mitigation (shield/dodge/reflect, §7) is applied to `typed`; finally **floor 0**. The type modifier is applied *before* mitigation, so a fire attack into a nature shield is `(power×3×1.5) − block`, not `((power×3) − block)×1.5`.
- **Heal** = `effective_power × heal_multiplier` (default ×2.5), added to HP, capped at `hp_max`.
- **Buff/debuff shift** = `round(base_power × buff_debuff_stat_shift_per_power)` (default ×1.0, i.e. shift = power), applied to the chosen stat for `buff_debuff_duration_turns` (default 2). See §7 for exactly when it starts and stops biting.

## 5. Mana cost (server-computed, never LLM-set)

`cost = ceil(power ^ cost_exponent × category_multiplier)` — parameters in `balance.json` (defaults: exponent 1.2; multipliers: attack 1.0, defense 0.8, buff 0.9, debuff 0.9, heal 1.1).

This is the power-scaling throttle: "I collapse a black hole onto you" is legal — the judge just scores it power 10, which prices it out of reach early and forces saving up. Imagination is unconstrained; drama isn't cheap.

## 6. Cooldowns

- Per-category cooldowns (in turns) apply after use — defaults: attack 0, defense 1, buff 2, debuff 2, heal 3.
- **Heavy-move rule:** any action with power ≥ 8 adds +1 turn to its category's cooldown.
- A category on cooldown cannot be selected; the judge response is checked against the player's cooldown state at confirm time.

## 7. Resolving a turn (one action)

Each turn the **active player A** takes one action against **opponent O**, resolved in this order:

1. **Effective stats** for A are computed from A's current buff/debuff (`base + buff − debuff`, power floored 0 / speed floored 1). **Base** power still drives mana cost, the heavy-move cooldown bump, and buff/debuff magnitude.
2. **Pay** A's mana cost (base power), floor 0.
3. **Apply** the action: attack (vs O's stance, below), defense (raise a stance on A), buff (on A), debuff (on O), or heal (A, capped). HP floors at 0. Emit one event.
4. **Match-over check**, then advance the turn (P1↔P2; a P2 action closes the round and checks the round cap, §1).

### Effect / cooldown timing (owner-turn, install-after-tick)
Durations and cooldowns count in the **owner's own turns**. At the **end of A's turn** (use-before-decrement, so an effect A *used* this turn still ticks after use): (a) decrement A's active buff/debuff/defense timers, drop expired; (b) tick A's cooldowns; (c) install A's newly-created effect + this action's cooldown; (d) mana regen A (capped). O's effects/cooldowns are untouched on A's turn — they tick on O's turns. Consequences: **a buff cast on your turn first bites on your *next* turn and lasts exactly `duration` of your turns; a cooldown-N move blocks exactly your next N turns.** A debuff lands on O immediately and weakens O's next `duration` turns (starting O's very next turn).

### Defenses are stances (not same-turn mitigation)
A defense raised on your turn doesn't block anything yet — it **persists as a stance** that mitigates the opponent's *next* attack. Its effective power/speed/element are **frozen at cast** (the block happens on the opponent's turn, so recomputing would be ambiguous). A stance is **consumed the moment it mitigates an attack**, and otherwise **expires at the start of your next turn** (`defense_stance_duration_turns`, default 1). Single slot — recasting replaces. Mitigation is applied to the *typed* damage (post-type-chart, §8):
- **Shield:** incoming damage reduced by `shield_power × block_multiplier` (default ×3), floor 0.
- **Dodge:** if `dodge_speed ≥ attacker's effective speed`, take 0 damage; otherwise take `partial_dodge_damage_fraction` (default 50%) of the typed damage.
- **Reflect:** if `reflect_power ≥ attacker's effective power`, negate the hit and return `reflect_return_fraction` (default 50%) of the typed damage **to the attacker** (can KO the attacker; not further type-charted). Otherwise absorb `reflect_power × block_multiplier` and the defender takes the remainder, floor 0.

*Open-info caveat: because both players see a raised stance, a deterministic dodge is easy to play around (attack with speed ≥ the visible dodge). The DESIGN P1 reliability system replaces this with a probabilistic evade.*

## 8. Elements and type chart

Elements (closed set): `physical`, `fire`, `water`, `nature`, `lightning`.

Advantage chart (attacker → defender/defense element): fire > nature, nature > water, water > fire, lightning > water, nature > lightning (grounding). `physical` is neutral everywhere.

- Advantage: damage ×1.5. Disadvantage (reverse direction): ×0.75. Neutral: ×1.0.
- The chart compares the attacker's element against the **defending action's element** (shield, dodge, or reflect) — a water shield blocks fire extra well, etc.
- **Elements are inert against an undefended target.** Players have no persistent element, so an attack that meets no defense this turn is always ×1.0 regardless of its element. Elements therefore only matter attack-vs-defense. *(This makes offensive elements situational; flagged for the M6 balance pass.)*
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
- 2026-07-03 — **Turn model → alternating single-action turns** (Worms-style, was simultaneous). Resolver is now `resolve_turn(state, action)`; deleted speed-ordering / snapshot-delta / double-KO tiebreak / defense-priority tier. HP floors at 0. Effect/cooldown upkeep is end-of-*your*-turn (owner-turn timing). **Defenses are now persistent stances** (frozen at cast, consume-on-hit, expire next turn). Round cap checked at the round boundary. Events enriched (`target` + `effect` summary) for clear result narration. Judge/`JudgedAction` unchanged.
- 2026-07-02 — M1 resolver: pinned previously-ambiguous rules — signed-HP double-KO tiebreak, snapshot-delta simultaneity, fixed damage pipeline (type chart before mitigation), effect/cooldown staging (buff bites T+1..T+duration; cooldown-N blocks exactly N turns), reflect returns to attacker + floors 0, elements inert vs. undefended targets, buff/debuff single-slot + `stat` field, base-vs-effective stat rules. Added `buff_debuff_stat_shift_per_power` (1.0). Added `JudgedAction.stat` (power|speed).
- 2026-07-01 — Initial version from design sessions. All numeric values are pre-playtest placeholders.
