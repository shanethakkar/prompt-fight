import type { MatchConfig, PlayerState } from "@/lib/types";
import { pct, statusChips, type ChipTone } from "@/lib/game";

const CHIP_CLASS: Record<ChipTone, string> = {
  buff: "bg-emerald-900/60 text-emerald-300",
  debuff: "bg-rose-900/60 text-rose-300",
  defense: "bg-sky-900/60 text-sky-300",
  cooldown: "bg-zinc-800 text-zinc-400",
};

export function Bar({
  label,
  value,
  max,
  color,
}: {
  label: string;
  value: number;
  max: number;
  color: string;
}) {
  return (
    <div>
      <div className="flex justify-between text-xs text-zinc-400">
        <span>{label}</span>
        <span>
          {Math.max(0, value)}/{max}
        </span>
      </div>
      <div className="h-2.5 w-full overflow-hidden rounded-full bg-zinc-800">
        <div
          className={`h-full rounded-full ${color} transition-all duration-500`}
          style={{ width: `${pct(value, max)}%` }}
        />
      </div>
    </div>
  );
}

export function PlayerStatus({
  player,
  config,
  active,
}: {
  player: PlayerState;
  config: MatchConfig;
  active?: boolean;
}) {
  const chips = statusChips(player);
  return (
    <div
      className={`flex flex-col gap-2 rounded-xl border p-3 ${
        active ? "border-amber-400/60 bg-amber-400/5" : "border-zinc-800 bg-zinc-900/40"
      }`}
    >
      <div className="font-semibold">{player.name}</div>
      <Bar label="HP" value={player.hp} max={config.hp_max} color="bg-emerald-500" />
      <Bar label="Mana" value={player.mana} max={config.mana_max} color="bg-sky-500" />
      {chips.length > 0 && (
        <div className="flex flex-wrap gap-1 text-[10px]">
          {chips.map((c, i) => (
            <span key={i} className={`rounded px-1.5 py-0.5 ${CHIP_CLASS[c.tone]}`}>
              {c.text}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
