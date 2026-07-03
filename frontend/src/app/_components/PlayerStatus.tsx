import type { MatchConfig, PlayerState } from "@/lib/types";
import { capitalize, pct } from "@/lib/game";

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
  const cooldowns = Object.entries(player.cooldowns).filter(([, t]) => t > 0);
  return (
    <div
      className={`flex flex-col gap-2 rounded-xl border p-3 ${
        active ? "border-amber-400/60 bg-amber-400/5" : "border-zinc-800 bg-zinc-900/40"
      }`}
    >
      <div className="font-semibold">{player.name}</div>
      <Bar label="HP" value={player.hp} max={config.hp_max} color="bg-emerald-500" />
      <Bar label="Mana" value={player.mana} max={config.mana_max} color="bg-sky-500" />
      {(cooldowns.length > 0 || player.active_buff || player.active_debuff) && (
        <div className="flex flex-wrap gap-1 text-[10px]">
          {cooldowns.map(([cat, t]) => (
            <span key={cat} className="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-400">
              {capitalize(cat)} CD {t}
            </span>
          ))}
          {player.active_buff && (
            <span className="rounded bg-emerald-900/60 px-1.5 py-0.5 text-emerald-300">
              Buff {player.active_buff.turns_remaining}
            </span>
          )}
          {player.active_debuff && (
            <span className="rounded bg-rose-900/60 px-1.5 py-0.5 text-rose-300">
              Debuff {player.active_debuff.turns_remaining}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
