"""M0 tests for the balance-config loader."""

from __future__ import annotations

from app.config import BalanceConfig, load_balance


def test_loads_balance_config() -> None:
    cfg = load_balance()
    assert isinstance(cfg, BalanceConfig)


def test_known_values() -> None:
    cfg = load_balance()
    assert cfg.hp_start == 100
    assert cfg.mana_start == 12
    assert cfg.mana_max == 22
    assert cfg.mana_regen_per_turn == 4
    assert cfg.judge_model == "claude-haiku-4-5"
    assert cfg.component_weights.damage == 1.0
    assert cfg.bundle_multipliers["1"] == 1.0
    assert cfg.max_components == 3
    assert cfg.kind_cooldowns_turns.heal == 3
    assert cfg.damage_taken_per_point == 0.1
    assert cfg.defense_stance_duration_turns == 1


def test_load_is_cwd_independent(tmp_path, monkeypatch) -> None:
    """The loader anchors on __file__, so a different CWD must not break it."""
    monkeypatch.chdir(tmp_path)
    load_balance.cache_clear()
    try:
        cfg = load_balance()
        assert cfg.hp_start == 100
    finally:
        # Reset the cache so other tests get a clean, in-repo load.
        load_balance.cache_clear()


def test_optional_env_override(tmp_path, monkeypatch) -> None:
    """STICKMANCER_BALANCE_PATH takes precedence when set."""
    import shutil

    from app.config import _find_balance_path

    real = _find_balance_path()
    custom = tmp_path / "balance.json"
    shutil.copy(real, custom)

    monkeypatch.setenv("STICKMANCER_BALANCE_PATH", str(custom))
    assert _find_balance_path() == custom.resolve()

    monkeypatch.delenv("STICKMANCER_BALANCE_PATH", raising=False)
    assert _find_balance_path() == real
