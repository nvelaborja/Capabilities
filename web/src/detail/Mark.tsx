import type { Tri } from "../api/types";
import { MARKS } from "./marks";

export function Mark({ tri }: { tri: Tri }) {
  const mark = MARKS[tri];
  return (
    <span className={`mark mark-${tri}`} role="img" aria-label={mark.label} title={mark.label}>
      {mark.glyph}
    </span>
  );
}
