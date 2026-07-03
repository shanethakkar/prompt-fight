# PROGRESS.md — Task Log

> Per `CLAUDE.md`: append an entry here after **every** completed task, newest first. Keep entries short and factual.

**Entry format:**
```
## YYYY-MM-DD — <task name>
- Done: <what was completed, 1-3 lines>
- Files: <files created/modified>
- Follow-ups: <anything deferred or discovered, or "none">
```

## DECISIONS (running log of nontrivial choices made during implementation)

- 2026-07-02 — **Major direction change:** move from the closed 5-category set to an open-ended **generic effect grammar** (flavor infinite, mechanics = a small set of composable dimensions the LLM projects prompts onto), plus two **modes** (competitive / sandbox) and a **reliability (miss/fizzle→partial→full→overload, backfire on overreach) system** driven mostly by counterplay with informed odds shown pre-Confirm and seeded RNG for replay. Full design in [[DESIGN.md]]; phased rollout in DESIGN §7. Comeback/rubber-band knob deferred. Supersedes SPEC §1 non-goals + GAME_MECHANICS §3/§11.

- 2026-07-01 — Mana cost computed server-side from judge's power/category (LLM never sets costs) — consistency + anti-fishing.
- 2026-07-01 — Resolver is a server-side pure function even in local-only v1, to make v2 online migration trivial.
- 2026-07-01 — Defense actions resolve in a priority tier before speed ordering (shields are up for the whole turn).
- 2026-07-02 — Backend is uv-managed (Python 3.12); no system Python required. `uv run …` is the documented command form.
- 2026-07-02 — `balance.json` located CWD-independently by walking up from `app/config.py` (env override `STICKMANCER_BALANCE_PATH`); loaded via a typed Pydantic `BalanceConfig` with `extra="forbid"` so config drift fails loudly.
- 2026-07-02 — Frontend scaffolded on Next.js 16 (App Router, `src/`, Tailwind v4, React 19). Next 16 removed `next lint`, so `lint` runs `eslint`; Tailwind included now to match the design tooling.
- 2026-07-02 — Frontend tests use vitest + jsdom + @testing-library; M0 test is a pure unit test (Vitest can't render async Server Components).
- 2026-07-02 — `JudgedAction` gains a `stat` (power|speed) field so the judge picks which stat a buff/debuff shifts (user-approved schema change). Buff/debuff magnitude = round(base_power × `buff_debuff_stat_shift_per_power`), single-slot (recast replaces).
- 2026-07-02 — Resolver design pins: signed HP with less-overkill-wins double-KO tiebreak; snapshot-delta for simultaneous actions (heal can save from lethal); fixed damage pipeline (type chart before mitigation); effect/cooldown staging (buff bites T+1..T+duration, cooldown-N blocks exactly N turns); reflect returns to attacker and floors 0; elements inert vs. undefended targets. All documented in GAME_MECHANICS.md.
- 2026-07-02 — Base power (not effective) drives mana cost, heavy-move cooldown bump, and buff shift magnitude — buffs never feed back into their own cost/cooldown/strength.
- 2026-07-02 — Judge uses forced tool-use (`emit_action` tool, `tool_choice`) at temp 0, not JSON-mode/prefill — robust across SDK versions; retry-once-then-sputter so the endpoint never 500s. Server trusts `subtype` and derives `category` from it (self-correcting).
- 2026-07-02 — Judge system prompt lives in `backend/app/judge_prompt.py` mirroring JUDGE.md; the live eval suite is the regression guard (per testing gate).
- 2026-07-02 — Moderation blocklist is deliberately conservative (excludes combat words + Scunthorpe-collision slurs like "chink"); optional model check behind `moderation_model_check_enabled` (off).
- 2026-07-02 — `/api/judge` accepts + decrements client-owned `rewrites_remaining` and returns `on_cooldown` (client enforces the cap/cooldowns in M3). `/api/resolve` added early (user-approved) so the backend API is complete before M3.
- (Renderer choice SVG vs. Canvas: record here when made in M4.)

---

## 2026-07-02 — Design direction documented (DESIGN.md)
- Done: Captured the agreed pivot to open-ended effects. New `DESIGN.md` covers the vision (player imagination is the limit), the generic effect grammar (§3), two modes (§4), the reliability system (§5), what's reused vs. reworked from M0–M2 (§6), a phased rollout P1–P4 (§7), and open decisions (§8). Cross-linked from CLAUDE.md source-of-truth map; direction-change notes added to SPEC.md and GAME_MECHANICS.md headers.
- Files: DESIGN.md (new), CLAUDE.md, SPEC.md, GAME_MECHANICS.md, PROGRESS.md.
- Follow-ups: No code yet. Next: pick the starting phase (recommend P1 — modes + reliability on the current engine) and plan it. Existing M0–M2 code is untouched and still green.

## 2026-07-02 — M2 judge + API endpoints
- Done: The game's only AI component. Moderation pre-filter (`moderation.py`, conservative regex + optional model check). LLM judge (`judge.py` + `judge_prompt.py`): forced `emit_action` tool-use vs Claude Haiku at temp 0, subtype→category reconciliation, retry-once-then-sputter. API models (`schemas.py`) + endpoints (`main.py`): `POST /api/judge` (moderate → judge → server cost via `rules.mana_cost` → affordable/on_cooldown/rewrites) and `POST /api/resolve` (thin wrapper over M1 resolver). Eval suite: `fixtures/judge_eval.json` (30 fixtures across all §7 buckets incl. buff/debuff stat) + `test_judge_eval.py` (`@pytest.mark.live`). Offline tests: `test_moderation.py`, `test_api.py` (judge mocked).
- Files: backend/app/{judge_prompt,judge,moderation,schemas}.py, backend/app/main.py, backend/tests/{test_moderation,test_api,test_judge_eval}.py, backend/tests/fixtures/judge_eval.json, JUDGE.md (§1/§4 tool-use notes), PROGRESS.md.
- Verified: `uv run pytest -m "not live"` 93 passed; ruff clean; **live eval suite 27/27 green** (real Haiku, temp 0 — near-dups score identically, stat classification correct); end-to-end smoke of both endpoints with the real judge.
- Follow-ups: **M3** — hot-seat UI over `/api/judge` + `/api/resolve`; mirror JudgedAction/GameState/ResolutionEvent (incl. `stat`) as TS types. Replay logging + rate limiting deferred to M5. No new deps (anthropic declared in M0).

## 2026-07-02 — M1 resolver core
- Done: Deterministic combat engine. Domain models (`models.py`: JudgedAction w/ new `stat` field, GameState/PlayerState/ActiveEffect, ResolutionEvent/ResolveResult, closed-set StrEnums). Pure rule helpers (`rules.py`: mana_cost, type_multiplier, effective_power/speed, buff_shift, category_cooldown). Pure `resolve(state, p1, p2, balance)` (`resolver.py`) implementing GAME_MECHANICS §7 with all pinned rules. Full test matrix: **73 tests** (test_rules.py + test_resolver.py) covering ordering/KO, snapshot-delta, all defense interactions, type-chart pipeline, buff/debuff timing+stat, cooldowns, mana, tiebreaks, immutability, determinism. Added `buff_debuff_stat_shift_per_power` to balance.json + BalanceConfig. Docs: GAME_MECHANICS §3/§4/§7/§8 + changelog; JUDGE §2/§4/§7/§8 (stat field + buff/debuff few-shots).
- Files: backend/app/{models,rules,resolver}.py, backend/tests/{test_rules,test_resolver}.py, backend/app/config.py, backend/tests/test_config.py, config/balance.json, GAME_MECHANICS.md, JUDGE.md.
- Verified: `uv run pytest` 73 passed; ruff check + format clean; scripted 4-turn duel resolves sanely (fire-vs-water shield disadvantage, power buff biting T+1/T+2 confirmed by hand).
- Follow-ups: **M2** — judge must emit `stat`; eval fixtures need ≥2 buff/debuff `stat` cases; reuse `rules.mana_cost` in /api/judge. **M3/M4** — mirror models (incl. `stat`) as TS types. Elements-inert-vs-undefended flagged for M6.

## 2026-07-02 — M0 scaffold
- Done: Monorepo stood up. git repo init'd (main). `balance.json` relocated to `config/`. Backend (`/backend`, uv + FastAPI): typed `BalanceConfig` loader (CWD-robust), `/health` endpoint, pydantic-settings for the backend-only API key, `tests/test_config.py` (4 passing, incl. CWD-independence). Frontend (`/frontend`, Next.js 16 + TS strict + Tailwind v4): minimal landing page, vitest wired (1 passing test), `test`/`typecheck` scripts. CI (`.github/workflows/ci.yml`): backend uv job (ruff + pytest) + frontend node job (lint/typecheck/test). Repo hygiene: `.gitignore`, `.gitattributes` (LF), `backend/.env.example`, `data/replays/.gitkeep`.
- Files: `.gitignore`, `.gitattributes`, `.github/workflows/ci.yml`, `config/balance.json` (moved), `data/replays/.gitkeep`, `backend/**` (pyproject.toml, .python-version, .env.example, app/{__init__,main,config,settings}.py, tests/{__init__,test_config}.py, uv.lock), `frontend/**` (create-next-app output + vitest.config.ts, vitest.setup.ts, src/lib/{site.ts,site.test.ts}, edited page.tsx/layout.tsx/package.json), CLAUDE.md (Commands), PROGRESS.md.
- Verified: `uv run pytest` 4 passed; `/health` → `{"status":"ok","judge_model":"claude-haiku-4-5"}`; ruff clean; frontend `test`/`typecheck`/`lint`/`build` all green.
- Follow-ups: M1 resolver core is next (GameState models + pure resolver + full unit matrix). CI not yet run on GitHub (no remote). Balance numbers remain pre-playtest placeholders.

## 2026-07-01 — Project documentation created
- Done: SPEC.md, CLAUDE.md, GAME_MECHANICS.md, JUDGE.md, PROGRESS.md, config/balance.json drafted from design sessions. v1 scope: local hot-seat only.
- Files: all of the above.
- Follow-ups: M0 scaffold is the next task. All balance numbers are pre-playtest placeholders.
