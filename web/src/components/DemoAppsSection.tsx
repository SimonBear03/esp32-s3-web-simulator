// SPDX-License-Identifier: GPL-2.0-only

import { ExternalLink, Gamepad2, Play } from "lucide-react";

import type { DemoAppsController } from "../hooks/useDemoApps";
import type { DemoApp } from "../lib/types";

interface DemoAppsSectionProps {
  demos: DemoAppsController;
  onRun: (demo: DemoApp) => Promise<void>;
  sessionActive: boolean;
  sessionStarting: boolean;
}

export function DemoAppsSection({
  demos,
  onRun,
  sessionActive,
  sessionStarting,
}: DemoAppsSectionProps) {
  return (
    <section className="rail-section demo-apps-section">
      <div className="rail-heading">Try a demo</div>
      {demos.loading ? <p className="rail-empty">Loading curated demos…</p> : null}
      {demos.error ? (
        <p className="rail-empty" role="alert">
          {demos.error}
        </p>
      ) : null}
      {demos.apps.map((demo) => (
        <article className="demo-app" key={demo.id}>
          <div className="demo-app-title">
            <Gamepad2 aria-hidden="true" size={17} />
            <div>
              <strong>{demo.name}</strong>
              <span>{demo.description}</span>
            </div>
          </div>
          <div className="demo-app-actions">
            <button
              className="demo-run-button"
              disabled={sessionActive || sessionStarting}
              onClick={() => void onRun(demo)}
              type="button"
            >
              <Play aria-hidden="true" size={13} fill="currentColor" />
              {sessionStarting ? "Starting…" : "Run demo"}
            </button>
            <div className="demo-app-links">
              <a href={demo.source_url} rel="noreferrer" target="_blank">
                Source <ExternalLink aria-hidden="true" size={10} />
              </a>
              <a href={demo.license_url} rel="noreferrer" target="_blank">
                {demo.license} <ExternalLink aria-hidden="true" size={10} />
              </a>
              <a href={demo.notices_url} rel="noreferrer" target="_blank">
                Notices <ExternalLink aria-hidden="true" size={10} />
              </a>
            </div>
          </div>
        </article>
      ))}
    </section>
  );
}
