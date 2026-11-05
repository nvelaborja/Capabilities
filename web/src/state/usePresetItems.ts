import { useEffect, useState } from "react";

import { api } from "../api/client";
import { profileItemId } from "./selection";

const NONE: ReadonlySet<string> = new Set();

/** The items a preset includes, so edits know whether an item comes from the preset. */
export function usePresetItems(preset: string | null): ReadonlySet<string> {
  const [loaded, setLoaded] = useState<{ preset: string; items: ReadonlySet<string> } | null>(null);

  useEffect(() => {
    if (!preset) return;
    const controller = new AbortController();
    api
      .profile(preset, controller.signal)
      .then((profile) => {
        const ids = profile.includes.map(profileItemId).filter((id): id is string => id !== null);
        setLoaded({ preset, items: new Set(ids) });
      })
      .catch(() => {});
    return () => controller.abort();
  }, [preset]);

  return preset && loaded?.preset === preset ? loaded.items : NONE;
}
