import { describe, it, expect } from "vitest";
import {
  canConfirm,
  canRewrite,
  capitalize,
  describeAction,
  ledgerLines,
  narrateResult,
  pct,
  statusChips,
  winnerLabel,
} from "@/lib/game";
import type {
  Action,
  ActiveEffect,
  JudgeResponse,
  LedgerEntry,
  ResolutionEvent,
  Unit,
} from "@/lib/types";

const NAMES = { p1: "Ada", p2: "Bo" } as const;

function ev(over: Partial<ResolutionEvent>): ResolutionEvent {
  return {
    actor: "p1",
    target: "p2",
    kind: "damage",
    element: "physical",
    outcome: "hit_knockback",
    amount: 0,
    effect: null,
    template: "melee",
    narration: "fx",
    state_delta: { p1_hp: 100, p2_hp: 100, p1_mana: 10, p2_mana: 10 },
    ...over,
  };
}

const action: Action = {
  components: [
    {
      type: "damage",
      target: "opponent",
      element: "fire",
      power: 6,
      magnitude: null,
      duration: null,
      stat: null,
      subtype: null,
    },
  ],
  element: "fire",
  speed: 6,
  template: "projectile",
  visual: { primitives: [] },
  flavor_text: "A roaring fireball!",
};

function judged(over: Partial<JudgeResponse> = {}): JudgeResponse {
  return {
    action,
    mana_cost: 9,
    affordable: true,
    on_cooldown: false,
    error: null,
    message: null,
    rewrites_remaining: 1,
    ...over,
  };
}

function eff(over: Partial<ActiveEffect>): ActiveEffect {
  return {
    kind: "stat",
    turns_remaining: 2,
    source: "p1",
    label: "",
    per_turn: 0,
    element: "physical",
    stat: null,
    magnitude: 0,
    subtype: null,
    power: 0,
    speed: 0,
    ...over,
  };
}

describe("pct", () => {
  it("clamps to [0,100]", () => {
    expect(pct(50, 100)).toBe(50);
    expect(pct(150, 100)).toBe(100);
    expect(pct(-10, 100)).toBe(0);
    expect(pct(5, 0)).toBe(0);
  });
});

describe("capitalize", () => {
  it("uppercases the first letter", () => {
    expect(capitalize("fire")).toBe("Fire");
    expect(capitalize("")).toBe("");
  });
});

describe("describeAction", () => {
  it("summarizes a single damage component", () => {
    expect(describeAction(action)).toBe("Fire strike · pow 6");
  });
  it("joins a bundle with a plus", () => {
    const bundle: Action = {
      ...action,
      components: [
        action.components[0],
        { type: "dot", target: "opponent", element: "nature", power: 5, magnitude: null, duration: 3, stat: null, subtype: null },
      ],
    };
    const text = describeAction(bundle);
    expect(text).toContain("Fire strike");
    expect(text).toContain("Poison · 5/turn × 3t");
    expect(text).toContain("+");
  });
});

describe("canConfirm", () => {
  it("allows an affordable, off-cooldown action", () => {
    expect(canConfirm(judged(), 1)).toBe(true);
  });
  it("blocks unaffordable while rewrites remain", () => {
    expect(canConfirm(judged({ affordable: false }), 1)).toBe(false);
  });
  it("blocks on-cooldown while rewrites remain", () => {
    expect(canConfirm(judged({ on_cooldown: true }), 1)).toBe(false);
  });
  it("forces confirm when rewrites are exhausted (auto-lock)", () => {
    expect(canConfirm(judged({ affordable: false }), 0)).toBe(true);
  });
  it("never confirms a null action", () => {
    expect(canConfirm(judged({ action: null }), 0)).toBe(false);
  });
});

describe("canRewrite", () => {
  it("is true only with rewrites left", () => {
    expect(canRewrite(1)).toBe(true);
    expect(canRewrite(0)).toBe(false);
  });
});

describe("winnerLabel", () => {
  it("names the winner", () => {
    expect(winnerLabel("p1", "Ada", "Bo")).toBe("Ada wins!");
    expect(winnerLabel("p2", "Ada", "Bo")).toBe("Bo wins!");
    expect(winnerLabel("draw", "Ada", "Bo")).toBe("Draw!");
  });
});

describe("narrateResult", () => {
  it("narrates a clean hit", () => {
    expect(narrateResult(ev({ kind: "damage", outcome: "hit_knockback", amount: 18 }), NAMES)).toBe(
      "Ada hits Bo for 18.",
    );
  });
  it("narrates a partial through a shield", () => {
    expect(
      narrateResult(ev({ kind: "damage", outcome: "partial", amount: 6, effect: { kind: "shield" } }), NAMES),
    ).toBe("It gets through the shield — 6 to Bo.");
  });
  it("narrates a reflect back at the attacker", () => {
    expect(
      narrateResult(ev({ kind: "damage", outcome: "reflected", target: "p1", amount: 9, effect: { kind: "reflect" } }), NAMES),
    ).toBe("Reflected! 9 bounces back at Ada.");
  });
  it("narrates a poison tick at start of turn", () => {
    expect(
      narrateResult(ev({ kind: "dot_tick", target: "p2", amount: 5, effect: { kind: "dot", label: "poison" } }), NAMES),
    ).toBe("Bo takes 5 poison damage.");
  });
  it("narrates a weaken with stat/magnitude/duration", () => {
    expect(
      narrateResult(
        ev({
          kind: "stat",
          outcome: "applied",
          effect: { kind: "stat", stat: "power", magnitude: -5, duration: 2, label: "weakened" },
        }),
        NAMES,
      ),
    ).toBe("Bo is weakened: -5 power for 2 turns.");
  });
  it("narrates armor as a damage-taken reduction", () => {
    expect(
      narrateResult(
        ev({ kind: "stat", target: "p1", outcome: "applied", effect: { kind: "stat", stat: "damage_taken", magnitude: -4, duration: 4 } }),
        NAMES,
      ),
    ).toBe("Ada is armored — takes 40% less damage for 4 turns.");
  });
  it("narrates a dot application", () => {
    expect(
      narrateResult(ev({ kind: "dot", outcome: "applied", effect: { kind: "dot", label: "poison", per_turn: 5, duration: 3 } }), NAMES),
    ).toBe("Ada afflicts Bo with poison — 5/turn for 3 turns.");
  });
  it("narrates a heal at cap as no effect", () => {
    expect(
      narrateResult(ev({ kind: "heal", actor: "p1", target: "p1", outcome: "healed", amount: 0 }), NAMES),
    ).toBe("Ada is already at full health.");
  });
});

describe("statusChips", () => {
  function ps(over: Partial<Unit>): Unit {
    return {
      id: "u",
      name: "P",
      kind: "stickman",
      hp: 100,
      max_hp: 100,
      effects: [],
      barriers: [],
      stun_immunity: 0,
      ...over,
    };
  }
  it("labels a power buff readably", () => {
    const chips = statusChips(ps({ effects: [eff({ stat: "power", magnitude: 5, turns_remaining: 2, label: "empowered" })] }));
    expect(chips[0]).toEqual({ text: "Empowered +5 power · 2t", tone: "buff" });
  });
  it("labels a weaken and a side cooldown", () => {
    const chips = statusChips(
      ps({ effects: [eff({ stat: "power", magnitude: -4, turns_remaining: 1, label: "weakened" })] }),
      { heal: 2 },
    );
    expect(chips.map((c) => c.text)).toContain("Weakened -4 power · 1t");
    expect(chips.map((c) => c.text)).toContain("Heal ready in 2");
  });
  it("labels a poison over-time effect", () => {
    const chips = statusChips(ps({ effects: [eff({ kind: "dot", per_turn: 5, turns_remaining: 3, label: "poison" })] }));
    expect(chips[0]).toEqual({ text: "Poison 5/t · 3t", tone: "debuff" });
  });
  it("labels armor as a buff with a percentage", () => {
    const chips = statusChips(ps({ effects: [eff({ stat: "damage_taken", magnitude: -4, turns_remaining: 4 })] }));
    expect(chips[0].tone).toBe("buff");
    expect(chips[0].text).toContain("Armored");
    expect(chips[0].text).toContain("40% dmg");
  });
  it("labels a shield stance", () => {
    const chips = statusChips(ps({ effects: [eff({ kind: "defense", subtype: "shield", turns_remaining: 1 })] }));
    expect(chips[0]).toEqual({ text: "Shield up", tone: "defense" });
  });
  it("labels a barrier with its remaining pool", () => {
    const chips = statusChips(
      ps({ barriers: [{ pool: 18, element: "physical", source: "p1", label: "barrier" }] }),
    );
    expect(chips[0]).toEqual({ text: "Barrier 18", tone: "defense" });
  });
  it("labels a stun", () => {
    const chips = statusChips(ps({ effects: [eff({ kind: "control", turns_remaining: 2 })] }));
    expect(chips[0]).toEqual({ text: "Stunned 2t", tone: "debuff" });
  });
});

describe("stun narration", () => {
  it("narrates a stun landing", () => {
    expect(
      narrateResult(ev({ kind: "control", outcome: "applied", effect: { kind: "control", duration: 2 } }), NAMES),
    ).toBe("Bo is stunned for 2 turns!");
  });
  it("narrates immunity", () => {
    expect(narrateResult(ev({ kind: "control", outcome: "fizzled" }), NAMES)).toBe(
      "Bo shrugs off the stun.",
    );
  });
  it("narrates a skipped turn", () => {
    expect(narrateResult(ev({ kind: "stun_skip", actor: "p2", target: "p2", outcome: "fizzled" }), NAMES)).toBe(
      "Bo is stunned — skips the turn.",
    );
  });
});

describe("barrier narration", () => {
  it("narrates a barrier being raised", () => {
    expect(
      narrateResult(ev({ kind: "barrier", actor: "p1", target: "p1", outcome: "applied", effect: { kind: "barrier", barrier_remaining: 18 } }), NAMES),
    ).toBe("Ada raises a barrier (18 absorb).");
  });
  it("narrates a full absorb", () => {
    expect(
      narrateResult(ev({ kind: "damage", outcome: "blocked", amount: 0, effect: { kind: "barrier", barrier_absorbed: 15, barrier_remaining: 3 } }), NAMES),
    ).toBe("Bo's barrier soaks the hit — 3 left.");
  });
  it("narrates a partial absorb with overflow", () => {
    expect(
      narrateResult(ev({ kind: "damage", outcome: "hit_knockback", amount: 5, effect: { kind: "barrier", barrier_absorbed: 10, barrier_remaining: 0 } }), NAMES),
    ).toBe("Ada hits Bo for 5 — barrier soaks 10.");
  });
  it("narrates a shatter", () => {
    expect(narrateResult(ev({ kind: "barrier_shatter", target: "p2", outcome: "shattered" }), NAMES)).toBe(
      "Bo's barrier shatters!",
    );
  });
});

describe("ledgerLines", () => {
  it("renders a committed turn's beats via narrateResult", () => {
    const entry: LedgerEntry = {
      round: 2,
      actor: "p1",
      events: [
        ev({ kind: "dot_tick", target: "p2", amount: 4, effect: { kind: "dot", label: "poison" } }),
        ev({ kind: "damage", outcome: "hit_knockback", amount: 12 }),
      ],
    };
    expect(ledgerLines(entry, NAMES)).toEqual(["Bo takes 4 poison damage.", "Ada hits Bo for 12."]);
  });
});
