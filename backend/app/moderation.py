"""Server-side moderation pre-filter (SPEC.md §7), run before every judge call.

A deliberately CONSERVATIVE word-boundary blocklist: it targets clearly
disallowed content (sexual content, hate slurs, real-person threats/self-harm
encouragement) and must NOT catch in-game combat language — "kill", "stab",
"blood", "destroy", "obliterate" are all legal attacks. An optional cheap
model-based check runs only when `moderation_model_check_enabled` is set. The
list is intentionally minimal and expected to be curated/expanded in the M6 pass.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import BalanceConfig

REJECT_MESSAGE = "Let's keep it in the arena — try a different attack."

# Word-boundary patterns for clearly disallowed content. Combat verbs are
# intentionally absent. Keep entries lowercase; matching is case-insensitive.
_BLOCKLIST = [
    # Sexual content
    r"\bporn\b",
    r"\brape\b",
    r"\braping\b",
    r"\bmolest\w*",
    r"\bpedophile?\b",
    # Hate slurs (representative; expand from a maintained list in M6). Terms
    # that collide with ordinary combat words ("a chink in their armor") are
    # deliberately excluded to avoid false positives.
    r"\bn[i1]gger\b",
    r"\bfaggot\b",
    r"\bkike\b",
    # Real-person self-harm encouragement (not in-game "you die")
    r"\bkill yourself\b",
    r"\bkys\b",
]

_BLOCK_RE = re.compile("|".join(_BLOCKLIST), re.IGNORECASE)


@dataclass(frozen=True)
class ModerationResult:
    allowed: bool
    message: str | None = None


def moderate(prompt: str, balance: BalanceConfig) -> ModerationResult:
    """Return whether the prompt may be sent to the judge."""
    if _BLOCK_RE.search(prompt):
        return ModerationResult(allowed=False, message=REJECT_MESSAGE)
    if balance.moderation_model_check_enabled and not _model_check(prompt, balance):
        return ModerationResult(allowed=False, message=REJECT_MESSAGE)
    return ModerationResult(allowed=True)


def _model_check(prompt: str, balance: BalanceConfig) -> bool:
    """Optional cheap model classification (off by default). True = allowed.

    Kept simple and fail-open: a moderation API hiccup should not block play.
    """
    from anthropic import Anthropic

    from app.settings import get_settings

    key = get_settings().anthropic_api_key
    client = Anthropic(api_key=key) if key else Anthropic()
    try:
        resp = client.messages.create(
            model=balance.judge_model,
            max_tokens=5,
            temperature=0,
            system=(
                "You screen attack prompts for a cartoon stick-figure fighting game. "
                "In-game violence is fine. Reply with exactly ALLOW or BLOCK. "
                "BLOCK only sexual content, hate slurs, or real-world threats/self-harm."
            ),
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip().upper()
        return not text.startswith("BLOCK")
    except Exception:  # noqa: BLE001 — fail open on any moderation error
        return True
