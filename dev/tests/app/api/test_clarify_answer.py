"""CLARIFY · NO_MATCH 답 문구.

LLM 을 부르지 않는다. resolve 결과 dict 를 만들어 넣고 문자열만 본다.
온톨로지 데이터가 바뀌어도 흔들리지 않게 경로와 배선 여부는 가짜로 준다.
"""

import pytest

from app.api.services import execute_service


def path(*names):
    """이름 목록을 path_of 모양으로. 맨 앞은 언제나 데이터 노드(말한 장소)."""
    chain = [{"node_id": "spoken_place", "name": "말한 장소", "out_type": "말한 장소"}]
    for index, name in enumerate(names):
        chain.append({"node_id": f"n{index}_{name}", "name": name, "out_type": name})
    return chain


def resolved(paths, status="CLARIFY", reason=""):
    """resolve 가 내는 dict 중 답 문구가 읽는 칸만."""
    return {
        "status": status,
        "recipe_id": None,
        "candidate_recipe_ids": list(paths),
        "paths": paths,
        "reason": reason,
    }


def wire(monkeypatch, paths, unwired=()):
    """가짜 경로를 실행 노드 판정에 연결. unwired 에 적은 recipe 만 배선이 없음."""
    monkeypatch.setattr(
        execute_service.ontology_service,
        "executable_in",
        lambda recipe_id: [
            entry["node_id"]
            for entry in paths.get(recipe_id, [])
            if entry["node_id"] != "spoken_place"
        ],
    )
    monkeypatch.setattr(
        execute_service.step_service,
        "unwired",
        lambda recipe_id: ["x"] if recipe_id in unwired else [],
    )


@pytest.fixture(autouse=True)
def no_ontology(monkeypatch):
    """온톨로지와 배선 표를 안 읽음. wire 를 안 부른 테스트도 파일을 안 건드림."""
    monkeypatch.setattr(
        execute_service.ontology_service, "executable_in", lambda recipe_id: []
    )
    monkeypatch.setattr(execute_service.step_service, "unwired", lambda recipe_id: [])


def test_two_candidates_give_a_short_preamble_and_numbered_names(monkeypatch):
    """recipe 번호는 사람에게 뜻이 없음. 마지막 노드 이름이 그 recipe 가 하는 일임."""
    paths = {
        "recipe_035": path("장소 좌표 변환", "전기차 충전소 검색"),
        "recipe_036": path("장소 좌표 변환", "전기차 충전기 조회"),
    }
    wire(monkeypatch, paths)

    answer = execute_service._no_recipe_answer(resolved(paths))

    assert answer.splitlines() == [
        "어느 것을 보시겠습니까?",
        "  1  전기차 충전소 검색",
        "  2  전기차 충전기 조회",
    ]
    assert "recipe_035" not in answer


def test_four_or_more_candidates_make_the_preamble_longer(monkeypatch):
    """둘셋은 그냥 고르면 되지만 다섯이면 먼저 여러 갈래라고 말해야 함."""
    paths = {f"recipe_{index:03d}": path(f"조회 {index}") for index in range(1, 6)}
    wire(monkeypatch, paths)

    answer = execute_service._no_recipe_answer(resolved(paths))
    lines = answer.splitlines()

    assert lines[0] == "여러 가지로 해석됩니다. 어느 것을 보시겠습니까?"
    assert len(lines) == 6


def test_overlapping_tail_names_are_split_apart_by_prefixing_the_previous_step(monkeypatch):
    """둘 다 철도 노선 조회로 끝나면 이름만으로는 고를 수가 없음."""
    paths = {
        "recipe_003": path("철도 노선 조회"),
        "recipe_026": path("장소 좌표 변환", "철도 노선 조회"),
    }
    wire(monkeypatch, paths)

    answer = execute_service._no_recipe_answer(resolved(paths))

    assert answer.splitlines()[1:] == [
        "  1  철도 노선 조회",
        "  2  장소 좌표 변환 -> 철도 노선 조회",
    ]


def test_non_overlapping_candidates_get_no_previous_step_prefix(monkeypatch):
    """짧을수록 읽기 쉬움. 가를 필요가 없으면 가르지 않음."""
    paths = {
        "recipe_001": path("장소 좌표 변환", "CCTV 조회"),
        "recipe_004": path("장소 좌표 변환", "행정구역 조회"),
    }
    wire(monkeypatch, paths)

    answer = execute_service._no_recipe_answer(resolved(paths))

    assert "->" not in answer


def test_an_unwired_candidate_stays_in_the_list_but_is_marked(monkeypatch):
    """골라도 실행되지 않는다는 것을 미리 알려야 함. 빼면 온톨로지가 아는 경로가 안 보임."""
    paths = {
        "recipe_004": path("행정구역 조회"),
        "recipe_045": path("연령별 인구 구성 조회"),
    }
    wire(monkeypatch, paths, unwired={"recipe_045"})

    answer = execute_service._no_recipe_answer(resolved(paths))

    assert answer.splitlines()[1:] == [
        "  1  행정구역 조회",
        "  2  연령별 인구 구성 조회 (아직 실행할 수 없음)",
    ]


def test_with_no_candidates_the_answer_says_it_is_out_of_scope():
    """NO_MATCH 첫 줄은 그대로 둠. 고를 것이 없으므로 목록도 없음.

    2026-08-29 에 그 뒤로 안내 두 줄이 붙었다. 첫 줄과 이유는 한 글자도 안
    바뀌었다 — 저쪽 unsupported-request 는 고정 문구 한 줄뿐이라 무엇을 대신
    말해야 할지 안 알려준다.
    """
    answer = execute_service._no_recipe_answer(
        {"status": "NO_MATCH", "candidate_recipe_ids": [], "paths": {}, "reason": "이유"}
    )

    head, reason, guide = answer.split("\n\n")

    assert head == "지금 할 수 있는 일 중에 맞는 것이 없습니다."
    assert reason == "이유"
    assert guide.count("\n") == 1


def test_the_guidance_words_come_from_the_ontology():
    """안내를 코드에 박지 않음. 노드를 등록하면 안내도 함께 늘어야 함.

    대상 이름과 시작 데이터 이름을 그대로 적는다. 화면에서 오는 둘(찍은 지점 ·
    보이는 범위)은 뺀다 — 사람이 더 말해 줄 것이 없다.
    """
    topics, starts = execute_service._offer_names()
    answer = execute_service._no_recipe_answer(
        {"status": "NO_MATCH", "candidate_recipe_ids": [], "paths": {}, "reason": ""}
    )

    assert topics and starts
    for name in topics + starts:
        assert name in answer
    for node_id in execute_service.step_service.CONTEXT_STARTS:
        assert node_id not in starts


def test_an_empty_reason_does_not_leave_a_bare_blank_line():
    """LLM 이 이유를 안 쓴 회차가 있음. 그때 답에 빈 칸이 뜨면 안 됨."""
    answer = execute_service._no_recipe_answer(
        {"status": "NO_MATCH", "candidate_recipe_ids": [], "paths": {}, "reason": ""}
    )

    assert "\n\n\n" not in answer
    assert answer.startswith("지금 할 수 있는 일 중에 맞는 것이 없습니다.\n\n제가 다루는 것은")


def test_empty_paths_fall_back_to_ids_without_dying():
    """paths 가 비어도 답은 나가야 함. 줄이 사라지는 것보다 뜻 없는 id 가 나음."""
    answer = execute_service._no_recipe_answer(
        {
            "status": "CLARIFY",
            "candidate_recipe_ids": ["recipe_035", "recipe_036"],
            "reason": "",
        }
    )

    assert answer.splitlines() == [
        "어느 것을 보시겠습니까?",
        "  1  recipe_035",
        "  2  recipe_036",
    ]


def test_the_reason_is_appended_verbatim_at_the_end_of_the_answer(monkeypatch):
    """왜 못 좁혔는지 읽을 수 있어야 함. 시연에서 설명할 근거임."""
    paths = {
        "recipe_035": path("전기차 충전소 검색"),
        "recipe_036": path("전기차 충전기 조회"),
    }
    wire(monkeypatch, paths)

    answer = execute_service._no_recipe_answer(
        resolved(paths, reason="충전소인지 충전기인지 분명하지 않음")
    )

    assert answer.endswith("\n\n충전소인지 충전기인지 분명하지 않음")
