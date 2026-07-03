# SPEC.md — Stickmancer (working title)

A turn-based stick-figure duel where players type freeform attack prompts. An LLM "judge" parses each prompt into structured game data; deterministic code renders, animates, and resolves everything else.

> **⚠️ Direction change (2026-07-02):** `DESIGN.md` supersedes parts of this file — the game is moving from a closed 5-category set to an **open-ended generic effect grammar** with two **modes** (competitive / sandbox) and a **reliability (miss/fizzle) system**. §1 non-goals below (single-effect, no minions, no status stacking) are being revised; §10 milestones are re-sequenced per DESIGN.md §7. This file still describes the implemented M0–M2 engine until each phase lands.

> **Source-of-truth map:** Overall design direction lives in `DESIGN.md`. Game rules live in `GAME_MECHANICS.md`. Judge behavior lives in `JUDGE.md`. All tunable numbers live in `config/balance.json`. This file covers architecture, scope, and build order only. If documents conflict, `GAME_MECHANICS.md` wins for rules and `config/balance.json` wins for numbers.

---

## 1. Goals and non-goals

**v1 goals**
- Local hot-seat play: two players on one device, pass-and-play.
- Freeform prompt → judged action → animated resolution, with a mana-cost preview before committing.
- Deterministic, server-computed combat math (LLM never does arithmetic that affects balance).
- Replay logging of every match.
- A judge eval suite so balance changes are regression-testable.

**Explicit non-goals for v1 (deferred to v2)**
- Online multiplayer (rooms, matchmaking, WebSockets)
- Accounts/auth (v1 uses local display names only)
- AI practice opponent (stub the interface, do not implement)
- Native iOS/Android builds (v1 is a responsive web app / PWA-ready)
- On-device/local LLM inference
- Diffusion-based image generation (never planned; see §4)

## 2. Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Frontend | Next.js (App Router) + TypeScript | Responsive, mobile-touch friendly |
| Rendering | SVG or Canvas 2D (choose one in first implementation task and record in DECISIONS section of PROGRESS.md) | Animation via requestAnimationFrame or a light tween lib; no game engine |
| Backend | Python 3.12 + FastAPI | Judge proxy, resolver, moderation, replay logging |
| Judge LLM | Cloud-hosted small model via API (default: Claude Haiku via Anthropic API; Groq-hosted small model acceptable alternative) | temperature=0, structured JSON output. Model name is a config value, never hardcoded |
| Config | `config/balance.json` | All tunable constants |
| Tests | pytest (backend + judge evals), vitest (frontend units) | See §9 |

**Key security rule:** The LLM API key exists only on the backend. The client never calls the LLM provider directly.

## 3. Architecture

```
[Browser — Next.js]
  ├─ Hot-seat UI (hidden-input handoff screens)
  ├─ Renderer (stick figures, shape primitives, animation templates)
  └─ Game state display (HP/mana bars, cooldowns, turn log)
        │  HTTPS/JSON
        ▼
[FastAPI backend]
  ├─ POST /api/judge     → moderation pre-filter → LLM judge → server-computed mana cost → parsed action
  ├─ POST /api/resolve   → pure-function resolver (speed order, type chart, block math) → resolution events + new state
  ├─ Replay logger       → JSONL per match in data/replays/
  └─ Rate limiter        → light per-IP limit (belt-and-suspenders beyond mana throttling)
        │
        ▼
[LLM provider API]  (judge calls only)
```

**Server-authoritative by design, even in v1.** The resolver is a pure function (`resolve(state, action_p1, action_p2) -> (events, new_state)`) living in the backend. Hot-seat doesn't strictly need this, but it makes the v2 online migration trivial and keeps the API key server-side anyway. The client is a renderer of server-returned events, not a rules engine.

## 4. Visuals: directed primitives, not image generation

There is no image-generation model. The judge outputs a small composition of shape primitives (see `JUDGE.md` §5) plus an animation template ID. The frontend owns:

- **Stick figures:** two rigged stick figures (lines + circle head) with a small pose set (idle, windup, cast, hit-stagger, knockback, block, KO'd).
- **Animation template library** (each template accepts the judge's primitives, element color, and resolution outcome):
  - `projectile` — spawn composition at attacker, tween toward defender
  - `beam` — instant/fast line effect (horizontal or from-sky vertical)
  - `melee` — attacker lunges, swing arc with composition as the weapon
  - `aoe_burst` — expanding ring/shape centered on target or field
  - `shield_raise`, `dodge`, `reflect` — defensive poses + composition
  - `buff_aura`, `debuff_cloud`, `heal_glow` — status visuals
- **Outcome variants per template:** `hit_knockback`, `blocked`, `reflected`, `dodged`, `partial`. The resolver decides the outcome; the renderer plays the matching variant. Knockback is a position tween scaled by damage — no physics engine.

## 5. Turn flow (v1 hot-seat)

1. **Player 1 input phase.** Handoff screen ("Pass to Player 1"), then prompt input. On **Submit**: client calls `/api/judge`; UI shows parsed effect + mana cost with **Confirm** / **Rewrite** (rewrite cap per `balance.json`, default 2). Moderation rejection consumes a rewrite, not mana. Confirmed action is held client-side, hidden from view.
2. **Player 2 input phase.** Same flow behind a handoff screen. Simultaneous-turn secrecy is preserved by the handoff screens.
3. **Resolution phase.** Client sends both confirmed actions + current state to `/api/resolve`. Backend resolves per `GAME_MECHANICS.md` (defense priority tier first, then speed order, type chart, block/dodge/reflect math, cooldowns, mana regen) and returns an ordered event list + new state.
4. **Playback phase.** Client animates the event list in order, updates bars, shows a one-line narration per action (judge's `flavor_text`).
5. **End check.** HP ≤ 0 → victory screen. Max-turn cap reached → tiebreak per `GAME_MECHANICS.md`. Otherwise loop to step 1.

Optional per-submission input timer is a config value (off by default for hot-seat).

## 6. API contract (v1)

### POST /api/judge
Request: `{ "prompt": str, "player": {"mana": int, "cooldowns": {...}}, "match_id": str }`
Response (success): `{ "action": <JudgedAction>, "mana_cost": int, "affordable": bool, "rewrites_remaining": int }`
Response (moderation reject): `{ "error": "moderation", "message": str }`
`JudgedAction` schema is defined once in `JUDGE.md` §4 and mirrored as a Pydantic model + TypeScript type. **Mana cost is computed server-side** from the judge's power/category via the formula in `balance.json` — the LLM never sets costs directly.

### POST /api/resolve
Request: `{ "match_id": str, "state": <GameState>, "p1_action": <JudgedAction>, "p2_action": <JudgedAction> }`
Response: `{ "events": [<ResolutionEvent>...], "state": <GameState>, "match_over": bool, "winner": "p1"|"p2"|"draw"|null }`
`ResolutionEvent` = `{ "actor": "p1"|"p2", "template": str, "outcome": str, "damage": int, "narration": str, "state_delta": {...} }` — the exact playback list the renderer animates.

## 7. Moderation

Server-side pre-filter runs before every judge call: a keyword/regex blocklist for clearly disallowed content, with an optional cheap model-based check behind a config flag. Rejected prompts return a friendly "try a different attack" message. Never send rejected text to the judge or the renderer.

## 8. Replay logging

Every `/api/judge` confirmation and `/api/resolve` call appends to `data/replays/{match_id}.jsonl`: timestamp, raw prompt, judged action, cost, resolution events, state snapshot. Purpose: debugging, balance analysis, and a future fine-tuning dataset for a local judge model (v2+).

## 9. Testing strategy

- **Resolver:** pure-function unit tests (pytest) covering the full resolution matrix — attack/attack speed ordering, KO-before-slower-resolves, all defense interactions, type-chart multipliers, cooldown enforcement, mana floor, tiebreaks.
- **Judge evals:** fixture file of ~30+ prompts with expected category, power range, and element (see `JUDGE.md` §7). Run via pytest against the live judge with temperature=0. **Must pass before any change to `JUDGE.md` or the judge prompt ships.**
- **Frontend:** vitest units for state display logic; template playback smoke-tested manually in v1.
- **Anti-stacking regression:** greedy multi-request fixture prompts must always resolve to exactly one effect.

## 10. Build order (milestones)

1. **M0 — Scaffold:** repo layout, FastAPI + Next.js skeletons, `balance.json` loading, CI running pytest.
2. **M1 — Resolver core:** GameState models, pure resolver with full matrix + unit tests. No LLM, no UI — test with hardcoded actions.
3. **M2 — Judge:** moderation pre-filter, judge call with structured output, server cost computation, eval suite green.
4. **M3 — Minimal playable:** hot-seat UI with handoff screens, text-only playback (no animation), full loop vs. real judge. **First fun-check happens here.**
5. **M4 — Renderer:** stick figures, primitives, animation template library, outcome variants.
6. **M5 — Polish:** cost-preview UX, cooldown/mana UI, victory screen, replay logging complete, mobile touch pass.
7. **M6 — Balance pass:** playtest, tune `balance.json`, expand judge evals with observed exploits.

## 11. v2 roadmap (recorded, not specced)

Online play (room codes, WebSockets — resolver already server-side), AI practice opponent (implement behind the existing stub interface), accounts, random matchmaking, native wrappers (Capacitor first), on-device judge (WebLLM/MLC + fine-tune from replay data), spectate/replay viewer.
