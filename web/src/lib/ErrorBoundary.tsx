import { Component, type ReactNode } from "react";

interface ErrorBoundaryProps {
  /** What to show instead of the children once they fail to render, or to load when lazy. */
  fallback: ReactNode;
  children: ReactNode;
}

/** Keeps a failing part of the page from blanking the whole app: React unmounts everything above an uncaught error. */
export class ErrorBoundary extends Component<ErrorBoundaryProps, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}
