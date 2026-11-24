/** When an upstream snapshot was retrieved, as "22 Nov 2026", in UTC so it matches the manifest. */
export function retrievedOn(iso: string | null): string {
  if (!iso) return "an unknown date";
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}
