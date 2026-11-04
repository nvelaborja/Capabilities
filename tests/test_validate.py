import pytest

from capabilities.validate import validate


class TestRepositoryData:
    def test_has_no_errors(self, repo_root):
        # given: the data checked into the repo
        # when: validating it
        issues = validate(repo_root)
        # then: there are no errors (warnings about evidence gaps are expected)
        errors = [str(i) for i in issues if i.severity == "error"]
        assert errors == []


BROKEN_ROUTE = """id: broken-route
kind: route
label: Broken on purpose
achieves: { thing: steel }
requires:
  - { role: consumed, thing: unobtainium }
outputs:
  - { thing: steel }
references:
  - { citation: "Nobody (2026).", status: unverified }
"""


class TestBrokenData:
    @pytest.mark.parametrize(
        ("relative_path", "content", "expected_message"),
        [
            ("data/routes/broken-route.yaml", BROKEN_ROUTE, "unknown id 'unobtainium'"),
            (
                "data/routes/no-references.yaml",
                "id: no-references\nkind: route\nlabel: X\nachieves: { thing: steel }\nrequires: []\noutputs:\n  - { thing: steel }\n",
                "'references' is a required property",
            ),
            (
                "data/routes/inverted-range.yaml",
                BROKEN_ROUTE.replace("broken-route", "inverted-range").replace("thing: unobtainium", "thing: charcoal")
                .replace("  - { thing: steel }", "  - { thing: steel, quantities: { hardness_mohs: [8, 7] } }"),
                "has low > high",
            ),
            (
                "data/routes/bad-band.yaml",
                BROKEN_ROUTE.replace("broken-route", "bad-band").replace(
                    "  - { role: consumed, thing: unobtainium }",
                    '  - { role: effect, effect: heat, where: [{ quantity: duration_h, op: ">=", band: forever }] }'),
                "unknown duration_h band 'forever'",
            ),
            (
                "data/routes/old-know-how.yaml",
                BROKEN_ROUTE.replace("broken-route", "old-know-how").replace(
                    "thing: unobtainium", "thing: charcoal }\n  - { role: know_how, thing: smithing"),
                "schema",
            ),
            (
                "data/routes/bad-action.yaml",
                BROKEN_ROUTE.replace("broken-route", "bad-action").replace(
                    "  - { role: consumed, thing: unobtainium }", "  - { role: action, verb: teleport, target: wood }"),
                "unknown verb 'teleport'",
            ),
            (
                "data/things/materials/wrong-name.yaml",
                "id: something-else\nkind: material\nlabel: X\norigin: produced\n",
                "does not match the file name",
            ),
            (
                "data/things/artifacts/misplaced.yaml",
                "id: misplaced\nkind: material\nlabel: X\norigin: produced\n",
                "does not belong in artifacts/",
            ),
            ("data/things/materials/not-yaml.yaml", "id: [unclosed\n", "YAML parse error"),
        ],
    )
    def test_each_mistake_is_reported(self, data_copy, relative_path, content, expected_message):
        # given: a copy of the data with one broken file added
        (data_copy / relative_path).write_text(content)
        # when: validating
        messages = [f"{i.where}: {i.message}" for i in validate(data_copy) if i.severity == "error"]
        # then: the mistake is reported as an error
        assert any(expected_message in m for m in messages), messages
