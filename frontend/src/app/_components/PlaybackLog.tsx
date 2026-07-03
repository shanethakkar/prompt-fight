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
  const names = { p1: preState.p1.name, p2: preState.p2.name };
  // A turn can emit several beats (start-of-turn ticks, then each component).
  // The bars show the final snapshot; each beat gets its own narration line.
  const last = result.events[result.events.length - 1];
  const d = last.state_delta;
  const flavor = result.events.find((e) => e.narration)?.narration ?? "";

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
        {flavor && <div className="italic text-zinc-300">“{flavor}”</div>}
        <ul className="mt-2 flex flex-col gap-1.5">
          {result.events.map((e, i) => {
            const line = narrateResult(e, names);
            if (!line) return null;
            return (
              <li key={i} className="font-medium text-zinc-100">
                {line}
              </li>
            );
          })}
        </ul>
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
