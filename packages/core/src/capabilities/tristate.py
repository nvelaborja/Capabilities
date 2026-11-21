"""Three-valued comparisons over numbers and [low, high] ranges.

Most quantities in the graph are ballpark ranges, so a comparison can be true for every value in the range (YES),
for none of them (NO), or for some (MAYBE). Missing data is always MAYBE, never NO.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Sequence, Union

Number = Union[int, float]
Value = Union[Number, Sequence[Number]]


class Tri(IntEnum):
    NO = 0
    MAYBE = 1
    YES = 2

    @property
    def label(self) -> str:
        return self.name.lower()


def as_range(value: Value) -> tuple[float, float]:
    if isinstance(value, (int, float)):
        return float(value), float(value)
    low, high = value
    return float(low), float(high)


def compare(have: Value | None, op: str, need: Value | None) -> Tri:
    """Compare `have <op> need` where either side may be a range."""
    if have is None or need is None:
        return Tri.MAYBE
    have_low, have_high = as_range(have)
    need_low, need_high = as_range(need)
    if op == ">=":
        holds_always, holds_never = have_low >= need_high, have_high < need_low
    elif op == ">":
        holds_always, holds_never = have_low > need_high, have_high <= need_low
    elif op == "<=":
        holds_always, holds_never = have_high <= need_low, have_low > need_high
    elif op == "<":
        holds_always, holds_never = have_high < need_low, have_low >= need_high
    elif op == "==":
        holds_always = have_low == have_high == need_low == need_high
        holds_never = have_high < need_low or have_low > need_high
    else:
        raise ValueError(f"Unknown operator {op!r}")
    if holds_always:
        return Tri.YES
    if holds_never:
        return Tri.NO
    return Tri.MAYBE
