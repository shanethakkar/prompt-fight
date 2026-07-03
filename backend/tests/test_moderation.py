"""Unit tests for the moderation pre-filter (non-live)."""

from __future__ import annotations

import pytest
from app.config import load_balance
from app.moderation import moderate

BAL = load_balance()


@pytest.mark.parametrize(
    "prompt",
    [
        "just kill yourself",
        "kys loser",
        "some porn nonsense",
        "I rape",  # standalone term
    ],
)
def test_blocks_disallowed(prompt):
    result = moderate(prompt, BAL)
    assert not result.allowed
    assert result.message


@pytest.mark.parametrize(
    "prompt",
    [
        "I kill them with my sword",
        "I stab the enemy in the heart",
        "a bloody meteor crushes them",
        "I destroy everything in sight",
        "I obliterate my foe with lightning",
        "I exploit a chink in their armor",  # 'chink' must NOT be blocked
        "the assassin strikes from the shadows",
        "I grab a grape and throw it",  # 'grape' must NOT trip 'rape'
        "I hurl a massive fireball",
    ],
)
def test_allows_combat_and_benign(prompt):
    assert moderate(prompt, BAL).allowed, prompt


def test_model_check_is_off_by_default():
    # moderation_model_check_enabled is false in balance.json, so no network call.
    assert BAL.moderation_model_check_enabled is False
