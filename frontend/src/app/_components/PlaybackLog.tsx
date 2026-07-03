import type { GameState, MatchConfig, ResolveResult } from "@/lib/types";
import { narrateResult } from "@/lib/game";
import { Bar } from "./PlayerStatus";

export function PlaybackLog({
  preState,
  result,
  config,
  onDone,
}: {
  preState: GameState;
  result: ResolveResult;
  config: MatchConfig;
  onDone: () => void;
}) {
  const e = result.events[0];
  const d = e.state_delta;
  const names = { p1: preState.p1.name, p2: preState.p2.name };

  return (
    <div className="flex w-full max-w-lg flex-col gap-4">
      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-2 rounded-xl border border-zinc-800 bg-zinc-900/40 p-3">
          <div className="font-semibold">{preState.p1.name}</div>
          <Bar label="HP" value={d.p1_hp} max={config.hp_max} color="bg-emerald-500" />
          <Bar label="Mana" value={d.p1_mana} max={config.mana_max} color="bg-sky-500" />
        </div>
        <div className="flex flex-col gap-2 rounded-xl border border-zinc-800 bg-zinc-900/40 p-3">
          <div className="font-semibold">{preState.p2.name}</div>
          <Bar label="HP" value={d.p2_hp} max={config.hp_max} color="bg-emerald-500" />
          <Bar label="Mana" value={d.p2_mana} max={config.mana_max} color="bg-sky-500" />
        </div>
      </div>

      <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
        <div className="italic text-zinc-300">“{e.narration}”</div>
        <div className="mt-2 font-medium text-zinc-100">{narrateResult(e, names)}</div>
      </div>

      <button
        onClick={onDone}
        className="self-start rounded-full bg-amber-400 px-6 py-2 font-semibold text-zinc-950 transition hover:bg-amber-300"
      >
        {result.match_over ? "See result" : "Next turn"}
      </button>
    </div>
  );
}
