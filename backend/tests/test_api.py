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


# ---- /api/new_match ---------------------------------------------------------


def test_new_match():
    r = client.post("/api/new_match", json={"p1_name": "Ada", "p2_name": "Bo"})
    assert r.status_code == 200
    body = r.json()
    assert body["match_id"]
    assert body["state"]["round"] == 1
    assert body["state"]["active"] == "p1"
    assert body["state"]["p1"]["name"] == "Ada"
    assert body["state"]["p1"]["hp"] == 100 and body["state"]["p1"]["mana"] == 10
    cfg = body["config"]
    assert cfg["hp_max"] == 100
    assert cfg["mana_max"] == 20
    assert cfg["rewrites_per_turn"] == 2
    assert cfg["max_turns"] == 30


def test_new_match_defaults():
    body = client.post("/api/new_match", json={}).json()
    assert body["state"]["p1"]["name"] == "Player 1"
    assert body["state"]["p2"]["name"] == "Player 2"


def test_cors_headers_present():
    r = client.post(
        "/api/new_match",
        json={},
        headers={"Origin": "http://localhost:3000"},
    )
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


# ---- /api/resolve -----------------------------------------------------------


def initial_game_json() -> dict:
    from app.config import load_balance

    return initial_game(load_balance()).model_dump(mode="json")


def test_resolve_endpoint():
    # active p1 attacks undefended p2: 6*3 = 18 -> p2 82; turn passes to p2.
    r = client.post(
        "/api/resolve",
        json={
            "match_id": "m1",
            "state": initial_game_json(),
            "action": _fireball().model_dump(mode="json"),
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["state"]["p2"]["hp"] == 82
    assert body["state"]["active"] == "p2"
    assert body["match_over"] is False
    assert body["events"][0]["actor"] == "p1"


def test_resolve_over_match_rejected():
    dead = GameState(
        p1=PlayerState(name="P1", hp=100, mana=10),
        p2=PlayerState(name="P2", hp=0, mana=10),
    )
    r = client.post(
        "/api/resolve",
        json={
            "match_id": "m1",
            "state": dead.model_dump(mode="json"),
            "action": _fireball().model_dump(mode="json"),
        },
    )
    assert r.status_code == 400


def test_resolve_match_over():
    # active p1 kills p2 (15 HP, 18 dmg).
    low = GameState(
        p1=PlayerState(name="P1", hp=100, mana=10),
        p2=PlayerState(name="P2", hp=15, mana=10),
    )
    r = client.post(
        "/api/resolve",
        json={
            "match_id": "m1",
            "state": low.model_dump(mode="json"),
            "action": _fireball().model_dump(mode="json"),
        },
    )
    body = r.json()
    assert body["match_over"] is True
    assert body["winner"] == "p1"
