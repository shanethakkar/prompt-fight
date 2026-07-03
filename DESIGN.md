# DESIGN.md — Open-Ended Effects, Game Modes & Reliability

> **Status: agreed design direction (2026-07-02).** This is the north star the game is migrating toward. It **supersedes parts of the v1 closed-set design.** `SPEC.md` / `GAME_MECHANICS.md` / `JUDGE.md` describe the *currently implemented* engine; this file describes where we're going and how we get there in phases (§7). Until a phase lands, the implemented docs describe today's reality; where they conflict with this doc, this doc states intent.

> **Update (2026-07-03):** playtesting drove a switch to **alternating one-by-one turns** (Worms-style) — clearer, and it converged defenses onto the persistent-effect model this doc anticipates (a shield is now a stance that soaks the next hit). Implemented in GAME_MECHANICS §1/§7. This lands **before** P1; P1 (reliability) additionally brings a seeded starting-player coin-flip and probabilistic evade (the open-info deterministic dodge is weak).

---

## 1. Vision

**The player's imagination is the limit — not our code.** Any prompt, including effects we never anticipated ("a sand monster throws sand in the archer's eyes and blinds them"; "my wand makes their zombie fight for me"), should produce a real, priced, mechanical effect. We do **not** maintain a hardcoded list of spells.

## 2. Core principle — flavor is infinite, mechanics are a small generic vocabulary

We do **not** try to enumerate every effect (players will always out-imagine any list). We enumerate the **mechanical dimensions** instead. The flavor — sand monster, magic wand, confused zombie, enemy archer — is free narration the judge echoes back verbatim. Stripped of flavor, almost everything a player invents collapses onto a small generic grammar. "Blind" was never hardcoded; **"reduce a probability/stat for a duration"** was, and the judge projects "blind" onto it, inventing the label on the fly.

| Player says (infinite) | Mechanically it is (small, generic) |
|---|---|
| "sand in the archer's eyes — blinded" | reduce **hit-chance** −X% for N turns |
| "poisoned" / "bleeding" / "on fire" | **Δhp per turn** for N turns |
| "frozen solid" / "webbed down" | **skip action** / reduce speed |
| "confused zombie fights for me" | **spawn/convert a combatant** (hp/attack/loyalty/duration) |
| "their magic fizzles" | **forbid a category** for N turns (silence) |
| "mirror shield" | **reflect** incoming |

## 3. The generic effect grammar (mechanical dimensions)

An **Action** is a small, bounded **bundle** of effect *components*, each drawn from a fixed set of generic dimensions. The judge maps a freeform prompt to 1–N components + parameters + an invented label ("Blinded") + `flavor_text`. Dimensions:

- **Instant HP change** — deal damage / heal (magnitude, element).
- **Over-time** — Δhp or Δmana per turn for N turns (poison, burn, bleed, regen, mana-drain).
- **Stat / probability modifier** — change power / speed / **hit-chance** / damage-taken / healing-received by ±X for N turns (weaken, slow, blind, expose, curse…).
- **Action control** — skip action (stun/freeze), act randomly (confuse), forbid a category (silence/disarm), taunt/redirect, reflect.
- **Mitigation** — shield (absorb), dodge (evade by speed), reflect (return).
- **Entities (minion layer)** — spawn a combatant (hp/attack/loyalty/duration) or convert an existing one (summon/charm).
- **Resource** — drain / grant mana.

The **server prices** mana from the components (magnitude × duration × per-stat weight), so the judge scores *inputs* and never sets price (no cost-fishing). Effects outside the grammar **clamp to the nearest component or are priced out of reach** (the black-hole rule — imagination is unconstrained; drama isn't cheap). The dimension set grows over time as playtesting reveals gaps.

## 4. Two game modes

Same engine, two rule profiles (a `mode` field in match config, tunables in `balance.json`):

- **Competitive** — tight per-turn cost + effect-count caps; a **steep reliability curve** (big/compound plays can whiff); **informed odds shown before Confirm**; seeded RNG (fair + replayable); balance-tuned.
- **Sandbox** — caps loosened or off; reliability flat or disabled (everything mostly lands); bigger/compound effects allowed. "Wow, that worked."

*(A comeback / rubber-band knob was considered and deferred — revisit later.)*

## 5. Reliability system (the miss / fizzle mechanic)

A **second throttle** alongside mana. **Mana gates frequency** (you save up); **reliability gates recklessness** (you don't overreach). "I collapse a black hole" should be spectacular *and* risky; a precise jab is boring and dependable.

- **A spectrum, not a coin flip:** `fizzle → partial → full → overload (crit)`, plus **backfire** on the greediest overreaches (the effect rebounds on the caster). Big plays can pay off *huge*, not just fail.
- **Base reliability falls with power/magnitude and complexity** (how many components you bundle). Modest, focused actions are dependable; sprawling apocalyptic ones are risky.
- **Counterplay dominates the roll — not flat dice.** Reliability is modified by what each side set up: the caster's accuracy buffs / **charge**; the defender's evasion (dodge, speed mismatch), **blind/dazzle debuffs** (which lower the caster's hit-chance via the same modifier dimension in §3), element matchup. **Skilled setup turns a coin-flip into a sure thing** — that's the skill ceiling. Blind them first, *then* swing.
- **Informed odds.** The cost-preview shows the outcome distribution before Confirm — e.g. *"Power 9 · ~45% full / 35% partial / 20% fizzle · 14 mana"* — so risk is a **decision**, not a dice-slap. Rewrite to a safer version, or gamble.
- **Charge to stabilize.** Optionally spend a turn / extra mana telegraphing a big attack to raise its reliability — telegraph-for-safety vs. rush-for-surprise.
- **Determinism preserved.** All randomness uses a **seed stored in match state**; the resolver stays a pure function of `(state, actions, seed)`; replays reproduce exactly; server-authority is intact.
- **Guardrail:** big/creative plays must be **aspirational, not traps.** Reward setups + crits so players are drawn to the wild swings, not scared off them. If the meta collapses to spamming safe medium hits, the reliability curve is mistuned.

## 6. What changes vs. what we keep (from M0–M2)

**Reused as-is:**
- The deterministic math (damage pipeline, type chart, snapshot-delta, KO ordering, mana regen, cooldowns) becomes the *implementation* of the `deal_damage` / stat / heal components.
- The judge architecture (forced tool-use, temp 0, moderation pre-filter, **server-side pricing**, retry→sputter fallback), the API shape, and the pytest harness all survive.

**Reworked:**
- `JudgedAction` (one category) → **Action = a bounded bundle of effect components** (M1/M2 schema change).
- The resolver's action model generalizes from "5 categories" to "resolve a component list," plus the seeded **reliability roll**.
- Mana pricing generalizes from `f(power, category)` to a **cost model over components**.
- Anti-stacking changes from "exactly one effect" to **"bounded bundle + cost/count caps."**
- Adds an optional **minion / entity layer**.

**Scope docs to amend as phases land:** SPEC §1 non-goals (single-effect, no minions, no status stacking) and GAME_MECHANICS §3/§11 (closed categories, out-of-scope list) are revised by this direction.

## 7. Phased rollout (how we proceed)

Ship value incrementally; every phase is playtestable and keeps the test suite green. Each phase updates GAME_MECHANICS / SPEC / JUDGE + the eval suite as it lands (Documentation Protocol).

- **P1 — Modes + reliability on the current engine.** Add a `mode` config and the reliability spectrum (seeded RNG + informed odds in the cost preview), applied to the existing 5-category actions. High-power / compound actions can fizzle / partial / crit. *Delivers the miss mechanic fast, with the smallest rework.*
- **P2 — Bundled effects + generic modifier grammar.** Relax single-effect to a bounded bundle; add the stat/probability + over-time modifier dimensions (blind, poison, slow, weaken…) as generic components; generalize pricing to the component cost model. *Delivers open-ended non-entity creativity — the sand/blind example.*
- **P3 — Entity / minion layer.** Summon + charm/convert; minion resolution each turn. *Delivers the zombie example.*
- **P4 — Balance pass.** Playtest both modes; tune caps, cost model, and the reliability curve; grow judge evals with observed exploits.

*(This reshapes the original SPEC §10 milestone order. The M3 renderer/UI work still happens, but now consumes the richer effect + reliability data; we'll re-sequence M3–M6 against these phases when we plan them.)*

## 8. Open decisions (settle per phase, not now)

- Exact reliability formula and the numbers behind the spectrum thresholds.
- The precise component list + per-component cost weights (playtest-driven).
- **Turn / effect budget:** one bundle per turn vs. chaining a couple of small setups into a payoff *(raised, not yet locked)*.
- Minion caps (how many, how strong, how long).
- Whether sandbox mode also loosens moderation / creativity latitude, or only the caps.
- How informed-odds interacts with rewrites (does seeing the odds and rewriting cost a rewrite?).
- Whether "charge to stabilize" is a P1 feature or comes later.
