import type { ReactNode } from "react";

interface Crumb {
  id: string;
  label: string;
}

interface DetailShellProps {
  label: string;
  /** Earlier steps of the drill-down trail, each leading back. */
  crumbs: Crumb[];
  onBack: (index: number) => void;
  title: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
  onClose: () => void;
  /** Three columns, left to right like the graph (ADR 0025). */
  children: ReactNode;
}

/** The frame every detail view shares: breadcrumb and title on the left, actions and close on the right, columns below. */
export function DetailShell({ label, crumbs, onBack, title, meta, actions, onClose, children }: DetailShellProps) {
  return (
    <section className="detail-pane" aria-label={`${label} details`}>
      <header className="detail-bar">
        <div className="detail-title">
          {crumbs.length > 0 && (
            <nav className="breadcrumb" aria-label="Drill-down trail">
              <ol>
                {crumbs.map((crumb, index) => (
                  <li key={crumb.id}>
                    <button type="button" className="link-button" onClick={() => onBack(index)}>
                      {crumb.label}
                    </button>
                  </li>
                ))}
              </ol>
            </nav>
          )}
          <h2>{title}</h2>
          {meta && <p className="detail-meta">{meta}</p>}
        </div>
        <div className="detail-actions">
          {actions}
          <button type="button" className="icon-button" onClick={onClose} aria-label="Close details" title="Close (Esc)">
            ×
          </button>
        </div>
      </header>
      <div className="detail-columns">{children}</div>
    </section>
  );
}
