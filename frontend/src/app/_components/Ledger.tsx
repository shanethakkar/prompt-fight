import type { LedgerEntry, Side } from "@/lib/types";
import { ledgerLines } from "@/lib/game";

/** A collapsible running history of resolved turns (newest first). */
export function Ledger({
  entries,
  names,
}: {
  entries: LedgerEntry[];
  names: Record<Side, string>;
}) {
  if (!entries.length) return null;
  const ordered = [...entries].reverse();

  return (
    <details className="w-full max-w-lg rounded-xl border border-zinc-800 bg-zinc-900/40">
      <summary className="cursor-pointer select-none px-4 py-2 text-xs uppercase tracking-widest text-zinc-400">
        Combat log · {entries.length} turn{entries.length === 1 ? "" : "s"}
      </summary>
      <div className="max-h-56 overflow-y-auto px-4 pb-3 text-sm">
        {ordered.map((entry, i) => {
          const flavor = entry.events.find((e) => e.narration)?.narration ?? "";
          const lines = ledgerLines(entry, names);
          return (
            <div
              key={`${entry.round}-${entry.actor}-${i}`}
              className="border-t border-zinc-800 py-2 first:border-t-0"
            >
              <div className="text-xs text-zinc-500">
                Round {entry.round} · {names[entry.actor]}
                {flavor && <span className="italic text-zinc-400"> — “{flavor}”</span>}
              </div>
              <ul className="mt-1 flex flex-col gap-0.5 text-zinc-300">
                {lines.map((l, j) => (
                  <li key={j}>{l}</li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>
    </details>
  );
}
