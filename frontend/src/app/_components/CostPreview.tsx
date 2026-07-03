import type { JudgeResponse } from "@/lib/types";
import { canConfirm, canRewrite, describeComponent, elementColor } from "@/lib/game";

// Reliability tiers, ordered best -> worst for the odds bar. [key, bar, label, text]
const ODDS_TIERS: [string, string, string, string][] = [
  ["full", "bg-emerald-500", "Full", "text-emerald-400"],
  ["overload", "bg-amber-400", "Crit", "text-amber-300"],
  ["partial", "bg-sky-500", "Partial", "text-sky-300"],
  ["miss", "bg-zinc-500", "Miss", "text-zinc-400"],
  ["backfire", "bg-rose-500", "Backfire", "text-rose-400"],
];

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

  const odds = res.success_odds ?? null;
  // Show the odds readout only when the outcome is actually uncertain (competitive).
  const hasRisk = !!odds && Object.entries(odds).some(([k, v]) => k !== "full" && v > 0.0005);

  // An ill-suited actor (P1.2) — surface WHY the odds are shaky.
  const misfit = action.components.find(
    (c) => (c.type === "damage" || c.type === "dot") && c.aptitude && c.aptitude !== "fit",
  );
  const aptNote = misfit
    ? `${misfit.aptitude === "unfit" ? "Ill-suited" : "Improvised"}${misfit.apt_basis ? ` — ${misfit.apt_basis}` : ""}`
    : null;

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

        {hasRisk && odds && (
          <div className="mt-3">
            <div className="mb-1 flex items-center gap-2 text-xs text-zinc-400">
              <span>Success odds</span>
              {aptNote && <span className="text-amber-400">⚠ {aptNote}</span>}
            </div>
            <div className="flex h-2 w-full overflow-hidden rounded-full bg-zinc-800">
              {ODDS_TIERS.map(([key, bar]) => {
                const pct = (odds[key] ?? 0) * 100;
                return pct > 0 ? (
                  <div key={key} className={bar} style={{ width: `${pct}%` }} />
                ) : null;
              })}
            </div>
            <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs">
              {ODDS_TIERS.map(([key, , label, text]) => {
                const pct = Math.round((odds[key] ?? 0) * 100);
                return pct > 0 ? (
                  <span key={key} className={text}>
                    {label} {pct}%
                  </span>
                ) : null;
              })}
            </div>
          </div>
        )}
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
