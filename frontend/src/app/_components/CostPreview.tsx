import type { JudgeResponse } from "@/lib/types";
import { canConfirm, canRewrite, describeAction, elementColor } from "@/lib/game";

export function CostPreview({
  res,
  rewritesRemaining,
  onConfirm,
  onRewrite,
}: {
  res: JudgeResponse;
  rewritesRemaining: number;
  onConfirm: () => void;
  onRewrite: () => void;
}) {
  const action = res.action!;
  const confirmable = canConfirm(res, rewritesRemaining);
  const rewritable = canRewrite(rewritesRemaining);
  const forced = rewritesRemaining <= 0;

  return (
    <div className="flex w-full max-w-lg flex-col gap-4">
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
        <div className={`text-lg font-semibold ${elementColor(action.element)}`}>
          {action.flavor_text}
        </div>
        <div className="mt-1 text-sm text-zinc-400">{describeAction(action)}</div>
        <div className="mt-3 flex items-center gap-4 text-sm">
          <span className="rounded bg-zinc-800 px-2 py-1">
            Cost <span className="font-semibold text-sky-400">{res.mana_cost}</span> mana
          </span>
          {res.affordable === false && (
            <span className="text-rose-400">Not enough mana</span>
          )}
          {res.on_cooldown && <span className="text-rose-400">Category on cooldown</span>}
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
