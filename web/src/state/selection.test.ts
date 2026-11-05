import { describe, expect, it } from "vitest";

import { applyEdit, EMPTY, HISTORY_LIMIT, historyReducer, isEdited, type Selection, startHistory, toRequest } from "./selection";

const egypt: Selection = { preset: "egypt", added: [], removed: [] };

describe("applyEdit", () => {
  it("adds items outside the preset and removes preset items, keeping lists sorted", () => {
    const added = applyEdit(applyEdit(egypt, { type: "add", item: "steel", inPreset: false }), { type: "add", item: "hematite", inPreset: false });
    const removed = applyEdit(added, { type: "remove", item: "copper", inPreset: true });
    expect(removed).toEqual({ preset: "egypt", added: ["hematite", "steel"], removed: ["copper"] });
  });

  it("undoes its own edits rather than stacking opposites", () => {
    // given: a preset item removed, and an extra item added
    const edited = { preset: "egypt", added: ["steel"], removed: ["copper"] };
    // when: adding the preset item back and removing the extra one
    const back = applyEdit(applyEdit(edited, { type: "add", item: "copper", inPreset: true }), { type: "remove", item: "steel", inPreset: false });
    // then: the selection is the plain preset again
    expect(back).toEqual(egypt);
    expect(isEdited(back)).toBe(false);
  });

  it("loading a preset or clearing wipes the edits", () => {
    const edited = { preset: "egypt", added: ["steel"], removed: [] };
    expect(applyEdit(edited, { type: "loadPreset", preset: "rome" })).toEqual({ preset: "rome", added: [], removed: [] });
    expect(applyEdit(edited, { type: "clear" })).toEqual(EMPTY);
  });
});

describe("historyReducer", () => {
  it("undoes and redoes every edit", () => {
    let history = startHistory(egypt);
    history = historyReducer(history, { type: "add", item: "steel", inPreset: false });
    history = historyReducer(history, { type: "loadPreset", preset: null });
    history = historyReducer(history, { type: "undo" });
    expect(history.present).toEqual({ preset: "egypt", added: ["steel"], removed: [] });
    history = historyReducer(history, { type: "undo" });
    expect(history.present).toEqual(egypt);
    history = historyReducer(history, { type: "redo" });
    expect(history.present.added).toEqual(["steel"]);
  });

  it("drops the redo stack after a new edit", () => {
    let history = historyReducer(startHistory(egypt), { type: "add", item: "steel", inPreset: false });
    history = historyReducer(history, { type: "undo" });
    history = historyReducer(history, { type: "add", item: "tin", inPreset: false });
    expect(history.future).toHaveLength(0);
  });

  it("adds no step for edits that change nothing", () => {
    const history = startHistory(egypt);
    expect(historyReducer(history, { type: "loadPreset", preset: "egypt" })).toBe(history);
    expect(historyReducer(history, { type: "undo" })).toBe(history);
  });

  it(`keeps at most ${HISTORY_LIMIT} steps`, () => {
    let history = startHistory(EMPTY);
    for (let i = 0; i < HISTORY_LIMIT + 20; i++) {
      history = historyReducer(history, { type: "add", item: `item-${i}`, inPreset: false });
    }
    expect(history.past).toHaveLength(HISTORY_LIMIT);
  });
});

describe("toRequest", () => {
  it("maps onto the explore request", () => {
    expect(toRequest({ preset: "egypt", added: ["steel"], removed: ["copper"] })).toEqual({
      profile: "egypt",
      select: ["steel"],
      deselect: ["copper"],
    });
  });
});
