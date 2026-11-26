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
                # Who proposed a reference is an agent run, whose summary is data/agent_runs/<run>.json (ADR 0049).
                "data/routes/proposed-by-someone.yaml",
                BROKEN_ROUTE.replace("broken-route", "proposed-by-someone").replace("thing: unobtainium", "thing: charcoal")
                .replace("status: unverified }", "status: unverified, proposed_by: someone }"),
                "proposed_by: 'someone' does not match",
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

    def test_an_override_must_name_a_known_thing(self, data_copy, write_override):
        write_override(data_copy, id="unobtainium-hardness", thing="unobtainium")
        messages = [f"{i.where}: {i.message}" for i in validate(data_copy) if i.severity == "error"]
        assert "override unobtainium-hardness: unknown thing 'unobtainium'" in messages

    def test_a_value_can_be_overridden_only_once(self, data_copy, write_override):
        write_override(data_copy)
        write_override(data_copy, id="granite-hardness-again")
        messages = [i.message for i in validate(data_copy) if i.severity == "error"]
        assert any("already overridden by" in message for message in messages), messages

    def test_an_override_must_give_a_reason_and_a_reference(self, data_copy, write_override):
        path = write_override(data_copy)
        path.write_text(path.read_text().split("reason:")[0], encoding="utf-8")
        messages = [i.message for i in validate(data_copy) if i.severity == "error"]
        assert any("'reason' is a required property" in message for message in messages), messages

    def test_an_override_must_replace_a_quantity_read_from_wikidata(self, data_copy, write_override):
        path = write_override(data_copy)
        path.write_text(path.read_text().replace("quantity: hardness_mohs", "quantity: toughness_mpa_sqrt_m"))
        messages = [i.message for i in validate(data_copy) if i.severity == "error"]
        assert any("toughness_mpa_sqrt_m isn't read from Wikidata" in message for message in messages), messages

    def test_a_well_formed_override_is_valid(self, data_copy, write_override):
        write_override(data_copy)
        assert [str(i) for i in validate(data_copy) if i.severity == "error"] == []

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

    def test_a_class_whose_members_all_come_from_the_ore_crosswalk_has_members(self, repo_root):
        # given: copper sulphide ore has no curated members; chalcocite, bornite and chalcopyrite join in the build
        warnings = [f"{i.where}: {i.message}" for i in validate(repo_root) if i.severity == "warning"]
        # then: it isn't reported as empty
        assert "thing copper-sulphide-ore: category has no members" not in warnings

    def test_warns_about_a_class_with_no_members_anywhere(self, data_copy):
        # given: a class that neither a curated thing nor an ore crosswalk row belongs to
        (data_copy / "data/things/categories/empty-ore.yaml").write_text("id: empty-ore\nkind: category\nlabel: X\n")
        warnings = [f"{i.where}: {i.message}" for i in validate(data_copy) if i.severity == "warning"]
        assert "thing empty-ore: category has no members" in warnings

    def test_warns_about_a_regional_material_without_a_source(self, data_copy):
        # given: an ore marked natural and regional, so it would be free to anyone who selects it, with no extraction
        (data_copy / "data/things/materials/loose-ore.yaml").write_text(
            "id: loose-ore\nkind: material\nlabel: X\norigin: natural\navailability: regional\n")
        warnings = [f"{i.where}: {i.message}" for i in validate(data_copy) if i.severity == "warning"]
        assert "thing loose-ore: regional natural material: give it a source and an extraction route (ADR 0032)" in warnings
