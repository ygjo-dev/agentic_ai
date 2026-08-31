"""좁히기 길의 스키마 둘. 지금 길의 recipe_selection_schema 는 안 건드렸다."""

from orchestrator.schemas.response_schema import (
    CLARIFY,
    NO_MATCH,
    REQUIRED,
    REQUIRED_AXES,
    REQUIRED_PICK,
    SELECT,
    axis_selection_schema,
    recipe_pick_schema,
    recipe_selection_schema,
)


def test_the_first_pass_schema_equals_the_first_five_fields_of_the_current_schema():
    full = recipe_selection_schema(120, ["g"], ["w"], ["a"])
    axes = axis_selection_schema(120, ["g"], ["w"], ["a"])

    assert list(axes["properties"]) == REQUIRED_AXES == REQUIRED[:5]
    for key in REQUIRED_AXES:
        assert axes["properties"][key] == full["properties"][key]
    assert axes["required"] == REQUIRED_AXES


def test_the_first_pass_schema_has_no_recipe_fields():
    axes = axis_selection_schema(120, ["g"], ["w"], ["a"])

    assert not {"candidate_recipe_ids", "status", "recipe_id"} & set(axes["properties"])


def test_the_second_pass_schema_keeps_the_candidates_a_closed_list():
    schema = recipe_pick_schema(120, ["recipe_030", "recipe_040"])

    assert schema["required"] == REQUIRED_PICK
    assert schema["properties"]["recipe_id"]["enum"] == ["recipe_030", "recipe_040", None]
    assert schema["properties"]["candidate_recipe_ids"]["items"]["enum"] == ["recipe_030", "recipe_040"]
    assert schema["properties"]["status"]["enum"] == [SELECT, CLARIFY, NO_MATCH]
    assert schema["properties"]["reason"]["maxLength"] == 120


def test_the_current_schema_is_unchanged():
    full = recipe_selection_schema(120, ["g"], ["w"], ["a"])

    assert full["required"] == REQUIRED
    assert list(full["properties"]) == REQUIRED
