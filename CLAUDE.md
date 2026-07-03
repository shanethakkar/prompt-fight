# CLAUDE.md

Stickmancer: turn-based stick-figure duel. Players type freeform prompts; an LLM judge parses them to structured JSON; deterministic code does all rendering, animation, and combat math.

## Source of truth (read before working)

| File | Owns | Rule |
|---|---|---|
| `DESIGN.md` | **Agreed design direction** (open-ended effect grammar, game modes, reliability system) | The north star; supersedes parts of v1. Implement in phases (DESIGN §7) |
| `SPEC.md` | Architecture, scope, API contract, build order | Don't change scope without asking the user |
| `GAME_MECHANICS.md` | All game rules | **The living design doc — see Documentation Protocol** |
| `JUDGE.md` | Judge prompt, schema, rubric, few-shot examples, eval fixtures | Any edit requires the judge eval suite to pass |
| `config/balance.json` | Every tunable number | **Never hardcode a balance constant anywhere in code** |
| `PROGRESS.md` | Task log + decisions | **Append after every completed task — see Documentation Protocol** |

## Documentation Protocol (mandatory, no exceptions)

1. **Any change that alters a game mechanic — in code, in the judge prompt, or in config — MUST update `GAME_MECHANICS.md` in the same commit.** If you change how blocking math works, how cooldowns apply, how cost is computed, or add/remove/modify any rule, the mechanics doc is updated before the task is considered done. Code and `GAME_MECHANICS.md` must never disagree.
2. **After completing any task, append an entry to `PROGRESS.md`** using the format defined at the top of that file: date, task, what was done, files touched, follow-ups. Do this even for small tasks.
3. Nontrivial design or architecture choices made during implementation get a one-line entry in the DECISIONS section of `PROGRESS.md`.

## Workflow rules

- **Use Plan Mode for any multi-file or architectural change.** Present the plan, get approval, then implement. Small single-file fixes can proceed directly.
- Follow the milestone order in `SPEC.md` §10 (M0 → M6). Do not start a later milestone before the current one's tests pass.
- Server-authoritative always: the resolver is a pure function in the backend; the client renders server-returned events and never computes combat outcomes.
- The LLM judge classifies; it never does balance-affecting arithmetic. Mana cost is computed server-side from `balance.json`.
- The API key lives only in backend env (`.env`, gitignored). Never expose it to the client bundle.
- Ask the user before: adding dependencies beyond the stack in `SPEC.md` §2, changing the `JudgedAction` schema, or changing v1 scope.

## Commands

```bash
# Backend (from /backend) — uv-managed; no manual venv activation needed
uv sync                                    # create/refresh .venv from pyproject + uv.lock
uv run uvicorn app.main:app --reload       # dev server (GET /health)
uv run pytest                              # all backend tests
uv run pytest -m "not live"                # CI subset (skips live judge evals)
uv run pytest tests/test_judge_eval.py     # judge eval suite (needs ANTHROPIC_API_KEY; M2+)
uv run ruff check . && uv run ruff format --check .   # lint + format check

# Frontend (from /frontend)
npm run dev
npm run test                        # vitest (one-shot)
npm run lint && npm run typecheck
```

(Adjust paths here if the scaffold differs; keep this section current.)

## Code conventions

- **Python:** 3.12, type hints everywhere, Pydantic v2 models for all API/judge schemas, `ruff` for lint+format. Resolver stays pure (no I/O inside).
- **TypeScript:** strict mode; the `JudgedAction`/`GameState`/`ResolutionEvent` types mirror the Pydantic models — if one changes, change both in the same commit.
- Small, focused commits, one logical change each; imperative-mood messages.

## Testing gates

- Resolver changes → resolver unit tests pass.
- Any change to `JUDGE.md`, the judge system prompt, or judge-adjacent code → full judge eval suite passes (temperature=0).
- Anti-stacking fixtures (greedy multi-request prompts) must always yield exactly one effect.
