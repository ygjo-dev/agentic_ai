"""대상 : execution/local_presentation.py — KRRI_ASAP 이 실행하지 않은 자리의 문구

순수 함수다. 네트워크 · 온톨로지 · LLM · 파일을 하나도 안 쓴다. 받은 구조로 만든
문자열만 본다.

실제로 실행한 워크플로의 답은 KRRI 가 만든다. 그것을 그대로 넘기는지는
test_workflow_execution.py 가 본다.
"""

import pytest

from execution import local_presentation


# ── 진행 표시 ────────────────────────────────────────────────────────


def test_a_tool_step_and_a_map_command_share_the_progress_shape():
    """부르는 화면이 따로 알아볼 것이 없다. 도구 이름 자리에 지도 명령 op 이 온다."""
    assert local_presentation.step_start("geo.geocode") == "geo.geocode 호출 중입니다..."
    assert local_presentation.command_start("digitalTwin.showFacility") == "digitalTwin.showFacility 명령을 내는 중입니다..."
    assert local_presentation.step_end("geo.geocode") == "geo.geocode 완료"
    assert local_presentation.step_end("road.getCctv", failed=True) == "road.getCctv 실패"


def test_the_resolve_step_names_its_status_and_the_chosen_recipe():
    assert local_presentation.resolve_end("SELECT", "recipe_036") == "SELECT recipe_036"
    assert local_presentation.resolve_end("NO_MATCH", None) == "NO_MATCH"


def test_there_is_no_function_that_reads_a_trace():
    """실제로 실행한 답과 그 성공 · 실패는 KRRI 가 주인이다. 여기서 trace 를 읽어 다시 짓지 않는다."""
    for name in ("compose_workflow_answer", "step_failed", "step_line", "summarize"):
        assert not hasattr(local_presentation, name), name


# ── 되묻기 · 못 찾음 문구 ───────────────────────────────────────────
#
# 이름은 부르는 쪽(resolve_service.answer_names)이 넘긴다. 여기서는 받은 이름으로 만든 문자열만 본다.


def clarify(steps, unwired=(), reason=""):
    """후보마다 부를 노드 이름을 준 되묻기 답."""
    resolved = {"status": "CLARIFY", "candidate_recipe_ids": list(steps), "reason": reason}
    return local_presentation.unresolved_answer(resolved, {"steps": steps, "unwired": list(unwired)})


def no_match(reason="", topics=("철도",), starts=("장소 이름",)):
    resolved = {"status": "NO_MATCH", "candidate_recipe_ids": [], "reason": reason}
    return local_presentation.unresolved_answer(resolved, {"topics": list(topics), "starts": list(starts)})


def test_two_candidates_give_a_short_preamble_and_numbered_names():
    """recipe 번호는 사람에게 뜻이 없음. 마지막 노드 이름이 그 recipe 가 하는 일임."""
    answer = clarify({
        "recipe_035": ["장소 좌표 변환", "전기차 충전소 검색"],
        "recipe_036": ["장소 좌표 변환", "전기차 충전기 조회"],
    })

    assert answer.splitlines() == [
        "어느 것을 보시겠습니까?",
        "  1  전기차 충전소 검색",
        "  2  전기차 충전기 조회",
    ]
    assert "recipe_035" not in answer


def test_four_or_more_candidates_make_the_preamble_longer():
    """둘셋은 그냥 고르면 되지만 다섯이면 먼저 여러 갈래라고 말해야 함."""
    lines = clarify({f"recipe_{index:03d}": [f"조회 {index}"] for index in range(1, 6)}).splitlines()

    assert lines[0] == "여러 가지로 해석됩니다. 어느 것을 보시겠습니까?"
    assert len(lines) == 6


def test_overlapping_tail_names_are_split_apart_by_prefixing_the_previous_step():
    """둘 다 철도 노선 조회로 끝나면 이름만으로는 고를 수가 없음."""
    answer = clarify({"recipe_003": ["철도 노선 조회"], "recipe_026": ["장소 좌표 변환", "철도 노선 조회"]})

    assert answer.splitlines()[1:] == [
        "  1  철도 노선 조회",
        "  2  장소 좌표 변환 -> 철도 노선 조회",
    ]


def test_non_overlapping_candidates_get_no_previous_step_prefix():
    """짧을수록 읽기 쉬움. 가를 필요가 없으면 가르지 않음."""
    answer = clarify({"recipe_001": ["장소 좌표 변환", "CCTV 조회"], "recipe_004": ["장소 좌표 변환", "행정구역 조회"]})

    assert "->" not in answer


def test_an_unwired_candidate_stays_in_the_list_but_is_marked():
    """골라도 실행되지 않는다는 것을 미리 알려야 함. 빼면 온톨로지가 아는 경로가 안 보임."""
    answer = clarify({"recipe_004": ["행정구역 조회"], "recipe_045": ["연령별 인구 구성 조회"]}, unwired=["recipe_045"])

    assert answer.splitlines()[1:] == [
        "  1  행정구역 조회",
        "  2  연령별 인구 구성 조회 (아직 실행할 수 없음)",
    ]


def test_empty_names_fall_back_to_ids_without_dying():
    """이름이 비어도 답은 나가야 함. 줄이 사라지는 것보다 뜻 없는 id 가 나음."""
    assert clarify({"recipe_035": [], "recipe_036": []}).splitlines() == [
        "어느 것을 보시겠습니까?",
        "  1  recipe_035",
        "  2  recipe_036",
    ]


def test_the_reason_is_appended_verbatim_at_the_end_of_the_answer():
    """왜 못 좁혔는지 읽을 수 있어야 함. 시연에서 설명할 근거임."""
    answer = clarify(
        {"recipe_035": ["전기차 충전소 검색"], "recipe_036": ["전기차 충전기 조회"]},
        reason="충전소인지 충전기인지 분명하지 않음",
    )

    assert answer.endswith("\n\n충전소인지 충전기인지 분명하지 않음")


def test_with_no_candidates_the_answer_says_it_is_out_of_scope():
    """NO_MATCH 첫 줄은 그대로 둠. 고를 것이 없으므로 목록도 없음.

    2026-08-29 에 그 뒤로 안내 두 줄이 붙었다. KRRI_ASAP 의 unsupported-request 는 고정 문구
    한 줄뿐이라 무엇을 대신 말해야 할지 안 알려준다.
    """
    head, reason, guide = no_match("이유").split("\n\n")

    assert head == "지금 할 수 있는 일 중에 맞는 것이 없습니다."
    assert reason == "이유"
    assert guide.count("\n") == 1


def test_an_empty_reason_does_not_leave_a_bare_blank_line():
    """LLM 이 이유를 안 쓴 회차가 있음. 그때 답에 빈 칸이 뜨면 안 됨."""
    answer = no_match("")

    assert "\n\n\n" not in answer
    assert answer.startswith("지금 할 수 있는 일 중에 맞는 것이 없습니다.\n\n제가 다루는 것은")


# ── 고른 것을 못 부를 때 ────────────────────────────────────────────


def unready(status, missing, paths=None, recipe_id="recipe_x"):
    materialized = {"status": status, "recipe_id": recipe_id, "missing": missing}
    return local_presentation.unready_answer(materialized, paths)


@pytest.mark.parametrize(
    "start, fragment",
    [("place_name", "장소를 함께"), ("keyword", "찾을 것을 함께"), ("district_code", "이름이나 코드를 함께"),
     ("모르는노드", "장소를 함께"), (None, "장소를 함께")],
    ids=["place", "keyword", "identifier", "unknown", "no_start"],
)
def test_a_missing_argument_asks_for_what_the_start_node_is(start, fragment):
    """장소 문구 하나로 두면 "선거구 찾아줘" 에 장소를 대라고 답하게 됨. 모르는 시작은 장소 문구다."""
    assert fragment in unready("MISSING_ARGUMENT", [start] if start else [])


def test_the_screen_guard_names_what_is_missing_in_the_order_it_was_given():
    answer = unready("MISSING_CONTEXT", ["map_extent", "point"])

    assert answer.splitlines() == [
        local_presentation.NO_CONTEXT_ANSWER["map_extent"],
        local_presentation.NO_CONTEXT_ANSWER["point"],
    ]


def test_an_unwired_node_is_named_by_the_path_the_resolution_carried():
    """id 가 아니라 노드 이름으로 적음. 사람이 읽는 문장임. 이름이 없으면 id 로 떨어짐."""
    paths = {"recipe_x": [{"node_id": "find_cctv", "name": "CCTV 조회"}]}

    assert unready("UNWIRED", ["find_cctv", "없는노드"], paths) == "CCTV 조회 · 없는노드 기능이 아직 붙지 않아 실행할 수 없습니다."


@pytest.mark.parametrize("status", ["NOT_ACCEPTED", "NOTHING_TO_CALL"])
def test_nothing_to_call_says_so(status):
    assert unready(status, []) == local_presentation.NO_TOOL_ANSWER
