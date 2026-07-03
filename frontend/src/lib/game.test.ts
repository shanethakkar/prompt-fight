import { describe, it, expect } from "vitest";
import {
  canConfirm,
  canRewrite,
  capitalize,
  describeAction,
  pct,
  winnerLabel,
} from "@/lib/game";
import type { JudgeResponse, JudgedAction } from "@/lib/types";

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
