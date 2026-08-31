"""_verdict 의 규칙 다섯.

LLM 도 온톨로지도 부르지 않는다. LLM 이 고른 목록과 축으로 뽑은 후보를
직접 넣고 최종 status 와 후보만 본다.

「겹치는 것 0개」 규칙은 2026-08-26 에 바뀌었다. 옛 규칙(뽑힌 후보만 씀)이
LLM 이 맞게 고른 답을 덮은 자리가 실측에서 아홉 번 나왔다. 안 셋을 재고
고른 것이고 표는 NOTES.md 「서른셋째」에 있다.
"""

from app.api.services.resolve_service import _verdict
from orchestrator.schemas.response_schema import CLARIFY, NO_MATCH, SELECT


def llm(status=SELECT, recipe_id=None, candidates=()):
    """LLM 응답 중 _verdict 가 읽는 칸만."""
    return {
        "status": status,
        "recipe_id": recipe_id,
        "candidate_recipe_ids": list(candidates),
    }


def test_a_single_overlap_is_selected():
    """축과 LLM 이 한 곳에서 만났으므로 되물을 것이 없음."""
    verdict = _verdict(llm(recipe_id="recipe_003"), ["recipe_003"], ["recipe_003", "recipe_021"])

    assert verdict["status"] == SELECT
    assert verdict["recipe_id"] == "recipe_003"
    assert verdict["candidate_recipe_ids"] == ["recipe_003"]


def test_several_overlaps_clarify_with_only_the_overlap():
    """겹치지 않는 것은 한쪽만 부른 것이라 후보에서 뺌.

    순서는 뽑힌 후보를 따름. 축이 낸 차례가 온톨로지의 차례임.
    """
    verdict = _verdict(
        llm(status=CLARIFY, candidates=["recipe_008", "recipe_007", "recipe_099"]),
        ["recipe_008", "recipe_007", "recipe_099"],
        ["recipe_007", "recipe_008", "recipe_009"],
    )

    assert verdict["status"] == CLARIFY
    assert verdict["recipe_id"] is None
    assert verdict["candidate_recipe_ids"] == ["recipe_007", "recipe_008"]


def test_no_overlap_clarifies_with_the_two_merged():
    """어느 쪽이 맞는지 이 자리에서 가릴 근거가 없음.

    2026-08-26 이전에는 뽑힌 후보만 썼음. 그것이 맞는 답을 덮은 자리임.
    LLM 이 쓴 것이 앞, 뽑힌 후보가 뒤임.
    """
    verdict = _verdict(
        llm(recipe_id="recipe_003"), ["recipe_003"], ["recipe_006", "recipe_013"]
    )

    assert verdict["status"] == CLARIFY
    assert verdict["recipe_id"] is None
    assert verdict["candidate_recipe_ids"] == ["recipe_003", "recipe_006", "recipe_013"]


def test_with_no_overlap_a_correct_LLM_pick_is_not_overwritten():
    """실측 발화 28 의 모양. 옛 규칙이 아홉 번 덮은 자리를 그대로 둠.

    LLM 단독 {003} 이 기대값과 같았는데 최종이 {006, 013} 이 되어 빗나감이었음.
    합치면 정답이 후보에 남으므로 근접이 됨. 틀린 답보다 정직한 되물음이 나음.
    """
    verdict = _verdict(
        llm(recipe_id="recipe_003"), ["recipe_003"], ["recipe_006", "recipe_013"]
    )

    assert "recipe_003" in verdict["candidate_recipe_ids"]


def test_an_id_the_merged_two_share_is_recorded_only_once():
    """LLM 과 축이 같은 것을 다른 차례로 부른 자리. 후보에 같은 id 가 두 번 들면 안 됨."""
    verdict = _verdict(
        llm(status=CLARIFY, candidates=["recipe_011", "recipe_029"]),
        ["recipe_011", "recipe_029"],
        ["recipe_029", "recipe_038"],
    )

    assert verdict["candidate_recipe_ids"] == ["recipe_029"]
    assert verdict["status"] == SELECT


def test_when_the_LLM_wrote_nothing_only_the_shortlist_remains():
    """합칠 것이 없음. 안을 바꾸기 전과 같은 결과여야 함."""
    verdict = _verdict(llm(status=NO_MATCH), [], ["recipe_038", "recipe_039"])

    assert verdict["status"] == CLARIFY
    assert verdict["candidate_recipe_ids"] == ["recipe_038", "recipe_039"]


def test_with_no_shortlist_what_the_LLM_wrote_is_left_as_is():
    """축이 틀린 것이므로 조회 결과를 안 믿음. 2026-08-26 변경에서 안 건드린 규칙임."""
    verdict = _verdict(
        llm(status=CLARIFY, recipe_id="recipe_001", candidates=["recipe_001", "recipe_002"]),
        ["recipe_001", "recipe_002"],
        [],
    )

    assert verdict["status"] == CLARIFY
    assert verdict["recipe_id"] == "recipe_001"
    assert verdict["candidate_recipe_ids"] == ["recipe_001", "recipe_002"]


def test_with_both_empty_there_is_nothing_to_attach():
    """LLM 도 축도 아무것도 못 낸 자리. 발화가 영역 밖임."""
    verdict = _verdict(llm(status=NO_MATCH), [], [])

    assert verdict["status"] == NO_MATCH
    assert verdict["recipe_id"] is None
    assert verdict["candidate_recipe_ids"] == []
