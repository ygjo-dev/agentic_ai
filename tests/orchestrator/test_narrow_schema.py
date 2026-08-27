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


def test_1차_스키마는_지금_스키마의_앞_다섯_칸과_같다():
    full = recipe_selection_schema(120, ["g"], ["w"], ["a"])
    axes = axis_selection_schema(120, ["g"], ["w"], ["a"])

    assert list(axes["properties"]) == REQUIRED_AXES == REQUIRED[:5]
    for key in REQUIRED_AXES:
        assert axes["properties"][key] == full["properties"][key]
    assert axes["required"] == REQUIRED_AXES


def test_1차_스키마에_recipe_칸이_없다():
    axes = axis_selection_schema(120, ["g"], ["w"], ["a"])

    assert not {"candidate_recipe_ids", "status", "recipe_id"} & set(axes["properties"])


def test_2차_스키마는_후보를_닫힌_목록으로_둔다():
    schema = recipe_pick_schema(120, ["recipe_030", "recipe_040"])

    assert schema["required"] == REQUIRED_PICK
    assert schema["properties"]["recipe_id"]["enum"] == ["recipe_030", "recipe_040", None]
    assert schema["properties"]["candidate_recipe_ids"]["items"]["enum"] == ["recipe_030", "recipe_040"]
    assert schema["properties"]["status"]["enum"] == [SELECT, CLARIFY, NO_MATCH]
    assert schema["properties"]["reason"]["maxLength"] == 120


def test_지금_스키마는_그대로다():
    full = recipe_selection_schema(120, ["g"], ["w"], ["a"])

    assert full["required"] == REQUIRED
    assert list(full["properties"]) == REQUIRED
