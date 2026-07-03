"use client";

import { useState, type ReactNode } from "react";
import type { Side, Unit } from "@/lib/types";
import { capitalize, elementColor, elementIcon, pct, statusChips } from "@/lib/game";
import { Chips } from "./Chips";

function MiniChips({ items, tone }: { items: string[]; tone: string }) {
  return (
    <div className="flex flex-wrap gap-1">
      {items.map((t, i) => (
        <span key={i} className={`rounded px-1.5 py-0.5 text-[10px] ${tone}`}>
          {t}
        </span>
      ))}
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex gap-2 text-xs">
      <span className="w-14 shrink-0 text-zinc-500">{label}</span>
      <div className="min-w-0 flex-1 text-zinc-300">{children}</div>
    </div>
  );
}

/** The floating detail card for one unit: vitals, weapon, tags, items, modifiers. */
export function UnitInspector({ unit, side }: { unit: Unit; side: Side }) {
  const mods = statusChips(unit); // effects + barriers, already toned
  const empty =
    !unit.weapon && unit.tags.length === 0 && unit.items.length === 0 && mods.length === 0;
  return (
    <div
      role="tooltip"
      className={`absolute top-full z-50 mt-1 w-56 rounded-lg border border-zinc-700 bg-zinc-900 p-3 shadow-xl ${
        side === "p2" ? "right-0" : "left-0"
      }`}
    >
      <div className="flex items-baseline justify-between">
        <span className="font-semibold text-zinc-100">{unit.name}</span>
        <span className="text-[10px] uppercase tracking-wide text-zinc-500">{unit.kind}</span>
      </div>

      <div className="mt-1.5">
        <div className="flex justify-between text-[10px] text-zinc-400">
          <span>HP</span>
          <span>
            {Math.max(0, unit.hp)}/{unit.max_hp}
          </span>
        </div>
        <div className="mt-0.5 h-1.5 w-full overflow-hidden rounded-full bg-zinc-800">
          <div
            className="h-full rounded-full bg-emerald-500/80"
            style={{ width: `${pct(unit.hp, unit.max_hp)}%` }}
          />
        </div>
      </div>

      <div className="mt-2 flex flex-col gap-1.5">
        {unit.weapon && (
          <Field label="Weapon">
            <span className={elementColor(unit.weapon.element)}>
              {elementIcon(unit.weapon.element)} {capitalize(unit.weapon.name)}
            </span>
            <span className="text-zinc-500">
              {" "}
              · {capitalize(unit.weapon.element)} {unit.weapon.power}
            </span>
          </Field>
        )}
        {unit.tags.length > 0 && (
          <Field label="Tags">
            <MiniChips items={unit.tags.map(capitalize)} tone="bg-violet-900/50 text-violet-300" />
          </Field>
        )}
        {unit.items.length > 0 && (
          <Field label="Items">
            <MiniChips items={unit.items} tone="bg-amber-900/40 text-amber-300" />
          </Field>
        )}
        {mods.length > 0 && (
          <Field label="Status">
            <Chips chips={mods} />
          </Field>
        )}
        {empty && <div className="text-[11px] text-zinc-500">No gear or active modifiers.</div>}
      </div>
    </div>
  );
}

/** Wraps a roster element as an accessible trigger that opens the inspector on
 *  hover / keyboard focus, and toggle-pins on click (Escape closes). */
export function UnitFrame({
  unit,
  side,
  children,
}: {
  unit: Unit;
  side: Side;
  children: ReactNode;
}) {
  const [hover, setHover] = useState(false);
  const [pinned, setPinned] = useState(false);
  const open = hover || pinned;
  return (
    <div
      className="relative"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <button
        type="button"
        aria-expanded={open}
        className="w-full cursor-help text-left"
        onClick={() => setPinned((p) => !p)}
        onFocus={() => setHover(true)}
        onBlur={() => setHover(false)}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            setPinned(false);
            e.currentTarget.blur();
          }
        }}
      >
        {children}
      </button>
      {open && <UnitInspector unit={unit} side={side} />}
    </div>
  );
}
