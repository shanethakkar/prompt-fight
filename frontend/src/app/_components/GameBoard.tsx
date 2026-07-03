"use client";

import { useState } from "react";
import * as api from "@/lib/api";
import type { GameState, JudgeResponse, JudgedAction, MatchConfig, ResolveResult, Side } from "@/lib/types";
import type { Phase } from "@/lib/game";
import { StartScreen } from "./StartScreen";
import { HandoffScreen } from "./HandoffScreen";
import { PromptPanel } from "./PromptPanel";
import { CostPreview } from "./CostPreview";
import { PlayerStatus } from "./PlayerStatus";
import { PlaybackLog } from "./PlaybackLog";
import { VictoryScreen } from "./VictoryScreen";

export default function GameBoard() {
  const [phase, setPhase] = useState<Phase>("start");
  const [matchId, setMatchId] = useState("");
  const [state, setState] = useState<GameState | null>(null);
  const [config, setConfig] = useState<MatchConfig | null>(null);
  const [active, setActive] = useState<Side>("p1");
  const [confirmed, setConfirmed] = useState<{ p1?: JudgedAction; p2?: JudgedAction }>({});
  const [rewritesLeft, setRewritesLeft] = useState(0);
  const [preview, setPreview] = useState<JudgeResponse | null>(null);
  const [preStateForPlayback, setPreState] = useState<GameState | null>(null);
  const [lastResult, setLastResult] = useState<ResolveResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [inputError, setInputError] = useState<string | null>(null);

  async function startMatch(p1Name: string, p2Name: string) {
    setBusy(true);
    setInputError(null);
    try {
      const r = await api.newMatch(p1Name, p2Name);
      setMatchId(r.match_id);
      setState(r.state);
      setConfig(r.config);
      setConfirmed({});
      setActive("p1");
      setRewritesLeft(r.config.rewrites_per_turn);
      setPreview(null);
      setLastResult(null);
      setPhase("handoff");
    } catch {
      setInputError("Couldn't reach the backend. Is it running on :8000?");
    } finally {
      setBusy(false);
    }
  }

  function handoffReady() {
    setInputError(null);
    setPreview(null);
    setPhase("input");
  }

  async function submitPrompt(prompt: string) {
    if (!state || !config) return;
    setBusy(true);
    setInputError(null);
    try {
      const p = state[active];
      const res = await api.judge({
        prompt,
        player: { mana: p.mana, cooldowns: p.cooldowns },
        match_id: matchId,
        rewrites_remaining: rewritesLeft,
      });
      setRewritesLeft(res.rewrites_remaining);
      if (res.error === "moderation") {
        setInputError(res.message ?? "Try a different attack.");
      } else {
        setPreview(res);
        setPhase("preview");
      }
    } catch {
      setInputError("The judge hiccuped. Try again.");
    } finally {
      setBusy(false);
    }
  }

  function confirmAction() {
    if (!preview?.action || !config) return;
    const action = preview.action;
    if (active === "p1") {
      setConfirmed((c) => ({ ...c, p1: action }));
      setActive("p2");
      setRewritesLeft(config.rewrites_per_turn);
      setPreview(null);
      setPhase("handoff");
    } else {
      const p1 = confirmed.p1!;
      setConfirmed({ p1, p2: action });
      void resolveTurn(p1, action);
    }
  }

  async function resolveTurn(p1Action: JudgedAction, p2Action: JudgedAction) {
    if (!state) return;
    setPreState(state);
    setPhase("resolving");
    try {
      const result = await api.resolve({
        match_id: matchId,
        state,
        p1_action: p1Action,
        p2_action: p2Action,
      });
      setLastResult(result);
      setPhase("playback");
    } catch {
      setInputError("Resolve failed. Try again.");
      setPhase("preview");
    }
  }

  function rewriteAction() {
    setPreview(null);
    setPhase("input");
  }

  function playbackDone() {
    if (!lastResult || !config) return;
    setState(lastResult.state);
    if (lastResult.match_over) {
      setPhase("gameover");
    } else {
      setActive("p1");
      setRewritesLeft(config.rewrites_per_turn);
      setConfirmed({});
      setPreview(null);
      setPhase("handoff");
    }
  }

  const showBoard = state && config && (phase === "handoff" || phase === "input" || phase === "preview");

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-zinc-950 px-4 py-10 font-sans text-zinc-100">
      {phase === "start" && <StartScreen onStart={startMatch} busy={busy} />}
      {phase === "start" && inputError && <div className="text-sm text-rose-400">{inputError}</div>}

      {showBoard && state && config && (
        <div className="flex w-full max-w-lg flex-col gap-5">
          <div className="text-center text-xs uppercase tracking-widest text-zinc-500">
            Turn {state.turn} / {config.max_turns}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <PlayerStatus player={state.p1} config={config} active={active === "p1" && phase !== "handoff"} />
            <PlayerStatus player={state.p2} config={config} active={active === "p2" && phase !== "handoff"} />
          </div>
          <div className="flex flex-col items-center">
            {phase === "handoff" && <HandoffScreen name={state[active].name} onReady={handoffReady} />}
            {phase === "input" && (
              <PromptPanel
                name={state[active].name}
                mana={state[active].mana}
                error={inputError}
                busy={busy}
                onSubmit={submitPrompt}
              />
            )}
            {phase === "preview" && preview && (
              <CostPreview
                res={preview}
                rewritesRemaining={rewritesLeft}
                onConfirm={confirmAction}
                onRewrite={rewriteAction}
              />
            )}
          </div>
        </div>
      )}

      {phase === "resolving" && <div className="text-lg text-zinc-400">Resolving…</div>}

      {phase === "playback" && preStateForPlayback && lastResult && config && (
        <PlaybackLog
          preState={preStateForPlayback}
          result={lastResult}
          config={config}
          onDone={playbackDone}
        />
      )}

      {phase === "gameover" && state && lastResult && (
        <VictoryScreen result={lastResult} finalState={state} onPlayAgain={() => startMatch(state.p1.name, state.p2.name)} />
      )}
    </main>
  );
}
