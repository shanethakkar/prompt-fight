import { useState } from "react";

export function StartScreen({
  onStart,
  busy,
}: {
  onStart: (p1: string, p2: string) => void;
  busy: boolean;
}) {
  const [p1, setP1] = useState("Player 1");
  const [p2, setP2] = useState("Player 2");

  return (
    <div className="flex flex-col items-center gap-6 text-center">
      <div>
        <h1 className="text-5xl font-bold tracking-tight">Stickmancer</h1>
        <p className="mt-2 text-zinc-400">Type your attack. The judge decides your fate.</p>
      </div>
      <div className="flex w-full max-w-xs flex-col gap-3">
        <label className="text-left text-sm text-zinc-400">
          Player 1
          <input
            value={p1}
            onChange={(e) => setP1(e.target.value)}
            className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-zinc-100 outline-none focus:border-amber-400"
          />
        </label>
        <label className="text-left text-sm text-zinc-400">
          Player 2
          <input
            value={p2}
            onChange={(e) => setP2(e.target.value)}
            className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-zinc-100 outline-none focus:border-amber-400"
          />
        </label>
      </div>
      <button
        onClick={() => onStart(p1.trim() || "Player 1", p2.trim() || "Player 2")}
        disabled={busy}
        className="rounded-full bg-amber-400 px-8 py-3 font-semibold text-zinc-950 transition hover:bg-amber-300 disabled:opacity-50"
      >
        {busy ? "Starting…" : "Start Duel"}
      </button>
    </div>
  );
}
