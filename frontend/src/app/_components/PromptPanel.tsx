import { useState } from "react";

export function PromptPanel({
  name,
  mana,
  error,
  busy,
  onSubmit,
}: {
  name: string;
  mana: number;
  error: string | null;
  busy: boolean;
  onSubmit: (prompt: string) => void;
}) {
  const [prompt, setPrompt] = useState("");
  const canSubmit = prompt.trim().length > 0 && !busy;

  return (
    <div className="flex w-full max-w-lg flex-col gap-3">
      <div className="flex items-baseline justify-between">
        <h2 className="text-2xl font-bold">{name}, what&apos;s your move?</h2>
        <span className="text-sm text-sky-400">{mana} mana</span>
      </div>
      <textarea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            if (canSubmit) onSubmit(prompt.trim());
          }
        }}
        rows={3}
        autoFocus
        placeholder="e.g. I hurl a massive fireball at my opponent"
        className="w-full resize-none rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-zinc-100 outline-none focus:border-amber-400"
      />
      {error && <div className="text-sm text-rose-400">{error}</div>}
      <div className="flex items-center gap-3">
        <button
          onClick={() => onSubmit(prompt.trim())}
          disabled={!canSubmit}
          className="self-start rounded-full bg-amber-400 px-6 py-2 font-semibold text-zinc-950 transition hover:bg-amber-300 disabled:opacity-50"
        >
          {busy ? "Judging…" : "Submit"}
        </button>
        <span className="text-xs text-zinc-500">Enter to submit · Shift+Enter for a new line</span>
      </div>
    </div>
  );
}
