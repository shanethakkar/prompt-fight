import type { Chip, ChipTone } from "@/lib/game";

// Shared status-chip rendering (used by the roster row + the unit inspector).
export const CHIP_CLASS: Record<ChipTone, string> = {
  buff: "bg-emerald-900/60 text-emerald-300",
  debuff: "bg-rose-900/60 text-rose-300",
  defense: "bg-sky-900/60 text-sky-300",
  cooldown: "bg-zinc-800 text-zinc-400",
};

export function Chips({ chips }: { chips: Chip[] }) {
  if (!chips.length) return null;
  return (
    <div className="flex flex-wrap gap-1 text-[10px]">
      {chips.map((c, i) => (
        <span key={i} className={`rounded px-1.5 py-0.5 ${CHIP_CLASS[c.tone]}`}>
          {c.text}
        </span>
      ))}
    </div>
  );
}
