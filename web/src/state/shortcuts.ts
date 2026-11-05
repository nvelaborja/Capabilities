export interface KeyLike {
  key: string;
  metaKey: boolean;
  ctrlKey: boolean;
  shiftKey: boolean;
  target: EventTarget | null;
}

function isTyping(target: EventTarget | null): boolean {
  if (!target || typeof (target as HTMLElement).tagName !== "string") return false;
  const element = target as HTMLElement;
  return ["INPUT", "TEXTAREA", "SELECT"].includes(element.tagName) || element.isContentEditable === true;
}

/** ⌘Z / ⇧⌘Z on macOS, Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y elsewhere. Ignored while typing in a field. */
export function historyShortcut(event: KeyLike): "undo" | "redo" | null {
  if (!(event.metaKey || event.ctrlKey) || isTyping(event.target)) return null;
  const key = event.key.toLowerCase();
  if (key === "z") return event.shiftKey ? "redo" : "undo";
  if (key === "y" && event.ctrlKey) return "redo";
  return null;
}
