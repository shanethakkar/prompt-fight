"""The LLM judge: freeform prompt -> one structured JudgedAction.

Uses forced tool-use against Claude Haiku at temperature 0. The judge only
classifies and scores — the server computes mana cost and all combat math. Any
failure retries once, then falls back to a harmless "sputter" no-op so the
endpoint never fails on a bad judge response.
"""

from __future__ import annotations

import logging
from typing import Any

from anthropic import Anthropic

from app.config import BalanceConfig
from app.judge_prompt import EMIT_ACTION_TOOL, JUDGE_SYSTEM
from app.models import SUBTYPE_CATEGORY, JudgedAction, Subtype
from app.settings import get_settings

logger = logging.getLogger(__name__)

_MAX_TOKENS = 512


def _build_client() -> Anthropic:
    key = get_settings().anthropic_api_key
    return Anthropic(api_key=key) if key else Anthropic()


def _sputter() -> JudgedAction:
    """The harmless flail returned when judging fails (JUDGE.md §1)."""
    return JudgedAction(
        category="attack",
        subtype="melee",
        element="physical",
        power=1,
        speed=5,
        flavor_text="A confused flail connects with nothing in particular.",
    )


def _action_from_tool_input(data: dict[str, Any]) -> JudgedAction:
    """Build a JudgedAction from the tool input, trusting subtype over category."""
    subtype = Subtype(data["subtype"])
    # Reconcile: subtype is the specific signal; derive category from it so a
    # judge mismatch self-corrects rather than raising in the model validator.
    category = SUBTYPE_CATEGORY[subtype]
    return JudgedAction(
        category=category,
        subtype=subtype,
        element=data.get("element", "physical"),
        power=data["power"],
        speed=data["speed"],
        stat=data.get("stat"),
        visual=data.get("visual") or {},
        flavor_text=data.get("flavor_text", ""),
    )


def _judge_once(client: Anthropic, prompt: str, balance: BalanceConfig) -> JudgedAction:
    response = client.messages.create(
        model=balance.judge_model,
        max_tokens=_MAX_TOKENS,
        temperature=balance.judge_temperature,
        system=JUDGE_SYSTEM,
        tools=[EMIT_ACTION_TOOL],
        tool_choice={"type": "tool", "name": "emit_action"},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == "emit_action":
            return _action_from_tool_input(dict(block.input))
    raise ValueError("judge response contained no emit_action tool call")


def judge(prompt: str, balance: BalanceConfig, *, client: Anthropic | None = None) -> JudgedAction:
    """Classify a freeform prompt into one JudgedAction. Never raises."""
    client = client or _build_client()
    for attempt in (1, 2):
        try:
            return _judge_once(client, prompt, balance)
        except Exception:  # noqa: BLE001 — any failure falls through to the sputter
            logger.warning("judge attempt %d failed", attempt, exc_info=True)
    return _sputter()
