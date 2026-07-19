// SPDX-License-Identifier: GPL-2.0-only

import { useCallback, useEffect, useRef, useState } from "react";

import {
  controlSession,
  createSession,
  deleteSession,
  getSession,
  openSessionSocket,
  sendInput,
} from "../lib/api";
import type {
  BoardId,
  InputEvent,
  SimulationSession,
} from "../lib/types";

type InputEventWithoutSequence = InputEvent extends infer Event
  ? Event extends InputEvent
    ? Omit<Event, "sequence">
    : never
  : never;

export interface SimulatorSessionController {
  session: SimulationSession | null;
  busyAction: "start" | "pause" | "resume" | "reset" | "stop" | null;
  error: string | null;
  inputConnected: boolean;
  start: (boardId: BoardId, firmware: File) => Promise<boolean>;
  pause: () => Promise<void>;
  resume: () => Promise<void>;
  reset: () => Promise<void>;
  stop: () => Promise<void>;
  sendBoardInput: (event: InputEventWithoutSequence) => boolean;
  clearError: () => void;
}

const ACTIVE_STATES = new Set(["starting", "running", "paused"]);

function messageFromError(error: unknown): string {
  return error instanceof Error ? error.message : "The simulator request failed";
}

export function useSimulatorSession(): SimulatorSessionController {
  const [session, setSession] = useState<SimulationSession | null>(null);
  const [busyAction, setBusyAction] = useState<
    SimulatorSessionController["busyAction"]
  >(null);
  const [error, setError] = useState<string | null>(null);
  const [inputConnected, setInputConnected] = useState(false);
  const inputSocketRef = useRef<WebSocket | null>(null);
  const sequenceRef = useRef(0);

  useEffect(() => {
    if (!session || !ACTIVE_STATES.has(session.state)) {
      inputSocketRef.current?.close();
      inputSocketRef.current = null;
      setInputConnected(false);
      return;
    }

    const socket = openSessionSocket(session.id, "input");
    inputSocketRef.current = socket;
    socket.addEventListener("open", () => {
      if (inputSocketRef.current === socket) setInputConnected(true);
    });
    socket.addEventListener("close", () => {
      if (inputSocketRef.current === socket) setInputConnected(false);
    });
    socket.addEventListener("error", () => {
      if (inputSocketRef.current === socket) setInputConnected(false);
    });
    return () => {
      socket.close();
      if (inputSocketRef.current === socket) inputSocketRef.current = null;
    };
  }, [session?.id, session?.state]);

  useEffect(() => {
    if (!session || !ACTIVE_STATES.has(session.state)) return;
    const sessionId = session.id;
    let current = true;
    const timer = window.setInterval(() => {
      void getSession(sessionId)
        .then((next) => {
          if (current) setSession(next);
        })
        .catch((pollError: unknown) => {
          if (current) setError(messageFromError(pollError));
        });
    }, 1000);
    return () => {
      current = false;
      window.clearInterval(timer);
    };
  }, [session?.id, session?.state]);

  const runAction = useCallback(
    async (
      action: Exclude<SimulatorSessionController["busyAction"], "start" | null>,
      operation: (sessionId: string) => Promise<SimulationSession>,
    ) => {
      if (!session) return;
      setBusyAction(action);
      setError(null);
      try {
        setSession(await operation(session.id));
      } catch (actionError) {
        setError(messageFromError(actionError));
      } finally {
        setBusyAction(null);
      }
    },
    [session],
  );

  const start = useCallback(async (boardId: BoardId, firmware: File) => {
    setBusyAction("start");
    setError(null);
    try {
      setSession(await createSession(boardId, firmware));
      return true;
    } catch (startError) {
      setError(messageFromError(startError));
      return false;
    } finally {
      setBusyAction(null);
    }
  }, []);

  const pause = useCallback(
    () => runAction("pause", (sessionId) => controlSession(sessionId, "pause")),
    [runAction],
  );
  const resume = useCallback(
    () => runAction("resume", (sessionId) => controlSession(sessionId, "resume")),
    [runAction],
  );
  const reset = useCallback(
    () => runAction("reset", (sessionId) => controlSession(sessionId, "reset")),
    [runAction],
  );
  const stop = useCallback(
    () => runAction("stop", deleteSession),
    [runAction],
  );

  const sendBoardInput = useCallback(
    (event: InputEventWithoutSequence) => {
      sequenceRef.current += 1;
      return sendInput(inputSocketRef.current, {
        ...event,
        sequence: sequenceRef.current,
      } as InputEvent);
    },
    [],
  );

  return {
    session,
    busyAction,
    error,
    inputConnected,
    start,
    pause,
    resume,
    reset,
    stop,
    sendBoardInput,
    clearError: useCallback(() => setError(null), []),
  };
}
