import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "./api/client";
import type { GraphResponse, Profile } from "./api/types";
import { createCatalog } from "./catalog";
import { type GraphFocus, GraphView } from "./graph/GraphView";
import { Legend } from "./legend/Legend";
import { ConfirmDialog } from "./panes/ConfirmDialog";
import { NodeCard } from "./panes/NodeCard";
import { SidePane } from "./panes/SidePane";
import { isEdited, toRequest } from "./state/selection";
import { ThemeSwitch } from "./state/ThemeSwitch";
import { useTheme } from "./state/theme";
import { useExplore } from "./state/useExplore";
import { usePresetItems } from "./state/usePresetItems";
import { useSelectionHistory } from "./state/useSelectionHistory";

type Loaded<T> = { status: "loading" } | { status: "ready"; value: T } | { status: "failed"; error: string };

const NO_FOCUS: GraphFocus = { id: null, center: false, seq: 0 };

export function App() {
  const [graph, setGraph] = useState<Loaded<GraphResponse>>({ status: "loading" });
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const { selection, canUndo, canRedo, dispatch } = useSelectionHistory();
  const presetItems = usePresetItems(selection.preset);
  const request = useMemo(() => toRequest(selection), [selection]);
  const explore = useExplore(request);
  const { preference, choose, theme } = useTheme();
  const [focus, setFocus] = useState<GraphFocus>(NO_FOCUS);
  // undefined: no confirmation pending. null or an id: the preset waiting to replace an edited selection.
  const [pendingPreset, setPendingPreset] = useState<string | null | undefined>(undefined);

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

  const catalog = useMemo(() => (graph.status === "ready" ? createCatalog(graph.value) : null), [graph]);
  const nodes = useMemo(
    () => new Map(graph.status === "ready" ? graph.value.nodes.map((node) => [node.id, node]) : []),
    [graph],
  );

  const showNode = useCallback((id: string | null, center: boolean) => {
    setFocus((previous) => ({ id, center, seq: previous.seq + 1 }));
  }, []);
  const onSelectNode = useCallback((id: string | null) => showNode(id, false), [showNode]);

  const choosePreset = (preset: string | null) => {
    if (preset === selection.preset) return;
    if (isEdited(selection)) setPendingPreset(preset);
    else dispatch({ type: "loadPreset", preset });
  };
  const add = (id: string) => dispatch({ type: "add", item: id, inPreset: presetItems.has(id) });
  const remove = (id: string) => dispatch({ type: "remove", item: id, inPreset: presetItems.has(id) });

  const pendingLabel = profiles.find((profile) => profile.id === pendingPreset)?.label ?? "an empty selection";
  const editedCount = selection.added.length + selection.removed.length;

  return (
    <div className="app">
      <header className="app-header">
        <h1>Capabilities</h1>
        <span className="app-tagline">What it takes to make things, and what else was within reach.</span>
        <span className="app-context" aria-live="polite">
          {explore.error && <span className="error">Couldn't update results.</span>}
        </span>
        <div className="history-buttons" role="group" aria-label="History">
          <button type="button" onClick={() => dispatch({ type: "undo" })} disabled={!canUndo} title="Undo (⌘Z / Ctrl+Z)">
            ↶ Undo
          </button>
          <button type="button" onClick={() => dispatch({ type: "redo" })} disabled={!canRedo} title="Redo (⇧⌘Z / Ctrl+Shift+Z)">
            ↷ Redo
          </button>
        </div>
        <ThemeSwitch preference={preference} onChoose={choose} />
      </header>
      <main className="app-graph">
        {graph.status === "ready" && (
          <GraphView graph={graph.value} explore={explore.data} theme={theme} focus={focus} onSelectNode={onSelectNode} />
        )}
        {graph.status === "loading" && <p className="notice">Loading the graph…</p>}
        {graph.status === "failed" && (
          <div className="notice" role="alert">
            <strong>Can't reach the Capabilities API.</strong>
            <span>
              Start it with <code>uv run capabilities serve</code>, then reload this page.
            </span>
          </div>
        )}
        {focus.id && catalog && (
          <NodeCard
            id={focus.id}
            node={nodes.get(focus.id)}
            catalog={catalog}
            explore={explore.data}
            onAdd={add}
            onRemove={remove}
            onClose={() => showNode(null, false)}
          />
        )}
        <Legend />
      </main>
      {catalog && (
        <SidePane
          profiles={profiles}
          preset={selection.preset}
          edited={isEdited(selection)}
          explore={explore.data}
          catalog={catalog}
          onChoosePreset={choosePreset}
          onClear={() => dispatch({ type: "clear" })}
          onRemove={remove}
          onPick={(id) => showNode(id, true)}
        />
      )}
      <ConfirmDialog
        open={pendingPreset !== undefined}
        title="Replace your selection?"
        message={`You've made ${editedCount} change${editedCount === 1 ? "" : "s"} to this preset. Switching to ${pendingLabel} replaces them. You can undo this.`}
        confirmLabel="Replace"
        onConfirm={() => {
          dispatch({ type: "loadPreset", preset: pendingPreset ?? null });
          setPendingPreset(undefined);
        }}
        onCancel={() => setPendingPreset(undefined)}
      />
    </div>
  );
}
