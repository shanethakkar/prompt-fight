"""Endpoint tests via TestClient. The judge is mocked so these run offline."""

from __future__ import annotations

import pytest
from app.main import app
from app.models import (
    Action,
    ComponentTarget,
    ComponentType,
    DefenseSubtype,
    EffectComponent,
    GameState,
    SideState,
    Template,
    Unit,
)
from app.resolver import initial_game
from fastapi.testclient import TestClient

client = TestClient(app)


def _side(name: str, hp: int, mana: int = 12) -> SideState:
    return SideState(name=name, mana=mana, stickman=Unit(id="s", name=name, hp=hp, max_hp=100))


def _judge_state(mana: int = 12, cooldowns: dict | None = None) -> dict:
    """A serialized battlefield for /api/judge with the active side's mana/cooldowns."""
    gs = GameState(p1=_side("P1", 100, mana), p2=_side("P2", 100))
    d = gs.model_dump(mode="json")
    d["p1"]["cooldowns"] = cooldowns or {}
    return d


def _fireball() -> Action:
    return Action(
        components=[
            EffectComponent(
                type=ComponentType.damage,
                target=ComponentTarget.opponent,
                element="fire",
                power=6,
            )
        ],
        element="fire",
        speed=6,
        template=Template.projectile,
        flavor_text="A roaring fireball!",
    )


def _heal() -> Action:
    return Action(
        components=[
            EffectComponent(type=ComponentType.heal, target=ComponentTarget.caster, power=4)
        ],
        template=Template.heal_glow,
        flavor_text="A green glow.",
    )


@pytest.fixture
def mock_judge(monkeypatch):
    monkeypatch.setattr("app.main.judge", lambda prompt, balance, roster=None: _fireball())


# ---- /api/judge -------------------------------------------------------------


def test_judge_success(mock_judge):
    r = client.post(
        "/api/judge",
        json={
            "prompt": "I hurl a fireball",
            "state": _judge_state(10),
            "match_id": "m1",
            "rewrites_remaining": 2,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["action"]["components"][0]["type"] == "damage"
    assert body["action"]["components"][0]["element"] == "fire"
    assert body["mana_cost"] == 9  # ceil((6*1.0)**1.2)
    assert body["affordable"] is True
    assert body["on_cooldown"] is False  # damage has no cooldownable kind
    assert body["rewrites_remaining"] == 1


def test_judge_unaffordable(mock_judge):
    r = client.post(
        "/api/judge",
        json={"prompt": "fireball", "state": _judge_state(5), "match_id": "m1"},
    )
    body = r.json()
    assert body["affordable"] is False
    assert body["rewrites_remaining"] == 1


def test_judge_reports_cooldown(monkeypatch):
    monkeypatch.setattr("app.main.judge", lambda prompt, balance, roster=None: _heal())
    r = client.post(
        "/api/judge",
        json={
            "prompt": "heal me",
            "state": _judge_state(10, {"heal": 1}),
            "match_id": "m1",
        },
    )
    assert r.json()["on_cooldown"] is True


def test_judge_moderation_reject(monkeypatch):
    def _boom(prompt, balance, roster=None):
        raise AssertionError("judge should not be called on a rejected prompt")

    monkeypatch.setattr("app.main.judge", _boom)
    r = client.post(
        "/api/judge",
        json={
            "prompt": "kill yourself",
            "state": _judge_state(10),
            "match_id": "m1",
            "rewrites_remaining": 2,
        },
    )
    body = r.json()
    assert body["error"] == "moderation"
    assert body["message"]
    assert body["action"] is None
    assert body["rewrites_remaining"] == 1


# ---- /api/new_match ---------------------------------------------------------


def test_new_match():
    r = client.post("/api/new_match", json={"p1_name": "Ada", "p2_name": "Bo"})
    assert r.status_code == 200
    body = r.json()
    assert body["match_id"]
    assert body["state"]["round"] == 1 and body["state"]["active"] == "p1"
    assert body["state"]["p1"]["name"] == "Ada"
    assert body["state"]["p1"]["stickman"]["hp"] == 100 and body["state"]["p1"]["mana"] == 14
    assert body["state"]["p1"]["stickman"]["effects"] == []
    cfg = body["config"]
    assert cfg["hp_max"] == 100 and cfg["mana_max"] == 24
    assert cfg["rewrites_per_turn"] == 2 and cfg["max_turns"] == 30


def test_new_match_defaults():
    body = client.post("/api/new_match", json={}).json()
    assert body["state"]["p1"]["name"] == "Player 1"
    assert body["state"]["p2"]["name"] == "Player 2"


def test_cors_headers_present():
    r = client.post("/api/new_match", json={}, headers={"Origin": "http://localhost:3000"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


# ---- /api/resolve -----------------------------------------------------------


def initial_game_json() -> dict:
    from app.config import load_balance

    return initial_game(load_balance()).model_dump(mode="json")


def test_resolve_endpoint():
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
    assert body["state"]["p2"]["stickman"]["hp"] == 82  # 6*3
    assert body["state"]["active"] == "p2"
    assert body["match_over"] is False
    assert body["events"][0]["actor"] == "p1"


def test_resolve_over_match_rejected():
    dead = GameState(
        p1=_side("P1", 100, 10),
        p2=_side("P2", 0, 10),
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
    low = GameState(
        p1=_side("P1", 100, 10),
        p2=_side("P2", 15, 10),
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
    assert body["match_over"] is True and body["winner"] == "p1"


def test_resolve_accepts_null_action():
    r = client.post(
        "/api/resolve",
        json={"match_id": "m1", "state": initial_game_json(), "action": None},
    )
    assert r.status_code == 200 and r.json()["state"]["active"] == "p2"


def test_resolve_ignores_action_while_stunned():
    st = initial_game_json()
    st["active"] = "p2"
    st["p2"]["stickman"]["effects"] = [{"kind": "control", "turns_remaining": 1, "source": "p1"}]
    r = client.post(
        "/api/resolve",
        json={"match_id": "m1", "state": st, "action": _fireball().model_dump(mode="json")},
    )
    body = r.json()
    assert body["state"]["p1"]["stickman"]["hp"] == 100  # the submitted fireball was ignored
    assert any(e["kind"] == "stun_skip" for e in body["events"])


def test_resolve_bundle_multi_event():
    bundle = Action(
        components=[
            EffectComponent(type=ComponentType.heal, target=ComponentTarget.caster, power=4),
            EffectComponent(
                type=ComponentType.defense,
                target=ComponentTarget.caster,
                subtype=DefenseSubtype.shield,
                power=4,
            ),
        ],
        template=Template.shield_raise,
        flavor_text="Guard up, wounds knit.",
    )
    st = initial_game_json()
    st["p1"]["stickman"]["hp"] = 80
    r = client.post(
        "/api/resolve",
        json={"match_id": "m1", "state": st, "action": bundle.model_dump(mode="json")},
    )
    body = r.json()
    assert [e["kind"] for e in body["events"]] == ["heal", "defense"]
    assert body["state"]["p1"]["stickman"]["hp"] == 90
    assert any(e["kind"] == "defense" for e in body["state"]["p1"]["stickman"]["effects"])
