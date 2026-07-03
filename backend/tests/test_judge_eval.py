"""Live judge eval suite (JUDGE.md §7).

Runs the real judge against Claude at temperature 0. Marked `live` so it is
excluded from the default (offline) test run and CI:

    uv run pytest -m live            # run the evals (needs ANTHROPIC_API_KEY)
    uv run pytest -m "not live"      # everything else

Each fixture asserts on the emitted component BUNDLE with optional keys:
  types_exact   sorted multiset of component types must match exactly
  contains      each listed type must appear at least once
  excludes      none of the listed types may appear
  max/min_components  bundle-size bounds (restraint tests)
  element       some component carries this element
  power         max component power falls in [lo, hi]
  checks        per-type detail: {type, stat?, target?, magnitude?, power?, duration?}
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.config import load_balance
from app.judge import judge

pytestmark = pytest.mark.live

BAL = load_balance()
_FIX = json.loads((Path(__file__).parent / "fixtures" / "judge_eval.json").read_text("utf-8"))


def _types(action) -> list[str]:
    return sorted(c.type.value for c in action.components)


def _in_range(value, bounds) -> bool:
    return value is not None and bounds[0] <= value <= bounds[1]


def _check_matches(components, chk) -> bool:
    """True if some component of chk['type'] satisfies every sub-constraint."""
    for c in components:
        if c.type.value != chk["type"]:
            continue
        if "stat" in chk and (c.stat is None or c.stat.value != chk["stat"]):
            continue
        if "target" in chk and c.target.value != chk["target"]:
            continue
        if "magnitude" in chk and not _in_range(c.magnitude, chk["magnitude"]):
            continue
        if "power" in chk and not _in_range(c.power, chk["power"]):
            continue
        if "duration" in chk and not _in_range(c.duration, chk["duration"]):
            continue
        return True
    return False


@pytest.mark.parametrize("fx", _FIX["fixtures"], ids=[f["prompt"][:40] for f in _FIX["fixtures"]])
def test_fixture(fx):
    action = judge(fx["prompt"], BAL)
    types = _types(action)
    comps = action.components

    assert len(comps) <= BAL.max_components, f"over cap: {types}"
    if "max_components" in fx:
        assert len(comps) <= fx["max_components"], f"too many: {types}"
    if "min_components" in fx:
        assert len(comps) >= fx["min_components"], f"too few: {types}"
    if "types_exact" in fx:
        assert types == sorted(fx["types_exact"]), f"types {types} != {fx['types_exact']}"
    for t in fx.get("contains", []):
        assert t in types, f"missing {t} in {types}"
    for t in fx.get("excludes", []):
        assert t not in types, f"unexpected {t} in {types}"
    if fx.get("element"):
        assert any(c.element.value == fx["element"] for c in comps), f"element {fx['element']}"
    if fx.get("power"):
        powers = [c.power for c in comps if c.power is not None]
        lo, hi = fx["power"]
        assert powers and lo <= max(powers) <= hi, f"power {powers} not in {fx['power']}"
    for chk in fx.get("checks", []):
        assert _check_matches(comps, chk), f"no {chk['type']} matched {chk}; got {types}"


@pytest.mark.parametrize(
    "pair", _FIX["near_duplicate_pairs"], ids=[p["a"][:40] for p in _FIX["near_duplicate_pairs"]]
)
def test_near_duplicate(pair):
    a = judge(pair["a"], BAL)
    b = judge(pair["b"], BAL)
    assert _types(a) == _types(b), f"types differ: {_types(a)} vs {_types(b)}"
    for t in pair.get("contains", []):
        assert t in _types(a)
