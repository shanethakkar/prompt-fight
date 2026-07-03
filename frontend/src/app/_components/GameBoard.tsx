"use client";

import { useState } from "react";
import * as api from "@/lib/api";
import type {
  Action,
  GameState,
  JudgeResponse,
  LedgerEntry,
  MatchConfig,
  ResolveResult,
} from "@/lib/types";
import type { Phase } from "@/lib/game";
import { StartScreen } from "./StartScreen";
import { HandoffScreen } from "./HandoffScreen";
import { PromptPanel } from "./PromptPanel";
import { CostPreview } from "./CostPreview";
import { PlayerStatus } from "./PlayerStatus";
import { PlaybackLog } from "./PlaybackLog";
import { Ledger } from "./Ledger";
import { VictoryScreen } from "./VictoryScreen";

export default function GameBoard() {
  const [phase, setPhase] = useState<Phase>("start");
  const [matchId, setMatchId] = useState("");
  const [state, setState] = useState<GameState | null>(null);
  const [config, setConfig] = useState<MatchConfig | null>(null);
  const [rewritesLeft, setRewritesLeft] = useState(0);
  const [preview, setPreview] = useState<JudgeResponse | null>(null);
  const [preState, setPreState] = useState<GameState | null>(null);
  const [lastResult, setLastResult] = useState<ResolveResult | null>(null);
  const [ledger, setLedger] = useState<LedgerEntry[]>([]);
  const [busy, setBusy] = useState(false);
  const [inputError, setInputError] = useState<string | null>(null);
  const [sandbox, setSandbox] = useState(true);

  const activeSide = state?.active ?? "p1";
  const activePlayer = state ? state[activeSide] : null;

  async function startMatch(p1Name: string, p2Name: string, sb: boolean) {
    setBusy(true);
    setInputError(null);
    setSandbox(sb);
    try {
      const r = await api.newMatch(p1Name, p2Name);
      setMatchId(r.match_id);
      setState(r.state);
      setConfig(r.config);
      setRewritesLeft(r.config.rewrites_per_turn);
      setPreview(null);
      setLastResult(null);
      setLedger([]);
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
      const p = state[state.active];
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

  async function confirmAction() {
    if (!preview?.action || !state) return;
    await resolveTurn(preview.action);
  }

  async function resolveTurn(action: Action) {
    if (!state) return;
    setPreState(state);
    setPreview(null);
    setPhase("resolving");
    try {
      const result = await api.resolve({ match_id: matchId, state, action });
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
    // Record the just-committed turn (public beats only — no secrecy leak).
    if (preState) {
      setLedger((l) => [
        ...l,
        { round: preState.round, actor: preState.active, events: lastResult.events },
      ]);
    }
    setState(lastResult.state);
    if (lastResult.match_over) {
      setPhase("gameover");
    } else {
      setRewritesLeft(config.rewrites_per_turn);
      setPreview(null);
      setPhase("handoff");
    }
  }

  const showBoard =
    state && config && (phase === "handoff" || phase === "input" || phase === "preview");

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-zinc-950 px-4 py-10 font-sans text-zinc-100">
      {phase === "start" && <StartScreen onStart={startMatch} busy={busy} />}
      {phase === "start" && inputError && <div className="text-sm text-rose-400">{inputError}</div>}

      {showBoard && state && config && activePlayer && (
        <div className="flex w-full max-w-lg flex-col gap-5">
          <div className="text-center text-xs uppercase tracking-widest text-zinc-500">
            Round {state.round} / {config.max_turns}
            {sandbox && <span className="ml-2 text-amber-400">· sandbox</span>}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <PlayerStatus player={state.p1} config={config} active={activeSide === "p1" && phase !== "handoff"} />
            <PlayerStatus player={state.p2} config={config} active={activeSide === "p2" && phase !== "handoff"} />
          </div>
          <div className="flex flex-col items-center">
            {phase === "handoff" && <HandoffScreen name={activePlayer.name} onReady={handoffReady} />}
            {phase === "input" && (
              <PromptPanel
                name={activePlayer.name}
                mana={activePlayer.mana}
                error={inputError}
                busy={busy}
                onSubmit={submitPrompt}
              />
            )}
            {phase === "preview" && preview && (
              <CostPreview
                res={preview}
                rewritesRemaining={rewritesLeft}
                sandbox={sandbox}
                onConfirm={confirmAction}
                onRewrite={rewriteAction}
              />
            )}
          </div>
          <Ledger entries={ledger} names={{ p1: state.p1.name, p2: state.p2.name }} />
        </div>
      )}

      {phase === "resolving" && <div className="text-lg text-zinc-400">Resolving…</div>}

      {phase === "playback" && preState && lastResult && config && (
        <PlaybackLog preState={preState} result={lastResult} config={config} onDone={playbackDone} />
      )}

      {phase === "gameover" && state && lastResult && (
        <VictoryScreen
          result={lastResult}
          finalState={state}
          onPlayAgain={() => startMatch(state.p1.name, state.p2.name, sandbox)}
        />
      )}
    </main>
  );
}
