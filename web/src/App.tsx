import { useCallback, useEffect, useMemo, useReducer, useState } from "react";

import { api } from "./api/client";
import type { GraphResponse, Profile } from "./api/types";
import { createCatalog } from "./catalog";
import { DetailPane } from "./detail/DetailPane";
import { edgeSubject } from "./detail/subjects";
import { type GraphFocus, GraphView } from "./graph/GraphView";
import { Splitter } from "./layout/Splitter";
import { usePaneSizes } from "./layout/usePaneSizes";
import { Legend } from "./legend/Legend";
import { ConfirmDialog } from "./panes/ConfirmDialog";
import { SidePane } from "./panes/SidePane";
import { searchIndex, type SearchEntry } from "./search/match";
import { SearchBox } from "./search/SearchBox";
import { isEdited, toRequest } from "./state/selection";
import { ThemeSwitch } from "./state/ThemeSwitch";
import { useTheme } from "./state/theme";
import { current, trailReducer } from "./state/trail";
import { decodeSelection, encodeSelection } from "./state/url";
import { useExplore } from "./state/useExplore";
import { usePresetItems } from "./state/usePresetItems";
import { useSelectionHistory } from "./state/useSelectionHistory";

type Loaded<T> = { status: "loading" } | { status: "ready"; value: T } | { status: "failed"; error: string };

/** Actions in the link that the graph doesn't draw by default ("cut:limestone") are drawn from the start. */
function linkedActions(): string[] {
  return decodeSelection(window.location.search).added.filter((item) => item.includes(":"));
}

export function App() {
  const [graph, setGraph] = useState<Loaded<GraphResponse>>({ status: "loading" });
  const [graphActions, setGraphActions] = useState<string[]>(linkedActions);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const { selection, canUndo, canRedo, dispatch } = useSelectionHistory();
  const presetItems = usePresetItems(selection.preset);
  const request = useMemo(() => toRequest(selection), [selection]);
  const explore = useExplore(request);
  const { preference, choose, theme } = useTheme();
  const { ref: appRef, layout } = usePaneSizes(encodeSelection(selection));
  const [trail, navigate] = useReducer(trailReducer, []);
  const [centerSeq, setCenterSeq] = useState({ center: false, seq: 0 });
  const [isolated, setIsolated] = useState<string | null>(null);
  // undefined: no confirmation pending. null or an id: the preset waiting to replace an edited selection.
  const [pendingPreset, setPendingPreset] = useState<string | null | undefined>(undefined);

  const actionsKey = graphActions.join(",");
  useEffect(() => {
    const controller = new AbortController();
    // The graph already on screen stays up while a larger one (with a new action) loads.
    api
      .graph(actionsKey ? actionsKey.split(",") : [], controller.signal)
      .then((value) => setGraph({ status: "ready", value }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setGraph((previous) => (previous.status === "ready" ? previous : { status: "failed", error: String(error) }));
      });
    return () => controller.abort();
  }, [actionsKey]);

  useEffect(() => {
    const controller = new AbortController();
    api
      .profiles(controller.signal)
      .then(setProfiles)
      .catch(() => {});
    return () => controller.abort();
  }, []);

  const loaded = graph.status === "ready" ? graph.value : null;
  const catalog = useMemo(() => (loaded ? createCatalog(loaded) : null), [loaded]);
  const entries = useMemo(() => (loaded ? searchIndex(loaded) : []), [loaded]);
  const shown = current(trail);
  const focus: GraphFocus = useMemo(() => ({ id: shown, ...centerSeq }), [shown, centerSeq]);

  /** Open a node's details from the graph, a list or search; `center` also brings it into view. */
  const open = useCallback((id: string | null, center: boolean) => {
    navigate(id ? { type: "open", id } : { type: "close" });
    setCenterSeq((previous) => ({ center, seq: previous.seq + 1 }));
  }, []);
  const onSelectNode = useCallback((id: string | null) => open(id, false), [open]);
  const onSelectEdge = useCallback((source: string, target: string) => open(edgeSubject(source, target), false), [open]);
  const drill = (id: string) => {
    navigate({ type: "drill", id });
    setCenterSeq((previous) => ({ center: true, seq: previous.seq + 1 }));
  };
  const back = (index: number) => {
    navigate({ type: "back", index });
    setCenterSeq((previous) => ({ center: true, seq: previous.seq + 1 }));
  };
  const chooseResult = (entry: SearchEntry) => {
    if (!entry.drawn) setGraphActions((actions) => [...new Set([...actions, entry.id])].sort());
    open(entry.id, true);
  };

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      // A dialog handles its own Escape; otherwise Escape closes the details.
      if (event.key !== "Escape" || document.querySelector("dialog[open]")) return;
      const target = event.target as HTMLElement | null;
      if (target?.tagName === "INPUT") return;
      navigate({ type: "close" });
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

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
    <div ref={appRef} style={layout.style} className={`app${shown ? " has-detail" : ""}${layout.sizes.selected ? " selected-sized" : ""}`}>
      <header className="app-header">
        <h1>Capabilities</h1>
        <span className="app-tagline">What it takes to make things, and what else was within reach.</span>
        <SearchBox entries={entries} onChoose={chooseResult} />
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
      {shown && catalog && <Splitter pane="detail" layout={layout} />}
      {shown && catalog && (
        <DetailPane
          trail={trail}
          catalog={catalog}
          explore={explore.data}
          selection={request}
          isolated={isolated}
          onDrill={drill}
          onBack={back}
          onClose={() => open(null, false)}
          onAdd={add}
          onRemove={remove}
          onIsolate={setIsolated}
        />
      )}
      <main className="app-graph">
        {loaded && (
          <GraphView
            graph={loaded}
            explore={explore.data}
            theme={theme}
            focus={focus}
            isolated={isolated}
            onSelectNode={onSelectNode}
            onSelectEdge={onSelectEdge}
            onShowWholeGraph={() => setIsolated(null)}
            toolbarExtra={<Legend />}
          />
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
      </main>
      {catalog && <Splitter pane="side" layout={layout} />}
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
          onPick={(id) => open(id, true)}
          splitter={<Splitter pane="selected" layout={layout} />}
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
