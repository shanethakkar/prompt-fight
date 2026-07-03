import type { GameState, ResolveResult } from "@/lib/types";
import { winnerLabel } from "@/lib/game";

export function VictoryScreen({
  result,
  finalState,
  onPlayAgain,
}: {
  result: ResolveResult;
  finalState: GameState;
  onPlayAgain: () => void;
}) {
  return (
    <div className="flex flex-col items-center gap-6 text-center">
      <div className="text-sm uppercase tracking-widest text-zinc-500">Match over</div>
      <h1 className="text-5xl font-bold text-amber-400">
        {winnerLabel(result.winner, finalState.p1.name, finalState.p2.name)}
      </h1>
      <div className="flex gap-8 text-lg">
        <span>
          {finalState.p1.name}: <span className="font-semibold">{finalState.p1.hp} HP</span>
        </span>
        <span>
          {finalState.p2.name}: <span className="font-semibold">{finalState.p2.hp} HP</span>
        </span>
      </div>
      <button
        onClick={onPlayAgain}
        className="rounded-full bg-amber-400 px-8 py-3 font-semibold text-zinc-950 transition hover:bg-amber-300"
      >
        Play again
      </button>
    </div>
  );
}
