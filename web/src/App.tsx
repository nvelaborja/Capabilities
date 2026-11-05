import { useEffect, useMemo, useState } from "react";

import { api } from "./api/client";
import type { GraphResponse, Profile, SelectionRequest } from "./api/types";
import { GraphView } from "./graph/GraphView";
import { Legend } from "./legend/Legend";
import { ThemeSwitch } from "./state/ThemeSwitch";
import { useTheme } from "./state/theme";
import { useExplore } from "./state/useExplore";

type Loaded<T> = { status: "loading" } | { status: "ready"; value: T } | { status: "failed"; error: string };

function readPreset(): string | null {
  return new URLSearchParams(window.location.search).get("preset");
}

export function App() {
  const [graph, setGraph] = useState<Loaded<GraphResponse>>({ status: "loading" });
  const [profiles, setProfiles] = useState<Profile[]>([]);
  // The preset picker arrives in the next phase; until then, ?preset=<id> in the URL chooses one.
  const [preset] = useState(readPreset);
  const selection = useMemo<SelectionRequest>(() => ({ profile: preset }), [preset]);
  const explore = useExplore(selection);
  const { preference, choose, theme } = useTheme();

  useEffect(() => {
    const controller = new AbortController();
    api
      .graph([], controller.signal)
      .then((value) => setGraph({ status: "ready", value }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setGraph({ status: "failed", error: String(error) });
      });
    api
      .profiles(controller.signal)
      .then(setProfiles)
      .catch(() => {});
    return () => controller.abort();
  }, []);

  const presetLabel = profiles.find((profile) => profile.id === preset)?.label;

  return (
    <div className="app">
      <header className="app-header">
        <h1>Capabilities</h1>
        <span className="app-tagline">What it takes to make things, and what else was within reach.</span>
        <span className="app-context" aria-live="polite">
          {explore.error ? <span className="error">Couldn't update results.</span> : presetLabel ? `Showing: ${presetLabel}` : "Nothing selected"}
        </span>
        <ThemeSwitch preference={preference} onChoose={choose} />
      </header>
      <main className="app-graph">
        {graph.status === "ready" && <GraphView graph={graph.value} explore={explore.data} theme={theme} />}
        {graph.status === "loading" && <p className="notice">Loading the graph…</p>}
        {graph.status === "failed" && (
          <div className="notice" role="alert">
            <strong>Can't reach the Capabilities API.</strong>
            <span>
              Start it with <code>uv run capabilities serve</code>, then reload this page.
            </span>
          </div>
        )}
        <Legend />
      </main>
    </div>
  );
}
