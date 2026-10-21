"use client";

// turn.ts: one voice question at a time. Each tap starts a new turn and cancels the one before it, so an answer that
// arrives late (say, after the connection comes back) is dropped and never spoken over the new one.
// Used by: features/l1/ask-voice.tsx, components/shell/ask-orb.tsx. Uses: nothing local.

// Config
const STEP_TIME_LIMIT_MS = 15000; // one request (hearing, answering or speaking) gives up after this long

export const CONNECTION_LOST = "Connection lost, sir. Ask again.";
export const OFFLINE = "You are offline, sir. Ask again when you are back.";

export type Turn = { signal: AbortSignal; isCurrent: () => boolean };
export type TurnKeeper = { current: AbortController | null };

/** Starts a new turn and cancels the one before it, with every request it still had running. */
export function startTurn(keeper: TurnKeeper): Turn {
  keeper.current?.abort();
  const controller = new AbortController();
  keeper.current = controller;
  return { signal: controller.signal, isCurrent: () => keeper.current === controller && !controller.signal.aborted };
}

/** Cancels the running turn, for a close or a stop. */
export function endTurn(keeper: TurnKeeper) {
  keeper.current?.abort();
  keeper.current = null;
}

/** The signal for one request: it ends when the turn is cancelled or the step runs past its time limit. */
export function stepSignal(turn: Turn): AbortSignal {
  return AbortSignal.any([turn.signal, AbortSignal.timeout(STEP_TIME_LIMIT_MS)]);
}

/** What to tell the person when a step fails: a lost connection reads differently from a brain that could not answer. */
export function failureNote(error: unknown, otherwise: string): string {
  const name = error instanceof Error ? error.name : "";
  // TimeoutError is the step's time limit; TypeError is how fetch reports a network that is gone.
  return isOffline() || name === "TimeoutError" || name === "TypeError" ? CONNECTION_LOST : otherwise;
}

/** The browser knows it has no network. A dropped connection it has not noticed yet is caught by the time limit. */
export const isOffline = () => typeof navigator !== "undefined" && navigator.onLine === false;
