export function HandoffScreen({ name, onReady }: { name: string; onReady: () => void }) {
  return (
    <div className="flex flex-col items-center gap-6 text-center">
      <div className="text-zinc-400">It&apos;s</div>
      <div className="text-4xl font-bold">{name}&apos;s turn</div>
      <p className="max-w-xs text-sm text-zinc-500">Pass the device over.</p>
      <button
        onClick={onReady}
        className="rounded-full bg-amber-400 px-8 py-3 font-semibold text-zinc-950 transition hover:bg-amber-300"
      >
        I&apos;m {name} — go
      </button>
    </div>
  );
}
