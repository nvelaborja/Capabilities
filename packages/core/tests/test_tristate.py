import pytest

from capabilities.tristate import Tri, compare


class TestCompare:
    @pytest.mark.parametrize(
        ("have", "op", "need", "expected"),
        [
            # Plain numbers behave like ordinary comparisons.
            (7, ">=", 7, Tri.YES),
            (6, ">=", 7, Tri.NO),
            (7, ">", 7, Tri.NO),
            (3, "<=", 5, Tri.YES),
            (5, "<", 5, Tri.NO),
            (5, "==", 5, Tri.YES),
            # Ranges: yes only when every value satisfies the comparison.
            ([7, 8], ">=", [6, 7], Tri.YES),
            ([2.5, 3], ">=", 3, Tri.MAYBE),
            ([2.5, 3], ">=", [6, 7], Tri.NO),
            ([1100, 1250], ">=", 1200, Tri.MAYBE),
            ([1100, 1250], ">=", 1100, Tri.YES),
            ([1, 2], "<=", [2, 3], Tri.YES),
            ([1, 4], "<=", [2, 3], Tri.MAYBE),
        ],
    )
    def test_three_valued_comparison(self, have, op, need, expected):
        # given: two values or ranges
        # when: comparing them
        # then: the result is yes, maybe, or no as appropriate
        assert compare(have, op, need) == expected

    @pytest.mark.parametrize(("have", "need"), [(None, 3), (3, None), (None, None)])
    def test_missing_data_is_maybe_never_no(self, have, need):
        # given: one side of the comparison is unknown
        # when: comparing
        # then: the answer is "maybe", because missing data must never rule something out
        assert compare(have, ">=", need) == Tri.MAYBE

    def test_unknown_operator_is_rejected(self):
        with pytest.raises(ValueError):
            compare(1, "~", 2)
