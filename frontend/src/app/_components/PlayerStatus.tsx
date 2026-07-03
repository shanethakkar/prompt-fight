import type { MatchConfig, Side, SideState, Unit } from "@/lib/types";
import { pct, statusChips } from "@/lib/game";
import { Chips } from "./Chips";
import { UnitFrame } from "./UnitInspector";

/** One entity row in the roster: name + HP bar + at-a-glance chips; hover/tap for the full inspector. */
function EntityRow({ unit, side }: { unit: Unit; side: Side }) {
  return (
    <UnitFrame unit={unit} side={side}>
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-2 transition-colors hover:border-zinc-600">
        <div className="flex justify-between text-xs">
          <span className="font-medium text-zinc-200">{unit.name}</span>
          <span className="text-zinc-500">
            {Math.max(0, unit.hp)}/{unit.max_hp}
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
    </UnitFrame>
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
  side,
}: {
  player: SideState;
  config: MatchConfig;
  active?: boolean;
  side: Side;
}) {
  return (
    <div
      className={`flex flex-col gap-2 rounded-xl border p-3 ${
        active ? "border-amber-400/60 bg-amber-400/5" : "border-zinc-800 bg-zinc-900/40"
      }`}
    >
      <UnitFrame unit={player.stickman} side={side}>
        <span className="font-semibold decoration-dotted decoration-zinc-600 underline-offset-4 hover:underline">
          {player.name}
        </span>
      </UnitFrame>
      <Bar label="HP" value={player.stickman.hp} max={config.hp_max} color="bg-emerald-500" />
      <Bar label="Mana" value={player.mana} max={config.mana_max} color="bg-sky-500" />
      <Chips chips={statusChips(player.stickman, player.cooldowns)} />
      {player.entities.length > 0 && (
        <div className="mt-1 flex flex-col gap-1.5">
          {player.entities.map((u) => (
            <EntityRow key={u.id} unit={u} side={side} />
          ))}
        </div>
      )}
    </div>
  );
}
