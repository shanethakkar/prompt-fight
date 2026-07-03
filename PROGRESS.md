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

- 2026-07-01 — Mana cost computed server-side from judge's power/category (LLM never sets costs) — consistency + anti-fishing.
- 2026-07-01 — Resolver is a server-side pure function even in local-only v1, to make v2 online migration trivial.
- 2026-07-01 — Defense actions resolve in a priority tier before speed ordering (shields are up for the whole turn).
- 2026-07-02 — Backend is uv-managed (Python 3.12); no system Python required. `uv run …` is the documented command form.
- 2026-07-02 — `balance.json` located CWD-independently by walking up from `app/config.py` (env override `STICKMANCER_BALANCE_PATH`); loaded via a typed Pydantic `BalanceConfig` with `extra="forbid"` so config drift fails loudly.
- 2026-07-02 — Frontend scaffolded on Next.js 16 (App Router, `src/`, Tailwind v4, React 19). Next 16 removed `next lint`, so `lint` runs `eslint`; Tailwind included now to match the design tooling.
- 2026-07-02 — Frontend tests use vitest + jsdom + @testing-library; M0 test is a pure unit test (Vitest can't render async Server Components).
- (Renderer choice SVG vs. Canvas: record here when made in M4.)

---

## 2026-07-02 — M0 scaffold
- Done: Monorepo stood up. git repo init'd (main). `balance.json` relocated to `config/`. Backend (`/backend`, uv + FastAPI): typed `BalanceConfig` loader (CWD-robust), `/health` endpoint, pydantic-settings for the backend-only API key, `tests/test_config.py` (4 passing, incl. CWD-independence). Frontend (`/frontend`, Next.js 16 + TS strict + Tailwind v4): minimal landing page, vitest wired (1 passing test), `test`/`typecheck` scripts. CI (`.github/workflows/ci.yml`): backend uv job (ruff + pytest) + frontend node job (lint/typecheck/test). Repo hygiene: `.gitignore`, `.gitattributes` (LF), `backend/.env.example`, `data/replays/.gitkeep`.
- Files: `.gitignore`, `.gitattributes`, `.github/workflows/ci.yml`, `config/balance.json` (moved), `data/replays/.gitkeep`, `backend/**` (pyproject.toml, .python-version, .env.example, app/{__init__,main,config,settings}.py, tests/{__init__,test_config}.py, uv.lock), `frontend/**` (create-next-app output + vitest.config.ts, vitest.setup.ts, src/lib/{site.ts,site.test.ts}, edited page.tsx/layout.tsx/package.json), CLAUDE.md (Commands), PROGRESS.md.
- Verified: `uv run pytest` 4 passed; `/health` → `{"status":"ok","judge_model":"claude-haiku-4-5"}`; ruff clean; frontend `test`/`typecheck`/`lint`/`build` all green.
- Follow-ups: M1 resolver core is next (GameState models + pure resolver + full unit matrix). CI not yet run on GitHub (no remote). Balance numbers remain pre-playtest placeholders.

## 2026-07-01 — Project documentation created
- Done: SPEC.md, CLAUDE.md, GAME_MECHANICS.md, JUDGE.md, PROGRESS.md, config/balance.json drafted from design sessions. v1 scope: local hot-seat only.
- Files: all of the above.
- Follow-ups: M0 scaffold is the next task. All balance numbers are pre-playtest placeholders.
