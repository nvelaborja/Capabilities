import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { ProfileDetail } from "../api/types";
import { profileItemId } from "./selection";

const NONE: ReadonlySet<string> = new Set();

export interface PresetProfile {
  /** The preset's profile, with its area and the sources found there; null with no preset, or while it loads. */
  profile: ProfileDetail | null;
  /** The items the preset starts with, so edits know whether an item comes from the preset. */
  items: ReadonlySet<string>;
}

/** The preset's own items, and the sources it had from the map (ADR 0052): removing one of those is an edit too. */
export function presetItemIds(profile: ProfileDetail): ReadonlySet<string> {
  const listed = profile.includes.map(profileItemId).filter((id): id is string => id !== null);
  const fromMap = (profile.map?.sources ?? []).filter((source) => source.from_map).map((source) => source.id);
  return new Set([...listed, ...fromMap]);
}

/** The preset's profile and the items it starts with. */
export function usePresetProfile(preset: string | null): PresetProfile {
  const [loaded, setLoaded] = useState<{ preset: string; profile: ProfileDetail } | null>(null);

  useEffect(() => {
    if (!preset) return;
    const controller = new AbortController();
    api
      .profile(preset, controller.signal)
      .then((profile) => setLoaded({ preset, profile }))
      .catch(() => {});
    return () => controller.abort();
  }, [preset]);

  if (!preset || loaded?.preset !== preset) return { profile: null, items: NONE };
  return { profile: loaded.profile, items: presetItemIds(loaded.profile) };
}
