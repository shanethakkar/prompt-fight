"""Live judge eval suite (JUDGE.md §7).

Runs the real judge against Claude at temperature 0. Marked `live` so it is
excluded from the default (offline) test run and CI:

    uv run pytest -m live            # run the evals (needs ANTHROPIC_API_KEY)
    uv run pytest -m "not live"      # everything else
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.config import load_balance
from app.judge import judge
from app.models import Category, Element, Stat

pytestmark = pytest.mark.live

BAL = load_balance()
_FIX = json.loads((Path(__file__).parent / "fixtures" / "judge_eval.json").read_text("utf-8"))


@pytest.mark.parametrize("fx", _FIX["fixtures"], ids=[f["prompt"][:32] for f in _FIX["fixtures"]])
def test_fixture(fx):
    action = judge(fx["prompt"], BAL)
    assert action.category == Category(fx["category"]), f"category: {action.category}"
    if fx.get("element"):
        assert action.element == Element(fx["element"]), f"element: {action.element}"
    lo, hi = fx["power"]
    assert lo <= action.power <= hi, f"power {action.power} not in [{lo},{hi}]"
    if fx.get("stat"):
        assert action.stat == Stat(fx["stat"]), f"stat: {action.stat}"


@pytest.mark.parametrize(
    "pair", _FIX["near_duplicate_pairs"], ids=[p["a"][:32] for p in _FIX["near_duplicate_pairs"]]
)
def test_near_duplicate(pair):
    a = judge(pair["a"], BAL)
    b = judge(pair["b"], BAL)
    assert a.category == b.category == Category(pair["category"])
    assert a.power == b.power, f"power differs: {a.power} vs {b.power}"
    lo, hi = pair["power"]
    assert lo <= a.power <= hi
    if pair.get("stat"):
        assert a.stat == b.stat == Stat(pair["stat"])
