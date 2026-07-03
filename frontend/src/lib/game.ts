// Pure, framework-free helpers for display + turn-flow gating. NO combat math
// lives here — the server is authoritative. Unit-tested in game.test.ts.

import type {
  Action,
  ActiveEffect,
  EffectComponent,
  Element,
  JudgeResponse,
  LedgerEntry,
  ResolutionEvent,
  Side,
  StatKind,
  Unit,
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

const DOT_LABEL: Record<Element, string> = {
  fire: "burn",
  nature: "poison",
  water: "chill",
  lightning: "shock",
  physical: "bleed",
};

function signed(n: number): string {
  return n >= 0 ? `+${n}` : `${n}`;
}

function statName(stat: StatKind): string {
  return stat === "damage_taken" ? "dmg taken" : stat;
}

/** A short label for one effect component (used in the cost preview). */
export function describeComponent(c: EffectComponent): string {
  switch (c.type) {
    case "damage":
      return `${capitalize(c.element)} strike · pow ${c.power}`;
    case "heal":
      return `Heal · pow ${c.power}`;
    case "dot":
      return `${capitalize(DOT_LABEL[c.element])} · ${c.power}/turn × ${c.duration}t`;
    case "hot":
      return `Regen · ${c.power}/turn × ${c.duration}t`;
    case "stat": {
      const who = c.target === "self" ? "you" : "foe";
      if (c.stat === "damage_taken") {
        const p = Math.abs(c.magnitude ?? 0) * 10;
        const kind = (c.magnitude ?? 0) < 0 ? "armor" : "expose";
        return `${who}: ${kind} ${p}% · ${c.duration}t`;
      }
      return `${who}: ${signed(c.magnitude ?? 0)} ${statName(c.stat!)} · ${c.duration}t`;
    }
    case "defense":
      return `${capitalize(c.subtype ?? "shield")}`;
    case "barrier":
      return `Barrier · pow ${c.power}`;
    case "control":
      return `Stun · ${c.duration}t`;
    case "summon":
      return `Summon ${c.name ?? "unit"} · ${c.hp}hp · ${c.element} ${c.power}`;
    case "item":
      return c.power ? `Equip ${c.name} (${c.element} ${c.power})` : `Equip ${c.name}`;
    default:
      return c.type;
  }
}

/** Human summary of a judged action bundle for the cost preview. */
export function describeAction(action: Action): string {
  if (!action.components.length) return "no effect";
  return action.components.map(describeComponent).join("  +  ");
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

/** A small glyph per element, for icon-led unit/kit display. */
export function elementIcon(element: Element): string {
  switch (element) {
    case "fire":
      return "🔥";
    case "water":
      return "💧";
    case "nature":
      return "🌿";
    case "lightning":
      return "⚡";
    default:
      return "⚔️"; // physical / mundane
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

/** A plain-language sentence telling the story of one playback beat's RESULT. */
export function narrateResult(e: ResolutionEvent, names: Record<Side, string>): string {
  const actor = e.actor_name ?? names[e.actor];
  const target = e.target_name ?? names[e.target];
  const eff = e.effect;

  if (e.kind === "summon") {
    return `${actor} summons ${target}!`;
  }
  if (e.kind === "removed") {
    return `${target} falls!`;
  }
  if (e.kind === "item") {
    const gear = eff?.label ?? "gear";
    const on = e.target_name && e.target_name !== actor ? ` on ${e.target_name}` : "";
    return `${actor} equips ${gear}${on}.`;
  }

  // Over-time ticks fire at the start of the afflicted's turn.
  if (e.kind === "dot_tick") {
    const what = eff?.label ? `${eff.label} damage` : "damage";
    return `${target} takes ${e.amount} ${what}.`;
  }
  if (e.kind === "hot_tick") {
    return e.amount > 0 ? `${target} regenerates ${e.amount} HP.` : `${target} is already at full health.`;
  }
  if (e.kind === "barrier_shatter") {
    return `${target}'s barrier shatters!`;
  }
  if (e.kind === "stun_skip") {
    return `${actor} is stunned — skips the turn.`;
  }

  switch (e.kind) {
    case "damage":
      return narrateDamage(e, actor, target) + effSuffix(eff);
    case "barrier":
      return `${actor} raises a barrier${eff?.barrier_remaining ? ` (${eff.barrier_remaining} absorb)` : ""}.`;
    case "control":
      return e.outcome === "fizzled"
        ? `${target} shrugs off the stun.`
        : `${target} is stunned${eff?.duration ? ` for ${eff.duration} turns` : ""}!`;
    case "heal":
      return e.amount > 0 ? `${actor} recovers ${e.amount} HP.` : `${actor} is already at full health.`;
    case "dot":
      if (e.outcome === "missed") return `${actor}'s ${eff?.label ?? "attack"} misses ${target}.`;
      return `${actor} afflicts ${target} with ${eff?.label ?? "an effect"} — ${eff?.per_turn}/turn for ${eff?.duration} turns.${effSuffix(eff)}`;
    case "hot":
      return `${actor} starts regenerating — ${eff?.per_turn}/turn for ${eff?.duration} turns.`;
    case "stat":
      return narrateStat(e, actor, target);
    case "defense": {
      const s = eff?.label;
      const how = s === "shield" ? "shield up" : s === "dodge" ? "ready to dodge" : "reflect ready";
      return `${actor} braces — ${how}.`;
    }
    case "fizzle":
      return `${actor}'s action fizzles.`;
    default:
      return "";
  }
}

/** A flourish for a non-neutral matchup (kryptonite vs Superman). */
function effSuffix(eff: ResolutionEvent["effect"]): string {
  switch (eff?.effectiveness) {
    case "devastating":
      return " 💥 Devastating!";
    case "strong":
      return " Super effective!";
    case "resisted":
      return " …but it's resisted.";
    default:
      return "";
  }
}

function narrateDamage(e: ResolutionEvent, actor: string, target: string): string {
  const eff = e.effect;
  const soaked = eff?.barrier_absorbed ?? 0;
  const left = eff?.barrier_remaining;
  const barrierTail = soaked ? ` — barrier soaks ${soaked}` : "";
  switch (e.outcome) {
    case "hit_knockback":
      return `${actor} hits ${target} for ${e.amount}${barrierTail}.`;
    case "blocked":
      if (soaked && !eff?.absorbed) {
        return `${target}'s barrier soaks the hit${left != null ? ` — ${left} left` : ""}.`;
      }
      return `${target} blocks it${eff?.absorbed ? ` (absorbed ${eff.absorbed})` : ""} — no damage.`;
    case "partial": {
      if (eff?.reliability === "partial") {
        return `A glancing hit — ${e.amount} to ${target}${barrierTail}.`;
      }
      const how =
        eff?.kind === "dodge"
          ? "grazes past the dodge"
          : eff?.kind === "reflect"
            ? "punches through the reflect"
            : "gets through the shield";
      return `It ${how} — ${e.amount} to ${target}${barrierTail}.`;
    }
    case "dodged":
      return `${target} dodges it completely.`;
    case "reflected":
      return `Reflected! ${e.amount} bounces back at ${actor}${barrierTail}.`;
    case "missed":
      return `${actor}'s attack misses ${target}.`;
    case "overload":
      return `💥 Overload! ${actor} crits ${target} for ${e.amount}${barrierTail}.`;
    case "backfired":
      return `${actor}'s overreach backfires — ${e.amount} rebounds on ${actor}!`;
    default:
      return `${actor} hits ${target} for ${e.amount}.`;
  }
}

function narrateStat(e: ResolutionEvent, actor: string, target: string): string {
  const eff = e.effect;
  const dur = eff?.duration;
  const mag = eff?.magnitude ?? 0;
  if (eff?.stat === "damage_taken") {
    const p = Math.abs(mag) * 10;
    return mag < 0
      ? `${target} is armored — takes ${p}% less damage for ${dur} turns.`
      : `${target} is exposed — takes ${p}% more damage for ${dur} turns.`;
  }
  const label = eff?.label ?? "affected";
  return `${target} is ${label}: ${signed(mag)} ${statName(eff?.stat ?? "power")} for ${dur} turns.`;
}

export type ChipTone = "buff" | "debuff" | "defense" | "cooldown";

export interface Chip {
  text: string;
  tone: ChipTone;
}

function statChip(e: ActiveEffect): Chip {
  const t = e.turns_remaining;
  if (e.stat === "damage_taken") {
    const p = Math.abs(e.magnitude) * 10;
    return e.magnitude < 0
      ? { text: `Armored −${p}% dmg · ${t}t`, tone: "buff" }
      : { text: `Exposed +${p}% dmg · ${t}t`, tone: "debuff" };
  }
  const good = e.magnitude >= 0;
  const label = e.label || (good ? "Buffed" : "Debuffed");
  return { text: `${capitalize(label)} ${signed(e.magnitude)} ${statName(e.stat ?? "power")} · ${t}t`, tone: good ? "buff" : "debuff" };
}

/** Readable status chips for a unit (effects + barriers) plus the side's cooldowns. */
export function statusChips(unit: Unit, cooldowns: Record<string, number> = {}): Chip[] {
  const chips: Chip[] = [];
  for (const e of unit.effects) {
    switch (e.kind) {
      case "dot":
        chips.push({ text: `${capitalize(e.label || "poison")} ${e.per_turn}/t · ${e.turns_remaining}t`, tone: "debuff" });
        break;
      case "hot":
        chips.push({ text: `Regen ${e.per_turn}/t · ${e.turns_remaining}t`, tone: "buff" });
        break;
      case "stat":
        chips.push(statChip(e));
        break;
      case "defense": {
        const s = e.subtype;
        const txt = s === "shield" ? "Shield up" : s === "dodge" ? "Braced (dodge)" : "Reflecting";
        chips.push({ text: txt, tone: "defense" });
        break;
      }
      case "control":
        chips.push({ text: `Stunned ${e.turns_remaining}t`, tone: "debuff" });
        break;
    }
  }
  for (const bar of unit.barriers) {
    chips.push({ text: `Barrier ${bar.pool}`, tone: "defense" });
  }
  for (const [kind, turns] of Object.entries(cooldowns)) {
    if (turns && turns > 0) {
      chips.push({ text: `${capitalize(kind)} ready in ${turns}`, tone: "cooldown" });
    }
  }
  return chips;
}

/** The narration lines of one committed turn, for the combat ledger. */
export function ledgerLines(entry: LedgerEntry, names: Record<Side, string>): string[] {
  return entry.events.map((e) => narrateResult(e, names)).filter(Boolean);
}
