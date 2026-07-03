import type { MatchConfig, SideState, Unit } from "@/lib/types";
import { capitalize, pct, statusChips, type Chip, type ChipTone } from "@/lib/game";

const CHIP_CLASS: Record<ChipTone, string> = {
  buff: "bg-emerald-900/60 text-emerald-300",
  debuff: "bg-rose-900/60 text-rose-300",
  defense: "bg-sky-900/60 text-sky-300",
  cooldown: "bg-zinc-800 text-zinc-400",
};

function Chips({ chips }: { chips: Chip[] }) {
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

/** One entity row in the roster: name + kit, an HP bar scaled to its own max, and chips. */
function EntityRow({ unit }: { unit: Unit }) {
  const kit = unit.weapon ? `${capitalize(unit.weapon.element)} ${unit.weapon.power}` : "";
  const tags = unit.tags.length ? ` · ${unit.tags.join(", ")}` : "";
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-2">
      <div className="flex justify-between text-xs">
        <span className="font-medium text-zinc-200">{unit.name}</span>
        <span className="text-zinc-500">
          {kit}
          {tags}
        </span>
      </div>
      <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-zinc-800">
        <div
          className="h-full rounded-full bg-emerald-500/80 transition-all duration-500"
          style={{ width: `${pct(unit.hp, unit.max_hp)}%` }}
        />
      </div>
      <Chips chips={statusChips(unit)} />
    </div>
  );
}

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
  player: SideState;
  config: MatchConfig;
  active?: boolean;
}) {
  return (
    <div
      className={`flex flex-col gap-2 rounded-xl border p-3 ${
        active ? "border-amber-400/60 bg-amber-400/5" : "border-zinc-800 bg-zinc-900/40"
      }`}
    >
      <div className="font-semibold">{player.name}</div>
      <Bar label="HP" value={player.stickman.hp} max={config.hp_max} color="bg-emerald-500" />
      <Bar label="Mana" value={player.mana} max={config.mana_max} color="bg-sky-500" />
      <Chips chips={statusChips(player.stickman, player.cooldowns)} />
      {player.entities.length > 0 && (
        <div className="mt-1 flex flex-col gap-1.5">
          {player.entities.map((u) => (
            <EntityRow key={u.id} unit={u} />
          ))}
        </div>
      )}
    </div>
  );
}
