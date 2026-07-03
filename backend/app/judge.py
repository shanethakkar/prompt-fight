"""The LLM judge: freeform prompt -> one structured Action (a small effect bundle).

Uses forced tool-use against Claude Haiku at temperature 0. The judge only
classifies and scores — the server prices the bundle and does all combat math.
The raw component list is permissive; `rules.normalize_components` validates,
clamps, caps, and drops before it becomes an Action. Any failure retries once,
then falls back to a harmless "sputter" no-op so the endpoint never fails.
"""

from __future__ import annotations

import logging
from typing import Any

from anthropic import Anthropic

from app.config import BalanceConfig
from app.judge_prompt import EMIT_ACTION_TOOL, JUDGE_SYSTEM, render_roster
from app.models import (
    Action,
    ComponentTarget,
    ComponentType,
    EffectComponent,
    Element,
    Roster,
    Template,
)
from app.rules import normalize_components
from app.settings import get_settings

logger = logging.getLogger(__name__)

_MAX_TOKENS = 640


def _build_client() -> Anthropic:
    key = get_settings().anthropic_api_key
    return Anthropic(api_key=key) if key else Anthropic()


def _sputter() -> Action:
    """The harmless flail returned when judging fails (JUDGE.md §1)."""
    return Action(
        components=[
            EffectComponent(
                type=ComponentType.damage,
                target=ComponentTarget.opponent,
                element=Element.physical,
                power=1,
            )
        ],
        element=Element.physical,
        speed=5,
        template=Template.melee,
        flavor_text="A confused flail connects with nothing in particular.",
    )


def _action_from_tool_input(
    data: dict[str, Any], balance: BalanceConfig, roster: Roster | None
) -> Action:
    """Build a validated Action from the judge's permissive tool input.

    The component list is normalized (validated/clamped/capped; unit ids grounded
    against the roster); if nothing survives we sputter so a turn is never
    structurally impossible.
    """
    raw = data.get("components")
    components = normalize_components(raw if isinstance(raw, list) else [], balance, roster)
    if not components:
        return _sputter()

    def _enum(value: Any, enum_cls, default):
        try:
            return enum_cls(value)
        except (ValueError, KeyError):
            return default

    try:
        speed = max(1, min(10, int(data.get("speed", 5))))
    except (TypeError, ValueError):
        speed = 5

    return Action(
        components=components,
        element=_enum(data.get("element"), Element, Element.physical),
        speed=speed,
        template=_enum(data.get("template"), Template, Template.projectile),
        visual=data.get("visual") or {},
        flavor_text=str(data.get("flavor_text", ""))[:90],
    )


def _judge_once(
    client: Anthropic, prompt: str, balance: BalanceConfig, roster: Roster | None
) -> Action:
    content = f"{render_roster(roster)}\n\nPLAYER PROMPT: {prompt}" if roster else prompt
    response = client.messages.create(
        model=balance.judge_model,
        max_tokens=_MAX_TOKENS,
        temperature=balance.judge_temperature,
        system=JUDGE_SYSTEM,
        tools=[EMIT_ACTION_TOOL],
        tool_choice={"type": "tool", "name": "emit_action"},
        messages=[{"role": "user", "content": content}],
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == "emit_action":
            return _action_from_tool_input(dict(block.input), balance, roster)
    raise ValueError("judge response contained no emit_action tool call")


def judge(
    prompt: str,
    balance: BalanceConfig,
    *,
    roster: Roster | None = None,
    client: Anthropic | None = None,
) -> Action:
    """Classify a freeform prompt into one Action bundle. Never raises."""
    client = client or _build_client()
    for attempt in (1, 2):
        try:
            return _judge_once(client, prompt, balance, roster)
        except Exception:  # noqa: BLE001 — any failure falls through to the sputter
            logger.warning("judge attempt %d failed", attempt, exc_info=True)
    return _sputter()
