import { Fragment, type ReactNode, useState } from "react";

import { bound, summaryLabel } from "../lib/bounded";

interface BoundedListProps<T> {
  items: readonly T[];
  kindOf: (item: T) => string;
  keyOf: (item: T) => string;
  /** Renders one <li>. */
  render: (item: T) => ReactNode;
  className?: string;
}

/**
 * The top N items (already ranked by the caller), then one button per kind for the rest ("6 other tools and
 * products"), each expanding in place, and "Show all" when there are several kinds (ADR 0020).
 */
export function BoundedList<T>({ items, kindOf, keyOf, render, className }: BoundedListProps<T>) {
  const [opened, setOpened] = useState<ReadonlySet<string>>(new Set());
  const [all, setAll] = useState(false);
  const { shown, hidden } = bound(items, kindOf);
  const closed = all ? [] : hidden.filter((group) => !opened.has(group.kind));
  const visible = all ? items : [...shown, ...hidden.filter((group) => opened.has(group.kind)).flatMap((group) => group.items)];

  return (
    <>
      <ul className={className}>{visible.map((item) => <Fragment key={keyOf(item)}>{render(item)}</Fragment>)}</ul>
      {closed.length > 0 && (
        <div className="bounded-more">
          {closed.map((group) => (
            <button key={group.kind} type="button" className="more-button" onClick={() => setOpened(new Set([...opened, group.kind]))}>
              {summaryLabel(group.kind, group.items.length)}
            </button>
          ))}
          {closed.length > 1 && (
            <button type="button" className="link-button" onClick={() => setAll(true)}>
              Show all
            </button>
          )}
        </div>
      )}
    </>
  );
}
