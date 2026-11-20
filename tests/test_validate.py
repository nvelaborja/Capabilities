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
            # A source says where a resource is found, so it must say how widely (ADR 0032).
            ("data/things/sources/nowhere.yaml", "id: nowhere\nkind: source\nlabel: X\n", "schema"),
            ("data/things/sources/made.yaml", "id: made\nkind: source\nlabel: X\navailability: regional\norigin: produced\n", "schema"),
        ],
    )
    def test_each_mistake_is_reported(self, data_copy, relative_path, content, expected_message):
        # given: a copy of the data with one broken file added
        (data_copy / relative_path).write_text(content)
        # when: validating
        messages = [f"{i.where}: {i.message}" for i in validate(data_copy) if i.severity == "error"]
        # then: the mistake is reported as an error
        assert any(expected_message in m for m in messages), messages

    def test_warns_about_a_source_nothing_is_extracted_from(self, data_copy):
        # given: a source that no route uses
        (data_copy / "data/things/sources/lonely-outcrop.yaml").write_text("id: lonely-outcrop\nkind: source\nlabel: X\navailability: regional\n")
        # when: validating
        warnings = [f"{i.where}: {i.message}" for i in validate(data_copy) if i.severity == "warning"]
        # then: it is flagged as a gap, not an error
        assert "thing lonely-outcrop: no route extracts anything from this source" in warnings

    def test_warns_about_an_extracted_material_with_no_route(self, data_copy):
        (data_copy / "data/things/materials/stray-ore.yaml").write_text("id: stray-ore\nkind: material\nlabel: X\norigin: extracted\n")
        warnings = [f"{i.where}: {i.message}" for i in validate(data_copy) if i.severity == "warning"]
        assert "thing stray-ore: no route produces it" in warnings

    def test_warns_about_a_regional_material_without_a_source(self, data_copy):
        # given: an ore marked natural and regional, so it would be free to anyone who selects it, with no extraction
        (data_copy / "data/things/materials/loose-ore.yaml").write_text(
            "id: loose-ore\nkind: material\nlabel: X\norigin: natural\navailability: regional\n")
        warnings = [f"{i.where}: {i.message}" for i in validate(data_copy) if i.severity == "warning"]
        assert "thing loose-ore: regional natural material: give it a source and an extraction route (ADR 0032)" in warnings
