// Pure, framework-free helpers for display + turn-flow gating. NO combat math
// lives here — the server is authoritative. Unit-tested in game.test.ts.

import type {
  Element,
  JudgeResponse,
  JudgedAction,
  PlayerState,
  ResolutionEvent,
  Side,
} from "./types";

export type Phase =
  | "start"
  | "handoff"
  | "input"
  | "preview"
  | "resolving"
  | "playback"
  | "gameover";

/** Clamp a value/max to a 0–100 percentage for a bar width. */
export function pct(value: number, max: number): number {
  if (max <= 0) return 0;
  return Math.max(0, Math.min(100, (value / max) * 100));
}

export function capitalize(s: string): string {
  return s.length ? s[0].toUpperCase() + s.slice(1) : s;
}

/** Human summary of a judged action for the cost preview. */
export function describeAction(action: JudgedAction): string {
  const base = `${capitalize(action.element)} ${action.subtype} · power ${action.power} · speed ${action.speed}`;
  return action.stat ? `${base} · ${action.stat}` : base;
}

/** Tailwind text-color class per element (UI accent only). */
export function elementColor(element: Element): string {
  switch (element) {
    case "fire":
      return "text-orange-400";
    case "water":
      return "text-sky-400";
    case "nature":
      return "text-green-400";
    case "lightning":
      return "text-yellow-300";
    default:
      return "text-zinc-300";
  }
}

export function canConfirm(res: JudgeResponse, rewritesRemaining: number): boolean {
  if (!res.action) return false;
  if (rewritesRemaining <= 0) return true;
  return res.affordable === true && res.on_cooldown !== true;
}

export function canRewrite(rewritesRemaining: number): boolean {
  return rewritesRemaining > 0;
}

export function winnerLabel(
  winner: Side | "draw" | null,
  p1Name: string,
  p2Name: string,
): string {
  if (winner === "draw") return "Draw!";
  if (winner === "p1") return `${p1Name} wins!`;
  if (winner === "p2") return `${p2Name} wins!`;
  return "Match over";
}

/** A plain-language sentence telling the story of one action's RESULT. */
export function narrateResult(e: ResolutionEvent, names: Record<Side, string>): string {
  const actor = names[e.actor];
  const target = names[e.target];
  const eff = e.effect;
  switch (e.outcome) {
    case "hit_knockback":
      return `${actor} hits ${target} for ${e.damage}.`;
    case "blocked":
      return `${target} blocks it${eff?.absorbed ? ` (absorbed ${eff.absorbed})` : ""} — no damage.`;
    case "partial": {
      const how =
        eff?.kind === "dodge"
          ? "grazes past the dodge"
          : eff?.kind === "reflect"
            ? "punches through the reflect"
            : "gets through the shield";
      return `It ${how} — ${e.damage} to ${target}.`;
    }
    case "dodged":
      return `${target} dodges it completely.`;
    case "reflected":
      return `Reflected! ${e.damage} bounces back at ${actor}.`;
    case "healed":
      return eff?.magnitude
        ? `${actor} recovers ${eff.magnitude} HP.`
        : `${actor} is already at full health.`;
    case "buffed":
      return `${actor} is ${eff?.kind === "hasten" ? "hastened" : "empowered"}: +${eff?.magnitude} ${eff?.stat} for ${eff?.duration} turns.`;
    case "debuffed":
      return `${target} is ${eff?.kind === "slow" ? "slowed" : "weakened"}: -${eff?.magnitude} ${eff?.stat} for ${eff?.duration} turns.`;
    case "defended":
      return `${actor} braces — ${eff?.kind === "shield" ? "shield up" : eff?.kind === "dodge" ? "ready to dodge" : "reflect ready"}.`;
    default:
      return "";
  }
}

export type ChipTone = "buff" | "debuff" | "defense" | "cooldown";

export interface Chip {
  text: string;
  tone: ChipTone;
}

/** Readable status chips for a player (what each effect actually does). */
export function statusChips(p: PlayerState): Chip[] {
  const chips: Chip[] = [];
  if (p.active_buff) {
    const b = p.active_buff;
    const txt = b.speed_shift
      ? `Hastened +${b.speed_shift} spd`
      : `Empowered +${b.power_shift} pow`;
    chips.push({ text: `${txt} · ${b.turns_remaining}t`, tone: "buff" });
  }
  if (p.active_debuff) {
    const d = p.active_debuff;
    const txt = d.speed_shift ? `Slowed -${d.speed_shift} spd` : `Weakened -${d.power_shift} pow`;
    chips.push({ text: `${txt} · ${d.turns_remaining}t`, tone: "debuff" });
  }
  if (p.active_defense) {
    const s = p.active_defense.subtype;
    const txt = s === "shield" ? "Shield up" : s === "dodge" ? "Braced (dodge)" : "Reflecting";
    chips.push({ text: txt, tone: "defense" });
  }
  for (const [cat, turns] of Object.entries(p.cooldowns)) {
    if (turns && turns > 0) {
      chips.push({ text: `${capitalize(cat)} ready in ${turns}`, tone: "cooldown" });
    }
  }
  return chips;
}
