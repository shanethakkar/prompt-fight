import { describe, it, expect } from "vitest";
import {
  canConfirm,
  canRewrite,
  capitalize,
  describeAction,
  narrateResult,
  pct,
  statusChips,
  winnerLabel,
} from "@/lib/game";
import type { JudgeResponse, JudgedAction, PlayerState, ResolutionEvent } from "@/lib/types";

const NAMES = { p1: "Ada", p2: "Bo" } as const;

function ev(over: Partial<ResolutionEvent>): ResolutionEvent {
  return {
    actor: "p1",
    target: "p2",
    template: "melee",
    outcome: "hit_knockback",
    damage: 0,
    effect: null,
    narration: "fx",
    state_delta: { p1_hp: 100, p2_hp: 100, p1_mana: 10, p2_mana: 10 },
    ...over,
  };
}

const action: JudgedAction = {
  category: "attack",
  subtype: "projectile",
  element: "fire",
  power: 6,
  speed: 6,
  stat: null,
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
  it("summarizes without stat", () => {
    expect(describeAction(action)).toBe("Fire projectile · power 6 · speed 6");
  });
  it("appends stat for buff/debuff", () => {
    const buff: JudgedAction = { ...action, category: "buff", subtype: "buff", stat: "speed" };
    expect(describeAction(buff)).toContain("· speed");
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
    expect(narrateResult(ev({ outcome: "hit_knockback", damage: 18 }), NAMES)).toBe(
      "Ada hits Bo for 18.",
    );
  });
  it("narrates a partial through a shield", () => {
    expect(
      narrateResult(ev({ outcome: "partial", damage: 6, effect: { kind: "shield" } }), NAMES),
    ).toBe("It gets through the shield — 6 to Bo.");
  });
  it("narrates a reflect back at the attacker", () => {
    expect(
      narrateResult(ev({ outcome: "reflected", target: "p1", damage: 9, effect: { kind: "reflect" } }), NAMES),
    ).toBe("Reflected! 9 bounces back at Ada.");
  });
  it("narrates a debuff with stat/magnitude/duration", () => {
    expect(
      narrateResult(
        ev({
          outcome: "debuffed",
          effect: { kind: "weaken", stat: "power", magnitude: 5, duration: 2 },
        }),
        NAMES,
      ),
    ).toBe("Bo is weakened: -5 power for 2 turns.");
  });
  it("narrates a heal at cap as no effect", () => {
    expect(
      narrateResult(ev({ actor: "p1", target: "p1", outcome: "healed", effect: { kind: "heal", magnitude: 0 } }), NAMES),
    ).toBe("Ada is already at full health.");
  });
});

describe("statusChips", () => {
  function ps(over: Partial<PlayerState>): PlayerState {
    return {
      name: "P",
      hp: 100,
      mana: 10,
      cooldowns: {},
      active_buff: null,
      active_debuff: null,
      active_defense: null,
      ...over,
    };
  }
  it("labels a power buff readably", () => {
    const chips = statusChips(ps({ active_buff: { power_shift: 5, speed_shift: 0, turns_remaining: 2 } }));
    expect(chips[0]).toEqual({ text: "Empowered +5 pow · 2t", tone: "buff" });
  });
  it("labels a debuff and a cooldown", () => {
    const chips = statusChips(
      ps({ active_debuff: { power_shift: 4, speed_shift: 0, turns_remaining: 1 }, cooldowns: { heal: 2 } }),
    );
    expect(chips.map((c) => c.text)).toContain("Weakened -4 pow · 1t");
    expect(chips.map((c) => c.text)).toContain("Heal ready in 2");
  });
  it("labels a shield stance", () => {
    const chips = statusChips(
      ps({ active_defense: { subtype: "shield", element: "physical", power: 4, speed: 5, turns_remaining: 1 } }),
    );
    expect(chips[0]).toEqual({ text: "Shield up", tone: "defense" });
  });
});
