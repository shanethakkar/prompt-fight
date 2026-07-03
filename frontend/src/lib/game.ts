// Pure, framework-free helpers for display + turn-flow gating. NO combat math
// lives here — the server is authoritative. These are unit-tested in game.test.ts.

import type { Element, JudgeResponse, JudgedAction, Side } from "./types";

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
  const parts = [capitalize(action.element), action.subtype];
  const base = `${parts.join(" ")} · power ${action.power} · speed ${action.speed}`;
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

/**
 * Can this judged result be confirmed? Yes when it's affordable and off
 * cooldown, OR when the player has no rewrites left (§9 auto-lock forces the
 * last judged action through — the resolver floors mana at 0).
 */
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
