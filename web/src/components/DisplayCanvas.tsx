// SPDX-License-Identifier: GPL-2.0-only

import { useEffect, useRef, useState } from "react";

import { openSessionSocket } from "../lib/api";
import { paintFramebuffer, parseFramebufferPacket } from "../lib/framebuffer";

interface DisplayCanvasProps {
  sessionId: string | null;
  streamGeneration: number;
  width: number;
  height: number;
  boardLabel: string;
}

export function DisplayCanvas({
  sessionId,
  streamGeneration,
  width,
  height,
  boardLabel,
}: DisplayCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [hasFrame, setHasFrame] = useState(false);
  const [streamError, setStreamError] = useState(false);

  useEffect(() => {
    setHasFrame(false);
    setStreamError(false);
    if (!sessionId) return;

    let current = true;
    const socket = openSessionSocket(sessionId, "framebuffer");
    socket.binaryType = "arraybuffer";
    socket.addEventListener("message", (event: MessageEvent<ArrayBuffer>) => {
      if (!current) return;
      try {
        const frame = parseFramebufferPacket(event.data);
        if (canvasRef.current) paintFramebuffer(canvasRef.current, frame);
        setHasFrame(true);
      } catch {
        setStreamError(true);
      }
    });
    socket.addEventListener("error", () => {
      if (current) setStreamError(true);
    });
    return () => {
      current = false;
      socket.close();
    };
  }, [sessionId, streamGeneration]);

  return (
    <div className="display-surface" style={{ aspectRatio: `${width} / ${height}` }}>
      <canvas
        aria-label={`${boardLabel} ${width} by ${height} framebuffer`}
        className="framebuffer-canvas"
        data-visible={hasFrame}
        height={height}
        ref={canvasRef}
        width={width}
      />
      {!hasFrame ? (
        <div className="display-idle" aria-live="polite">
          <span className="idle-trace" aria-hidden="true" />
          <strong>{streamError ? "FRAME STREAM OFFLINE" : "AWAITING FIRMWARE"}</strong>
          <small>
            {width} × {height} · RGB24
          </small>
        </div>
      ) : null}
    </div>
  );
}
