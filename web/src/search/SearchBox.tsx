import { useEffect, useId, useMemo, useRef, useState } from "react";

import { TYPE_ICONS } from "../graph/styles";
import { kindName } from "../detail/marks";
import { search, type SearchEntry } from "./match";
import "./search.css";

interface SearchBoxProps {
  entries: readonly SearchEntry[];
  onChoose: (entry: SearchEntry) => void;
}

/**
 * Find any thing or action by name (design doc: search). Choosing one opens its details and centres it on the graph;
 * an action not on the graph yet is added to it. "/" jumps here from anywhere except a text field.
 */
export function SearchBox({ entries, onChoose }: SearchBoxProps) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listId = useId();
  const results = useMemo(() => search(entries, query), [entries, query]);
  const showing = open && query.trim().length > 0;

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing = target && (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.isContentEditable);
      if (event.key === "/" && !typing && !event.metaKey && !event.ctrlKey) {
        event.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const choose = (entry: SearchEntry | undefined) => {
    if (!entry) return;
    onChoose(entry);
    setQuery("");
    setOpen(false);
    inputRef.current?.blur();
  };

  return (
    <div className="search-box">
      <input
        ref={inputRef}
        type="search"
        role="combobox"
        aria-label="Search things and actions"
        aria-expanded={showing}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={showing && results[active] ? `${listId}-${active}` : undefined}
        placeholder="Search things and actions  ( / )"
        value={query}
        onChange={(event) => {
          setQuery(event.target.value);
          setActive(0);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setActive((index) => Math.min(index + 1, results.length - 1));
          } else if (event.key === "ArrowUp") {
            event.preventDefault();
            setActive((index) => Math.max(index - 1, 0));
          } else if (event.key === "Enter") {
            event.preventDefault();
            choose(results[active]);
          } else if (event.key === "Escape") {
            setQuery("");
            setOpen(false);
          }
        }}
      />
      {showing && (
        <ul id={listId} role="listbox" className="search-results" aria-label="Matches">
          {results.length === 0 && <li className="search-empty">No matches</li>}
          {results.map((entry, index) => (
            <li
              key={entry.id}
              id={`${listId}-${index}`}
              role="option"
              aria-selected={index === active}
              className="search-result"
              // mousedown, not click: the input's blur would close the list before a click lands.
              onMouseDown={(event) => {
                event.preventDefault();
                choose(entry);
              }}
              onMouseEnter={() => setActive(index)}
            >
              <span aria-hidden="true">{TYPE_ICONS[entry.kind as keyof typeof TYPE_ICONS] ?? "•"}</span>
              <span className="search-label">{entry.label}</span>
              <span className="search-kind">{entry.drawn ? kindName(entry.kind) : "Action · adds to graph"}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
