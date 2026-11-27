import { describe, expect, it } from "vitest";

import { REPOSITORY, reportUrl } from "./report";

const fields = (url: string) => Object.fromEntries(new URL(url).searchParams);

describe("report links", () => {
  it("open the report form on the project's repository, titled after the fact", () => {
    const url = reportUrl({ fact: "steel", kind: "node", label: "Steel" });
    expect(url.startsWith(`${REPOSITORY}/issues/new?`)).toBe(true);
    expect(fields(url)).toEqual({ template: "report.yml", title: "Report: Steel", fact: "steel", kind: "node" });
  });

  it("name a reference's citation and the agent run that proposed it", () => {
    const url = reportUrl({
      fact: "smelt-copper",
      kind: "reference",
      label: "Smelting copper: Craddock & Co. (1995)",
      reference: "Craddock, P. T. & Co. (1995). Early metal mining & production?",
      run: "routes-20261126-191441",
    });
    expect(fields(url)).toMatchObject({
      fact: "smelt-copper",
      reference: "Craddock, P. T. & Co. (1995). Early metal mining & production?",
      run: "routes-20261126-191441",
    });
  });

  it("leave out what isn't known", () => {
    expect(Object.keys(fields(reportUrl({ fact: "steel", kind: "node", label: "Steel" })))).not.toContain("run");
  });
});
