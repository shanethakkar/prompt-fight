export function StunnedScreen({
  name,
  busy,
  onSkip,
}: {
  name: string;
  busy: boolean;
  onSkip: () => void;
}) {
  return (
    <div className="flex w-full max-w-lg flex-col items-center gap-4 rounded-xl border border-rose-900/60 bg-rose-950/20 p-6 text-center">
      <div className="text-lg font-semibold text-rose-300">{name} is stunned!</div>
      <p className="text-sm text-zinc-400">
        Frozen in place — you skip this turn. Any lingering effects (poison, regen) still tick.
      </p>
      <button
        onClick={onSkip}
        disabled={busy}
        className="rounded-full bg-amber-400 px-6 py-2 font-semibold text-zinc-950 transition hover:bg-amber-300 disabled:opacity-50"
      >
        {busy ? "…" : "Skip turn"}
      </button>
    </div>
  );
}
