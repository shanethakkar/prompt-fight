"""Endpoint tests via TestClient. The judge is mocked so these run offline."""

from __future__ import annotations

import pytest
from app.main import app
from app.models import GameState, JudgedAction, PlayerState
from app.resolver import initial_game
from fastapi.testclient import TestClient

client = TestClient(app)


def _fireball() -> JudgedAction:
    return JudgedAction(
        category="attack",
        subtype="projectile",
        element="fire",
        power=6,
        speed=6,
        flavor_text="A roaring fireball!",
    )


@pytest.fixture
def mock_judge(monkeypatch):
    monkeypatch.setattr("app.main.judge", lambda prompt, balance: _fireball())


# ---- /api/judge -------------------------------------------------------------


def test_judge_success(mock_judge):
    r = client.post(
        "/api/judge",
        json={
            "prompt": "I hurl a fireball",
            "player": {"mana": 10, "cooldowns": {}},
            "match_id": "m1",
            "rewrites_remaining": 2,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["action"]["subtype"] == "projectile"
    assert body["action"]["template"] == "projectile"  # server-normalized
    assert body["mana_cost"] == 9  # ceil(6**1.2 * 1.0)
    assert body["affordable"] is True
    assert body["on_cooldown"] is False
    assert body["rewrites_remaining"] == 1


def test_judge_unaffordable(mock_judge):
    r = client.post(
        "/api/judge",
        json={"prompt": "fireball", "player": {"mana": 5, "cooldowns": {}}, "match_id": "m1"},
    )
    body = r.json()
    assert body["affordable"] is False
    # rewrites default to balance rewrites_per_turn (2) - 1 = 1
    assert body["rewrites_remaining"] == 1


def test_judge_reports_cooldown(mock_judge):
    r = client.post(
        "/api/judge",
        json={
            "prompt": "fireball",
            "player": {"mana": 10, "cooldowns": {"attack": 1}},
            "match_id": "m1",
        },
    )
    assert r.json()["on_cooldown"] is True


def test_judge_moderation_reject(monkeypatch):
    # If moderation rejects, the judge must never be called.
    def _boom(prompt, balance):
        raise AssertionError("judge should not be called on a rejected prompt")

    monkeypatch.setattr("app.main.judge", _boom)
    r = client.post(
        "/api/judge",
        json={
            "prompt": "kill yourself",
            "player": {"mana": 10, "cooldowns": {}},
            "match_id": "m1",
            "rewrites_remaining": 2,
        },
    )
    body = r.json()
    assert body["error"] == "moderation"
    assert body["message"]
    assert body["action"] is None
    assert body["rewrites_remaining"] == 1  # a reject still consumes a rewrite


# ---- /api/resolve -----------------------------------------------------------


def test_resolve_endpoint():
    state = initial_game_json()
    p1 = _fireball()
    p2 = JudgedAction(
        category="attack", subtype="melee", element="physical", power=1, speed=1, flavor_text="jab"
    )
    r = client.post(
        "/api/resolve",
        json={
            "match_id": "m1",
            "state": state,
            "p1_action": p1.model_dump(mode="json"),
            "p2_action": p2.model_dump(mode="json"),
        },
    )
    assert r.status_code == 200
    body = r.json()
    # p1 faster (speed 6 > 1); undefended fireball = 6*3 = 18 -> p2 100 -> 82
    assert body["state"]["p2"]["hp"] == 82
    assert body["match_over"] is False
    assert [e["actor"] for e in body["events"]] == ["p1", "p2"]


def initial_game_json() -> dict:
    from app.config import load_balance

    return initial_game(load_balance()).model_dump(mode="json")


def test_resolve_match_over():
    # p2 at 15 HP takes a lethal 18 -> KO
    low = GameState(
        p1=PlayerState(name="P1", hp=100, mana=10),
        p2=PlayerState(name="P2", hp=15, mana=10),
    )
    r = client.post(
        "/api/resolve",
        json={
            "match_id": "m1",
            "state": low.model_dump(mode="json"),
            "p1_action": _fireball().model_dump(mode="json"),
            "p2_action": JudgedAction(
                category="heal",
                subtype="heal",
                element="nature",
                power=1,
                speed=1,
                flavor_text="sip",
            ).model_dump(mode="json"),
        },
    )
    body = r.json()
    assert body["match_over"] is True
    assert body["winner"] == "p1"
