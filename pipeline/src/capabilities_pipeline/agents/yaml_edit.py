"""Changing a curated file's references as text, so nothing else in the file moves (ADR 0049).

A YAML library that round-trips files would be simpler to call, but ruamel.yaml rewrote every flow mapping in all 54
route files (`{ role: tool }` to `{role: tool}`) on load and dump alone: a pull request adding one reference would
touch every requirement. So lines are inserted, and the file is parsed again to check that the only difference is the
one intended; an edit that would change anything else is refused.
"""

from __future__ import annotations

import copy
import json
import re

import yaml

# The order a reference's keys are written in, as the curated files have them (data-format.md).
KEYS = ("citation", "doi", "url", "supports", "quote", "status", "proposed_by")
ITEM = re.compile(r"^(\s*)- ")
# A word YAML reads as itself, written plain as the files write a status or an id; any other value is quoted.
PLAIN = re.compile(r"^[a-z][a-z0-9_-]*$")
NOT_PLAIN = {"yes", "no", "on", "off", "true", "false", "null", "y", "n"}


class EditError(Exception):
    """The edit can't be made, or wouldn't make only the change intended."""


def add_reference(text: str, reference: dict) -> str:
    """The file with `reference` appended to its top-level `references`."""
    lines = text.splitlines(keepends=True)
    start, end, indent = _references(lines)
    block = _item(reference, indent)
    if start is None:
        # No references yet: the list goes at the end of the file.
        new = text + ("" if text.endswith("\n") else "\n") + "references:\n" + block
    else:
        new = "".join(lines[:end]) + block + "".join(lines[end:])
    expected = yaml.safe_load(text)
    expected.setdefault("references", []).append(reference)
    return _checked(new, expected)


def quote_reference(text: str, index: int, fields: dict) -> str:
    """The file with `fields` (a quote, and who proposed it) added to its `index`th reference, which mustn't have them."""
    data = yaml.safe_load(text)
    references = data.get("references") or []
    if not 0 <= index < len(references):
        raise EditError(f"there is no reference {index + 1}: the file has {len(references)}")
    if present := [key for key in fields if key in references[index]]:
        raise EditError(f"reference {index + 1} already has {', '.join(present)}")
    lines = text.splitlines(keepends=True)
    start, end, indent = _references(lines)
    items = [i for i in range(start + 1, end) if (m := ITEM.match(lines[i])) and len(m.group(1)) == indent]
    item_end = items[index + 1] if index + 1 < len(items) else end
    last = max(i for i in range(items[index], item_end) if lines[i].strip() and not lines[i].lstrip().startswith("#"))
    status = next((i for i in range(items[index], last + 1) if re.match(rf"^\s{{{indent + 2}}}status:", lines[i])), None)
    # Who proposed it comes last, after the status; the rest before the status, as the files order a reference's keys.
    # Inserted from the bottom up, so the place found for the second is still right after the first.
    first = {key: value for key, value in fields.items() if key != "proposed_by"}
    late = {key: value for key, value in fields.items() if key == "proposed_by"}
    new_lines = list(lines)
    new_lines[last + 1:last + 1] = [_line(key, value, indent + 2) for key, value in late.items()]
    at = status if status is not None else last + 1
    new_lines[at:at] = [_line(key, value, indent + 2) for key, value in first.items()]
    expected = copy.deepcopy(data)
    expected["references"][index].update(fields)
    return _checked("".join(new_lines), expected)


def _references(lines: list[str]) -> tuple[int | None, int, int]:
    """Where the top-level `references` block starts and ends (the end is after its last item, before any blank lines
    or comments that follow it), and how far its items are indented."""
    start = next((i for i, line in enumerate(lines) if re.match(r"^references:\s*(#.*)?$", line)), None)
    if start is None:
        return None, len(lines), 2
    end = next((i for i in range(start + 1, len(lines)) if lines[i].strip() and not lines[i][0].isspace()
                and not lines[i].startswith(("-", "#"))), len(lines))
    while end > start + 1 and (not lines[end - 1].strip() or lines[end - 1].lstrip().startswith("#")):
        end -= 1
    first = next((ITEM.match(lines[i]) for i in range(start + 1, end) if ITEM.match(lines[i])), None)
    if first is None:
        raise EditError("the references block has no items to add to")
    if not lines[end - 1].endswith("\n"):
        lines[end - 1] += "\n"
    return start, end, len(first.group(1))


def _item(reference: dict, indent: int) -> str:
    keys = [key for key in KEYS if key in reference] + [key for key in reference if key not in KEYS]
    first, *rest = keys
    return (" " * indent + "- " + _line(first, reference[first], 0)
            + "".join(_line(key, reference[key], indent + 2) for key in rest))


def _line(key: str, value: str, indent: int) -> str:
    # JSON's string is a YAML double-quoted scalar: every character, quote and backslash written safely on one line.
    plain = PLAIN.match(value) and value not in NOT_PLAIN
    return f"{' ' * indent}{key}: {value if plain else json.dumps(value, ensure_ascii=False)}\n"


def _checked(new: str, expected: dict) -> str:
    try:
        parsed = yaml.safe_load(new)
    except yaml.YAMLError as error:
        raise EditError(f"the edit would leave the file unreadable: {error}") from error
    if parsed != expected:
        raise EditError("the edit would change more than the reference it was for")
    return new
