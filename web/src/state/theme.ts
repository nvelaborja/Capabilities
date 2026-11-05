import { useEffect, useState } from "react";

export type ThemePreference = "system" | "light" | "dark";
export type Theme = "light" | "dark";

export const THEME_KEY = "capabilities.theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";

// Per-viewer convenience: storage can be unavailable (private windows), so failures fall back to the system theme.
export function readPreference(): ThemePreference {
  try {
    const stored = window.localStorage.getItem(THEME_KEY);
    return stored === "light" || stored === "dark" ? stored : "system";
  } catch {
    return "system";
  }
}

function savePreference(preference: ThemePreference): void {
  try {
    if (preference === "system") window.localStorage.removeItem(THEME_KEY);
    else window.localStorage.setItem(THEME_KEY, preference);
  } catch {
    // Remembering the theme is optional.
  }
}

/** theme.css switches on data-theme; without it, the system theme applies. */
export function applyPreference(preference: ThemePreference, root: HTMLElement = document.documentElement): void {
  if (preference === "system") delete root.dataset.theme;
  else root.dataset.theme = preference;
}

export function resolveTheme(preference: ThemePreference, systemIsDark: boolean): Theme {
  if (preference !== "system") return preference;
  return systemIsDark ? "dark" : "light";
}

/**
 * The viewer's theme choice and the theme actually showing. The attribute is set inside the click handler, before
 * React re-renders, so the graph reads the new colours when it restyles.
 */
export function useTheme() {
  const [preference, setPreference] = useState<ThemePreference>(readPreference);
  const [systemIsDark, setSystemIsDark] = useState(() => window.matchMedia(DARK_QUERY).matches);

  useEffect(() => {
    const query = window.matchMedia(DARK_QUERY);
    const onChange = (event: MediaQueryListEvent) => setSystemIsDark(event.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  const choose = (next: ThemePreference) => {
    applyPreference(next);
    savePreference(next);
    setPreference(next);
  };

  return { preference, choose, theme: resolveTheme(preference, systemIsDark) };
}
