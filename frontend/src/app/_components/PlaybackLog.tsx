import { useEffect, useState } from "react";
import type { GameState, MatchConfig, ResolveResult } from "@/lib/types";
import { capitalize } from "@/lib/game";
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
  const events = result.events;
  const [revealed, setRevealed] = useState(0);

  useEffect(() => {
    if (revealed >= events.length) return;
    const t = setTimeout(() => setRevealed((r) => r + 1), 1100);
    return () => clearTimeout(t);
  }, [revealed, events.length]);

  const done = revealed >= events.length;
  const delta = revealed > 0 ? events[revealed - 1].state_delta : null;
  const name = (side: "p1" | "p2") => preState[side].name;

  return (
    <div className="flex w-full max-w-lg flex-col gap-4">
      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-2 rounded-xl border border-zinc-800 bg-zinc-900/40 p-3">
          <div className="font-semibold">{preState.p1.name}</div>
          <Bar label="HP" value={delta ? delta.p1_hp : preState.p1.hp} max={config.hp_max} color="bg-emerald-500" />
          <Bar label="Mana" value={delta ? delta.p1_mana : preState.p1.mana} max={config.mana_max} color="bg-sky-500" />
        </div>
        <div className="flex flex-col gap-2 rounded-xl border border-zinc-800 bg-zinc-900/40 p-3">
          <div className="font-semibold">{preState.p2.name}</div>
          <Bar label="HP" value={delta ? delta.p2_hp : preState.p2.hp} max={config.hp_max} color="bg-emerald-500" />
          <Bar label="Mana" value={delta ? delta.p2_mana : preState.p2.mana} max={config.mana_max} color="bg-sky-500" />
        </div>
      </div>

      <ol className="flex min-h-[6rem] flex-col gap-2">
        {events.slice(0, revealed).map((e, i) => (
          <li key={i} className="rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2 text-sm">
            <span className="text-zinc-500">{name(e.actor)}:</span> {e.narration}
            <span className="ml-2 text-xs text-zinc-500">
              [{capitalize(e.outcome.replace("_", " "))}
              {e.damage > 0 ? ` · ${e.damage}` : ""}]
            </span>
          </li>
        ))}
      </ol>

      <div className="flex gap-3">
        {!done && (
          <button
            onClick={() => setRevealed(events.length)}
            className="rounded-full border border-zinc-600 px-5 py-2 text-sm text-zinc-200 hover:border-zinc-400"
          >
            Skip
          </button>
        )}
        {done && (
          <button
            onClick={onDone}
            className="rounded-full bg-amber-400 px-6 py-2 font-semibold text-zinc-950 transition hover:bg-amber-300"
          >
            {result.match_over ? "See result" : "Next turn"}
          </button>
        )}
      </div>
    </div>
  );
}
