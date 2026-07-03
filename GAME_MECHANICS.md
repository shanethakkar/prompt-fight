# GAME_MECHANICS.md — Living Design Document

> **This file is the single source of truth for game rules.** Per `CLAUDE.md`, any change to a mechanic — in code, judge prompt, or config — must be reflected here in the same commit. Numbers shown below are the current values in `config/balance.json`; that file wins if they drift.

> **⚠️ Redesign in progress (2026-07-02):** `DESIGN.md` is the agreed direction — an open-ended **generic effect grammar** (bundled components, not one of 5 categories), two **modes** (competitive / sandbox), and a **reliability (miss/fizzle) system**. The rules below describe the **currently implemented** engine; they are revised phase-by-phase per DESIGN §7. In particular §3 (closed categories / single-effect) and §11 (out-of-scope: minions, status stacking) are superseded by that direction.

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

## 7. Resolution order (within a turn)

1. **Priority tier — Defense first.** All Defense actions activate at the start of resolution regardless of speed (a shield raised is up for the whole turn). A defense always resolves (it can never be KO'd before acting) and always incurs its cooldown.
2. **Everything else resolves in descending *effective* speed order.** Ties resolve simultaneously.
3. **KO check between resolutions:** if the faster action reduces a player to ≤ 0 HP, the slower action does not resolve (it "fizzles"). Simultaneous ties both resolve, then the §1 tiebreak applies.

### HP accounting and simultaneity
- **HP is a signed running total during resolution:** it is upper-bounded by `hp_max` (heals cannot overheal) but is **never floored to 0 mid-resolution**. A player is KO'd when HP ≤ 0. The returned state floors HP to `[0, hp_max]` for display.
- **Double-KO tiebreak uses the signed values:** if both players are ≤ 0 in the same resolution, the one with the **higher (less-negative) HP wins**; exactly equal is a draw. (This is why HP isn't clamped early — otherwise both would read 0 and every double-KO would be a draw.)
- **Simultaneous (speed-tie) actions use snapshot-delta:** each computes its HP change against the same turn-start HP, then the changes are summed and applied once. Consequence: **a simultaneous heal can save you from otherwise-lethal simultaneous damage** (net change is what matters).
- **Event order is deterministic:** defense-activation events first (P1 then P2), then resolving actions in descending speed; within a speed tie, P1 before P2.

### Effect and cooldown timing (staging)
Buffs, debuffs, and cooldowns created *this* turn are staged and installed during end-of-turn upkeep, in this order per player: (a) decrement pre-existing buff/debuff timers and drop expired ones; (b) tick pre-existing cooldowns down by 1; (c) install the newly-created effects/cooldowns; (d) apply mana regen (capped). Because new effects are installed *after* the decrement, **a buff cast on turn T first bites on turn T+1 and lasts exactly `duration` turns; a cooldown-N move blocks exactly the next N turns.** A buff never affects the caster's own action on the turn it is cast (that action is the buff itself).

### Defense interaction math
Mitigation is applied to the *typed* damage (post-type-chart, §8) and applies to all three defense subtypes.
- **Shield:** incoming damage reduced by `shield_effective_power × block_multiplier` (default ×3), floor 0.
- **Dodge:** if `dodge_effective_speed ≥ attack_effective_speed`, take 0 damage; otherwise take `partial_dodge_damage_fraction` (default 50%) of the typed damage. (Only dodge consumes speed; shield/reflect speed is unused.)
- **Reflect:** if `reflect_effective_power ≥ attack_effective_power`, negate the hit and return `reflect_return_fraction` (default 50%) of the typed damage **to the attacker** (this can itself KO the attacker; the returned damage is not further type-charted). Otherwise absorb `reflect_effective_power × block_multiplier` and the defender takes the remainder, floor 0.
- Mana is charged for both players' actions even if one later fizzles (the fizzled actor is already KO'd, so it is unobservable). A fizzled action incurs no cooldown.
- Defense actions only affect incoming actions this turn; they do not persist.

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
- 2026-07-02 — M1 resolver: pinned previously-ambiguous rules — signed-HP double-KO tiebreak, snapshot-delta simultaneity, fixed damage pipeline (type chart before mitigation), effect/cooldown staging (buff bites T+1..T+duration; cooldown-N blocks exactly N turns), reflect returns to attacker + floors 0, elements inert vs. undefended targets, buff/debuff single-slot + `stat` field, base-vs-effective stat rules. Added `buff_debuff_stat_shift_per_power` (1.0). Added `JudgedAction.stat` (power|speed).
- 2026-07-01 — Initial version from design sessions. All numeric values are pre-playtest placeholders.
