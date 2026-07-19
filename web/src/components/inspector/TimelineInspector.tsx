// SPDX-License-Identifier: GPL-2.0-only

import { Activity, Download, RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";

import {
  diagnosticsUrl,
  getSessionEvents,
  replaySession,
} from "../../lib/api";
import type {
  ReplayStatus,
  SessionEvent,
  SimulationSession,
} from "../../lib/types";

interface TimelineInspectorProps {
  session: SimulationSession | null;
}

function eventSummary(event: SessionEvent): string {
  if (event.category === "peripheral" && typeof event.data.detail === "string") {
    return event.data.detail || String(event.data.trace_event ?? "worker trace");
  }
  if (event.type === "input.key") {
    return `${String(event.data.key)} · ${event.data.pressed ? "down" : "up"}`;
  }
  if (event.type === "input.button") {
    return `button ${String(event.data.button).toUpperCase()} · ${
      event.data.pressed ? "down" : "up"
    }`;
  }
  if (event.type === "input.serial") {
    return `${String(event.data.byte_count)} UART bytes · content redacted`;
  }
  if (event.type === "input.power") {
    return `${String(event.data.battery_mv)} mV battery`;
  }
  if (event.type === "input.imu") return "accelerometer + gyroscope sample";
  if (event.type.startsWith("replay.")) {
    const count = event.data.action_count;
    return typeof count === "number" ? `${count} external actions` : "replay state";
  }
  if (typeof event.data.exit_code === "number") {
    return `exit ${event.data.exit_code}`;
  }
  return event.source;
}

function eventTitle(type: string): string {
  return type
    .split(".")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" · ");
}

export function TimelineInspector({ session }: TimelineInspectorProps) {
  const [events, setEvents] = useState<SessionEvent[]>([]);
  const [eventsDropped, setEventsDropped] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [replay, setReplay] = useState<ReplayStatus | null>(null);
  const [replayBusy, setReplayBusy] = useState(false);

  useEffect(() => {
    setEvents([]);
    setEventsDropped(0);
    setError(null);
    setReplay(null);
    if (!session) return;

    let current = true;
    let cursor = 0;
    let recentEvents: SessionEvent[] = [];
    let refreshing = false;
    const refresh = async () => {
      if (refreshing) return;
      refreshing = true;
      try {
        for (let pageIndex = 0; pageIndex < 10; pageIndex += 1) {
          const page = await getSessionEvents(session.id, cursor, 500);
          if (!current) return;
          if (page.cursor_truncated) recentEvents = [];
          cursor = page.next_after;
          recentEvents = [...recentEvents, ...page.events].slice(-200);
          setEvents(recentEvents);
          setEventsDropped(page.events_dropped);
          setError(null);
          if (page.events.length < 500) break;
        }
      } catch (refreshError: unknown) {
        if (current) {
          setError(
            refreshError instanceof Error
              ? refreshError.message
              : "Timeline unavailable",
          );
        }
      } finally {
        refreshing = false;
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 1000);
    return () => {
      current = false;
      window.clearInterval(timer);
    };
  }, [session?.id]);

  useEffect(() => {
    if (
      session &&
      ["running", "completed", "failed", "cancelled"].includes(
        session.replay.status,
      )
    ) {
      setReplay(null);
    }
  }, [session?.generation, session?.replay.status]);

  if (!session) {
    return (
      <div className="inspector-section empty-inspector">
        <Activity size={28} />
        <strong>No session timeline</strong>
        <p>Start firmware to capture accepted inputs, controls, and worker state.</p>
      </div>
    );
  }

  const replayState = replay?.status ?? session.replay.status;
  const sessionId = session.id;
  const actionCount = session.recording.replayable_action_count;
  const replayDisabled =
    replayBusy ||
    replayState === "queued" ||
    replayState === "running" ||
    actionCount === 0 ||
    session.recording.replayable_actions_dropped > 0 ||
    !["running", "paused"].includes(session.state);

  async function beginReplay() {
    setReplayBusy(true);
    setError(null);
    try {
      setReplay(await replaySession(sessionId));
    } catch (replayError) {
      setError(
        replayError instanceof Error ? replayError.message : "Replay unavailable",
      );
    } finally {
      setReplayBusy(false);
    }
  }

  return (
    <div className="inspector-section timeline-inspector">
      <div className="inspector-title timeline-title">
        <Activity size={15} />
        <span>Session timeline</span>
        <span className="timeline-generation">GEN {session.generation}</span>
      </div>

      <div className="timeline-actions">
        <button
          className="secondary-button"
          disabled={replayDisabled}
          onClick={() => void beginReplay()}
          type="button"
        >
          <RotateCcw size={13} />
          {replayState === "queued" || replayState === "running"
            ? "Replaying…"
            : "Replay input"}
        </button>
        <a
          className="secondary-button diagnostics-link"
          download
          href={diagnosticsUrl(sessionId)}
        >
          <Download size={13} />
          Diagnostics
        </a>
      </div>

      <p className="timeline-contract">
        Replay restores the original flash and NVS baseline, then reapplies accepted
        external input. Diagnostics exclude firmware and serial contents.
      </p>

      <div className="timeline-stats" aria-label="Recording status">
        <span>{events.length} visible</span>
        <span>{session.recording.trace_events_recorded} traced</span>
        <span>{actionCount} replayable</span>
        <span data-warning={eventsDropped > 0}>
          {eventsDropped > 0
            ? `${eventsDropped} history dropped`
            : `${session.recording.trace_events_dropped} trace sampled`}
        </span>
      </div>

      {error ? <div className="debug-error" role="alert">{error}</div> : null}
      {replayState === "failed" && session.replay.error ? (
        <div className="debug-error" role="alert">{session.replay.error}</div>
      ) : null}

      <ol className="timeline-list" aria-label="Recorded session events">
        {events.length ? (
          [...events].reverse().map((event) => (
            <li key={event.sequence}>
              <span className="timeline-marker" data-category={event.category} />
              <div>
                <div className="timeline-event-heading">
                  <strong>{eventTitle(event.type)}</strong>
                  <time>G{event.generation} +{(event.offset_ms / 1000).toFixed(3)}s</time>
                </div>
                <p>{eventSummary(event)}</p>
              </div>
            </li>
          ))
        ) : (
          <li className="timeline-empty">Waiting for the first accepted event…</li>
        )}
      </ol>
    </div>
  );
}
