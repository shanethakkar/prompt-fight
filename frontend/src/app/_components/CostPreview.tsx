import type { JudgeResponse } from "@/lib/types";
import { canConfirm, canRewrite, describeComponent, elementColor } from "@/lib/game";

export function CostPreview({
  res,
  rewritesRemaining,
  sandbox,
  onConfirm,
  onRewrite,
}: {
  res: JudgeResponse;
  rewritesRemaining: number;
  sandbox: boolean;
  onConfirm: () => void;
  onRewrite: () => void;
}) {
  const action = res.action!;
  const confirmable = sandbox || canConfirm(res, rewritesRemaining);
  const rewritable = canRewrite(rewritesRemaining);
  const forced = !sandbox && rewritesRemaining <= 0;

  return (
    <div className="flex w-full max-w-lg flex-col gap-4">
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
        <div className={`text-lg font-semibold ${elementColor(action.element)}`}>
          {action.flavor_text}
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {action.components.map((c, i) => (
            <span
              key={i}
              className="rounded bg-zinc-800 px-1.5 py-0.5 text-xs text-zinc-300"
            >
              {describeComponent(c)}
            </span>
          ))}
        </div>
        <div className="mt-3 flex items-center gap-4 text-sm">
          <span className="rounded bg-zinc-800 px-2 py-1">
            Cost <span className="font-semibold text-sky-400">{res.mana_cost}</span> mana
          </span>
          {res.affordable === false && (
            <span className="text-rose-400">Not enough mana</span>
          )}
          {res.on_cooldown && <span className="text-rose-400">On cooldown</span>}
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={onConfirm}
          disabled={!confirmable}
          className="rounded-full bg-emerald-500 px-6 py-2 font-semibold text-zinc-950 transition hover:bg-emerald-400 disabled:opacity-40"
        >
          {forced ? "Lock it in" : "Confirm"}
        </button>
        <button
          onClick={onRewrite}
          disabled={!rewritable}
          className="rounded-full border border-zinc-600 px-6 py-2 font-semibold text-zinc-200 transition hover:border-zinc-400 disabled:opacity-40"
        >
          Rewrite
        </button>
        <span className="text-xs text-zinc-500">
          {rewritesRemaining} rewrite{rewritesRemaining === 1 ? "" : "s"} left
        </span>
      </div>
    </div>
  );
}
