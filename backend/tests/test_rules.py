"""Unit tests for the pure rule helpers (rules.py): normalization, aggregate
pricing, kind cooldowns, and effective-stat folding over the effect list."""

from __future__ import annotations

import pytest
from app.config import load_balance
from app.models import (
    Action,
    ActiveEffect,
    ComponentTarget,
    ComponentType,
    DefenseSubtype,
    EffectComponent,
    EffectKind,
    Element,
    GameState,
    Roster,
    RosterUnit,
    SideState,
    StatKind,
    Template,
    Unit,
)
from app.rules import (
    build_roster,
    bundle_cost,
    damage_taken_mult,
    effective_power,
    effective_speed,
    kind_cooldowns,
    normalize_components,
    reach,
    roll_outcome,
    success_odds,
    type_multiplier,
)

BAL = load_balance()


def dmg(power=6, element="physical"):
    return EffectComponent(type=ComponentType.damage, element=Element(element), power=power)


def stat_eff(stat, magnitude, turns=2, source="p1"):
    return ActiveEffect(
        kind=EffectKind.stat,
        stat=StatKind(stat),
        magnitude=magnitude,
        turns_remaining=turns,
        source=source,
    )


# ---------------------------------------------------------------------------
# normalize_components: validate / clamp / cap / drop
# ---------------------------------------------------------------------------


def test_normalize_fills_and_clamps():
    out = normalize_components([{"type": "damage", "power": 99, "element": "fire"}], BAL)
    assert len(out) == 1
    assert out[0].power == 10 and out[0].element is Element.fire
    assert out[0].target is ComponentTarget.opponent


def test_normalize_drops_unknown_type():
    assert normalize_components([{"type": "teleport"}, {"type": "damage", "power": 3}], BAL) == [
        EffectComponent(type=ComponentType.damage, target=ComponentTarget.opponent, power=3)
    ]


def test_normalize_at_most_one_damage():
    out = normalize_components(
        [{"type": "damage", "power": 5}, {"type": "damage", "power": 8}], BAL
    )
    assert [c.type for c in out] == [ComponentType.damage]
    assert out[0].power == 5  # the first survives


def test_normalize_truncates_to_max_components():
    raw = [
        {"type": "damage", "power": 5},
        {"type": "heal", "power": 4},
        {"type": "defense", "subtype": "shield", "power": 4},
        {"type": "hot", "power": 3, "duration": 3},
        {"type": "barrier", "power": 5},
    ]
    assert len(normalize_components(raw, BAL)) == BAL.max_components == 4


def test_normalize_stat_requires_stat_and_magnitude():
    assert normalize_components([{"type": "stat", "magnitude": 4}], BAL) == []  # no stat kind
    assert normalize_components([{"type": "stat", "stat": "power", "magnitude": 0}], BAL) == []
    out = normalize_components(
        [{"type": "stat", "stat": "power", "magnitude": -99, "duration": 9, "target": "self"}], BAL
    )
    assert out[0].magnitude == -BAL.max_stat_magnitude
    assert out[0].duration == BAL.max_effect_duration
    assert out[0].target is ComponentTarget.caster


def test_normalize_heal_and_hot_default_to_self():
    out = normalize_components(
        [{"type": "heal", "power": 4}, {"type": "hot", "power": 3, "duration": 2}], BAL
    )
    assert all(c.target is ComponentTarget.caster for c in out)


def test_normalize_defense_defaults_shield():
    out = normalize_components([{"type": "defense", "power": 5}], BAL)
    assert out[0].subtype is DefenseSubtype.shield
    assert out[0].target is ComponentTarget.caster


def test_normalize_ignores_non_dicts():
    assert normalize_components(["nope", 3, {"type": "damage", "power": 2}], BAL)[0].power == 2


# ---------------------------------------------------------------------------
# bundle_cost: aggregate, super-additive, capped
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "power,expected",
    [(1, 1), (5, 7), (6, 9), (10, 16)],  # ceil(power**1.2) with weight 1.0
)
def test_single_damage_cost_matches_legacy_curve(power, expected):
    assert bundle_cost([dmg(power=power)], BAL) == expected


def test_heal_and_defense_single_costs():
    heal = EffectComponent(type=ComponentType.heal, power=5)
    shield = EffectComponent(type=ComponentType.defense, subtype=DefenseSubtype.shield, power=5)
    assert bundle_cost([heal], BAL) == 7  # ceil((5*1.0)**1.2)
    assert bundle_cost([shield], BAL) == 5  # ceil((5*0.75)**1.2)


def test_bundle_is_super_additive():
    a = EffectComponent(type=ComponentType.stat, stat=StatKind.power, magnitude=3, duration=2)
    b = EffectComponent(type=ComponentType.stat, stat=StatKind.speed, magnitude=3, duration=2)
    combined = bundle_cost([a, b], BAL)
    assert combined > bundle_cost([a], BAL)
    assert combined > bundle_cost([b], BAL)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ([{"type": "heal", "power": 5}, {"type": "defense", "subtype": "shield", "power": 4}], 13),
        ([{"type": "damage", "power": 5}, {"type": "dot", "power": 5, "duration": 3}], 15),
        (
            [
                {"type": "stat", "stat": "speed", "magnitude": -6, "duration": 2},
                {"type": "dot", "power": 5, "duration": 3},
            ],
            15,
        ),
        ([{"type": "damage", "power": 6}, {"type": "heal", "power": 5}], 18),  # lifesteal
    ],
)
def test_retuned_bundle_targets(raw, expected):
    """Retune lands typical 2-effect bundles at ~13-18, not pinned to the cap."""
    assert bundle_cost(normalize_components(raw, BAL), BAL) == expected


def test_no_burst_discount():
    """A bundle never costs less than its most expensive component alone."""
    bundles = [
        [{"type": "damage", "power": 8}, {"type": "heal", "power": 3}],
        [
            {"type": "stat", "stat": "power", "magnitude": 8, "duration": 4},
            {"type": "dot", "power": 2, "duration": 1},
        ],
        [
            {"type": "damage", "power": 6},
            {"type": "dot", "power": 5, "duration": 3},
            {"type": "heal", "power": 4},
        ],
    ]
    for raw in bundles:
        comps = normalize_components(raw, BAL)
        combined = bundle_cost(comps, BAL)
        singles = [bundle_cost([c], BAL) for c in comps]
        assert combined >= max(singles), f"{combined} < max single {max(singles)}"


def test_bundle_cost_capped_at_max():
    big = [
        EffectComponent(type=ComponentType.damage, power=10),
        EffectComponent(type=ComponentType.heal, power=10),
        EffectComponent(type=ComponentType.defense, subtype=DefenseSubtype.shield, power=10),
    ]
    assert bundle_cost(big, BAL) == BAL.max_bundle_cost


def test_empty_bundle_is_free():
    assert bundle_cost([], BAL) == 0


def test_barrier_costs_more_than_shield_at_equal_power():
    shield = EffectComponent(type=ComponentType.defense, subtype=DefenseSubtype.shield, power=6)
    barrier = EffectComponent(type=ComponentType.barrier, power=6)
    assert bundle_cost([barrier], BAL) > bundle_cost([shield], BAL)


def test_normalize_barrier_targets_self():
    out = normalize_components([{"type": "barrier", "power": 6, "target": "opponent"}], BAL)
    assert out[0].type is ComponentType.barrier and out[0].target is ComponentTarget.caster


def test_barrier_shares_defense_cooldown():
    comps = [EffectComponent(type=ComponentType.barrier, power=5)]
    assert kind_cooldowns(comps, BAL) == {"defense": BAL.kind_cooldowns_turns.defense}


def test_normalize_at_most_one_control():
    out = normalize_components(
        [{"type": "control", "duration": 2}, {"type": "control", "duration": 1}], BAL
    )
    assert [c.type for c in out] == [ComponentType.control] and out[0].duration == 2


def test_control_duration_clamped():
    out = normalize_components([{"type": "control", "duration": 9}], BAL)
    assert out[0].duration == BAL.max_control_duration


def test_control_cost_scales_with_duration():
    c1 = EffectComponent(type=ComponentType.control, duration=1)
    c2 = EffectComponent(type=ComponentType.control, duration=2)
    assert bundle_cost([c2], BAL) > bundle_cost([c1], BAL)


def test_control_has_cooldown():
    comps = [EffectComponent(type=ComponentType.control, duration=1)]
    assert kind_cooldowns(comps, BAL) == {"control": BAL.kind_cooldowns_turns.control}


# ---------------------------------------------------------------------------
# kind_cooldowns: only heal/defense throttled; heavy bump
# ---------------------------------------------------------------------------


def test_kind_cooldowns_only_heal_and_defense():
    comps = [
        dmg(power=8),  # heavy but damage has no cooldown
        EffectComponent(type=ComponentType.heal, power=4),
        EffectComponent(type=ComponentType.defense, subtype=DefenseSubtype.shield, power=4),
    ]
    cds = kind_cooldowns(comps, BAL)
    assert cds == {"heal": 3, "defense": 1}


def test_kind_cooldowns_heavy_move_bump():
    comps = [EffectComponent(type=ComponentType.heal, power=9)]  # >= threshold 8
    assert kind_cooldowns(comps, BAL) == {"heal": 4}


def test_stat_and_dot_have_no_cooldown():
    comps = [
        EffectComponent(type=ComponentType.stat, stat=StatKind.power, magnitude=-4, duration=2),
        EffectComponent(type=ComponentType.dot, power=5, duration=3),
    ]
    assert kind_cooldowns(comps, BAL) == {}


# ---------------------------------------------------------------------------
# effective stats folded over the effect list
# ---------------------------------------------------------------------------


def test_effective_power_sums_additively():
    effects = [stat_eff("power", 3), stat_eff("power", 2)]
    assert effective_power(5, effects) == 10  # 5 + 3 + 2


def test_effective_power_floors_at_zero():
    assert effective_power(5, [stat_eff("power", -10)]) == 0


def test_effective_speed_floors_at_one():
    assert effective_speed(2, [stat_eff("speed", -9)]) == 1


def test_damage_taken_mult_multiplies_and_floors():
    armor = [stat_eff("damage_taken", -4), stat_eff("damage_taken", -4)]
    # (1-0.4)*(1-0.4) = 0.36
    assert damage_taken_mult(armor, BAL) == pytest.approx(0.36)
    heavy = [stat_eff("damage_taken", -8), stat_eff("damage_taken", -8)]
    assert damage_taken_mult(heavy, BAL) == BAL.damage_taken_mult_floor  # clamped


def test_damage_taken_mult_expose_increases():
    assert damage_taken_mult([stat_eff("damage_taken", 4)], BAL) == pytest.approx(1.4)


def test_damage_taken_mult_neutral_when_no_armor():
    assert damage_taken_mult([stat_eff("power", 3)], BAL) == 1.0


# ---------------------------------------------------------------------------
# type_multiplier (unchanged element chart)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "attacker,defender,expected",
    [
        ("fire", "nature", 1.5),
        ("nature", "fire", 0.75),
        ("water", "fire", 1.5),
        ("physical", "fire", 1.0),
        ("fire", "lightning", 1.0),
    ],
)
def test_type_multiplier(attacker, defender, expected):
    assert type_multiplier(Element(attacker), Element(defender), BAL) == expected


# ---------------------------------------------------------------------------
# Roster building + unit-id validation (P3.1a)
# ---------------------------------------------------------------------------


def _roster():
    return Roster(
        you=[RosterUnit(id="p1s", name="Ada", kind="stickman", hp=100, max_hp=100)],
        foe=[RosterUnit(id="p2s", name="Bo", kind="stickman", hp=100, max_hp=100)],
    )


def test_normalize_grounds_invalid_ids_to_stickman():
    out = normalize_components(
        [{"type": "damage", "power": 5, "source_id": "bogus", "target_id": "nope"}], BAL, _roster()
    )
    assert out[0].source_id == "p1s" and out[0].target_id == "p2s"


def test_normalize_keeps_a_valid_target_id():
    out = normalize_components([{"type": "damage", "power": 5, "target_id": "p2s"}], BAL, _roster())
    assert out[0].target_id == "p2s"


def test_normalize_without_roster_leaves_ids_none():
    out = normalize_components([{"type": "damage", "power": 5}], BAL)
    assert out[0].source_id is None and out[0].target_id is None


def test_build_roster_you_is_the_caster():
    from app.resolver import initial_game

    r = build_roster(initial_game(BAL), "p2")
    assert r.caster_stickman() == "p2s" and r.opponent_stickman() == "p1s"


# ---------------------------------------------------------------------------
# Combos (P3.1c): <=1 damage per source, unit cap, cost cap scales
# ---------------------------------------------------------------------------


def _ru(uid, name, kind="entity", hp=40):
    return RosterUnit(id=uid, name=name, kind=kind, hp=hp, max_hp=hp)


def _combat_roster(n_entities=1):
    you = [_ru("p1s", "Ada", "stickman", 100)] + [
        _ru(f"p1e{i}a", f"E{i}") for i in range(1, n_entities + 1)
    ]
    return Roster(you=you, foe=[_ru("p2s", "Bo", "stickman", 100)])


def test_combo_allows_one_damage_per_source():
    r = _combat_roster(1)
    out = normalize_components(
        [
            {"type": "damage", "power": 5, "source_id": "p1s", "target_id": "p2s"},
            {"type": "damage", "power": 6, "source_id": "p1e1a", "target_id": "p2s"},
        ],
        BAL,
        r,
    )
    assert [c.type for c in out] == [ComponentType.damage, ComponentType.damage]
    assert {c.source_id for c in out} == {"p1s", "p1e1a"}


def test_combo_dedups_two_damage_from_the_same_source():
    r = _combat_roster(1)
    out = normalize_components(
        [
            {"type": "damage", "power": 5, "source_id": "p1e1a"},
            {"type": "damage", "power": 6, "source_id": "p1e1a"},
        ],
        BAL,
        r,
    )
    assert len([c for c in out if c.type is ComponentType.damage]) == 1


def test_combo_caps_units_per_command():
    r = _combat_roster(2)  # stickman + 2 entities = 3 possible sources
    out = normalize_components(
        [
            {"type": "damage", "power": 5, "source_id": "p1s"},
            {"type": "damage", "power": 5, "source_id": "p1e1a"},
            {"type": "damage", "power": 5, "source_id": "p1e2a"},
        ],
        BAL,
        r,
    )
    assert len({c.source_id for c in out}) == BAL.max_units_per_command


def test_combo_cost_cap_scales_with_participants():
    r = _combat_roster(1)
    comps = normalize_components(
        [
            {"type": "damage", "power": 10, "source_id": "p1s"},
            {"type": "damage", "power": 10, "source_id": "p1e1a"},
        ],
        BAL,
        r,
    )
    assert bundle_cost(comps, BAL) > BAL.max_bundle_cost  # a 2-unit combo can cost more


# ---------------------------------------------------------------------------
# Effectiveness (P3.3): tier multipliers + grounding to target tags
# ---------------------------------------------------------------------------


def test_effectiveness_mult_values():
    from app.models import Effectiveness
    from app.rules import effectiveness_mult

    assert effectiveness_mult(Effectiveness.devastating, BAL) == 2.0
    assert effectiveness_mult(Effectiveness.resisted, BAL) == 0.4
    assert effectiveness_mult(Effectiveness.neutral, BAL) == 1.0


def test_effectiveness_grounds_to_a_real_target_tag():
    from app.models import Effectiveness

    r = Roster(
        # attacker is equipped with kryptonite (tag) -> "specially equipped"
        you=[
            RosterUnit(id="p1s", name="A", kind="stickman", hp=100, max_hp=100, tags=["kryptonite"])
        ],
        foe=[
            RosterUnit(
                id="p2s", name="Superman", kind="stickman", hp=100, max_hp=100, tags=["kryptonian"]
            )
        ],
    )
    grounded = normalize_components(
        [
            {
                "type": "damage",
                "power": 6,
                "effectiveness": "devastating",
                "eff_tag": "kryptonian",
                "target_id": "p2s",
            }
        ],
        BAL,
        r,
    )
    assert grounded[0].effectiveness is Effectiveness.devastating
    ungrounded = normalize_components(
        [
            {
                "type": "damage",
                "power": 6,
                "effectiveness": "devastating",
                "eff_tag": "undead",
                "target_id": "p2s",
            }
        ],
        BAL,
        r,
    )
    assert ungrounded[0].effectiveness is Effectiveness.neutral  # tag not on target -> dropped


def test_effectiveness_needs_a_specially_equipped_attacker():
    from app.models import Effectiveness

    # target IS a kryptonian, but a bare-fisted attacker (no gear) can't devastate it.
    r = Roster(
        you=[
            RosterUnit(id="p1s", name="A", kind="stickman", hp=100, max_hp=100)
        ],  # no tags/items/weapon
        foe=[
            RosterUnit(
                id="p2s", name="Superman", kind="stickman", hp=100, max_hp=100, tags=["kryptonian"]
            )
        ],
    )
    out = normalize_components(
        [
            {
                "type": "damage",
                "power": 6,
                "effectiveness": "devastating",
                "eff_tag": "kryptonian",
                "target_id": "p2s",
            }
        ],
        BAL,
        r,
    )
    assert out[0].effectiveness is Effectiveness.neutral


# ---------------------------------------------------------------------------
# Reliability odds (P1) — pure reach / success_odds / roll_outcome
# ---------------------------------------------------------------------------


def _cstate(mode="competitive", dodge_speed=None):
    eff = []
    if dodge_speed is not None:
        eff = [
            ActiveEffect(
                kind=EffectKind.defense,
                turns_remaining=1,
                source="p2",
                subtype=DefenseSubtype.dodge,
                speed=dodge_speed,
            )
        ]
    return GameState(
        round=1,
        active="p1",
        mode=mode,
        seed=0,
        p1=SideState(name="P1", mana=99, stickman=Unit(id="p1s", name="P1", hp=100, max_hp=100)),
        p2=SideState(
            name="P2", mana=99, stickman=Unit(id="p2s", name="P2", hp=100, max_hp=100, effects=eff)
        ),
    )


def _atk(power, fillers=0, speed=5):
    comps = [
        EffectComponent(type=ComponentType.damage, target=ComponentTarget.opponent, power=power)
    ]
    comps += [
        EffectComponent(type=ComponentType.hot, target=ComponentTarget.caster, power=3, duration=2)
        for _ in range(fillers)
    ]
    return Action(
        components=comps,
        element=Element.physical,
        speed=speed,
        template=Template.projectile,
        flavor_text="x",
    )


def test_reach_scales_with_power_and_component_count():
    assert reach(_atk(6).components, BAL) == 6.0
    assert reach(_atk(8, fillers=2).components, BAL) == 8 + BAL.reliability.reach_component_step * 2


def test_success_odds_sandbox_and_non_offensive_are_certain():
    assert success_odds(_atk(10, 3), _cstate(mode="sandbox"), BAL) == {"full": 1.0}
    heal = Action(
        components=[
            EffectComponent(type=ComponentType.heal, target=ComponentTarget.caster, power=6)
        ],
        element=Element.physical,
        speed=5,
        template=Template.heal_glow,
        flavor_text="x",
    )
    assert success_odds(heal, _cstate(), BAL) == {"full": 1.0}


@pytest.mark.parametrize("power,fillers", [(4, 0), (7, 0), (10, 3), (1, 0)])
def test_success_odds_is_a_distribution(power, fillers):
    o = success_odds(_atk(power, fillers), _cstate(), BAL)
    assert abs(sum(o.values()) - 1.0) < 1e-9
    assert all(v >= 0.0 for v in o.values())


def test_modest_action_is_reliable_apocalypse_is_risky():
    modest = success_odds(_atk(4), _cstate(), BAL)
    apocalypse = success_odds(_atk(10, 3), _cstate(), BAL)
    assert modest["full"] >= 0.9 and modest["backfire"] == 0.0
    assert apocalypse["full"] < 0.55 and apocalypse["miss"] > 0 and apocalypse["backfire"] > 0


def test_dodge_stance_lowers_hit_odds():
    plain = success_odds(_atk(10, 3), _cstate(), BAL)
    dodged = success_odds(_atk(10, 3), _cstate(dodge_speed=9), BAL)
    assert dodged["full"] < plain["full"] and dodged["miss"] > plain["miss"]


def test_roll_outcome_certain_and_partitioned():
    import random
    from collections import Counter

    assert roll_outcome({"full": 1.0}, random.Random(0)) == "full"
    counts = Counter(
        roll_outcome({"miss": 0.2, "full": 0.8}, random.Random(s)) for s in range(3000)
    )
    assert 0.15 < counts["miss"] / 3000 < 0.25


# ---------------------------------------------------------------------------
# Aptitude grounding (P1.2): a fit claim needs a mundane action or a suited actor
# ---------------------------------------------------------------------------


def _apt_comp(element="fire", aptitude="fit", source_id="p1s"):
    return {
        "type": "damage",
        "power": 6,
        "element": element,
        "aptitude": aptitude,
        "source_id": source_id,
        "target_id": "p2s",
    }


def _apt_roster(you_unit):
    return Roster(
        you=[you_unit],
        foe=[RosterUnit(id="p2s", name="Foe", kind="stickman", hp=100, max_hp=100)],
    )


def test_aptitude_bare_stickman_spell_drops_to_improvised():
    from app.models import Aptitude

    r = _apt_roster(RosterUnit(id="p1s", name="Stick", kind="stickman", hp=100, max_hp=100))
    out = normalize_components([_apt_comp(element="fire", aptitude="fit")], BAL, r)
    assert out[0].aptitude is Aptitude.improvised  # no arcane focus -> not full fit


def test_aptitude_mundane_physical_stays_fit():
    from app.models import Aptitude

    r = _apt_roster(RosterUnit(id="p1s", name="Stick", kind="stickman", hp=100, max_hp=100))
    out = normalize_components([_apt_comp(element="physical", aptitude="fit")], BAL, r)
    assert out[0].aptitude is Aptitude.fit  # a punch is fit for anyone


def test_aptitude_summoned_caster_stays_fit():
    from app.models import Aptitude

    r = Roster(
        you=[RosterUnit(id="p1e1a", name="Mage", kind="entity", hp=30, max_hp=30)],
        foe=[RosterUnit(id="p2s", name="Foe", kind="stickman", hp=100, max_hp=100)],
    )
    out = normalize_components(
        [_apt_comp(element="fire", aptitude="fit", source_id="p1e1a")], BAL, r
    )
    assert out[0].aptitude is Aptitude.fit  # an entity is inherently specialized


def test_aptitude_wand_equipped_stickman_stays_fit():
    from app.models import Aptitude

    r = _apt_roster(
        RosterUnit(id="p1s", name="Stick", kind="stickman", hp=100, max_hp=100, items=["wand"])
    )
    out = normalize_components([_apt_comp(element="fire", aptitude="fit")], BAL, r)
    assert out[0].aptitude is Aptitude.fit  # gear earns the magic


def test_aptitude_elemental_weapon_stays_fit():
    from app.models import Aptitude, Weapon

    r = _apt_roster(
        RosterUnit(
            id="p1s",
            name="Stick",
            kind="stickman",
            hp=100,
            max_hp=100,
            weapon=Weapon(name="flame blade", element=Element.fire, power=6),
        )
    )
    out = normalize_components([_apt_comp(element="fire", aptitude="fit")], BAL, r)
    assert out[0].aptitude is Aptitude.fit


def test_aptitude_trusts_improvised_and_unfit_for_bare_actor():
    from app.models import Aptitude

    r = _apt_roster(RosterUnit(id="p1s", name="Stick", kind="stickman", hp=100, max_hp=100))
    imp = normalize_components([_apt_comp(element="fire", aptitude="improvised")], BAL, r)
    assert imp[0].aptitude is Aptitude.improvised
    unf = normalize_components([_apt_comp(element="fire", aptitude="unfit")], BAL, r)
    assert unf[0].aptitude is Aptitude.unfit


def test_aptitude_server_is_authoritative_on_fit_for_geared_actor():
    from app.models import Aptitude

    # even if the judge under-calls "unfit", a wand-equipped actor is granted fit.
    r = _apt_roster(
        RosterUnit(id="p1s", name="Stick", kind="stickman", hp=100, max_hp=100, items=["wand"])
    )
    out = normalize_components([_apt_comp(element="fire", aptitude="unfit")], BAL, r)
    assert out[0].aptitude is Aptitude.fit


def test_success_odds_drops_with_poor_competence():
    from app.models import Aptitude

    fit = success_odds(_atk(6), _cstate(), BAL)
    poor = _atk(6)
    poor.components[0].aptitude = Aptitude.improvised
    imp = success_odds(poor, _cstate(), BAL)
    assert imp["full"] < fit["full"] and imp["miss"] > fit["miss"]
